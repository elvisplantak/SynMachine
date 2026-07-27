from dataclasses import dataclass

from app.demo.calibration_models import PumpCalibrationSet
from app.demo.column_fraction_collection_operation_plan import (
    ColumnFractionCollectionConfiguration,
    plan_column_fraction_collection_operations,
)
from app.demo.hardware_contract import HardwareCommandError
from app.demo.machine_models import (
    PhaseExecutionOutcome,
    RuntimeHardwareFaultReason,
)
from app.demo.operation_models import MoveCarouselToNextFractionOperation, PlannedOperation
from app.demo.operation_executor import ProtectedOperationError
from app.demo.operation_plan_runner import (
    OperationPlanExecutionError,
    OperationPlanRunner,
    PlanRunOutcome,
    PlanRunResult,
)
from app.demo.p1_reagent_operation_plan import (
    plan_p1_reagent_to_reactor_operations,
)
from app.demo.p1_solvent_operation_plan import (
    plan_p1_solvent_to_reactor_operations,
)
from app.demo.p2_reactor_to_sf_operation_plan import (
    plan_p2_reactor_to_sf_operations,
)
from app.demo.p2_sf_to_column_operation_plan import (
    plan_p2_sf_to_column_operations,
)
from app.demo.phases import HARDWARE_EXECUTION_PHASES, RunPhase
from app.demo.run_models import DemoRun


@dataclass(frozen=True)
class ColumnFractionCollectionReadiness:
    """Explicit caller confirmations, not sensor-based physical verification."""

    carousel_ready_confirmed: bool
    column_bottom_valve_referenced_confirmed: bool


@dataclass(frozen=True)
class PreparedGuidedDemoPhase:
    run_id: str
    run_event_sequence: int
    phase: RunPhase
    operations: tuple[PlannedOperation, ...]


@dataclass(frozen=True)
class GuidedDemoPhaseExecutionResult:
    phase: RunPhase
    outcome: PhaseExecutionOutcome
    plan_run_result: PlanRunResult | None = None
    failure_reason: str | None = None
    cleanup_failure_reason: str | None = None
    primary_failure_reason: str | None = None
    runtime_fault_reason: RuntimeHardwareFaultReason | None = None


class UnsupportedGuidedDemoExecutionPhaseError(RuntimeError):
    def __init__(self, phase: RunPhase) -> None:
        self.phase = phase
        super().__init__(f"unsupported Guided Demo execution phase: {phase.value}")


class MissingColumnFractionCollectionReadinessError(RuntimeError):
    def __init__(self) -> None:
        self.phase = RunPhase.COLUMN_FRACTION_COLLECTION
        super().__init__(
            "column_readiness is required for COLUMN_FRACTION_COLLECTION"
        )


