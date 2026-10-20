from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from app.demo.calibration_models import PumpCalibrationSet, PumpId
from app.demo.fluid_plan import FluidPlan
from app.demo.operation_models import (
    AspirateFromSfOperation,
    DispenseOperation,
    OperationKind,
    PlannedOperation,
    PrepareSfToColumnTransferOperation,
    SelectRouteOperation,
    SymbolicRouteId,
    TopologyId,
)
from app.demo.phase_transfer_planner import plan_nominal_phase_transfer_cycles
from app.demo.phases import RunPhase
from app.demo.transfer_cycle_planner import TransferCyclePlan


class P2SfToColumnOperationPlanningError(ValueError):
    pass


class LogicalValveState(StrEnum):
    CLOSED = "CLOSED"


class P2NominalContents(StrEnum):
    EMPTY = "EMPTY"
    CYCLE_VOLUME = "CYCLE_VOLUME"


class SfToColumnLogicalState(BaseModel):
    model_config = ConfigDict(frozen=True)

    sf_bottom_valve: LogicalValveState
    column_bottom_valve: LogicalValveState
    p2_contents: P2NominalContents


def build_p2_sf_to_column_operations(
    transfer_cycle_plan: TransferCyclePlan,
) -> tuple[PlannedOperation, ...]:
    if transfer_cycle_plan.pump_id is not PumpId.P2:
        raise P2SfToColumnOperationPlanningError(
            "P2_TRANSFER_SF_TO_COLUMN transfer cycle plan must use pump P2"
        )
    if transfer_cycle_plan.requested_volume_ml <= 0 or transfer_cycle_plan.cycle_count == 0:
        raise P2SfToColumnOperationPlanningError(
            "P2_TRANSFER_SF_TO_COLUMN requires at least one positive-volume transfer cycle"
        )

    operations: list[PlannedOperation] = [
        PrepareSfToColumnTransferOperation(
            operation_kind=OperationKind.PREPARE_SF_TO_COLUMN_TRANSFER,
            operation_number=1,
        )
    ]
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
                    route_id=SymbolicRouteId.SF_BOTTOM_TO_P2,
                    **cycle_fields,
                ),
                AspirateFromSfOperation(
                    operation_kind=OperationKind.ASPIRATE_FROM_SF,
                    operation_number=first_operation_number + 1,
                    pump_id=PumpId.P2,
                    volume_ml=cycle.volume_ml,
                    **cycle_fields,
                ),
                SelectRouteOperation(
                    operation_kind=OperationKind.SELECT_ROUTE,
                    operation_number=first_operation_number + 2,
                    route_id=SymbolicRouteId.P2_TO_COLUMN,
                    **cycle_fields,
                ),
                DispenseOperation(
                    operation_kind=OperationKind.DISPENSE,
                    operation_number=first_operation_number + 3,
                    pump_id=PumpId.P2,
                    volume_ml=cycle.volume_ml,
                    **cycle_fields,
                ),
            )
        )
    return tuple(operations)


class P2SfToColumnOperationPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    phase: RunPhase
    required_topology_id: TopologyId
    transfer_cycle_plan: TransferCyclePlan
    operations: tuple[PlannedOperation, ...]

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        if self.phase is not RunPhase.P2_TRANSFER_SF_TO_COLUMN:
            raise ValueError("phase must be P2_TRANSFER_SF_TO_COLUMN")
        if self.required_topology_id is not TopologyId.LABFORGE_V1_APPROVED_TARGET:
            raise ValueError("required topology must be LABFORGE_V1_APPROVED_TARGET")
        if self.transfer_cycle_plan.pump_id is not PumpId.P2:
            raise ValueError("transfer cycle plan must use pump P2")
        try:
            expected = build_p2_sf_to_column_operations(self.transfer_cycle_plan)
        except P2SfToColumnOperationPlanningError as error:
            raise ValueError(str(error)) from error
        if self.operations != expected:
            raise ValueError(
                "operations must exactly match the protected SF-to-Column transfer plan"
            )
        return self

    @property
    def operation_count(self) -> int:
        return len(self.operations)

    def logical_state_after(self, operation_number: int) -> SfToColumnLogicalState:
        """Return state inferred after one successfully completed scheduler operation."""
        if operation_number < 1 or operation_number > self.operation_count:
            raise ValueError("operation number is outside this plan")
        p2_contents = P2NominalContents.EMPTY
        for operation in self.operations[:operation_number]:
            if isinstance(operation, AspirateFromSfOperation):
                p2_contents = P2NominalContents.CYCLE_VOLUME
            elif isinstance(operation, DispenseOperation):
                p2_contents = P2NominalContents.EMPTY
        return SfToColumnLogicalState(
            sf_bottom_valve=LogicalValveState.CLOSED,
            column_bottom_valve=LogicalValveState.CLOSED,
            p2_contents=p2_contents,
        )


def plan_p2_sf_to_column_operations(
    fluid_plan: FluidPlan,
    calibrations: PumpCalibrationSet,
) -> P2SfToColumnOperationPlan:
    transfer_cycle_plan = plan_nominal_phase_transfer_cycles(
        RunPhase.P2_TRANSFER_SF_TO_COLUMN, fluid_plan, calibrations
    )
    operations = build_p2_sf_to_column_operations(transfer_cycle_plan)

    return P2SfToColumnOperationPlan(
        phase=RunPhase.P2_TRANSFER_SF_TO_COLUMN,
        required_topology_id=TopologyId.LABFORGE_V1_APPROVED_TARGET,
        transfer_cycle_plan=transfer_cycle_plan,
        operations=operations,
    )
