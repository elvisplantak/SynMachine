from __future__ import annotations

from decimal import Decimal
from enum import StrEnum
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from app.demo.machine_models import MachineState
from app.demo.models import DemoExecutionSettings
from app.demo.operation_models import (
    CollectColumnFractionOperation,
    MoveCarouselToNextFractionOperation,
    OperationKind,
    PlannedOperation,
    PrepareColumnFractionCollectionOperation,
    TopologyId,
)
from app.demo.phases import RunPhase
from app.demo.run_models import RunStatus

class ColumnFractionCollectionConfiguration(BaseModel):
    """Immutable Service contract for one colored-liquid collection phase."""

    model_config = ConfigDict(frozen=True)

    fraction_count: StrictInt = Field(ge=1)
    fraction_duration_seconds: Decimal
    carousel_ready_confirmed: StrictBool
    column_bottom_valve_referenced_confirmed: StrictBool

    @field_validator("fraction_duration_seconds")
    @classmethod
    def validate_duration(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("fraction duration must be finite and greater than zero")
        return value

    @model_validator(mode="after")
    def validate_readiness(self) -> Self:
        if not self.carousel_ready_confirmed:
            raise ValueError("carousel readiness must be confirmed")
        if not self.column_bottom_valve_referenced_confirmed:
            raise ValueError("COLUMN_BOTTOM_VALVE must be referenced before collection")
        return self

    @classmethod
    def from_execution_settings(
        cls,
        settings: DemoExecutionSettings,
        *,
        carousel_ready_confirmed: bool,
        column_bottom_valve_referenced_confirmed: bool,
    ) -> ColumnFractionCollectionConfiguration:
        return cls(
            fraction_count=settings.fraction_count,
            fraction_duration_seconds=settings.fraction_duration_seconds,
            carousel_ready_confirmed=carousel_ready_confirmed,
            column_bottom_valve_referenced_confirmed=(
                column_bottom_valve_referenced_confirmed
            ),
        )


class LogicalColumnValveState(StrEnum):
    CLOSED = "CLOSED"


class FractionCompletion(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    PARTIAL = "PARTIAL"
    COMPLETE = "COMPLETE"


class FractionCollectionStopPoint(StrEnum):
    BEFORE_COLLECTION = "BEFORE_COLLECTION"
    DURING_COLLECTION = "DURING_COLLECTION"
    AFTER_COLLECTION_CLOSE_BEFORE_MOVE = "AFTER_COLLECTION_CLOSE_BEFORE_MOVE"
    DURING_CAROUSEL_MOVE = "DURING_CAROUSEL_MOVE"


class ColumnFractionCollectionLogicalState(BaseModel):
    """Logical demo state inferred from successful commands, without sensors."""

    model_config = ConfigDict(frozen=True)

    column_bottom_valve: LogicalColumnValveState
    carousel_fraction_number: StrictInt | None = Field(default=None, ge=1)
    carousel_position_trusted: StrictBool
    last_fraction_number: StrictInt | None = Field(default=None, ge=1)
    last_fraction_completion: FractionCompletion
    collection_timer_interrupted: bool
    pending_carousel_movement: bool
    further_operations_blocked: bool
    normal_abort_resulting_run_status: RunStatus | None
    normal_abort_resulting_machine_state: MachineState | None
    failure_requires_existing_fault_mechanism: bool

    @model_validator(mode="after")
    def validate_carousel_position(self) -> Self:
        if self.carousel_position_trusted != (self.carousel_fraction_number is not None):
            raise ValueError("trusted carousel position requires a logical fraction number")
        return self


def build_column_fraction_collection_operations(
    configuration: ColumnFractionCollectionConfiguration,
) -> tuple[PlannedOperation, ...]:
    operations: list[PlannedOperation] = [
        PrepareColumnFractionCollectionOperation(
            operation_kind=OperationKind.PREPARE_COLUMN_FRACTION_COLLECTION,
            operation_number=1,
            column_bottom_valve_referenced=True,
        )
    ]
    for fraction_number in range(1, configuration.fraction_count + 1):
        operations.append(
            CollectColumnFractionOperation(
                operation_kind=OperationKind.COLLECT_COLUMN_FRACTION,
                operation_number=len(operations) + 1,
                fraction_number=fraction_number,
                fraction_count=configuration.fraction_count,
                configured_duration_seconds=(
                    configuration.fraction_duration_seconds
                ),
                stop_interrupts_collection_timer=True,
                required_close_follows_stop=True,
                required_close_failure_blocks_further_operations=True,
            )
        )
        if fraction_number < configuration.fraction_count:
            operations.append(
                MoveCarouselToNextFractionOperation(
                    operation_kind=(
                        OperationKind.MOVE_CAROUSEL_TO_NEXT_FRACTION
                    ),
                    operation_number=len(operations) + 1,
                    fraction_count=configuration.fraction_count,
                    source_fraction_number=fraction_number,
                    destination_fraction_number=fraction_number + 1,
                    requires_successful_collection=True,
                    requires_column_bottom_valve_closed=True,
                    movement_failure_leaves_column_bottom_valve_closed=True,
                    movement_failure_marks_carousel_position_untrusted=True,
                    movement_failure_blocks_next_fraction=True,
                    movement_failure_uses_existing_fault_mechanism=True,
                )
            )
    return tuple(operations)


class ColumnFractionCollectionOperationPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    phase: RunPhase
    required_topology_id: TopologyId
    configuration: ColumnFractionCollectionConfiguration
    operations: tuple[PlannedOperation, ...]

    @model_validator(mode="after")
    def validate_plan(self) -> Self:
        if self.phase is not RunPhase.COLUMN_FRACTION_COLLECTION:
            raise ValueError("phase must be COLUMN_FRACTION_COLLECTION")
        if self.required_topology_id is not TopologyId.LABFORGE_V1_APPROVED_TARGET:
            raise ValueError("required topology must be LABFORGE_V1_APPROVED_TARGET")
        expected = build_column_fraction_collection_operations(self.configuration)
        if self.operations != expected:
            raise ValueError(
                "operations must exactly match the Column fraction collection configuration"
            )
        return self

    @property
    def operation_count(self) -> int:
        return len(self.operations)

    def logical_state_after(
        self, operation_number: int
    ) -> ColumnFractionCollectionLogicalState:
        if operation_number < 1 or operation_number > self.operation_count:
            raise ValueError("operation number is outside this plan")

        carousel_fraction_number = 1
        last_fraction_number: int | None = None
        last_fraction_completion = FractionCompletion.NOT_STARTED
        pending_carousel_movement = False
        for operation in self.operations[:operation_number]:
            if isinstance(operation, CollectColumnFractionOperation):
                last_fraction_number = operation.fraction_number
                last_fraction_completion = FractionCompletion.COMPLETE
                pending_carousel_movement = (
                    operation.fraction_number < operation.fraction_count
                )
            elif isinstance(operation, MoveCarouselToNextFractionOperation):
                carousel_fraction_number = operation.destination_fraction_number
                pending_carousel_movement = False

        return ColumnFractionCollectionLogicalState(
            column_bottom_valve=LogicalColumnValveState.CLOSED,
            carousel_fraction_number=carousel_fraction_number,
            carousel_position_trusted=True,
            last_fraction_number=last_fraction_number,
            last_fraction_completion=last_fraction_completion,
            collection_timer_interrupted=False,
            pending_carousel_movement=pending_carousel_movement,
            further_operations_blocked=False,
            normal_abort_resulting_run_status=None,
            normal_abort_resulting_machine_state=None,
            failure_requires_existing_fault_mechanism=False,
        )

    def logical_state_after_stop(
        self,
        fraction_number: int,
        stop_point: FractionCollectionStopPoint,
    ) -> ColumnFractionCollectionLogicalState:
        if not 1 <= fraction_number <= self.configuration.fraction_count:
            raise ValueError("fraction number is outside this plan")

        carousel_fraction_number = fraction_number
        last_fraction_number: int | None = fraction_number
        last_fraction_completion = FractionCompletion.NOT_STARTED
        timer_interrupted = False
        if stop_point is FractionCollectionStopPoint.DURING_COLLECTION:
            last_fraction_completion = FractionCompletion.PARTIAL
            timer_interrupted = True
        elif stop_point in {
            FractionCollectionStopPoint.AFTER_COLLECTION_CLOSE_BEFORE_MOVE,
            FractionCollectionStopPoint.DURING_CAROUSEL_MOVE,
        }:
            last_fraction_completion = FractionCompletion.COMPLETE
        if stop_point is FractionCollectionStopPoint.DURING_CAROUSEL_MOVE:
            if fraction_number >= self.configuration.fraction_count:
                raise ValueError("there is no carousel movement after the final fraction")
            carousel_fraction_number += 1
        if stop_point is FractionCollectionStopPoint.BEFORE_COLLECTION:
            if fraction_number == 1:
                last_fraction_number = None
            else:
                last_fraction_number = fraction_number - 1
                last_fraction_completion = FractionCompletion.COMPLETE
        if (
            stop_point
            is FractionCollectionStopPoint.AFTER_COLLECTION_CLOSE_BEFORE_MOVE
            and fraction_number >= self.configuration.fraction_count
        ):
            raise ValueError("there is no carousel movement after the final fraction")

        return ColumnFractionCollectionLogicalState(
            column_bottom_valve=LogicalColumnValveState.CLOSED,
            carousel_fraction_number=carousel_fraction_number,
            carousel_position_trusted=True,
            last_fraction_number=last_fraction_number,
            last_fraction_completion=last_fraction_completion,
            collection_timer_interrupted=timer_interrupted,
            pending_carousel_movement=False,
            further_operations_blocked=True,
            normal_abort_resulting_run_status=RunStatus.ABORTED,
            normal_abort_resulting_machine_state=MachineState.FLUSH_REQUIRED,
            failure_requires_existing_fault_mechanism=False,
        )

    def logical_state_after_carousel_move_failure(
        self, source_fraction_number: int
    ) -> ColumnFractionCollectionLogicalState:
        if not 1 <= source_fraction_number < self.configuration.fraction_count:
            raise ValueError("there is no carousel movement for this fraction")
        return ColumnFractionCollectionLogicalState(
            column_bottom_valve=LogicalColumnValveState.CLOSED,
            carousel_fraction_number=None,
            carousel_position_trusted=False,
            last_fraction_number=source_fraction_number,
            last_fraction_completion=FractionCompletion.COMPLETE,
            collection_timer_interrupted=False,
            pending_carousel_movement=False,
            further_operations_blocked=True,
            normal_abort_resulting_run_status=None,
            normal_abort_resulting_machine_state=None,
            failure_requires_existing_fault_mechanism=True,
        )


def plan_column_fraction_collection_operations(
    configuration: ColumnFractionCollectionConfiguration,
) -> ColumnFractionCollectionOperationPlan:
    return ColumnFractionCollectionOperationPlan(
        phase=RunPhase.COLUMN_FRACTION_COLLECTION,
        required_topology_id=TopologyId.LABFORGE_V1_APPROVED_TARGET,
        configuration=configuration,
        operations=build_column_fraction_collection_operations(configuration),
    )


class ColumnRecoveryAction(StrEnum):
    RESTORE_COLUMN_BOTTOM_VALVE_CLOSED = "RESTORE_COLUMN_BOTTOM_VALVE_CLOSED"
    CONTINUE_EXISTING_MACHINE_RECOVERY = "CONTINUE_EXISTING_MACHINE_RECOVERY"


class ColumnPowerLossRecoveryRequirements(BaseModel):
    """Column additions to the existing RECOVERING to FLUSH_REQUIRED lifecycle.

    A future System Flush remains sequential: the rest of the machine flushes
    first, then the Column uses protected open/collect/close operations and moves
    only after close. Its operator-prepared carousel tubes are classified as
    Flush waste; this does not create a Column-to-Waste route.
    """

    model_config = ConfigDict(frozen=True)

    ordered_actions: tuple[ColumnRecoveryAction, ...] = (
        ColumnRecoveryAction.RESTORE_COLUMN_BOTTOM_VALVE_CLOSED,
        ColumnRecoveryAction.CONTINUE_EXISTING_MACHINE_RECOVERY,
    )
    reference_column_bottom_valve_as_needed: Literal[True] = True
    old_fraction_run_must_not_resume: Literal[True] = True
    active_fraction_untrusted: Literal[True] = True
    previous_column_bottom_valve_position_trusted: Literal[False] = False
    recovery_target_column_bottom_valve_state: Literal[
        LogicalColumnValveState.CLOSED
    ] = LogicalColumnValveState.CLOSED
    successful_recovery_result_column_bottom_valve_state: Literal[
        LogicalColumnValveState.CLOSED
    ] = LogicalColumnValveState.CLOSED
    carousel_position_trusted: Literal[False] = False
    automatic_carousel_movement_allowed: Literal[False] = False
    manual_carousel_alignment_required: Literal[True] = True
    service_confirmation_required_before_future_run_or_flush: Literal[True] = True
    resulting_machine_state: Literal[MachineState.FLUSH_REQUIRED] = (
        MachineState.FLUSH_REQUIRED
    )

    @model_validator(mode="after")
    def validate_order(self) -> Self:
        expected = (
            ColumnRecoveryAction.RESTORE_COLUMN_BOTTOM_VALVE_CLOSED,
            ColumnRecoveryAction.CONTINUE_EXISTING_MACHINE_RECOVERY,
        )
        if self.ordered_actions != expected:
            raise ValueError("Column valve close must be the first recovery action")
        return self


def column_power_loss_recovery_requirements() -> ColumnPowerLossRecoveryRequirements:
    return ColumnPowerLossRecoveryRequirements()
