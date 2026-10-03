"""Explicit colored-demo recovery/flush policy; no physical authorization."""

from decimal import Decimal
from datetime import datetime
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, StrictInt, model_validator

from app.demo.calibration_models import PumpCalibrationSet, PumpId
from app.demo.operation_models import (
    AspirateFromSfOperation,
    AspirateOperation,
    CollectColumnFractionOperation,
    DispenseOperation,
    MoveCarouselToNextFractionOperation,
    OperationKind,
    PlannedOperation,
    SelectRouteOperation,
    SymbolicRouteId,
)


class MaintenanceKind(StrEnum):
    RECOVERY = "RECOVERY"
    FLUSH = "FLUSH"


class MaintenanceIntent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    execution_id: str
    owner_id: str
    run_id: str
    kind: MaintenanceKind
    started_at: datetime
    operator: str
    evidence_note: str

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if any(
            not v.strip()
            for v in (
                self.execution_id,
                self.owner_id,
                self.run_id,
                self.operator,
                self.evidence_note,
            )
        ):
            raise ValueError("maintenance identities must be explicit")
        if self.started_at.tzinfo is None or self.started_at.utcoffset() is None:
            raise ValueError("maintenance timestamp must be timezone-aware")
        return self


class RecoveryOperation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    operation_kind: Literal[OperationKind.RECOVER_REFERENCES]
    operation_number: Literal[1]
    valve_home_order: tuple[str, ...]
    carousel_position: StrictInt

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        if len(self.valve_home_order) != 8 or set(self.valve_home_order) != {
            f"V{i}" for i in range(1, 9)
        }:
            raise ValueError("explicit HOME order must contain each V1-V8 exactly once")
        if not 1 <= self.carousel_position <= 40:
            raise ValueError("explicit manual carousel alignment must be 1..40")
        return self


class FlushPolicy(BaseModel):
    """All volumes, drain time and tube margin are supplied, never defaults."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    liquid_volume_ml: Decimal
    air_volume_ml: Decimal
    column_drain_seconds: Decimal
    safe_tube_volume_ml: Decimal
    rinse_start_position: StrictInt

    @model_validator(mode="after")
    def validate_values(self) -> Self:
        if not 1 <= self.rinse_start_position <= 40:
            raise ValueError("rinse tube alignment must be explicit and in 1..40")
        if any(
            not v.is_finite() or v <= 0
            for v in (
                self.liquid_volume_ml,
                self.air_volume_ml,
                self.column_drain_seconds,
                self.safe_tube_volume_ml,
            )
        ):
            raise ValueError("flush values must be explicit positive finite values")
        if (
            self.safe_tube_volume_ml >= 10
            or max(self.liquid_volume_ml, self.air_volume_ml) > self.safe_tube_volume_ml
        ):
            raise ValueError(
                "flush strokes must fit an explicit margin below nominal 10 ml tube size"
            )
        return self


class FlushPreparationOperation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    operation_kind: Literal[OperationKind.PREPARE_REQUIRED_FLUSH]
    operation_number: Literal[1]
    carousel_position: StrictInt


class MaintenancePlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    kind: MaintenanceKind
    calibrations: PumpCalibrationSet
    recovery: RecoveryOperation | None = None
    flush: FlushPolicy | None = None

    @model_validator(mode="after")
    def validate_kind(self) -> Self:
        if self.kind is MaintenanceKind.RECOVERY:
            if self.recovery is None or self.flush is not None:
                raise ValueError("recovery needs explicit references and no flush policy")
        elif self.flush is None or self.recovery is not None:
            raise ValueError("flush needs explicit policy and no recovery operations")
        return self

    @property
    def operations(
        self,
    ) -> tuple[PlannedOperation | RecoveryOperation | FlushPreparationOperation, ...]:
        if self.recovery is not None:
            return (self.recovery,)
        policy = self.flush
        result = [
            FlushPreparationOperation(
                operation_kind=OperationKind.PREPARE_REQUIRED_FLUSH,
                operation_number=1,
                carousel_position=policy.rinse_start_position,
            )
        ]

        def add(cls, kind, **values):
            result.append(cls(operation_kind=kind, operation_number=len(result) + 1, **values))

        def route(value):
            add(
                SelectRouteOperation,
                OperationKind.SELECT_ROUTE,
                route_id=value,
                cycle_number=1,
                cycle_count=1,
            )

        def transfer(pump, source, destination, volume, *, sf=False):
            route(source)
            add(
                AspirateFromSfOperation if sf else AspirateOperation,
                OperationKind.ASPIRATE_FROM_SF if sf else OperationKind.ASPIRATE,
                pump_id=pump,
                volume_ml=volume,
                cycle_number=1,
                cycle_count=1,
            )
            route(destination)
            add(
                DispenseOperation,
                OperationKind.DISPENSE,
                pump_id=pump,
                volume_ml=volume,
                cycle_number=1,
                cycle_count=1,
            )

        # Two liquid cycles, then air through the same SF/Waste and Column paths.
        for number, volume in enumerate(
            (policy.liquid_volume_ml, policy.liquid_volume_ml, policy.air_volume_ml), 1
        ):
            source = SymbolicRouteId.S_TO_P1 if number < 3 else SymbolicRouteId.P1_TO_WASTE
            for column in (False, True):
                transfer(PumpId.P1, source, SymbolicRouteId.P1_TO_REACTOR, volume)
                transfer(
                    PumpId.P2,
                    SymbolicRouteId.REACTOR_TO_P2,
                    SymbolicRouteId.P2_TO_COLUMN if column else SymbolicRouteId.P2_TO_SF_TOP,
                    volume,
                )
                if not column:
                    transfer(
                        PumpId.P2,
                        SymbolicRouteId.SF_BOTTOM_TO_P2,
                        SymbolicRouteId.P2_TO_WASTE,
                        volume,
                        sf=True,
                    )
                else:
                    add(
                        CollectColumnFractionOperation,
                        OperationKind.COLLECT_COLUMN_FRACTION,
                        fraction_number=number,
                        fraction_count=3,
                        configured_duration_seconds=policy.column_drain_seconds,
                        stop_interrupts_collection_timer=True,
                        required_close_follows_stop=True,
                        required_close_failure_blocks_further_operations=True,
                    )
                    if number < 3:
                        add(
                            MoveCarouselToNextFractionOperation,
                            OperationKind.MOVE_CAROUSEL_TO_NEXT_FRACTION,
                            fraction_count=3,
                            source_fraction_number=number,
                            destination_fraction_number=number + 1,
                            requires_successful_collection=True,
                            requires_column_bottom_valve_closed=True,
                            movement_failure_leaves_column_bottom_valve_closed=True,
                            movement_failure_marks_carousel_position_untrusted=True,
                            movement_failure_blocks_next_fraction=True,
                            movement_failure_uses_existing_fault_mechanism=True,
                        )
        return tuple(result)
