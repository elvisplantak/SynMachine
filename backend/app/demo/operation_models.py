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

from app.demo.calibration_models import PumpId
from app.demo.transfer_cycle_planner import TransferCyclePlan


class TopologyId(StrEnum):
    LABFORGE_V1_APPROVED_TARGET = "LABFORGE_V1_APPROVED_TARGET"


class SymbolicRouteId(StrEnum):
    S_TO_P1 = "S_TO_P1"
    B1_TO_P1 = "B1_TO_P1"
    B2_TO_P1 = "B2_TO_P1"
    P1_TO_REACTOR = "P1_TO_REACTOR"
    REACTOR_TO_P2 = "REACTOR_TO_P2"
    P2_TO_SF_TOP = "P2_TO_SF_TOP"
    SF_BOTTOM_TO_P2 = "SF_BOTTOM_TO_P2"
    P2_TO_COLUMN = "P2_TO_COLUMN"


class OperationKind(StrEnum):
    SELECT_ROUTE = "SELECT_ROUTE"
    ASPIRATE = "ASPIRATE"
    DISPENSE = "DISPENSE"
    PREPARE_SF_TO_COLUMN_TRANSFER = "PREPARE_SF_TO_COLUMN_TRANSFER"
    ASPIRATE_FROM_SF = "ASPIRATE_FROM_SF"


class PrepareSfToColumnAction(StrEnum):
    CLOSE_SF_BOTTOM_VALVE = "SET SF_BOTTOM_VALVE CLOSED"
    CLOSE_COLUMN_BOTTOM_VALVE = "SET COLUMN_BOTTOM_VALVE CLOSED"


class AspirateFromSfAction(StrEnum):
    OPEN_SF_BOTTOM_VALVE = "OPEN SF_BOTTOM_VALVE"
    ASPIRATE_P2 = "ASPIRATE P2"
    CLOSE_SF_BOTTOM_VALVE = "CLOSE SF_BOTTOM_VALVE"


class PrepareSfToColumnTransferOperation(BaseModel):
    """One protected scheduler operation; successful commands imply CLOSED.

    Valve state is inferred from successful command execution, not independently
    sensor-confirmed. This is accepted only for the low-risk colored-liquid demo.
    """

    model_config = ConfigDict(frozen=True)

    operation_kind: Literal[OperationKind.PREPARE_SF_TO_COLUMN_TRANSFER]
    operation_number: Literal[1]
    required_action_sequence: tuple[PrepareSfToColumnAction, ...] = (
        PrepareSfToColumnAction.CLOSE_SF_BOTTOM_VALVE,
        PrepareSfToColumnAction.CLOSE_COLUMN_BOTTOM_VALVE,
    )

    @model_validator(mode="after")
    def validate_action_sequence(self) -> Self:
        expected = (
            PrepareSfToColumnAction.CLOSE_SF_BOTTOM_VALVE,
            PrepareSfToColumnAction.CLOSE_COLUMN_BOTTOM_VALVE,
        )
        if self.required_action_sequence != expected:
            raise ValueError(
                "protected preparation actions must exactly match SF close then Column close"
            )
        return self


class AspirateFromSfOperation(BaseModel):
    """Atomic open/aspirate/required-close scheduler operation.

    A failed required close fails this operation, and further plan execution must
    stop; symbolic success does not prove physical valve movement.
    """

    model_config = ConfigDict(frozen=True)

    operation_kind: Literal[OperationKind.ASPIRATE_FROM_SF]
    operation_number: StrictInt = Field(ge=1)
    cycle_number: StrictInt = Field(ge=1)
    cycle_count: StrictInt = Field(ge=1)
    pump_id: Literal[PumpId.P2]
    volume_ml: Decimal
    required_action_sequence: tuple[AspirateFromSfAction, ...] = (
        AspirateFromSfAction.OPEN_SF_BOTTOM_VALVE,
        AspirateFromSfAction.ASPIRATE_P2,
        AspirateFromSfAction.CLOSE_SF_BOTTOM_VALVE,
    )

    @field_validator("volume_ml")
    @classmethod
    def validate_volume(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("operation volume must be finite and greater than zero")
        return value

    @model_validator(mode="after")
    def validate_semantics(self) -> Self:
        if self.cycle_number > self.cycle_count:
            raise ValueError("cycle number must not exceed cycle count")
        expected = (
            AspirateFromSfAction.OPEN_SF_BOTTOM_VALVE,
            AspirateFromSfAction.ASPIRATE_P2,
            AspirateFromSfAction.CLOSE_SF_BOTTOM_VALVE,
        )
        if self.required_action_sequence != expected:
            raise ValueError(
                "protected aspiration actions must exactly match open, aspirate, close"
            )
        return self


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
    SelectRouteOperation
    | AspirateOperation
    | DispenseOperation
    | PrepareSfToColumnTransferOperation
    | AspirateFromSfOperation,
    Field(discriminator="operation_kind"),
]


def build_syringe_transfer_operations(
    transfer_cycle_plan: TransferCyclePlan,
    *,
    aspiration_route_id: SymbolicRouteId,
    dispense_route_id: SymbolicRouteId,
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
                    route_id=aspiration_route_id,
                    **cycle_fields,
                ),
                AspirateOperation(
                    operation_kind=OperationKind.ASPIRATE,
                    operation_number=first_operation_number + 1,
                    pump_id=transfer_cycle_plan.pump_id,
                    volume_ml=cycle.volume_ml,
                    **cycle_fields,
                ),
                SelectRouteOperation(
                    operation_kind=OperationKind.SELECT_ROUTE,
                    operation_number=first_operation_number + 2,
                    route_id=dispense_route_id,
                    **cycle_fields,
                ),
                DispenseOperation(
                    operation_kind=OperationKind.DISPENSE,
                    operation_number=first_operation_number + 3,
                    pump_id=transfer_cycle_plan.pump_id,
                    volume_ml=cycle.volume_ml,
                    **cycle_fields,
                ),
            )
        )
    return tuple(operations)
