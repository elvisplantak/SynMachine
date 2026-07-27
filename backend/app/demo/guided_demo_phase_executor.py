from dataclasses import dataclass

from app.demo.calibration_models import PumpCalibrationSet
from app.demo.column_fraction_collection_operation_plan import (
    ColumnFractionCollectionConfiguration,
    plan_column_fraction_collection_operations,
)
from app.demo.operation_models import PlannedOperation
from app.demo.operation_plan_runner import (
    OperationPlanRunner,
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
class GuidedDemoPhaseExecutionResult:
    phase: RunPhase
    plan_run_result: PlanRunResult


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
        operations = self._build_current_phase_operations(
            run,
            calibrations,
            column_readiness=column_readiness,
        )
        plan_run_result = self._plan_runner.run(operations)
        return GuidedDemoPhaseExecutionResult(
            phase=run.phase,
            plan_run_result=plan_run_result,
        )

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
