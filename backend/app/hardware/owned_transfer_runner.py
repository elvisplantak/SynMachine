"""Candidate transfer execution through shared ownership; fake assembly only.

No API, environment startup, live route approval or hardware trust is added here.
The lifecycle coordinator uses this runner instead of the historical simulator.
"""

from pathlib import Path
import sqlite3
from threading import RLock
from uuid import uuid4

from app.demo.hardware_contract import BottomValveState
from app.demo.column_fraction_collection_operation_plan import ColumnFractionCollectionOperationPlan
from app.hardware.arduino_command_journal import (
    SQLiteArduinoCommandJournal,
    _SCHEMA as ARDUINO_SCHEMA,
)
from app.hardware.command_plan_store import SQLiteCommandPlanStore, _SCHEMA as PLAN_SCHEMA
from app.hardware.command_planning import ArduinoAction, SfBottomValveAction
from app.hardware.durable_arduino import DurableArduinoCommandExecutor
from app.hardware.owned_hardware import OwnedHardware
from app.hardware.sequence_ownership import HardwareOwnership, OwnershipBlocked
from app.hardware.simulated_p1_runner import SimulatedP1Device, SimulationBlocked

IDENTITY_SCHEMA = """CREATE TABLE execution_identity (
 id TEXT NOT NULL, ownership_id TEXT NOT NULL
)"""
SF_SCHEMA = """CREATE TABLE sf_action_journal (
 action_id TEXT PRIMARY KEY NOT NULL, phase_id TEXT NOT NULL,
 session_id TEXT NOT NULL, target TEXT NOT NULL CHECK(target IN ('OPEN', 'CLOSED')),
 state TEXT NOT NULL CHECK(state IN ('INTENT_PERSISTED', 'COMPLETED', 'OUTCOME_UNKNOWN')),
 error TEXT
)"""
SCHEMAS = (IDENTITY_SCHEMA, SF_SCHEMA, PLAN_SCHEMA, ARDUINO_SCHEMA)


def provision_execution(database: Path, ownership_id: str) -> str:
    """Explicit fresh fixture creation only, never restart/recovery provisioning."""
    with database.open("xb"):
        pass
    identity = str(uuid4())
    with sqlite3.connect(database) as db:
        for statement in SCHEMAS:
            db.execute(statement)
        db.execute("INSERT INTO execution_identity VALUES (?, ?)", (identity, ownership_id))
    return identity


class DurableSfExecutor:
    """Commit intent before transport, never retry, conservatively retain uncertainty.

    SF currently has no accepted protocol for definitive negative acknowledgments.
    Every transport exception is therefore unknown, not an invented FAILED result.
    The outer OwnedHardware gate retains ownership on any exception.
    """

    def __init__(self, db, transport):
        self._db = db
        self._transport = transport
        self._lock = RLock()
        self._session = transport.sf_session_id

    def _session_check(self):
        if not self._session or self._transport.sf_session_id != self._session:
            raise SimulationBlocked("SF session changed or absent")

    def execute(self, *, phase_execution_id, operation_command_id, state):
        if (
            type(state) is not BottomValveState
            or not phase_execution_id
            or not operation_command_id
        ):
            raise ValueError("invalid SF command identity or state")
        with self._lock:
            self._session_check()
            # A duplicate primary key refuses every prior attempt, including success.
            self._db.execute(
                "INSERT INTO sf_action_journal VALUES (?, ?, ?, ?, 'INTENT_PERSISTED', NULL)",
                (operation_command_id, phase_execution_id, self._session, state.value),
            )
            try:
                self._transport.execute_sf(
                    phase_execution_id=phase_execution_id,
                    operation_command_id=operation_command_id,
                    state=state.value,
                )
                self._session_check()
            except BaseException as error:
                try:
                    self._db.execute(
                        "UPDATE sf_action_journal SET state='OUTCOME_UNKNOWN', error=? "
                        "WHERE action_id=?",
                        (str(error), operation_command_id),
                    )
                except BaseException as write_error:
                    error.add_note(f"SF outcome persistence failed: {write_error}")
                raise
            self._db.execute(
                "UPDATE sf_action_journal SET state='COMPLETED' WHERE action_id=?",
                (operation_command_id,),
            )