class GuidedDemoPhaseExecutor:
    def __init__(self, plan_runner: OperationPlanRunner) -> None:
        self._plan_runner = plan_runner

    def execute_current_phase(
        self,
        run: DemoRun,
        calibrations: PumpCalibrationSet,
        *,
        column_readiness: ColumnFractionCollectionReadiness | None = None,
    ) -> GuidedDemoPhaseExecutionResult:
        prepared = self.prepare_current_phase(
            run,
            calibrations,
            column_readiness=column_readiness,
        )
        return self.execute_prepared_phase(prepared)

    def prepare_current_phase(
        self,
        run: DemoRun,
        calibrations: PumpCalibrationSet,
        *,
        column_readiness: ColumnFractionCollectionReadiness | None = None,
    ) -> PreparedGuidedDemoPhase:
        operations = self._build_current_phase_operations(
            run,
            calibrations,
            column_readiness=column_readiness,
        )
        return PreparedGuidedDemoPhase(
            run_id=run.run_id,
            run_event_sequence=run.event_sequence,
            phase=run.phase,
            operations=operations,
        )

    def execute_prepared_phase(
        self,
        prepared: PreparedGuidedDemoPhase,
    ) -> GuidedDemoPhaseExecutionResult:
        try:
            plan_run_result = self._plan_runner.run(prepared.operations)
        except OperationPlanExecutionError as error:
            return self._map_plan_error(
                prepared.phase, prepared.operations, error
            )
        outcome = (
            PhaseExecutionOutcome.COMPLETED
            if plan_run_result.outcome is PlanRunOutcome.COMPLETED
            else PhaseExecutionOutcome.STOPPED_AT_SAFE_BOUNDARY
        )
        return GuidedDemoPhaseExecutionResult(
            phase=prepared.phase,
            outcome=outcome,
            plan_run_result=plan_run_result,
        )

    @staticmethod
    def _map_plan_error(
        phase: RunPhase,
        operations: tuple[PlannedOperation, ...],
        error: OperationPlanExecutionError,
    ) -> GuidedDemoPhaseExecutionResult:
        original = error.original_error
        if isinstance(original, HardwareCommandError) and getattr(
            original, "_labforge_required_followup_failure", False
        ):
            return GuidedDemoPhaseExecutionResult(
                phase=phase,
                outcome=PhaseExecutionOutcome.REQUIRED_CLEANUP_FAILED,
                cleanup_failure_reason=str(original),
                runtime_fault_reason=(
                    RuntimeHardwareFaultReason.REQUIRED_FOLLOWUP_FAILED
                ),
            )
        if isinstance(original, ProtectedOperationError):
            return GuidedDemoPhaseExecutionResult(
                phase=phase,
                outcome=PhaseExecutionOutcome.REQUIRED_CLEANUP_FAILED,
                cleanup_failure_reason=str(original.followup_error),
                primary_failure_reason=str(original.primary_error),
                runtime_fault_reason=(
                    RuntimeHardwareFaultReason.REQUIRED_FOLLOWUP_FAILED
                ),
            )
        if isinstance(original, HardwareCommandError):
            failed_operation = operations[error.failed_operation_number - 1]
            runtime_reason = (
                RuntimeHardwareFaultReason.CAROUSEL_MOVEMENT_FAILED
                if isinstance(
                    failed_operation, MoveCarouselToNextFractionOperation
                )
                else RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED
            )
            return GuidedDemoPhaseExecutionResult(
                phase=phase,
                outcome=PhaseExecutionOutcome.HARDWARE_COMMAND_FAILED,
                failure_reason=str(original),
                runtime_fault_reason=runtime_reason,
            )
        raise error

    @staticmethod
    def _build_current_phase_operations(
        run: DemoRun,
        calibrations: PumpCalibrationSet,
        *,
        column_readiness: ColumnFractionCollectionReadiness | None,
    ) -> tuple[PlannedOperation, ...]:
        if run.phase not in HARDWARE_EXECUTION_PHASES:
            raise UnsupportedGuidedDemoExecutionPhaseError(run.phase)
        if run.phase is RunPhase.P1_TRANSFER_S_TO_REACTOR:
            return plan_p1_solvent_to_reactor_operations(
                run.fluid_plan,
                calibrations,
            ).operations
        if run.phase in {
            RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
            RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
        }:
            return plan_p1_reagent_to_reactor_operations(
                run.phase,
                run.fluid_plan,
                calibrations,
            ).operations
        if run.phase is RunPhase.P2_TRANSFER_REACTOR_TO_SF:
            return plan_p2_reactor_to_sf_operations(
                run.fluid_plan,
                calibrations,
            ).operations
        if run.phase is RunPhase.P2_TRANSFER_SF_TO_COLUMN:
            return plan_p2_sf_to_column_operations(
                run.fluid_plan,
                calibrations,
            ).operations
        if run.phase is RunPhase.COLUMN_FRACTION_COLLECTION:
            if column_readiness is None:
                raise MissingColumnFractionCollectionReadinessError
            configuration = ColumnFractionCollectionConfiguration.from_execution_settings(
                run.execution_settings,
                carousel_ready_confirmed=(
                    column_readiness.carousel_ready_confirmed
                ),
                column_bottom_valve_referenced_confirmed=(
                    column_readiness.column_bottom_valve_referenced_confirmed
                ),
            )
            return plan_column_fraction_collection_operations(
                configuration
            ).operations
        raise AssertionError(
            f"missing Guided Demo execution builder for phase {run.phase.value}"
        )
