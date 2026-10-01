"""Passive delay/hold plans; no reactor heater or mixer command is implied."""

from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from app.demo.operation_models import OperationKind, PausableWaitOperation
from app.demo.phases import RunPhase
from app.demo.run_models import DemoRun


class PausableWaitPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    phase: Literal[RunPhase.DELAY_BETWEEN_ADDITIONS, RunPhase.REACTION_HOLD]
    duration_seconds: Decimal
    operations: tuple[PausableWaitOperation, ...]

    @model_validator(mode="after")
    def validate_operations(self) -> Self:
        expected = PausableWaitOperation(
            operation_kind=OperationKind.PAUSABLE_RUN_WAIT,
            operation_number=1,
            duration_seconds=self.duration_seconds,
        )
        if self.operations != (expected,):
            raise ValueError("wait operations differ from configured duration")
        return self


def plan_pausable_wait(run: DemoRun) -> PausableWaitPlan:
    if run.phase is RunPhase.DELAY_BETWEEN_ADDITIONS:
        duration = run.configuration.delay_between_additions_seconds
    elif run.phase is RunPhase.REACTION_HOLD:
        duration = run.configuration.reaction_duration_seconds
    else:
        raise ValueError("not a pausable wait phase")
    return PausableWaitPlan(
        phase=run.phase,
        duration_seconds=duration,
        operations=(
            PausableWaitOperation(
                operation_kind=OperationKind.PAUSABLE_RUN_WAIT,
                operation_number=1,
                duration_seconds=duration,
            ),
        ),
    )
