"""Offline timed SF plans. Mixer output uses only the commissioned fixed profile."""

from decimal import Decimal
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from app.demo.operation_models import OperationKind, PlannedOperation, TimedSfOperation
from app.demo.phases import RunPhase
from app.demo.run_models import DemoRun


class TimedSfOperationPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Literal[RunPhase.SF_MIXING, RunPhase.SF_SETTLING]
    duration_seconds: Decimal
    operations: tuple[PlannedOperation, ...]

    @model_validator(mode="after")
    def validate_operations(self) -> Self:
        kind = (
            OperationKind.TIMED_SF_MIXING
            if self.phase is RunPhase.SF_MIXING
            else OperationKind.SF_SETTLING_WAIT
        )
        expected = TimedSfOperation(
            operation_kind=kind, operation_number=1, duration_seconds=self.duration_seconds
        )
        if self.operations != (expected,):
            raise ValueError("timed SF operations do not match the phase and duration")
        return self


def plan_timed_sf_operations(run: DemoRun) -> TimedSfOperationPlan:
    if run.phase is RunPhase.SF_MIXING:
        duration = run.execution_settings.sf_mixing_duration_seconds
        if duration is None:
            raise ValueError("configure SF mixing duration before starting the run")
        kind = OperationKind.TIMED_SF_MIXING
    elif run.phase is RunPhase.SF_SETTLING:
        duration = run.execution_settings.sf_settling_duration_seconds
        kind = OperationKind.SF_SETTLING_WAIT
    else:
        raise ValueError("not a timed SF phase")
    return TimedSfOperationPlan(
        phase=run.phase,
        duration_seconds=duration,
        operations=(
            TimedSfOperation(operation_kind=kind, operation_number=1, duration_seconds=duration),
        ),
    )
