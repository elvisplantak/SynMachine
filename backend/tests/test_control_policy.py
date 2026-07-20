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
        RunPhase.P1_TRANSFER_S_TO_REACTOR,
        RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
        RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
    ],
)
def test_addition_speed_is_editable_in_p1_reactor_transfer_phases(phase: RunPhase) -> None:
    assert ControlId.ADDITION_SPEED in editable_controls_for_phase(phase)


@pytest.mark.parametrize(
    "phase",
    [
        RunPhase.P2_TRANSFER_REACTOR_TO_SF,
        RunPhase.P2_TRANSFER_SF_TO_COLUMN,
    ],
)
def test_addition_speed_is_not_editable_in_p2_transfer_phases(phase: RunPhase) -> None:
    assert ControlId.ADDITION_SPEED not in editable_controls_for_phase(phase)


def test_p1_transfer_s_to_reactor_does_not_allow_reactor_mixing() -> None:
    assert ControlId.REACTOR_MIXING not in editable_controls_for_phase(
        RunPhase.P1_TRANSFER_S_TO_REACTOR
    )


def test_reactor_mixing_matches_agreed_phases() -> None:
    expected = {
        RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
        RunPhase.DELAY_BETWEEN_ADDITIONS,
        RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
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


@pytest.mark.parametrize(
    "phase",
    [
        RunPhase.SF_SETTLING,
        RunPhase.P2_TRANSFER_SF_TO_COLUMN,
        RunPhase.COLUMN_FRACTION_COLLECTION,
    ],
)
def test_new_downstream_phases_have_no_editable_controls(phase: RunPhase) -> None:
    assert editable_controls_for_phase(phase) == frozenset()


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
