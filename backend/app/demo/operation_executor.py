from abc import ABC, abstractmethod
from collections.abc import Callable
from decimal import Decimal
from enum import StrEnum
from typing import TypeVar

from app.demo.hardware_contract import BottomValveState, HardwareContract
from app.demo.operation_models import (
    AspirateFromSfOperation,
    AspirateOperation,
    CollectColumnFractionOperation,
    DispenseOperation,
    MoveCarouselToNextFractionOperation,
    PlannedOperation,
    PrepareColumnFractionCollectionOperation,
    PrepareSfToColumnTransferOperation,
    SelectRouteOperation,
)


class CollectionTimerOutcome(StrEnum):
    COMPLETED = "COMPLETED"
    STOP_REQUESTED = "STOP_REQUESTED"


class CollectionTimer(ABC):
    @abstractmethod
    def wait(self, duration_seconds: Decimal) -> CollectionTimerOutcome: ...


class OperationExecutionOutcome(StrEnum):
    COMPLETED = "COMPLETED"
    COLLECTION_STOP_REQUESTED = "COLLECTION_STOP_REQUESTED"


class ProtectedOperationError(RuntimeError):
    """Both a primary action and its required safety follow-up failed."""

    def __init__(self, primary_error: Exception, followup_error: Exception) -> None:
        self.primary_error = primary_error
        self.followup_error = followup_error
        super().__init__("primary operation and required safety follow-up both failed")


_Result = TypeVar("_Result")


def _execute_with_required_followup(
    primary: Callable[[], _Result],
    followup: Callable[[], None],
) -> _Result:
    primary_error: Exception | None = None
    result: _Result | None = None
    try:
        result = primary()
    except Exception as error:
        primary_error = error

    try:
        followup()
    except Exception as followup_error:
        if primary_error is not None:
            raise ProtectedOperationError(primary_error, followup_error) from followup_error
        setattr(followup_error, "_labforge_required_followup_failure", True)
        raise

    if primary_error is not None:
        raise primary_error
    return result  # type: ignore[return-value]


class OperationExecutor:
    def __init__(
        self,
        hardware: HardwareContract,
        collection_timer: CollectionTimer,
    ) -> None:
        self._hardware = hardware
        self._collection_timer = collection_timer

    def execute(self, operation: PlannedOperation) -> OperationExecutionOutcome:
        if isinstance(operation, SelectRouteOperation):
            self._hardware.select_route(operation.route_id)
        elif isinstance(operation, AspirateOperation):
            self._hardware.aspirate(operation.pump_id, operation.volume_ml)
        elif isinstance(operation, DispenseOperation):
            self._hardware.dispense(operation.pump_id, operation.volume_ml)
        elif isinstance(operation, PrepareSfToColumnTransferOperation):
            _execute_with_required_followup(
                lambda: self._hardware.set_sf_bottom_valve(BottomValveState.CLOSED),
                lambda: self._hardware.set_column_bottom_valve(
                    BottomValveState.CLOSED
                ),
            )
        elif isinstance(operation, AspirateFromSfOperation):
            self._execute_aspirate_from_sf(operation)
        elif isinstance(operation, PrepareColumnFractionCollectionOperation):
            self._hardware.set_column_bottom_valve(BottomValveState.CLOSED)
        elif isinstance(operation, CollectColumnFractionOperation):
            timer_outcome = self._execute_column_collection(operation)
            if timer_outcome is CollectionTimerOutcome.STOP_REQUESTED:
                return OperationExecutionOutcome.COLLECTION_STOP_REQUESTED
        elif isinstance(operation, MoveCarouselToNextFractionOperation):
            self._hardware.move_carousel_to_next_fraction(
                operation.source_fraction_number,
                operation.destination_fraction_number,
            )
        else:
            raise TypeError(
                f"unsupported planned operation type: {type(operation).__name__}"
            )
        return OperationExecutionOutcome.COMPLETED

    def _execute_aspirate_from_sf(
        self,
        operation: AspirateFromSfOperation,
    ) -> None:
        def open_and_aspirate() -> None:
            self._hardware.set_sf_bottom_valve(BottomValveState.OPEN)
            self._hardware.aspirate(operation.pump_id, operation.volume_ml)

        _execute_with_required_followup(
            open_and_aspirate,
            lambda: self._hardware.set_sf_bottom_valve(BottomValveState.CLOSED),
        )

    def _execute_column_collection(
        self,
        operation: CollectColumnFractionOperation,
    ) -> CollectionTimerOutcome:
        def open_and_wait() -> CollectionTimerOutcome:
            self._hardware.set_column_bottom_valve(BottomValveState.OPEN)
            outcome = self._collection_timer.wait(
                operation.configured_duration_seconds
            )
            if outcome not in {
                CollectionTimerOutcome.COMPLETED,
                CollectionTimerOutcome.STOP_REQUESTED,
            }:
                raise ValueError(f"unsupported collection timer outcome: {outcome!r}")
            return outcome

        return _execute_with_required_followup(
            open_and_wait,
            lambda: self._hardware.set_column_bottom_valve(
                BottomValveState.CLOSED
            ),
        )
