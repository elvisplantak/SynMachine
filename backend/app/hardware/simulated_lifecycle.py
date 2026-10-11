"""Explicit offline binding to the real run lifecycle; never activated by startup."""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
import sqlite3
from uuid import uuid4

from app.demo import lifecycle
from app.demo.events import DomainEventType
from app.demo.machine_events import MachineEventType
from app.demo.phases import PAUSABLE_EXECUTION_PHASES
from app.demo.pausable_wait_plan import PausableWaitPlan, plan_pausable_wait
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
from app.hardware.owned_transfer_runner import OwnedTransferRunner
from app.demo.timed_sf_operation_plan import TimedSfOperationPlan, plan_timed_sf_operations


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

    def __init__(
        self, database: Path, identity: str, simulation_id: str, *, read_only: bool = False
    ):
        self.simulation_id = simulation_id
        self._connection = sqlite3.connect(
            database.resolve().as_uri() + ("?mode=ro" if read_only else "?mode=rw"),
            uri=True, isolation_level=None, check_same_thread=not read_only,
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

    def persist_maintenance_transition(self, expected, machine, event):
        """Compare the complete current snapshot inside the lifecycle transaction."""
        from app.persistence.sqlite_store import MACHINE_AGGREGATE, MACHINE_AGGREGATE_ID

        self._connection.execute("BEGIN IMMEDIATE")
        try:
            if self.load_machine_snapshot() != expected:
                raise SimulationBlocked("maintenance lifecycle changed")
            if event.event_type is MachineEventType.MAINTENANCE_STARTED:
                if machine.active_maintenance != event.maintenance_intent:
                    raise SimulationBlocked("maintenance start event differs from current intent")
            elif machine.active_maintenance is not None:
                raise SimulationBlocked("maintenance resolution must clear the active intent")
            self._validate_machine_transition(machine, (event,))
            self._write_transition(MACHINE_AGGREGATE, MACHINE_AGGREGATE_ID, machine, (event,))
            self._connection.execute("COMMIT")
        except BaseException:
            self._connection.execute("ROLLBACK")
            raise

    def set_wait_paused(self, execution_id: str, *, paused: bool, occurred_at: datetime):
        """Explicit offline control on a started wait; no API or hardware dispatch."""
        if type(paused) is not bool:
            raise ValueError("paused must be boolean")
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            machine = self.load_machine_snapshot()
            intent = machine.active_execution if machine is not None else None
            if (
                machine is None
                or machine.state is not MachineState.BUSY
                or intent is None
                or intent.execution_id != execution_id
                or intent.phase not in PAUSABLE_EXECUTION_PHASES
                or intent.start_committed_at is None
                or machine.active_run_id != intent.run_id
            ):
                raise SimulationBlocked("Pause/Resume requires the current started wait intent")
            run = self.load_demo_run(intent.run_id)
            if run is None or run.phase != intent.phase:
                raise SimulationBlocked("wait phase differs from current run")
            transition = (lifecycle.pause_run if paused else lifecycle.resume_run)(run, occurred_at)
            self._validate_run_transition(transition.run, transition.events)
            self._write_transition(
                "RUN", run.run_id, transition.run, self._normalize_events(transition.events)
            )
            self._connection.execute("COMMIT")
            return transition.run
        except BaseException:
            self._connection.execute("ROLLBACK")
            raise

    def read_wait_control(self, initial_run, intent):
        """Read one snapshot and accept only replayable Pause/Resume/Stop events."""
        self._connection.execute("BEGIN")
        try:
            current = self.load_demo_run(initial_run.run_id)
            machine = self.load_machine_snapshot()
            if (
                current is None
                or machine is None
                or machine.state is not MachineState.BUSY
                or machine.active_execution != intent
                or machine.active_run_id != initial_run.run_id
                or initial_run.phase not in PAUSABLE_EXECUTION_PHASES
            ):
                raise SimulationBlocked("wait lifecycle identity changed")
            replay = initial_run
            transitions = {
                DomainEventType.RUN_PAUSED: lifecycle.pause_run,
                DomainEventType.RUN_RESUMED: lifecycle.resume_run,
                DomainEventType.ABORT_REQUESTED: lifecycle.request_abort,
            }
            for event in self.load_events("RUN", initial_run.run_id):
                if event.sequence_number <= initial_run.event_sequence:
                    continue
                transition = transitions.get(event.event_type)
                if transition is None:
                    raise SimulationBlocked("unexpected lifecycle event during wait")
                expected = transition(replay, event.occurred_at)
                if expected.events != (event,):
                    raise SimulationBlocked("wait event differs from valid lifecycle transition")
                replay = expected.run
            if replay != current:
                raise SimulationBlocked("wait snapshot differs from validated control history")
            self._connection.execute("COMMIT")
            return current.status, current.event_sequence
        except BaseException:
            self._connection.execute("ROLLBACK")
            raise


class PlanLifecycleCoordinator:
    """Shared plan validation and lifecycle binding for both offline execution paths.

    Failure/unknown intentionally leaves lifecycle execution unresolved for the
    existing startup reconciliation path. No automatic resend/resume or cleanup.
    """

    def __init__(
        self,
        store: SimulationLifecycleStore,
        runner: SimulatedP1Runner | OwnedTransferRunner,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        if type(store) is not SimulationLifecycleStore or type(runner) not in (
            SimulatedP1Runner,
            OwnedTransferRunner,
        ):
            raise TypeError(
                "only explicit offline lifecycle and approved offline runners supported"
            )
        if store.simulation_id != runner.database_id:
            raise SimulationBlocked("lifecycle and runner database identities differ")
        self.store = store
        self.runner = runner
        self.clock = clock
        self.before_control_poll = lambda: None

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
        from app.demo.maintenance_plan import MaintenancePlan
        if isinstance(plan.source.plan, MaintenancePlan):
            raise SimulationBlocked("maintenance plans require the owned maintenance lifecycle")
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
        pausable = isinstance(plan.source.plan, PausableWaitPlan)
        if run.recipe is not None:
            from app.recipes.planning import source_for_recipe_run
            if type(self.runner) is not OwnedTransferRunner:
                raise SimulationBlocked("recipe steps require the owned runner")
            current_source = source_for_recipe_run(run, calibrations, column_readiness)
            if current_source != plan.source.plan:
                raise SimulationBlocked("stored recipe plan differs from current step snapshot")
            operations = current_source.operations
        elif pausable:
            if type(self.runner) is not OwnedTransferRunner:
                raise SimulationBlocked("pausable waits require the owned runner")
            current_source = plan_pausable_wait(run)
            if current_source != plan.source.plan:
                raise SimulationBlocked("stored wait plan differs from current run")
            operations = current_source.operations
        elif isinstance(plan.source.plan, TimedSfOperationPlan):
            # Full source equality prevents changes to duration/phase metadata.
            current_source = plan_timed_sf_operations(run)
            if current_source != plan.source.plan:
                raise SimulationBlocked("stored timed SF plan differs from current run")
            operations = current_source.operations
        else:
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

        def wait_control():
            self.before_control_poll()
            self.runner._check_boot(plan.prepared.assumptions.controller_boot_id)
            self.runner._sf._session_check()
            if self.runner._session is not None:
                self.runner._session.validate_completion()
            return self.store.read_wait_control(run, intent)

        def stopped():
            self.before_control_poll()
            if pausable:
                return wait_control()[0] is RunStatus.ABORTING
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
            while True:
                resolution = self.store.resolve_phase_execution(
                    PhaseExecutionResult(
                        execution_id=phase_id, outcome=outcome, reported_at=self.clock()
                    ),
                    **({"defer_paused_wait": True} if pausable else {}),
                )
                if resolution is not None:
                    break
                # Pause won the lifecycle commit race after the duration elapsed.
                # Keep the same intent/owner; wait for Resume or Stop, never resend.
                self.runner._timer.wait_pausable(Decimal(0), wait_control)
            # Stop may win inside result persistence, even after all actions completed.
            return resolution.run.status is not RunStatus.ABORTED

        self.runner.run(
            phase_id,
            run_id=run.run_id,
            run_event_sequence=run.event_sequence,
            stop_requested=stopped,
            before_execute=start,
            before_finish=finish,
            **({"wait_control": wait_control} if pausable else {}),
        )
        assert resolution is not None
        return resolution


# Historical name retained for existing offline callers. Both runners share the
# same lifecycle validation and commit path; the candidate uses shared ownership.
SimulatedLifecycleCoordinator = PlanLifecycleCoordinator
