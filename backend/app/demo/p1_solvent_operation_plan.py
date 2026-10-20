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


class P1SolventToReactorOperationPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    phase: RunPhase
    required_topology_id: TopologyId
    transfer_cycle_plan: TransferCyclePlan
    operations: tuple[PlannedOperation, ...]

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        if self.phase is not RunPhase.P1_TRANSFER_S_TO_REACTOR:
            raise ValueError("phase must be P1_TRANSFER_S_TO_REACTOR")
        if self.required_topology_id is not TopologyId.LABFORGE_V1_APPROVED_TARGET:
            raise ValueError("required topology must be LABFORGE_V1_APPROVED_TARGET")
        if self.transfer_cycle_plan.pump_id is not PumpId.P1:
            raise ValueError("transfer cycle plan must use pump P1")
        expected_operations = build_syringe_transfer_operations(
            self.transfer_cycle_plan,
            aspiration_route_id=SymbolicRouteId.S_TO_P1,
            dispense_route_id=SymbolicRouteId.P1_TO_REACTOR,
        )
        if self.operations != expected_operations:
            raise ValueError("operations must exactly match the transfer cycle plan")
        return self

    @property
    def operation_count(self) -> int:
        return len(self.operations)


def plan_p1_solvent_to_reactor_operations(
    fluid_plan: FluidPlan,
    calibrations: PumpCalibrationSet,
) -> P1SolventToReactorOperationPlan:
    transfer_cycle_plan = plan_nominal_phase_transfer_cycles(
        RunPhase.P1_TRANSFER_S_TO_REACTOR,
        fluid_plan,
        calibrations,
    )
    operations = build_syringe_transfer_operations(
        transfer_cycle_plan,
        aspiration_route_id=SymbolicRouteId.S_TO_P1,
        dispense_route_id=SymbolicRouteId.P1_TO_REACTOR,
    )

    return P1SolventToReactorOperationPlan(
        phase=RunPhase.P1_TRANSFER_S_TO_REACTOR,
        required_topology_id=TopologyId.LABFORGE_V1_APPROVED_TARGET,
        transfer_cycle_plan=transfer_cycle_plan,
        operations=operations,
    )
