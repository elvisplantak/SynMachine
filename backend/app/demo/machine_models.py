from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.demo.phases import HARDWARE_EXECUTION_PHASES, RunPhase


class MachineState(StrEnum):
    STARTING = "STARTING"
    READY = "READY"
    BUSY = "BUSY"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    RECOVERING = "RECOVERING"
    FLUSH_REQUIRED = "FLUSH_REQUIRED"
    FLUSHING = "FLUSHING"


class RuntimeHardwareFaultReason(StrEnum):
    HARDWARE_COMMAND_FAILED = "HARDWARE_COMMAND_FAILED"
    REQUIRED_FOLLOWUP_FAILED = "REQUIRED_FOLLOWUP_FAILED"
    CAROUSEL_MOVEMENT_FAILED = "CAROUSEL_MOVEMENT_FAILED"


class PhaseExecutionIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    execution_id: str
    run_id: str
    phase: RunPhase
    claimed_at: datetime

    @field_validator("execution_id")
    @classmethod
    def validate_execution_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("execution_id must not be empty")
        return value

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("run_id must not be empty")
        return value

    @field_validator("phase")
    @classmethod
    def validate_phase(cls, value: RunPhase) -> RunPhase:
        if value not in HARDWARE_EXECUTION_PHASES:
            raise ValueError("phase does not support hardware execution")
        return value

    @field_validator("claimed_at")
    @classmethod
    def validate_claimed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("claimed_at must be timezone-aware")
        return value


class MachineSnapshot(BaseModel):
    """Immutable machine state; sequence zero means no machine event has been emitted yet."""

    model_config = ConfigDict(frozen=True)

    state: MachineState
    event_sequence: int = Field(ge=0)
    active_run_id: str | None = None
    interrupted_run_id: str | None = None
    runtime_fault_reason: RuntimeHardwareFaultReason | None = None
    hardware_outcome_unknown: bool = False
    carousel_position_untrusted: bool = False
    active_execution: PhaseExecutionIntent | None = None

    @field_validator("active_run_id", "interrupted_run_id")
    @classmethod
    def validate_run_id(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("run identifier must not be empty")
        return value

    @model_validator(mode="after")
    def validate_state_invariants(self) -> Self:
        if self.active_run_id is not None and self.interrupted_run_id is not None:
            raise ValueError("active_run_id and interrupted_run_id cannot both be set")
        if self.state is MachineState.BUSY:
            if self.active_run_id is None:
                raise ValueError("BUSY requires active_run_id")
            if self.interrupted_run_id is not None:
                raise ValueError("BUSY requires interrupted_run_id to be empty")
            if (
                self.active_execution is not None
                and self.active_execution.run_id != self.active_run_id
            ):
                raise ValueError(
                    "active_execution run_id must match active_run_id"
                )
        elif self.active_run_id is not None:
            raise ValueError(f"{self.state.value} requires active_run_id to be empty")
        elif self.active_execution is not None:
            raise ValueError(
                f"{self.state.value} requires active_execution to be empty"
            )

        if self.state in {MachineState.RECOVERY_REQUIRED, MachineState.RECOVERING}:
            if self.interrupted_run_id is None:
                raise ValueError(f"{self.state.value} requires interrupted_run_id")
        elif self.state in {MachineState.STARTING, MachineState.READY}:
            if self.interrupted_run_id is not None:
                raise ValueError(
                    f"{self.state.value} requires interrupted_run_id to be empty"
                )

        if self.state is MachineState.RECOVERY_REQUIRED:
            if self.runtime_fault_reason is None:
                raise ValueError("RECOVERY_REQUIRED requires runtime_fault_reason")
            if not self.hardware_outcome_unknown:
                raise ValueError("RECOVERY_REQUIRED requires hardware_outcome_unknown")
            carousel_failure = (
                self.runtime_fault_reason
                is RuntimeHardwareFaultReason.CAROUSEL_MOVEMENT_FAILED
            )
            if self.carousel_position_untrusted is not carousel_failure:
                raise ValueError(
                    "carousel_position_untrusted must match CAROUSEL_MOVEMENT_FAILED"
                )
        elif (
            self.runtime_fault_reason is not None
            or self.hardware_outcome_unknown
            or self.carousel_position_untrusted
        ):
            raise ValueError(
                f"{self.state.value} requires default runtime fault metadata"
            )
        return self
