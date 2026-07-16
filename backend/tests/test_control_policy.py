import pytest

from app.demo.control_policy import (
    PERMANENTLY_LOCKED_FLUID_PLAN_FIELDS,
    ControlId,
    LockedFluidPlanField,
    editable_controls_for_phase,
)
from app.demo.phases import RunPhase


@pytest.mark.parametrize(
    "phase",
    [
        RunPhase.P1_DISPENSE_S_TO_REACTOR,
        RunPhase.P1_DISPENSE_FIRST_LIQUID_TO_REACTOR,
        RunPhase.P1_DISPENSE_SECOND_LIQUID_TO_REACTOR,
    ],
)
def test_addition_speed_is_editable_in_p1_reactor_dispense_phases(phase: RunPhase) -> None:
    assert ControlId.ADDITION_SPEED in editable_controls_for_phase(phase)


@pytest.mark.parametrize(
    "phase",
    [
        RunPhase.P1_ASPIRATE_S,
        RunPhase.P1_ASPIRATE_FIRST_LIQUID,
        RunPhase.P1_ASPIRATE_SECOND_LIQUID,
    ],
)
def test_addition_speed_is_not_editable_in_aspiration_phases(phase: RunPhase) -> None:
    assert ControlId.ADDITION_SPEED not in editable_controls_for_phase(phase)


def test_p1_aspirate_s_does_not_allow_reactor_mixing() -> None:
    assert ControlId.REACTOR_MIXING not in editable_controls_for_phase(RunPhase.P1_ASPIRATE_S)


def test_p1_dispense_s_to_reactor_allows_reactor_mixing() -> None:
    assert ControlId.REACTOR_MIXING in editable_controls_for_phase(
        RunPhase.P1_DISPENSE_S_TO_REACTOR
    )


def test_reactor_mixing_matches_agreed_phases() -> None:
    expected = {
        RunPhase.P1_DISPENSE_S_TO_REACTOR,
        RunPhase.P1_ASPIRATE_FIRST_LIQUID,
        RunPhase.P1_DISPENSE_FIRST_LIQUID_TO_REACTOR,
        RunPhase.DELAY_BETWEEN_ADDITIONS,
        RunPhase.P1_ASPIRATE_SECOND_LIQUID,
        RunPhase.P1_DISPENSE_SECOND_LIQUID_TO_REACTOR,
        RunPhase.REACTION_HOLD,
    }
    actual = {
        phase
        for phase in RunPhase
        if ControlId.REACTOR_MIXING in editable_controls_for_phase(phase)
    }
    assert actual == expected


@pytest.mark.parametrize(
    ("control", "only_phase"),
    [
        (ControlId.DELAY_BETWEEN_ADDITIONS, RunPhase.DELAY_BETWEEN_ADDITIONS),
        (ControlId.SIMULATED_TEMPERATURE, RunPhase.REACTION_HOLD),
        (ControlId.REACTION_DURATION_REMAINING_TIME, RunPhase.REACTION_HOLD),
        (ControlId.SF_MIXING, RunPhase.SF_MIXING),
    ],
)
def test_control_is_editable_only_in_expected_phase(
    control: ControlId, only_phase: RunPhase
) -> None:
    editable_phases = {
        phase for phase in RunPhase if control in editable_controls_for_phase(phase)
    }
    assert editable_phases == {only_phase}


def test_completed_phase_has_no_editable_controls() -> None:
    assert editable_controls_for_phase(RunPhase.COMPLETED) == frozenset()


def test_permanent_fluid_plan_lock_fields_are_complete() -> None:
    assert PERMANENTLY_LOCKED_FLUID_PLAN_FIELDS == frozenset(
        {
            LockedFluidPlanField.B1_B2_RATIO,
            LockedFluidPlanField.TOTAL_MIXTURE_VOLUME,
            LockedFluidPlanField.COMBINED_B1_B2_VOLUME,
            LockedFluidPlanField.CALCULATED_B1_B2_S_VOLUMES,
            LockedFluidPlanField.ADDITION_ORDER,
        }
    )
