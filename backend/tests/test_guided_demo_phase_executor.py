from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

import app.demo.guided_demo_phase_executor as phase_executor_module
from app.demo.calibration_models import (
    PumpCalibration,
    PumpCalibrationSet,
    PumpId,
)
from app.demo.guided_demo_phase_executor import (
    ColumnFractionCollectionReadiness,
    GuidedDemoPhaseExecutor,
    MissingColumnFractionCollectionReadinessError,
    UnsupportedGuidedDemoExecutionPhaseError,
)
from app.demo.lifecycle import create_demo_run
from app.demo.models import (
    AdditionOrder,
    DemoConfiguration,
    DemoExecutionSettings,
)
from app.demo.operation_models import PlannedOperation
from app.demo.operation_plan_runner import (
    OperationPlanExecutionError,
    PlanRunOutcome,
    PlanRunResult,
)
from app.demo.phases import RunPhase
from app.demo.run_models import DemoRun

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=UTC)
READINESS = ColumnFractionCollectionReadiness(
    carousel_ready_confirmed=True,
    column_bottom_valve_referenced_confirmed=True,
)


@dataclass
class RecordingPlanRunner:
    result: PlanRunResult

    def __post_init__(self) -> None:
        self.calls: list[tuple[PlannedOperation, ...]] = []
        self.error: Exception | None = None

    def run(self, operations: tuple[PlannedOperation, ...]) -> PlanRunResult:
        self.calls.append(operations)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def run() -> DemoRun:
    configuration = DemoConfiguration(
        b1_ratio_percent="40",
        total_mixture_volume_ml="10",
        combined_b1_b2_volume_ml="4",
        addition_order=AdditionOrder.B1_THEN_B2,
        addition_speed_command_percent="50",
        reactor_mixing_command_percent="60",
        sf_mixing_command_percent="40",
        simulated_target_temperature_c="25",
        reaction_duration_seconds="600",
        delay_between_additions_seconds="5",
    )
    execution_settings = DemoExecutionSettings(
        sf_settling_duration_seconds="12.5",
        fraction_count=3,
        fraction_duration_seconds="45.25",
    )
    return create_demo_run(
        "run-1",
        configuration,
        execution_settings,
        NOW,
    ).run


@pytest.fixture
def calibrations() -> PumpCalibrationSet:
    return PumpCalibrationSet(
        p1=PumpCalibration(
            pump_id=PumpId.P1,
            working_volume_ml="2.5",
            working_full_chamber_position_steps=1000,
            working_empty_chamber_position_steps=6000,
        ),
        p2=PumpCalibration(
            pump_id=PumpId.P2,
            working_volume_ml="3",
            working_full_chamber_position_steps=2000,
            working_empty_chamber_position_steps=8000,
        ),
    )


@pytest.fixture
def plan_result() -> PlanRunResult:
    return PlanRunResult(
        outcome=PlanRunOutcome.COMPLETED,
        completed_operation_count=2,
        total_operation_count=2,
        last_completed_operation_number=2,
        stop_operation_number=None,
    )


SUPPORTED_BUILDER_CASES = (
    (
        RunPhase.P1_TRANSFER_S_TO_REACTOR,
        "plan_p1_solvent_to_reactor_operations",
    ),
    (
        RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
        "plan_p1_reagent_to_reactor_operations",
    ),
    (
        RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
        "plan_p1_reagent_to_reactor_operations",
    ),
    (
        RunPhase.P2_TRANSFER_REACTOR_TO_SF,
        "plan_p2_reactor_to_sf_operations",
    ),
    (
        RunPhase.P2_TRANSFER_SF_TO_COLUMN,
        "plan_p2_sf_to_column_operations",
    ),
    (
        RunPhase.COLUMN_FRACTION_COLLECTION,
        "plan_column_fraction_collection_operations",
    ),
)


@pytest.mark.parametrize(("phase", "builder_name"), SUPPORTED_BUILDER_CASES)
def test_each_supported_phase_selects_exact_builder_and_runs_its_operations(
    monkeypatch: pytest.MonkeyPatch,
    run: DemoRun,
    calibrations: PumpCalibrationSet,
    plan_result: PlanRunResult,
    phase: RunPhase,
    builder_name: str,
) -> None:
    current_run = run.model_copy(update={"phase": phase})
    operations: tuple[PlannedOperation, ...] = ()
    builder_calls: list[tuple[object, ...]] = []

    def recording_builder(*args: object) -> SimpleNamespace:
        builder_calls.append(args)
        return SimpleNamespace(operations=operations)

    monkeypatch.setattr(
        phase_executor_module,
        builder_name,
        recording_builder,
    )
    runner = RecordingPlanRunner(plan_result)

    result = GuidedDemoPhaseExecutor(runner).execute_current_phase(
        current_run,
        calibrations,
        column_readiness=READINESS,
    )

    assert runner.calls == [operations]
    assert len(builder_calls) == 1
    if phase is RunPhase.COLUMN_FRACTION_COLLECTION:
        (configuration,) = builder_calls[0]
        assert configuration.fraction_count == 3
        assert configuration.fraction_duration_seconds == Decimal("45.25")
        assert configuration.carousel_ready_confirmed is True
        assert configuration.column_bottom_valve_referenced_confirmed is True
    elif phase in {
        RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
        RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
    }:
        assert builder_calls[0] == (
            phase,
            current_run.fluid_plan,
            calibrations,
        )
    else:
        assert builder_calls[0] == (current_run.fluid_plan, calibrations)
    assert result.phase is phase
    assert result.plan_run_result is plan_result


