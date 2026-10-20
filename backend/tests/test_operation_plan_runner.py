from collections.abc import Callable
from decimal import Decimal

import pytest

from app.demo.calibration_models import PumpId
from app.demo.operation_executor import (
    OperationExecutionOutcome,
    OperationExecutor,
    ProtectedOperationError,
)
from app.demo.operation_models import (
    AspirateFromSfOperation,
    CollectColumnFractionOperation,
    OperationKind,
    PlannedOperation,
    SelectRouteOperation,
    SymbolicRouteId,
)
from app.demo.operation_plan_runner import (
    OperationPlanExecutionError,
    OperationPlanRunner,
    PlanRunOutcome,
    PlanRunResult,
)


class RecordingExecutor(OperationExecutor):
    def __init__(
        self,
        *,
        outcomes: dict[int, OperationExecutionOutcome] | None = None,
        errors: dict[int, Exception] | None = None,
    ) -> None:
        self.calls: list[PlannedOperation] = []
        self.outcomes = outcomes or {}
        self.errors = errors or {}

    def execute(self, operation: PlannedOperation) -> OperationExecutionOutcome:
        self.calls.append(operation)
        error = self.errors.get(operation.operation_number)
        if error is not None:
            raise error
        return self.outcomes.get(
            operation.operation_number,
            OperationExecutionOutcome.COMPLETED,
        )


class RecordingStop:
    def __init__(self, *values: bool, error: Exception | None = None) -> None:
        self._values = iter(values)
        self.error = error
        self.call_count = 0

    def __call__(self) -> bool:
        self.call_count += 1
        if self.error is not None:
            raise self.error
        return next(self._values, False)


def route_operation(
    operation_number: int,
    route_id: SymbolicRouteId = SymbolicRouteId.S_TO_P1,
) -> SelectRouteOperation:
    return SelectRouteOperation(
        operation_kind=OperationKind.SELECT_ROUTE,
        operation_number=operation_number,
        cycle_number=1,
        cycle_count=1,
        route_id=route_id,
    )


def protected_operation(operation_number: int) -> AspirateFromSfOperation:
    return AspirateFromSfOperation(
        operation_kind=OperationKind.ASPIRATE_FROM_SF,
        operation_number=operation_number,
        cycle_number=1,
        cycle_count=1,
        pump_id=PumpId.P2,
        volume_ml=Decimal("1.25"),
    )


def collection_operation(operation_number: int) -> CollectColumnFractionOperation:
    return CollectColumnFractionOperation(
        operation_kind=OperationKind.COLLECT_COLUMN_FRACTION,
        operation_number=operation_number,
        fraction_number=1,
        fraction_count=1,
        configured_duration_seconds=Decimal("12.5"),
        stop_interrupts_collection_timer=True,
        required_close_follows_stop=True,
        required_close_failure_blocks_further_operations=True,
    )


def runner(
    executor: RecordingExecutor,
    stop_requested: Callable[[], bool] = lambda: False,
) -> OperationPlanRunner:
    return OperationPlanRunner(executor, stop_requested)


def test_empty_tuple_completes_without_stop_check() -> None:
    executor = RecordingExecutor()
    stop = RecordingStop(True)

    result = runner(executor, stop).run(())

    assert result == PlanRunResult(
        outcome=PlanRunOutcome.COMPLETED,
        completed_operation_count=0,
        total_operation_count=0,
        last_completed_operation_number=None,
        stop_operation_number=None,
    )
    assert stop.call_count == 0
    assert executor.calls == []


def test_operations_execute_exactly_once_in_tuple_order_with_complete_progress() -> None:
    operations = (
        route_operation(4, SymbolicRouteId.B1_TO_P1),
        route_operation(5, SymbolicRouteId.P1_TO_REACTOR),
        route_operation(6, SymbolicRouteId.REACTOR_TO_P2),
    )
    executor = RecordingExecutor()
    stop = RecordingStop(False, False, False, True)

    result = runner(executor, stop).run(operations)

    assert executor.calls == list(operations)
    assert stop.call_count == 3
    assert result == PlanRunResult(
        outcome=PlanRunOutcome.COMPLETED,
        completed_operation_count=3,
        total_operation_count=3,
        last_completed_operation_number=6,
        stop_operation_number=None,
    )


def test_stop_before_first_operation_executes_nothing() -> None:
    operations = (route_operation(7), route_operation(8))
    executor = RecordingExecutor()

    result = runner(executor, RecordingStop(True)).run(operations)

    assert result == PlanRunResult(
        outcome=PlanRunOutcome.STOP_REQUESTED,
        completed_operation_count=0,
        total_operation_count=2,
        last_completed_operation_number=None,
        stop_operation_number=7,
    )
    assert executor.calls == []


def test_stop_between_operations_preserves_completed_progress() -> None:
    operations = (route_operation(10), route_operation(11), route_operation(12))
    executor = RecordingExecutor()

    result = runner(executor, RecordingStop(False, True)).run(operations)

    assert executor.calls == [operations[0]]
    assert result == PlanRunResult(
        outcome=PlanRunOutcome.STOP_REQUESTED,
        completed_operation_count=1,
        total_operation_count=3,
        last_completed_operation_number=10,
        stop_operation_number=11,
    )


def test_collection_stop_does_not_complete_operation_or_run_later_operations() -> None:
    operations = (
        route_operation(20),
        collection_operation(21),
        route_operation(22),
    )
    executor = RecordingExecutor(
        outcomes={
            21: OperationExecutionOutcome.COLLECTION_STOP_REQUESTED,
        }
    )

    result = runner(executor).run(operations)

    assert executor.calls == list(operations[:2])
    assert result == PlanRunResult(
        outcome=PlanRunOutcome.COLLECTION_STOP_REQUESTED,
        completed_operation_count=1,
        total_operation_count=3,
        last_completed_operation_number=20,
        stop_operation_number=21,
    )


@pytest.mark.parametrize(
    "original_error",
    [
        RuntimeError("hardware failed"),
        ProtectedOperationError(
            RuntimeError("primary failed"),
            RuntimeError("cleanup failed"),
        ),
        TypeError("unsupported operation"),
    ],
)
def test_first_executor_error_stops_and_preserves_identity_and_context(
    original_error: Exception,
) -> None:
    operations = (route_operation(30), route_operation(31), route_operation(32))
    executor = RecordingExecutor(errors={31: original_error})

    with pytest.raises(OperationPlanExecutionError) as caught:
        runner(executor).run(operations)

    assert executor.calls == list(operations[:2])
    assert caught.value.original_error is original_error
    assert caught.value.__cause__ is original_error
    assert caught.value.failed_operation_number == 31
    assert caught.value.completed_operation_count == 1


def test_stop_callback_error_propagates_unchanged() -> None:
    stop_error = RuntimeError("Stop source failed")

    with pytest.raises(RuntimeError) as caught:
        runner(RecordingExecutor(), RecordingStop(error=stop_error)).run(
            (route_operation(40),)
        )

    assert caught.value is stop_error


def test_protected_operation_is_one_checkpoint_and_one_executor_call() -> None:
    operation = protected_operation(50)
    executor = RecordingExecutor()
    stop = RecordingStop(False)

    result = runner(executor, stop).run((operation,))

    assert stop.call_count == 1
    assert executor.calls == [operation]
    assert result.completed_operation_count == 1
    assert result.last_completed_operation_number == 50
