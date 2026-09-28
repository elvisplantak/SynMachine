"""Offline-only P1/P2 transfer harness. Never constructed by application startup."""

from collections.abc import Callable
from pathlib import Path
import sqlite3
from threading import RLock
from uuid import uuid4

from app.demo.p2_reactor_to_sf_operation_plan import P2ReactorToSfOperationPlan
from app.demo.p2_sf_to_column_operation_plan import P2SfToColumnOperationPlan
from app.demo.operation_executor import ProtectedOperationError, _execute_with_required_followup
from app.demo.hardware_contract import BottomValveState
from app.demo.p1_reagent_operation_plan import P1ReagentToReactorOperationPlan
from app.demo.p1_solvent_operation_plan import P1SolventToReactorOperationPlan
from app.hardware.arduino_command_journal import (
    ArduinoCommandJournalState,
    SQLiteArduinoCommandJournal,
)
from app.hardware.arduino_serial import (
    ArduinoCommandFailedError,
    ArduinoCommandRejectedError,
    ArduinoCommandResult,
    ArduinoUnavailableError,
)
from app.hardware.command_plan_store import SQLiteCommandPlanStore
from app.hardware.command_planning import ArduinoAction, CommandPlanningContext, SfBottomValveAction
from app.hardware.durable_arduino import DurableArduinoCommandExecutor


class SimulationBlocked(RuntimeError):
    """The sequence requires explicit investigation; never retry or resume."""


class SimulatedP1Device:
    """Explicit independent fixture, not a source of real hardware trust.

    A device fixture is consumed by one attempt. Hooks inject faults in tests;
    they are not hardware transport adapters.
    """

    def __init__(self, current: CommandPlanningContext) -> None:
        self.current = current
        self.controller_boot_id = current.controller_boot_id
        self.calls: list[dict] = []
        self.before_send: Callable[[dict], None] = lambda _: None
        self.used = False
        self.sf_session_id = str(uuid4())
        self.sf_calls: list[dict] = []
        self.before_sf_send: Callable[[dict], None] = lambda _: None

    def execute(self, **values) -> ArduinoCommandResult:
        self.before_send(values)
        self.calls.append(values)
        return ArduinoCommandResult(result={}, accepted=True, started=True)

    def execute_sf(self, **values) -> None:
        self.before_sf_send(values)
        self.sf_calls.append(values)


_SCHEMA = """
CREATE TABLE simulation_identity (id TEXT NOT NULL);
CREATE TABLE simulation_owner (slot INTEGER PRIMARY KEY CHECK(slot=1), phase_id TEXT);
INSERT INTO simulation_owner VALUES (1, NULL);
CREATE TABLE simulation_sf_actions (
 action_id TEXT PRIMARY KEY, phase_id TEXT NOT NULL, session_id TEXT NOT NULL,
 target TEXT NOT NULL CHECK(target IN ('OPEN', 'CLOSED')),
 state TEXT NOT NULL, error TEXT
);
CREATE TABLE simulation_phases (
 phase_id TEXT PRIMARY KEY, state TEXT NOT NULL,
 completed_operations INTEGER NOT NULL DEFAULT 0
);
"""


def provision_simulation(database: Path) -> str:
    """Create a NEW test database explicitly. Never provision on recovery/open."""
    with database.open("xb"):
        pass
    identity = str(uuid4())
    with sqlite3.connect(database) as db:
        db.executescript(_SCHEMA)
        db.execute("INSERT INTO simulation_identity VALUES (?)", (identity,))
    with SQLiteCommandPlanStore(database), SQLiteArduinoCommandJournal(database):
        pass
    return identity


