"""Explicit offline binding to the real run lifecycle; never activated by startup."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from uuid import uuid4

from app.demo.calibration_models import PumpCalibrationSet, PumpId
from app.demo.execution_lifecycle import PhaseExecutionStartCommitOutcome
from app.demo.guided_demo_phase_executor import (
    ColumnFractionCollectionReadiness,
    GuidedDemoPhaseExecutor,
)
from app.demo.machine_models import MachineState, PhaseExecutionOutcome, PhaseExecutionResult
from app.demo.phase_result_resolution import PhaseExecutionResolution
from app.demo.run_models import RunStatus
from app.hardware.simulated_p1_runner import SimulatedP1Runner, SimulationBlocked
from app.persistence.sqlite_store import SCHEMA_VERSION, SQLiteStore


def provision_lifecycle(database: Path, simulation_id: str) -> str:
    """Explicit new offline database only. Never called while reopening/recovering."""
    with database.open("xb"):
        pass
    with SQLiteStore(database):
        pass
    identity = str(uuid4())
    with sqlite3.connect(database) as db:
        db.execute("CREATE TABLE offline_lifecycle_identity (id TEXT, simulation_id TEXT)")
        db.execute(
            "INSERT INTO offline_lifecycle_identity VALUES (?, ?)", (identity, simulation_id)
        )
    return identity


class SimulationLifecycleStore(SQLiteStore):
    """Real lifecycle transitions, strict existing-file open, explicit fixture identity.

    This schema extension is offline-only and deliberately incompatible with normal
    application startup. No absent/empty/wrong database is provisioned or repaired.
    """

    def __init__(self, database: Path, identity: str, simulation_id: str):
        self.simulation_id = simulation_id
        self._connection = sqlite3.connect(
            database.resolve().as_uri() + "?mode=rw", uri=True, isolation_level=None
        )
        try:
            actual = self._connection.execute(
                "SELECT id, simulation_id FROM offline_lifecycle_identity"
            ).fetchall()
            if actual != [(identity, simulation_id)]:
                raise SimulationBlocked("wrong lifecycle database identity or simulation binding")
            if self._connection.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
                raise SimulationBlocked("unsupported lifecycle database schema")
            self._connection.row_factory = sqlite3.Row
            self._connection.execute("PRAGMA foreign_keys = ON")
            self._connection.execute("PRAGMA synchronous = FULL")
            self._validate_schema_structure()
        except BaseException:
            self._connection.close()
            raise

    def _user_tables(self) -> list[str]:
        return [name for name in super()._user_tables() if name != "offline_lifecycle_identity"]


class SimulatedLifecycleCoordinator:
    """Bind a validated stored plan to claim/start/Stop/result using fake devices only.

    Failure/unknown intentionally leaves lifecycle execution unresolved for the
    existing startup reconciliation path. No automatic resend/resume or cleanup.
    """

    def __init__(
        self,
        store: SimulationLifecycleStore,
        runner: SimulatedP1Runner,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        if type(store) is not SimulationLifecycleStore or type(runner) is not SimulatedP1Runner:
            raise TypeError("only explicit offline lifecycle and simulation runner supported")
        if store.simulation_id != runner.database_id:
            raise SimulationBlocked("lifecycle and runner database identities differ")
        self.store = store
        self.runner = runner
        self.clock = clock

    def execute(
        self,
        phase_id: str,
        calibrations: PumpCalibrationSet,
        *,
        column_readiness: ColumnFractionCollectionReadiness | None = None,
    ) -> PhaseExecutionResolution:
        plan = self.runner.load_plan(phase_id)
        if plan is None:
            raise SimulationBlocked("stored plan is absent in the verified database")
        run = self.store.load_demo_run(plan.source.run_id)
        if (
            run is None
            or run.status is not RunStatus.RUNNING
            or run.event_sequence != plan.source.run_event_sequence
            or run.phase != plan.source.plan.phase
        ):
            raise SimulationBlocked("stored plan does not match the current run")
        supplied = {PumpId.P1: calibrations.p1, PumpId.P2: calibrations.p2}
        if any(
            p.calibration != supplied[p.calibration.pump_id]
            for p in plan.prepared.assumptions.pumps
        ):
            raise SimulationBlocked("current calibration does not match prepared assumptions")
        operations = GuidedDemoPhaseExecutor._build_current_phase_operations(
            run, calibrations, column_readiness=column_readiness
        )
        if operations != plan.source.plan.operations:
            raise SimulationBlocked("stored operations do not match current run preparation")
        intent = None
        resolution = None

        def start():
            nonlocal intent
            claimed = self.store.claim_phase_execution(
                run_id=run.run_id,
                execution_id=phase_id,
                claimed_at=self.clock(),
                expected_run_event_sequence=run.event_sequence,
                expected_phase=run.phase,
            )
            result = self.store.commit_phase_execution_start(
                claimed,
                expected_run_event_sequence=run.event_sequence,
                expected_phase=run.phase,
                start_committed_at=self.clock(),
            )
            intent = result.intent
            if (
                result.outcome is not PhaseExecutionStartCommitOutcome.STOP_WON
                and intent.start_committed_at is None
            ):
                raise SimulationBlocked("execution start was not committed")

        def stopped():
            current = self.store.load_demo_run(run.run_id)
            machine = self.store.load_machine_snapshot()
            if (
                current is None
                or machine is None
                or machine.state is not MachineState.BUSY
                or machine.active_execution != intent
                or machine.active_run_id != run.run_id
                or current.phase != run.phase
            ):
                raise SimulationBlocked("lifecycle changed during simulation")
            if current.status is RunStatus.ABORTING:
                return True
            if (
                current.status is not RunStatus.RUNNING
                or current.event_sequence != run.event_sequence
            ):
                raise SimulationBlocked("run changed during simulation")
            return False

        def finish(state, completed):
            nonlocal resolution
            # Revalidate ownership even when Stop arrived during the final operation.
            stopped()
            outcome = (
                PhaseExecutionOutcome.COMPLETED
                if state == "COMPLETED"
                else PhaseExecutionOutcome.STOPPED_AT_SAFE_BOUNDARY
            )
            resolution = self.store.resolve_phase_execution(
                PhaseExecutionResult(
                    execution_id=phase_id,
                    outcome=outcome,
                    reported_at=self.clock(),
                )
            )
            # Stop may win inside result persistence, even after all actions completed.
            return resolution.run.status is not RunStatus.ABORTED

        self.runner.run(
            phase_id,
            run_id=run.run_id,
            run_event_sequence=run.event_sequence,
            stop_requested=stopped,
            before_execute=start,
            before_finish=finish,
        )
        assert resolution is not None
        return resolution
