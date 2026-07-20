from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

from app.demo.calibration_models import PumpCalibrationSet, PumpId
from app.demo.fluid_plan import FluidPlan
from app.demo.phase_transfer_planner import plan_nominal_phase_transfer_cycles
from app.demo.phases import RunPhase
from app.demo.transfer_cycle_planner import TransferCyclePlan


class TopologyId(StrEnum):
    LABFORGE_V1_APPROVED_TARGET = "LABFORGE_V1_APPROVED_TARGET"


class SymbolicRouteId(StrEnum):
    S_TO_P1 = "S_TO_P1"
    P1_TO_REACTOR = "P1_TO_REACTOR"


class OperationKind(StrEnum):
    SELECT_ROUTE = "SELECT_ROUTE"
    ASPIRATE = "ASPIRATE"
    DISPENSE = "DISPENSE"


class SelectRouteOperation(BaseModel):
    model_config = ConfigDict(frozen=True)

    operation_kind: Literal[OperationKind.SELECT_ROUTE]
    operation_number: StrictInt = Field(ge=1)
    cycle_number: StrictInt = Field(ge=1)
    cycle_count: StrictInt = Field(ge=1)
    route_id: SymbolicRouteId

    @model_validator(mode="after")
    def validate_cycle_position(self) -> Self:
        if self.cycle_number > self.cycle_count:
            raise ValueError("cycle number must not exceed cycle count")
        return self


class AspirateOperation(BaseModel):
    model_config = ConfigDict(frozen=True)

    operation_kind: Literal[OperationKind.ASPIRATE]
    operation_number: StrictInt = Field(ge=1)
    cycle_number: StrictInt = Field(ge=1)
    cycle_count: StrictInt = Field(ge=1)
    pump_id: PumpId
    volume_ml: Decimal

    @field_validator("volume_ml")
    @classmethod
    def validate_volume(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("operation volume must be finite and greater than zero")
        return value

    @model_validator(mode="after")
    def validate_cycle_position(self) -> Self:
        if self.cycle_number > self.cycle_count:
            raise ValueError("cycle number must not exceed cycle count")
        return self


class DispenseOperation(BaseModel):
    model_config = ConfigDict(frozen=True)

    operation_kind: Literal[OperationKind.DISPENSE]
    operation_number: StrictInt = Field(ge=1)
    cycle_number: StrictInt = Field(ge=1)
    cycle_count: StrictInt = Field(ge=1)
    pump_id: PumpId
    volume_ml: Decimal

    @field_validator("volume_ml")
    @classmethod
    def validate_volume(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("operation volume must be finite and greater than zero")
        return value

    @model_validator(mode="after")
    def validate_cycle_position(self) -> Self:
        if self.cycle_number > self.cycle_count:
            raise ValueError("cycle number must not exceed cycle count")
        return self


PlannedOperation = Annotated[
    SelectRouteOperation | AspirateOperation | DispenseOperation,
    Field(discriminator="operation_kind"),
]


def _operations_for_transfer_cycle_plan(
    transfer_cycle_plan: TransferCyclePlan,
) -> tuple[PlannedOperation, ...]:
    operations: list[PlannedOperation] = []
    for cycle in transfer_cycle_plan.cycles:
        cycle_fields = {
            "cycle_number": cycle.cycle_number,
            "cycle_count": transfer_cycle_plan.cycle_count,
        }
        first_operation_number = len(operations) + 1
        operations.extend(
            (
                SelectRouteOperation(
                    operation_kind=OperationKind.SELECT_ROUTE,
                    operation_number=first_operation_number,
                    route_id=SymbolicRouteId.S_TO_P1,
                    **cycle_fields,
                ),
                AspirateOperation(
                    operation_kind=OperationKind.ASPIRATE,
                    operation_number=first_operation_number + 1,
                    pump_id=PumpId.P1,
                    volume_ml=cycle.volume_ml,
                    **cycle_fields,
                ),
                SelectRouteOperation(
                    operation_kind=OperationKind.SELECT_ROUTE,
                    operation_number=first_operation_number + 2,
                    route_id=SymbolicRouteId.P1_TO_REACTOR,
                    **cycle_fields,
                ),
                DispenseOperation(
                    operation_kind=OperationKind.DISPENSE,
                    operation_number=first_operation_number + 3,
                    pump_id=PumpId.P1,
                    volume_ml=cycle.volume_ml,
                    **cycle_fields,
                ),
            )
        )
    return tuple(operations)


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
        expected_operations = _operations_for_transfer_cycle_plan(
            self.transfer_cycle_plan
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
    operations = _operations_for_transfer_cycle_plan(transfer_cycle_plan)

    return P1SolventToReactorOperationPlan(
        phase=RunPhase.P1_TRANSFER_S_TO_REACTOR,
        required_topology_id=TopologyId.LABFORGE_V1_APPROVED_TARGET,
        transfer_cycle_plan=transfer_cycle_plan,
        operations=operations,
    )
