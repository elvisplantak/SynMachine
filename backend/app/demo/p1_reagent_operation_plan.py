from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from app.demo.calibration_models import PumpCalibrationSet, PumpId
from app.demo.fluid_plan import FluidPlan
from app.demo.operation_models import (
    PlannedOperation,
    SymbolicRouteId,
    TopologyId,
    build_syringe_transfer_operations,
)
from app.demo.phase_transfer_planner import plan_nominal_phase_transfer_cycles
from app.demo.phases import RunPhase
from app.demo.transfer_cycle_planner import TransferCyclePlan


class ReagentId(StrEnum):
    B1 = "B1"
    B2 = "B2"


class P1ReagentOperationPlanningError(ValueError):
    pass


_SUPPORTED_REAGENT_PHASES = frozenset(
    {
        RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
        RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
    }
)


def _aspiration_route_id(reagent_id: ReagentId) -> SymbolicRouteId:
    if reagent_id is ReagentId.B1:
        return SymbolicRouteId.B1_TO_P1
    if reagent_id is ReagentId.B2:
        return SymbolicRouteId.B2_TO_P1
    raise P1ReagentOperationPlanningError(
        f"unsupported P1 reagent identity {reagent_id!r}"
    )


class P1ReagentToReactorOperationPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    phase: RunPhase
    reagent_id: ReagentId
    required_topology_id: TopologyId
    transfer_cycle_plan: TransferCyclePlan
    operations: tuple[PlannedOperation, ...]

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        if self.phase not in _SUPPORTED_REAGENT_PHASES:
            raise ValueError("phase must be a supported P1 reagent-transfer phase")
        if self.required_topology_id is not TopologyId.LABFORGE_V1_APPROVED_TARGET:
            raise ValueError("required topology must be LABFORGE_V1_APPROVED_TARGET")
        if self.transfer_cycle_plan.pump_id is not PumpId.P1:
            raise ValueError("transfer cycle plan must use pump P1")
        expected_operations = build_syringe_transfer_operations(
            self.transfer_cycle_plan,
            aspiration_route_id=_aspiration_route_id(self.reagent_id),
            dispense_route_id=SymbolicRouteId.P1_TO_REACTOR,
        )
        if self.operations != expected_operations:
            raise ValueError("operations must exactly match the reagent transfer cycle plan")
        return self

    @property
    def operation_count(self) -> int:
        return len(self.operations)


def plan_p1_reagent_to_reactor_operations(
    phase: RunPhase,
    fluid_plan: FluidPlan,
    calibrations: PumpCalibrationSet,
) -> P1ReagentToReactorOperationPlan:
    if phase not in _SUPPORTED_REAGENT_PHASES:
        raise P1ReagentOperationPlanningError(
            f"phase {phase.value} is not a P1 reagent-transfer phase"
        )

    if phase is RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR:
        liquid = fluid_plan.first_liquid
    elif phase is RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR:
        liquid = fluid_plan.second_liquid
    else:
        raise P1ReagentOperationPlanningError(
            f"phase {phase.value} is not a P1 reagent-transfer phase"
        )
    if liquid == "B1":
        reagent_id = ReagentId.B1
    elif liquid == "B2":
        reagent_id = ReagentId.B2
    else:
        raise P1ReagentOperationPlanningError(
            f"unsupported P1 reagent identity {liquid!r}"
        )

    transfer_cycle_plan = plan_nominal_phase_transfer_cycles(
        phase,
        fluid_plan,
        calibrations,
    )
    operations = build_syringe_transfer_operations(
        transfer_cycle_plan,
        aspiration_route_id=_aspiration_route_id(reagent_id),
        dispense_route_id=SymbolicRouteId.P1_TO_REACTOR,
    )

    return P1ReagentToReactorOperationPlan(
        phase=phase,
        reagent_id=reagent_id,
        required_topology_id=TopologyId.LABFORGE_V1_APPROVED_TARGET,
        transfer_cycle_plan=transfer_cycle_plan,
        operations=operations,
    )
