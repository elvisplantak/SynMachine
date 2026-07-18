from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MachineState(StrEnum):
    STARTING = "STARTING"
    READY = "READY"
    BUSY = "BUSY"
    RECOVERING = "RECOVERING"
    FLUSH_REQUIRED = "FLUSH_REQUIRED"
    FLUSHING = "FLUSHING"


class MachineSnapshot(BaseModel):
    """Immutable machine state; sequence zero means no machine event has been emitted yet."""

    model_config = ConfigDict(frozen=True)

    state: MachineState
    event_sequence: int = Field(ge=0)
    active_run_id: str | None = None
    interrupted_run_id: str | None = None

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
        elif self.active_run_id is not None:
            raise ValueError(f"{self.state.value} requires active_run_id to be empty")

        if self.state is MachineState.RECOVERING:
            if self.interrupted_run_id is None:
                raise ValueError("RECOVERING requires interrupted_run_id")
        elif self.state in {MachineState.STARTING, MachineState.READY}:
            if self.interrupted_run_id is not None:
                raise ValueError(
                    f"{self.state.value} requires interrupted_run_id to be empty"
                )
        return self