class OwnedTransferRunner:
    """One command path for prepared transfers and explicitly composed Services.

    No simulator owner/phase/SF tables are used. Lifecycle remains the run ledger,
    HardwareOwnership the exclusive owner, and command journals the send evidence.
    Only transfers (no timers, collection or continuous mixer) are supported.
    """

    def __init__(self, database, database_id, ownership, device):
        if type(device) is not SimulatedP1Device or type(ownership) is not HardwareOwnership:
            raise TypeError("this checkpoint permits explicit fake transport assembly only")
        self.database_id = database_id
        self.device = device
        self._lock = RLock()
        self._db = sqlite3.connect(
            Path(database).resolve().as_uri() + "?mode=rw",
            uri=True,
            isolation_level=None,
            check_same_thread=False,
        )
        self._plans = None
        self._journal = None
        try:
            self._db.execute("PRAGMA synchronous=FULL")
            # Compare compiled schemas before opening the legacy auto-create stores.
            with sqlite3.connect(":memory:") as expected:
                for statement in SCHEMAS:
                    expected.execute(statement)
                expected_schema = self._schema(expected)
            if self._schema(self._db) != expected_schema:
                raise SimulationBlocked("incompatible execution database schema")
            if self._db.execute("SELECT id, ownership_id FROM execution_identity").fetchall() != [
                (database_id, ownership.database_id)
            ]:
                raise SimulationBlocked("wrong execution identity or ownership binding")
            self._plans = SQLiteCommandPlanStore(database)
            self._journal = SQLiteArduinoCommandJournal(database)
            self._sf = DurableSfExecutor(self._db, device)
            self.hardware = OwnedHardware(
                ownership,
                DurableArduinoCommandExecutor(device, self._journal),
                self._sf,
                journaled_sf=True,
            )
        except BaseException:
            self.close()
            raise

    @staticmethod
    def _schema(db):
        return sorted(
            (kind, name, "".join(sql.lower().split()))
            for kind, name, sql in db.execute(
                "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL"
            )
        )

    def close(self):
        if self._journal is not None:
            self._journal.close()
        if self._plans is not None:
            self._plans.close()
        self._db.close()

    def load_plan(self, phase_id):
        return self._plans.load(phase_id)

    def _validate(self, phase_id, run_id, run_event_sequence):
        plan = self.load_plan(phase_id)
        if plan is None:
            raise SimulationBlocked("stored plan is absent in the verified database")
        if isinstance(plan.source.plan, ColumnFractionCollectionOperationPlan):
            raise SimulationBlocked("collection is outside this transfer slice")
        if (plan.source.run_id, plan.source.run_event_sequence) != (run_id, run_event_sequence):
            raise SimulationBlocked("source lifecycle identity mismatch")
        if (
            self.device.used
            or self.device.calls
            or self.device.sf_calls
            or self.device.current != plan.prepared.assumptions
        ):
            raise SimulationBlocked("independent fixture does not match stored assumptions")
        for operation in plan.prepared.operations:
            for action in (*operation.actions, *operation.required_followup):
                if type(action) not in (ArduinoAction, SfBottomValveAction):
                    raise SimulationBlocked("only transfer actions supported in this slice")
                if isinstance(action, ArduinoAction) and action.command not in (
                    "VALVE_SET_POSITION",
                    "PUMP_MOVE_ABSOLUTE_STEPS",
                    "COLUMN_BOTTOM_VALVE_SET_POSITION",
                ):
                    raise SimulationBlocked("only transfer commands supported in this slice")
            if any(
                not (
                    isinstance(a, SfBottomValveAction)
                    and a.state is BottomValveState.CLOSED
                    or isinstance(a, ArduinoAction)
                    and a.command == "COLUMN_BOTTOM_VALVE_SET_POSITION"
                    and dict(a.arguments) == {"position_degrees": 4}
                )
                for a in operation.required_followup
            ):
                raise SimulationBlocked("only required bottom valve CLOSE supported in this slice")
        for table, column in (
            ("arduino_command_journal", "phase_execution_id"),
            ("sf_action_journal", "phase_id"),
        ):
            if self._db.execute(
                f"SELECT 1 FROM {table} WHERE {column}=? LIMIT 1", (phase_id,)
            ).fetchone():
                raise SimulationBlocked("existing command evidence prohibits replay")
        self._check_boot(plan.prepared.assumptions.controller_boot_id)
        self._sf._session_check()
        return plan

    def _check_boot(self, expected):
        if self.device.controller_boot_id != expected:
            raise SimulationBlocked("current controller session differs from prepared session")

    def run(
        self, phase_id, *, run_id, run_event_sequence, stop_requested, before_execute, before_finish
    ):
        with self._lock:
            plan = self._validate(phase_id, run_id, run_event_sequence)
            owner = self.hardware.ownership
            lease = owner.claim(phase_id)
            completed = 0
            state = "COMPLETED"
            try:
                # Service can win between preflight and claim. Revalidate under
                # the exclusive owner before lifecycle start or any action.
                owner.invoke(lease, lambda: self._validate(phase_id, run_id, run_event_sequence))
                self.device.used = True
                owner.invoke(lease, before_execute)
                for operation in plan.prepared.operations:
                    if owner.invoke(lease, stop_requested):
                        state = "STOPPED"
                        break

                    def send(commands, actions):
                        for action in actions:
                            if isinstance(action, SfBottomValveAction):
                                commands.execute_sf(
                                    phase_execution_id=phase_id,
                                    operation_command_id=action.operation_command_id,
                                    state=action.state,
                                )
                            else:
                                self._check_boot(plan.prepared.assumptions.controller_boot_id)
                                commands.execute(
                                    phase_execution_id=phase_id,
                                    operation_command_id=action.operation_command_id,
                                    command=action.command,
                                    arguments=dict(action.arguments),
                                )
                                self._check_boot(plan.prepared.assumptions.controller_boot_id)

                    self.hardware.run_operation(
                        lease,
                        lambda commands: send(commands, operation.actions),
                        required_followup=(
                            (lambda commands: send(commands, operation.required_followup))
                            if operation.required_followup
                            else None
                        ),
                    )
                    completed += 1
                release = owner.invoke(lease, lambda: before_finish(state, completed))
                if state == "COMPLETED" and release is True:
                    owner.complete(lease)
                else:
                    owner.block(lease)
            except BaseException as error:
                # An inner gate may already have poisoned the lease. Never replace
                # the original exception or attempt cleanup/release after this point.
                try:
                    owner.block(lease)
                except BaseException as block_error:
                    if not isinstance(block_error, OwnershipBlocked):
                        error.add_note(f"Final ownership retention failed: {block_error}")
                raise
            return state, completed