class SimulatedP1Runner:
    """Durable sequence ownership for this isolated simulation database only.

    Existing production Service, SF and API paths are deliberately not wired to
    this harness. Their shared ownership is still a gate before live integration.
    """

    def __init__(self, database: Path, database_id: str, device: SimulatedP1Device):
        if type(device) is not SimulatedP1Device:
            raise TypeError("only the explicit simulated device is supported")
        self._lock = RLock()
        self.device = device
        self._sf_session = device.sf_session_id
        self._db = sqlite3.connect(
            database.resolve().as_uri() + "?mode=rw",
            uri=True,
            isolation_level=None,
            check_same_thread=False,
        )
        try:
            self._db.execute("PRAGMA synchronous=FULL")
            identities = self._db.execute("SELECT id FROM simulation_identity").fetchall()
            if identities != [(database_id,)]:
                raise SimulationBlocked("wrong simulation database identity")
            tables = {
                r[0] for r in self._db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if (
                not {
                    "simulation_owner",
                    "simulation_phases",
                    "simulation_sf_actions",
                    "prepared_command_plans",
                    "arduino_command_journal",
                }
                <= tables
            ):
                raise SimulationBlocked("incomplete simulation database")
            self._plans = SQLiteCommandPlanStore(database)
            try:
                self._journal = SQLiteArduinoCommandJournal(database)
            except BaseException:
                self._plans.close()
                raise
        except BaseException:
            self._db.close()
            raise
        self._executor = DurableArduinoCommandExecutor(device, self._journal)

    def close(self):
        self._journal.close()
        self._plans.close()
        self._db.close()

    def status(self, phase_id: str) -> tuple[str, int] | None:
        with self._lock:
            return self._db.execute(
                "SELECT state, completed_operations FROM simulation_phases WHERE phase_id=?",
                (phase_id,),
            ).fetchone()

    def _claim(self, phase_id: str):
        self._db.execute("BEGIN IMMEDIATE")
        try:
            owner = self._db.execute(
                "SELECT phase_id FROM simulation_owner WHERE slot=1"
            ).fetchone()
            if owner != (None,) or self.status(phase_id) is not None:
                raise SimulationBlocked("sequence already attempted or ownership unresolved")
            if self._db.execute(
                "SELECT 1 FROM arduino_command_journal WHERE phase_execution_id=? LIMIT 1",
                (phase_id,),
            ).fetchone():
                raise SimulationBlocked("existing command intent requires investigation")
            if self._db.execute(
                "SELECT 1 FROM simulation_sf_actions WHERE phase_id=? LIMIT 1", (phase_id,)
            ).fetchone():
                raise SimulationBlocked("existing SF intent requires investigation")
            self._db.execute("INSERT INTO simulation_phases VALUES (?, 'RUNNING', 0)", (phase_id,))
            self._db.execute("UPDATE simulation_owner SET phase_id=? WHERE slot=1", (phase_id,))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def _finish(self, phase_id: str, state: str, completed: int):
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._db.execute(
                "UPDATE simulation_phases SET state=?, completed_operations=? WHERE phase_id=?",
                (state, completed, phase_id),
            )
            # Every incomplete attempt retains ownership, including normal Stop.
            if state == "COMPLETED":
                self._db.execute("UPDATE simulation_owner SET phase_id=NULL WHERE slot=1")
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def _execute_sf(self, phase_id: str, action: SfBottomValveAction):
        if self.device.sf_session_id != self._sf_session:
            raise ArduinoUnavailableError("simulated SF session changed")
        # An existing identity is never reissued, even if it previously completed.
        self._db.execute(
            "INSERT INTO simulation_sf_actions VALUES (?, ?, ?, ?, 'INTENT_PERSISTED', NULL)",
            (action.operation_command_id, phase_id, self._sf_session, action.state.value),
        )
        try:
            self.device.execute_sf(
                phase_execution_id=phase_id,
                operation_command_id=action.operation_command_id,
                state=action.state.value,
            )
            if self.device.sf_session_id != self._sf_session:
                raise ArduinoUnavailableError("simulated SF session changed during command")
        except Exception as error:
            state = (
                "FAILED"
                if isinstance(error, (ArduinoCommandFailedError, ArduinoCommandRejectedError))
                else "OUTCOME_UNKNOWN"
            )
            self._db.execute(
                "UPDATE simulation_sf_actions SET state=?, error=? WHERE action_id=?",
                (state, str(error), action.operation_command_id),
            )
            raise
        self._db.execute(
            "UPDATE simulation_sf_actions SET state='COMPLETED' WHERE action_id=?",
            (action.operation_command_id,),
        )

    def _execute_action(self, phase_id, action, expected_boot):
        if isinstance(action, SfBottomValveAction):
            self._execute_sf(phase_id, action)
            return
        if self.device.controller_boot_id != expected_boot:
            raise ArduinoUnavailableError("controller session changed")
        result = self._executor.execute(
            phase_execution_id=phase_id,
            operation_command_id=action.operation_command_id,
            command=action.command,
            arguments=dict(action.arguments),
        )
        if self.device.controller_boot_id != expected_boot:
            raise ArduinoUnavailableError("controller session changed during command")
        if result.state is not ArduinoCommandJournalState.COMPLETED:
            raise SimulationBlocked("command did not complete")

    @staticmethod
    def _definitive(error):
        if isinstance(error, ProtectedOperationError):
            return SimulatedP1Runner._definitive(
                error.primary_error
            ) and SimulatedP1Runner._definitive(error.followup_error)
        return isinstance(error, (ArduinoCommandFailedError, ArduinoCommandRejectedError))

    def run(
        self,
        phase_id: str,
        *,
        run_id: str,
        run_event_sequence: int,
        stop_requested: Callable[[], bool] = lambda: False,
    ) -> tuple[str, int]:
        with self._lock:
            plan = self._plans.load(phase_id)
            if plan is None:
                raise SimulationBlocked("stored plan is absent in the verified database")
            if type(plan.source.plan) not in (
                P1SolventToReactorOperationPlan,
                P1ReagentToReactorOperationPlan,
                P2ReactorToSfOperationPlan,
                P2SfToColumnOperationPlan,
            ):
                raise SimulationBlocked("only P1/P2 transfer phases are supported")
            if plan.source.run_id != run_id or plan.source.run_event_sequence != run_event_sequence:
                raise SimulationBlocked("source lifecycle identity mismatch")
            if self.device.used or self.device.current != plan.prepared.assumptions:
                raise SimulationBlocked("independent simulation state does not match assumptions")
            for operation in plan.prepared.operations:
                if any(
                    type(a) not in (ArduinoAction, SfBottomValveAction)
                    for a in (*operation.actions, *operation.required_followup)
                ):
                    raise SimulationBlocked("unsupported operation or follow-up")
                if any(
                    isinstance(a, SfBottomValveAction) and a.state is not BottomValveState.CLOSED
                    for a in operation.required_followup
                ):
                    raise SimulationBlocked("unsupported operation or follow-up")
            if self.device.controller_boot_id != plan.prepared.assumptions.controller_boot_id:
                raise SimulationBlocked("controller session changed")
            self._claim(phase_id)
            self.device.used = True
            completed = 0
            state = "COMPLETED"
            try:
                for operation in plan.prepared.operations:
                    if stop_requested():
                        state = "STOPPED"
                        break

                    def primary():
                        for action in operation.actions:
                            self._execute_action(
                                phase_id, action, plan.prepared.assumptions.controller_boot_id
                            )

                    def followup():
                        for action in operation.required_followup:
                            self._execute_action(
                                phase_id, action, plan.prepared.assumptions.controller_boot_id
                            )

                    _execute_with_required_followup(primary, followup)
                    completed += 1
                    self._db.execute(
                        "UPDATE simulation_phases SET completed_operations=? WHERE phase_id=?",
                        (completed, phase_id),
                    )
            except BaseException as error:
                # Successful CLOSE never resolves an uncertain primary action.
                outcome = "FAILED" if self._definitive(error) else "OUTCOME_UNKNOWN"
                self._finish(phase_id, outcome, completed)
                raise
            self._finish(phase_id, state, completed)
            return state, completed


# Historical P1 names remain compatible for existing offline callers.
SimulatedTransferDevice = SimulatedP1Device
SimulatedTransferRunner = SimulatedP1Runner
