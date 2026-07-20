from decimal import Decimal

import pytest

from app.demo.calibration_models import PumpCalibration, PumpCalibrationSet, PumpId
from app.demo.fluid_plan import FluidPlan, build_fluid_plan
from app.demo.models import AdditionOrder, DemoConfiguration
from app.demo.phase_transfer_planner import (
    PhaseTransferPlanningError,
    plan_nominal_phase_transfer_cycles,
)
from app.demo.phases import RunPhase
from app.demo.transfer_cycle_planner import TransferCyclePlan


def configuration(**overrides: object) -> DemoConfiguration:
    values: dict[str, object] = {
        "b1_ratio_percent": "20",
        "total_mixture_volume_ml": "10",
        "combined_b1_b2_volume_ml": "5",
        "addition_order": AdditionOrder.B1_THEN_B2,
        "addition_speed_command_percent": "50",
        "reactor_mixing_command_percent": "60",
        "sf_mixing_command_percent": "40",
        "simulated_target_temperature_c": "25",
        "reaction_duration_seconds": "600",
        "delay_between_additions_seconds": "5",
    }
    values.update(overrides)
    return DemoConfiguration(**values)


def calibration(pump_id: PumpId, working_volume_ml: str) -> PumpCalibration:
    return PumpCalibration(
        pump_id=pump_id,
        working_full_chamber_position_steps=1234,
        working_empty_chamber_position_steps=9876,
        working_volume_ml=working_volume_ml,
    )


def calibration_set(
    p1_working_volume_ml: str = "3",
    p2_working_volume_ml: str = "4",
) -> PumpCalibrationSet:
    return PumpCalibrationSet(
        p1=calibration(PumpId.P1, p1_working_volume_ml),
        p2=calibration(PumpId.P2, p2_working_volume_ml),
    )


@pytest.mark.parametrize(
    ("phase", "expected_pump", "expected_volume"),
    [
        (RunPhase.P1_TRANSFER_S_TO_REACTOR, PumpId.P1, Decimal("5")),
        (RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR, PumpId.P1, Decimal("1")),
        (RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR, PumpId.P1, Decimal("4")),
        (RunPhase.P2_TRANSFER_REACTOR_TO_SF, PumpId.P2, Decimal("10")),
        (RunPhase.P2_TRANSFER_SF_TO_COLUMN, PumpId.P2, Decimal("10")),
    ],
)
def test_exact_phase_mapping(
    phase: RunPhase,
    expected_pump: PumpId,
    expected_volume: Decimal,
) -> None:
    result = plan_nominal_phase_transfer_cycles(
        phase,
        build_fluid_plan(configuration()),
        calibration_set(),
    )

    assert result.pump_id is expected_pump
    assert result.requested_volume_ml == expected_volume


@pytest.mark.parametrize(
    ("addition_order", "expected_first", "expected_second"),
    [
        (AdditionOrder.B1_THEN_B2, Decimal("1"), Decimal("4")),
        (AdditionOrder.B2_THEN_B1, Decimal("4"), Decimal("1")),
    ],
)
def test_liquid_phase_volumes_follow_resolved_addition_order(
    addition_order: AdditionOrder,
    expected_first: Decimal,
    expected_second: Decimal,
) -> None:
    fluid_plan = build_fluid_plan(configuration(addition_order=addition_order))
    calibrations = calibration_set()

    first = plan_nominal_phase_transfer_cycles(
        RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
        fluid_plan,
        calibrations,
    )
    second = plan_nominal_phase_transfer_cycles(
        RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
        fluid_plan,
        calibrations,
    )

    assert first.requested_volume_ml == expected_first
    assert second.requested_volume_ml == expected_second


@pytest.mark.parametrize(
    "phase",
    [
        RunPhase.P1_TRANSFER_S_TO_REACTOR,
        RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
        RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
    ],
)
def test_all_p1_phases_use_p1_calibration(phase: RunPhase) -> None:
    result = plan_nominal_phase_transfer_cycles(
        phase,
        build_fluid_plan(configuration()),
        calibration_set(p1_working_volume_ml="0.75", p2_working_volume_ml="7"),
    )

    assert result.pump_id is PumpId.P1
    assert result.working_volume_ml == Decimal("0.75")
    assert all(cycle.volume_ml <= Decimal("0.75") for cycle in result.cycles)


