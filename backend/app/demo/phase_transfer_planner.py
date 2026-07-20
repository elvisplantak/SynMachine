from decimal import Decimal

from app.demo.calibration_models import PumpCalibrationSet
from app.demo.fluid_plan import FluidPlan
from app.demo.phases import RunPhase
from app.demo.transfer_cycle_planner import TransferCyclePlan, plan_transfer_cycles


class PhaseTransferPlanningError(ValueError):
    pass


_P1_TRANSFER_PHASES = frozenset(
    {
        RunPhase.P1_TRANSFER_S_TO_REACTOR,
        RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
        RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
    }
)
_P2_TRANSFER_PHASES = frozenset(
    {
        RunPhase.P2_TRANSFER_REACTOR_TO_SF,
        RunPhase.P2_TRANSFER_SF_TO_COLUMN,
    }
)
_SUPPORTED_TRANSFER_PHASES = _P1_TRANSFER_PHASES | _P2_TRANSFER_PHASES


def _configured_liquid_volume(liquid: str, fluid_plan: FluidPlan) -> Decimal:
    if liquid == "B1":
        return fluid_plan.b1_configured_volume_ml
    if liquid == "B2":
        return fluid_plan.b2_configured_volume_ml
    raise PhaseTransferPlanningError(
        f"cannot resolve nominal requested volume for liquid identity {liquid!r}"
    )


def _nominal_requested_volume(phase: RunPhase, fluid_plan: FluidPlan) -> Decimal:
    if phase is RunPhase.P1_TRANSFER_S_TO_REACTOR:
        return fluid_plan.s_configured_volume_ml
    if phase is RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR:
        return _configured_liquid_volume(fluid_plan.first_liquid, fluid_plan)
    if phase is RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR:
        return _configured_liquid_volume(fluid_plan.second_liquid, fluid_plan)
    if phase is RunPhase.P2_TRANSFER_REACTOR_TO_SF:
        return fluid_plan.total_configured_volume_ml
    if phase is RunPhase.P2_TRANSFER_SF_TO_COLUMN:
        return fluid_plan.total_configured_volume_ml
    raise PhaseTransferPlanningError(
        f"phase {phase.value} is not a liquid-transfer phase"
    )


def plan_nominal_phase_transfer_cycles(
    phase: RunPhase,
    fluid_plan: FluidPlan,
    calibrations: PumpCalibrationSet,
) -> TransferCyclePlan:
    """Plan nominal transfer cycles without claiming physical delivery."""
    if phase not in _SUPPORTED_TRANSFER_PHASES:
        raise PhaseTransferPlanningError(
            f"phase {phase.value} is not a liquid-transfer phase"
        )

    if phase in _P1_TRANSFER_PHASES:
        calibration = calibrations.p1
    elif phase in _P2_TRANSFER_PHASES:
        calibration = calibrations.p2
    else:
        raise PhaseTransferPlanningError(
            f"phase {phase.value} is not a liquid-transfer phase"
        )
    requested_volume_ml = _nominal_requested_volume(phase, fluid_plan)

    return plan_transfer_cycles(requested_volume_ml, calibration)
