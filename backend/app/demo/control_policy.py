from enum import StrEnum

from app.demo.phases import RunPhase


class ControlId(StrEnum):
    ADDITION_SPEED = "ADDITION_SPEED"
    REACTOR_MIXING = "REACTOR_MIXING"
    SF_MIXING = "SF_MIXING"
    SIMULATED_TEMPERATURE = "SIMULATED_TEMPERATURE"
    REACTION_DURATION_REMAINING_TIME = "REACTION_DURATION_REMAINING_TIME"
    DELAY_BETWEEN_ADDITIONS = "DELAY_BETWEEN_ADDITIONS"


class LockedFluidPlanField(StrEnum):
    B1_B2_RATIO = "B1_B2_RATIO"
    TOTAL_MIXTURE_VOLUME = "TOTAL_MIXTURE_VOLUME"
    COMBINED_B1_B2_VOLUME = "COMBINED_B1_B2_VOLUME"
    CALCULATED_B1_B2_S_VOLUMES = "CALCULATED_B1_B2_S_VOLUMES"
    ADDITION_ORDER = "ADDITION_ORDER"


PERMANENTLY_LOCKED_FLUID_PLAN_FIELDS = frozenset(LockedFluidPlanField)

_P1_DISPENSE_TO_REACTOR_PHASES = frozenset(
    {
        RunPhase.P1_DISPENSE_S_TO_REACTOR,
        RunPhase.P1_DISPENSE_FIRST_LIQUID_TO_REACTOR,
        RunPhase.P1_DISPENSE_SECOND_LIQUID_TO_REACTOR,
    }
)

_REACTOR_RELATED_PHASES = frozenset(
    {
        RunPhase.P1_DISPENSE_S_TO_REACTOR,
        RunPhase.P1_ASPIRATE_FIRST_LIQUID,
        RunPhase.P1_DISPENSE_FIRST_LIQUID_TO_REACTOR,
        RunPhase.DELAY_BETWEEN_ADDITIONS,
        RunPhase.P1_ASPIRATE_SECOND_LIQUID,
        RunPhase.P1_DISPENSE_SECOND_LIQUID_TO_REACTOR,
        RunPhase.REACTION_HOLD,
    }
)


def editable_controls_for_phase(phase: RunPhase) -> frozenset[ControlId]:
    controls: set[ControlId] = set()

    if phase in _P1_DISPENSE_TO_REACTOR_PHASES:
        controls.add(ControlId.ADDITION_SPEED)
    if phase in _REACTOR_RELATED_PHASES:
        controls.add(ControlId.REACTOR_MIXING)
    if phase is RunPhase.DELAY_BETWEEN_ADDITIONS:
        controls.add(ControlId.DELAY_BETWEEN_ADDITIONS)
    if phase is RunPhase.REACTION_HOLD:
        controls.update(
            {
                ControlId.SIMULATED_TEMPERATURE,
                ControlId.REACTION_DURATION_REMAINING_TIME,
            }
        )
    if phase is RunPhase.SF_MIXING:
        controls.add(ControlId.SF_MIXING)

    return frozenset(controls)
