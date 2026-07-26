from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from app.demo.operation_executor import (
    OperationExecutionOutcome,
    OperationExecutor,
)
from app.demo.operation_models import PlannedOperation


class PlanRunOutcome(StrEnum):
    COMPLETED = "COMPLETED"
    STOP_REQUESTED = "STOP_REQUESTED"
    COLLECTION_STOP_REQUESTED = "COLLECTION_STOP_REQUESTED"


@dataclass(frozen=True)
class PlanRunResult:
    outcome: PlanRunOutcome
    completed_operation_count: int
    total_operation_count: int
    last_completed_operation_number: int | None
    stop_operation_number: int | None


class OperationPlanExecutionError(RuntimeError):
    def __init__(
        self,
        *,
        original_error: Exception,
        failed_operation_number: int,
        completed_operation_count: int,
    ) -> None:
        self.original_error = original_error
        self.failed_operation_number = failed_operation_number
        self.completed_operation_count = completed_operation_count
        super().__init__(
            f"operation {failed_operation_number} failed after "
            f"{completed_operation_count} completed operations"
        )


class OperationPlanRunner:
    def __init__(
        self,
        executor: OperationExecutor,
        stop_requested: Callable[[], bool],
    ) -> None:
        self._executor = executor
        self._stop_requested = stop_requested

    def run(
        self,
        operations: tuple[PlannedOperation, ...],
    ) -> PlanRunResult:
        total_operation_count = len(operations)
        completed_operation_count = 0
        last_completed_operation_number: int | None = None

        for operation in operations:
            if self._stop_requested():
                return PlanRunResult(
                    outcome=PlanRunOutcome.STOP_REQUESTED,
                    completed_operation_count=completed_operation_count,
                    total_operation_count=total_operation_count,
                    last_completed_operation_number=(
                        last_completed_operation_number
                    ),
                    stop_operation_number=operation.operation_number,
                )

            try:
                execution_outcome = self._executor.execute(operation)
            except Exception as original_error:
                raise OperationPlanExecutionError(
                    original_error=original_error,
                    failed_operation_number=operation.operation_number,
                    completed_operation_count=completed_operation_count,
                ) from original_error

            if (
                execution_outcome
                is OperationExecutionOutcome.COLLECTION_STOP_REQUESTED
            ):
                return PlanRunResult(
                    outcome=PlanRunOutcome.COLLECTION_STOP_REQUESTED,
                    completed_operation_count=completed_operation_count,
                    total_operation_count=total_operation_count,
                    last_completed_operation_number=(
                        last_completed_operation_number
                    ),
                    stop_operation_number=operation.operation_number,
                )
            if execution_outcome is not OperationExecutionOutcome.COMPLETED:
                raise ValueError(
                    f"unsupported operation execution outcome: {execution_outcome!r}"
                )

            completed_operation_count += 1
            last_completed_operation_number = operation.operation_number

        return PlanRunResult(
            outcome=PlanRunOutcome.COMPLETED,
            completed_operation_count=completed_operation_count,
            total_operation_count=total_operation_count,
            last_completed_operation_number=last_completed_operation_number,
            stop_operation_number=None,
        )