def test_column_readiness_is_required_before_builder_or_runner(
    monkeypatch: pytest.MonkeyPatch,
    run: DemoRun,
    calibrations: PumpCalibrationSet,
    plan_result: PlanRunResult,
) -> None:
    current_run = run.model_copy(
        update={"phase": RunPhase.COLUMN_FRACTION_COLLECTION}
    )
    builder_called = False

    def unexpected_builder(*args: object) -> SimpleNamespace:
        nonlocal builder_called
        builder_called = True
        return SimpleNamespace(operations=())

    monkeypatch.setattr(
        phase_executor_module,
        "plan_column_fraction_collection_operations",
        unexpected_builder,
    )
    runner = RecordingPlanRunner(plan_result)

    with pytest.raises(MissingColumnFractionCollectionReadinessError) as caught:
        GuidedDemoPhaseExecutor(runner).execute_current_phase(
            current_run,
            calibrations,
        )

    assert caught.value.phase is RunPhase.COLUMN_FRACTION_COLLECTION
    assert builder_called is False
    assert runner.calls == []


@pytest.mark.parametrize(
    "phase",
    [
        RunPhase.READY,
        RunPhase.DELAY_BETWEEN_ADDITIONS,
        RunPhase.REACTION_HOLD,
        RunPhase.SF_MIXING,
        RunPhase.SF_SETTLING,
        RunPhase.COMPLETED,
    ],
)
def test_every_unsupported_phase_is_rejected_before_runner(
    run: DemoRun,
    calibrations: PumpCalibrationSet,
    plan_result: PlanRunResult,
    phase: RunPhase,
) -> None:
    runner = RecordingPlanRunner(plan_result)

    with pytest.raises(UnsupportedGuidedDemoExecutionPhaseError) as caught:
        GuidedDemoPhaseExecutor(runner).execute_current_phase(
            run.model_copy(update={"phase": phase}),
            calibrations,
        )

    assert caught.value.phase is phase
    assert runner.calls == []


def test_runner_error_propagates_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    run: DemoRun,
    calibrations: PumpCalibrationSet,
    plan_result: PlanRunResult,
) -> None:
    current_run = run.model_copy(
        update={"phase": RunPhase.P1_TRANSFER_S_TO_REACTOR}
    )
    monkeypatch.setattr(
        phase_executor_module,
        "plan_p1_solvent_to_reactor_operations",
        lambda *args: SimpleNamespace(operations=()),
    )
    error = OperationPlanExecutionError(
        original_error=RuntimeError("hardware failed"),
        failed_operation_number=1,
        completed_operation_count=0,
    )
    runner = RecordingPlanRunner(plan_result)
    runner.error = error

    with pytest.raises(OperationPlanExecutionError) as caught:
        GuidedDemoPhaseExecutor(runner).execute_current_phase(
            current_run,
            calibrations,
        )

    assert caught.value is error
    assert runner.calls == [()]


def test_planning_error_propagates_before_runner_and_run_is_unchanged(
    monkeypatch: pytest.MonkeyPatch,
    run: DemoRun,
    calibrations: PumpCalibrationSet,
    plan_result: PlanRunResult,
) -> None:
    current_run = run.model_copy(
        update={"phase": RunPhase.P2_TRANSFER_REACTOR_TO_SF}
    )
    original_snapshot = current_run.model_dump()
    error = ValueError("invalid planning input")

    def failing_builder(*args: object) -> SimpleNamespace:
        raise error

    monkeypatch.setattr(
        phase_executor_module,
        "plan_p2_reactor_to_sf_operations",
        failing_builder,
    )
    runner = RecordingPlanRunner(plan_result)

    with pytest.raises(ValueError) as caught:
        GuidedDemoPhaseExecutor(runner).execute_current_phase(
            current_run,
            calibrations,
        )

    assert caught.value is error
    assert runner.calls == []
    assert current_run.model_dump() == original_snapshot
