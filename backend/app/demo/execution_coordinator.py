from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from app.demo.calibration_models import PumpCalibrationSet
from app.demo.guided_demo_phase_executor import (
    ColumnFractionCollectionReadiness,
    GuidedDemoPhaseExecutionResult,
    GuidedDemoPhaseExecutor,
)
from app.demo.execution_lifecycle import PhaseExecutionStartCommitOutcome, PhaseExecutionClaimError
from app.demo.phases import PAUSABLE_EXECUTION_PHASES
from app.demo.machine_models import (
    PhaseExecutionIntent,
    PhaseExecutionOutcome,
    PhaseExecutionResult,
)
from app.demo.phase_result_resolution import PhaseExecutionResolution
from app.persistence.sqlite_store import SQLiteStore

ExecutionIdFactory = Callable[[], str]
AwareClock = Callable[[], datetime]


def _generate_execution_id() -> str:
    return str(uuid4())


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class GuidedDemoExecutionCoordinatorResult:
    execution_id: str
    intent: PhaseExecutionIntent
    executor_result: GuidedDemoPhaseExecutionResult | None
    phase_result: PhaseExecutionResult
    resolution: PhaseExecutionResolution


class GuidedDemoExecutionConsistencyError(RuntimeError):
    """Persisted post-claim aggregate does not match its execution intent."""


class GuidedDemoExecutionCoordinator:
    """Synchronously claims, executes, and resolves one hardware phase."""

    def __init__(
        self,
        store: SQLiteStore,
        phase_executor: GuidedDemoPhaseExecutor,
        *,
        execution_id_factory: ExecutionIdFactory = _generate_execution_id,
        clock: AwareClock = _utc_now,
    ) -> None:
        self._store = store
        self._phase_executor = phase_executor
        self._execution_id_factory = execution_id_factory
        self._clock = clock

    def execute_current_phase(
        self,
        run_id: str,
        calibrations: PumpCalibrationSet,
        *,
        column_readiness: ColumnFractionCollectionReadiness | None = None,
    ) -> GuidedDemoExecutionCoordinatorResult:
        run = self._store.load_demo_run(run_id)
        if run is None:
            raise GuidedDemoExecutionConsistencyError(
                f"Guided Demo run {run_id!r} was not found before preparation"
            )
        if run.phase in PAUSABLE_EXECUTION_PHASES:
            raise PhaseExecutionClaimError("legacy coordinator does not support owned pausable waits")
        prepared = self._phase_executor.prepare_current_phase(
            run,
            calibrations,
            column_readiness=column_readiness,
        )
        if prepared.run_id != run_id:
            raise GuidedDemoExecutionConsistencyError(
                f"prepared run_id={prepared.run_id!r} "
                f"!= requested run_id={run_id!r}"
            )
        execution_id = self._execution_id_factory()
        claimed_intent = self._store.claim_phase_execution(
            run_id=run_id,
            execution_id=execution_id,
            claimed_at=self._clock(),
            expected_run_event_sequence=prepared.run_event_sequence,
            expected_phase=prepared.phase,
        )
        start = self._store.commit_phase_execution_start(
            claimed_intent,
            expected_run_event_sequence=prepared.run_event_sequence,
            expected_phase=prepared.phase,
            start_committed_at=self._clock(),
        )
        intent = start.intent

        executor_result: GuidedDemoPhaseExecutionResult | None
        if start.outcome is PhaseExecutionStartCommitOutcome.STOP_WON:
            executor_result = None
            phase_result = PhaseExecutionResult(
                execution_id=execution_id,
                outcome=PhaseExecutionOutcome.STOPPED_AT_SAFE_BOUNDARY,
                reported_at=self._clock(),
            )
        else:
            executor_result = self._phase_executor.execute_prepared_phase(
                prepared
            )
            phase_result = self._to_phase_result(
                execution_id, executor_result, self._clock()
            )

        resolution = self._store.resolve_phase_execution(phase_result)
        return GuidedDemoExecutionCoordinatorResult(
            execution_id=execution_id,
            intent=intent,
            executor_result=executor_result,
            phase_result=phase_result,
            resolution=resolution,
        )

    @staticmethod
    def _to_phase_result(
        execution_id: str,
        result: GuidedDemoPhaseExecutionResult,
        reported_at: datetime,
    ) -> PhaseExecutionResult:
        return PhaseExecutionResult(
            execution_id=execution_id,
            outcome=result.outcome,
            reported_at=reported_at,
            failure_reason=result.failure_reason,
            cleanup_failure_reason=result.cleanup_failure_reason,
            primary_failure_reason=result.primary_failure_reason,
            runtime_fault_reason=result.runtime_fault_reason,
        )
