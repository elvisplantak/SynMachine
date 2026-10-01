"""Candidate phase execution through shared ownership; fake assembly only.

No API, environment startup, live route approval or hardware trust is added here.
The lifecycle coordinator uses this runner instead of the historical simulator.
"""

from pathlib import Path
import sqlite3
from threading import RLock
from uuid import uuid4

from app.demo.hardware_contract import BottomValveState
from app.demo.operation_executor import CollectionTimerOutcome
from app.demo.timed_sf_operation_plan import TimedSfOperationPlan
from app.demo.column_fraction_collection_operation_plan import ColumnFractionCollectionOperationPlan
from app.hardware.arduino_command_journal import (
    SQLiteArduinoCommandJournal,
    _SCHEMA as ARDUINO_SCHEMA,
)
from app.hardware.command_plan_store import SQLiteCommandPlanStore, _SCHEMA as PLAN_SCHEMA
from app.hardware.command_planning import ArduinoAction, SfBottomValveAction, CollectionWait
from app.hardware.execution_timer import MonotonicExecutionTimer
from app.hardware.command_planning import PausableWait
from app.demo.pausable_wait_plan import PausableWaitPlan
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
WAIT_SCHEMA = """CREATE TABLE execution_waits (
 phase_id TEXT NOT NULL, operation_number INTEGER NOT NULL,
 duration_seconds TEXT NOT NULL, state TEXT NOT NULL
 CHECK(state IN ('INTENT_PERSISTED', 'COMPLETED', 'STOP_REQUESTED', 'OUTCOME_UNKNOWN')),
 operation_completed INTEGER NOT NULL DEFAULT 0 CHECK(operation_completed IN (0, 1)),
 PRIMARY KEY(phase_id, operation_number)
)"""
CAROUSEL_SCHEMA = """CREATE TABLE execution_carousel_projection (
 phase_id TEXT PRIMARY KEY NOT NULL, position INTEGER CHECK(position BETWEEN 1 AND 40)
)"""
SCHEMAS = (IDENTITY_SCHEMA, SF_SCHEMA, PLAN_SCHEMA, ARDUINO_SCHEMA, WAIT_SCHEMA, CAROUSEL_SCHEMA)


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
    """One command path for prepared phases and explicitly composed Services.

    No simulator owner/phase/SF tables are used. Lifecycle remains the run ledger,
    HardwareOwnership the exclusive owner, and command journals the send evidence.
    Transfers, collection and timed SF phases share this execution loop and owner.
    """

    def __init__(self, database, database_id, ownership, device, *, timer=None):
        if type(device) is not SimulatedP1Device or type(ownership) is not HardwareOwnership:
            raise TypeError("this checkpoint permits explicit fake transport assembly only")
        if timer is not None and type(timer) is not MonotonicExecutionTimer:
            raise TypeError("only the bounded monotonic timer or default virtual wait is supported")
        self._timer = timer
        self._active_phase = None
        self._session = None
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
        if (plan.source.run_id, plan.source.run_event_sequence) != (run_id, run_event_sequence):
            raise SimulationBlocked("source lifecycle identity mismatch")
        if self._session is not None:
            self._session.validate_plan(plan)
        elif (
            self.device.used
            or self.device.calls
            or self.device.sf_calls
            or self.device.current != plan.prepared.assumptions
        ):
            raise SimulationBlocked("independent fixture does not match stored assumptions")
        if isinstance(plan.source.plan, ColumnFractionCollectionOperationPlan):
            if self.device.carousel_position != plan.prepared.assumptions.carousel_position:
                raise SimulationBlocked(
                    "current carousel fixture does not match prepared alignment"
                )
        if isinstance(plan.source.plan, TimedSfOperationPlan):
            if self.device.sf_mixer_running is not False:
                raise SimulationBlocked("timed SF phases require independently stopped mixer")
        if isinstance(plan.source.plan, PausableWaitPlan) and self._timer is None:
            raise SimulationBlocked("pausable phases require an explicit monotonic timer")
        for operation in plan.prepared.operations:
            for action in (*operation.actions, *operation.required_followup):
                if type(action) not in (
                    ArduinoAction,
                    SfBottomValveAction,
                    CollectionWait,
                    PausableWait,
                ):
                    raise SimulationBlocked("unsupported prepared action")
                if isinstance(action, ArduinoAction) and action.command not in (
                    "VALVE_SET_POSITION",
                    "PUMP_MOVE_ABSOLUTE_STEPS",
                    "COLUMN_BOTTOM_VALVE_SET_POSITION",
                    "CAROUSEL_MOVE_TO_POSITION",
                    "SF_MIXER_SET_STATE",
                ):
                    raise SimulationBlocked("unsupported Arduino command in owned plan")
            if any(
                not (
                    isinstance(a, SfBottomValveAction)
                    and a.state is BottomValveState.CLOSED
                    or isinstance(a, ArduinoAction)
                    and a.command == "COLUMN_BOTTOM_VALVE_SET_POSITION"
                    and dict(a.arguments) == {"position_degrees": 4}
                    or isinstance(a, ArduinoAction)
                    and a.command == "SF_MIXER_SET_STATE"
                    and dict(a.arguments) == {"running": False}
                )
                for a in operation.required_followup
            ):
                raise SimulationBlocked("only required valve CLOSE or mixer STOP supported")
        for table, column in (
            ("arduino_command_journal", "phase_execution_id"),
            ("sf_action_journal", "phase_id"),
            ("execution_waits", "phase_id"),
            ("execution_carousel_projection", "phase_id"),
        ):
            if self._db.execute(
                f"SELECT 1 FROM {table} WHERE {column}=? LIMIT 1", (phase_id,)
            ).fetchone():
                raise SimulationBlocked("existing command evidence prohibits replay")
        self._check_boot(plan.prepared.assumptions.controller_boot_id)
        self._sf._session_check()
        return plan

    def _check_boot(self, expected):
        if self._session is not None:
            try:
                self._session.check_arduino()
            except SimulationBlocked:
                if self._active_phase is not None:
                    self._invalidate_carousel(self._active_phase)
                raise
        if self.device.controller_boot_id != expected:
            self.device.carousel_position = None
            self.device.sf_mixer_running = None
            if self._active_phase is not None:
                self._invalidate_carousel(self._active_phase)
            raise SimulationBlocked("current controller session differs from prepared session")

    def _wait(self, phase_id, operation_number, action, stop_requested, wait_control=None):
        self._db.execute(
            "INSERT INTO execution_waits (phase_id, operation_number, duration_seconds, state) "
            "VALUES (?, ?, ?, 'INTENT_PERSISTED')",
            (phase_id, operation_number, str(action.duration_seconds)),
        )
        try:
            if isinstance(action, PausableWait):
                if self._timer is None or wait_control is None:
                    raise SimulationBlocked("pausable wait requires bound lifecycle control")
                outcome = self._timer.wait_pausable(action.duration_seconds, wait_control)
            else:
                wait = self.device.wait if self._timer is None else self._timer.wait
                outcome = wait(action.duration_seconds, stop_requested)
            if type(outcome) is not CollectionTimerOutcome:
                raise ValueError("invalid timer outcome")
        except BaseException as error:
            try:
                self._db.execute(
                    "UPDATE execution_waits SET state='OUTCOME_UNKNOWN' "
                    "WHERE phase_id=? AND operation_number=?",
                    (phase_id, operation_number),
                )
            except BaseException as write_error:
                error.add_note(f"Timer outcome persistence failed: {write_error}")
            raise
        self._db.execute(
            "UPDATE execution_waits SET state=? WHERE phase_id=? AND operation_number=?",
            (outcome.value, phase_id, operation_number),
        )
        return outcome

    def _invalidate_carousel(self, phase_id):
        self.device.carousel_position = None
        self._db.execute(
            "UPDATE execution_carousel_projection SET position=NULL WHERE phase_id=?", (phase_id,)
        )

    def run(
        self,
        phase_id,
        *,
        run_id,
        run_event_sequence,
        stop_requested,
        before_execute,
        before_finish,
        wait_control=None,
    ):
        with self._lock:
            plan = self._validate(phase_id, run_id, run_event_sequence)
            owner = self.hardware.ownership
            lease = (
                owner.claim(phase_id, expected_generation=self._session.generation)
                if self._session is not None
                else owner.claim(phase_id)
            )
            completed = 0
            state = "COMPLETED"
            try:
                # Service can win between preflight and claim. Revalidate under
                # the exclusive owner before lifecycle start or any action.
                owner.invoke(lease, lambda: self._validate(phase_id, run_id, run_event_sequence))
                self.device.used = True
                self._active_phase = phase_id
                owner.invoke(lease, before_execute)
                if isinstance(plan.source.plan, ColumnFractionCollectionOperationPlan):
                    self._db.execute(
                        "INSERT INTO execution_carousel_projection VALUES (?, ?)",
                        (phase_id, self.device.carousel_position),
                    )

                def checked_stop():
                    self._check_boot(plan.prepared.assumptions.controller_boot_id)
                    if self._session is not None:
                        self._session.check_connections()
                    if isinstance(plan.source.plan, TimedSfOperationPlan):
                        self._sf._session_check()
                    return stop_requested()

                for operation in plan.prepared.operations:
                    if owner.invoke(lease, checked_stop):
                        state = "STOPPED"
                        break

                    def send(commands, actions, *, followup=False):
                        for action in actions:
                            if self._session is not None and not followup:
                                self._check_boot(plan.prepared.assumptions.controller_boot_id)
                                self._session.check_connections()
                            if isinstance(action, (CollectionWait, PausableWait)):
                                outcome = self._wait(
                                    phase_id,
                                    operation.operation_number,
                                    action,
                                    checked_stop,
                                    wait_control,
                                )
                                if outcome is CollectionTimerOutcome.STOP_REQUESTED:
                                    return outcome
                            elif isinstance(action, SfBottomValveAction):
                                if self._session is not None:
                                    self._session.check_sf()
                                commands.execute_sf(
                                    phase_execution_id=phase_id,
                                    operation_command_id=action.operation_command_id,
                                    state=action.state,
                                )
                                if self._session is not None:
                                    self._session.check_sf()
                                    self._session.observe(action)
                            else:
                                self._check_boot(plan.prepared.assumptions.controller_boot_id)
                                mixer_action = action.command == "SF_MIXER_SET_STATE"
                                if mixer_action:
                                    self.device.sf_mixer_running = None
                                carousel_move = action.command == "CAROUSEL_MOVE_TO_POSITION"
                                if carousel_move:
                                    self._invalidate_carousel(phase_id)
                                commands.execute(
                                    phase_execution_id=phase_id,
                                    operation_command_id=action.operation_command_id,
                                    command=action.command,
                                    arguments=dict(action.arguments),
                                )
                                self._check_boot(plan.prepared.assumptions.controller_boot_id)
                                if mixer_action:
                                    self.device.sf_mixer_running = dict(action.arguments)["running"]
                                if carousel_move:
                                    position = dict(action.arguments)["position"]
                                    self._db.execute(
                                        "UPDATE execution_carousel_projection SET position=? WHERE phase_id=?",
                                        (position, phase_id),
                                    )
                                    self.device.carousel_position = position
                                if self._session is not None:
                                    self._session.observe(action)

                    outcome = self.hardware.run_operation(
                        lease,
                        lambda commands: send(commands, operation.actions),
                        required_followup=(
                            (
                                lambda commands: send(
                                    commands, operation.required_followup, followup=True
                                )
                            )
                            if operation.required_followup
                            else None
                        ),
                    )
                    if outcome is CollectionTimerOutcome.STOP_REQUESTED:
                        state = "STOPPED"
                        break
                    # A completed dwell alone never counts a collected fraction.
                    # Record completion only after its required CLOSE succeeded.
                    self._db.execute(
                        "UPDATE execution_waits SET operation_completed=1 "
                        "WHERE phase_id=? AND operation_number=? AND state='COMPLETED'",
                        (phase_id, operation.operation_number),
                    )
                    completed += 1
                if self._session is not None:
                    self._session.check_connections()
                release = owner.invoke(lease, lambda: before_finish(state, completed))
                if state == "COMPLETED" and release is True:
                    if self._session is not None:
                        owner.invoke(lease, self._session.validate_completion)
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