@pytest.mark.parametrize(
    "phase",
    [RunPhase.P2_TRANSFER_REACTOR_TO_SF, RunPhase.P2_TRANSFER_SF_TO_COLUMN],
)
def test_both_p2_phases_use_p2_calibration_and_exact_total(phase: RunPhase) -> None:
    result = plan_nominal_phase_transfer_cycles(
        phase,
        build_fluid_plan(configuration()),
        calibration_set(p1_working_volume_ml="7", p2_working_volume_ml="3"),
    )

    assert result.pump_id is PumpId.P2
    assert result.working_volume_ml == Decimal("3")
    assert result.requested_volume_ml == Decimal("10")
    assert tuple(cycle.volume_ml for cycle in result.cycles) == (
        Decimal("3"),
        Decimal("3"),
        Decimal("3"),
        Decimal("1"),
    )


SUPPORTED_PHASES = {
    RunPhase.P1_TRANSFER_S_TO_REACTOR,
    RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
    RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
    RunPhase.P2_TRANSFER_REACTOR_TO_SF,
    RunPhase.P2_TRANSFER_SF_TO_COLUMN,
}


@pytest.mark.parametrize("phase", [phase for phase in RunPhase if phase not in SUPPORTED_PHASES])
def test_non_transfer_phases_are_rejected(phase: RunPhase) -> None:
    with pytest.raises(
        PhaseTransferPlanningError,
        match=rf"phase {phase.value} is not a liquid-transfer phase",
    ):
        plan_nominal_phase_transfer_cycles(
            phase,
            build_fluid_plan(configuration()),
            calibration_set(),
        )


@pytest.mark.parametrize("identity_field", ["first_liquid", "second_liquid"])
def test_unexpected_liquid_identity_is_rejected(identity_field: str) -> None:
    valid_plan = build_fluid_plan(configuration())
    invalid_values = valid_plan.model_dump()
    invalid_values[identity_field] = "unexpected"
    invalid_plan = FluidPlan.model_validate(invalid_values)
    phase = (
        RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR
        if identity_field == "first_liquid"
        else RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR
    )

    with pytest.raises(PhaseTransferPlanningError, match="nominal requested volume"):
        plan_nominal_phase_transfer_cycles(phase, invalid_plan, calibration_set())


def test_result_uses_existing_transfer_cycle_plan_output_boundary() -> None:
    result = plan_nominal_phase_transfer_cycles(
        RunPhase.P1_TRANSFER_S_TO_REACTOR,
        build_fluid_plan(configuration()),
        calibration_set(),
    )

    assert isinstance(result, TransferCyclePlan)
    assert set(TransferCyclePlan.model_fields) == {
        "pump_id",
        "requested_volume_ml",
        "working_volume_ml",
        "cycles",
    }


def test_fractional_nominal_volume_preserves_exact_decimal_arithmetic() -> None:
    fluid_plan = build_fluid_plan(
        configuration(
            b1_ratio_percent="25",
            total_mixture_volume_ml="2.345",
            combined_b1_b2_volume_ml="1.234",
        )
    )

    result = plan_nominal_phase_transfer_cycles(
        RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
        fluid_plan,
        calibration_set(p1_working_volume_ml="0.1"),
    )

    assert result.requested_volume_ml == Decimal("0.30850")
    assert isinstance(result.requested_volume_ml, Decimal)
    assert result.planned_volume_ml == result.requested_volume_ml
    assert all(isinstance(cycle.volume_ml, Decimal) for cycle in result.cycles)


def test_zero_nominal_volume_preserves_empty_cycle_plan_behavior() -> None:
    fluid_plan = build_fluid_plan(configuration(b1_ratio_percent="0"))

    result = plan_nominal_phase_transfer_cycles(
        RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
        fluid_plan,
        calibration_set(),
    )

    assert result.requested_volume_ml == Decimal("0")
    assert result.cycles == ()
