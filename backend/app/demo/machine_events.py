from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.demo.machine_models import MachineState, RuntimeHardwareFaultReason
from app.demo.phases import HARDWARE_EXECUTION_PHASES, RunPhase


class MachineEventType(StrEnum):
    MACHINE_CREATED = "MACHINE_CREATED"
    STARTUP_COMPLETED = "STARTUP_COMPLETED"
    RUN_STARTED = "RUN_STARTED"
    RUN_COMPLETED = "RUN_COMPLETED"
    STOP_DEMO_COMPLETED = "STOP_DEMO_COMPLETED"
    RUNTIME_HARDWARE_FAULT_DETECTED = "RUNTIME_HARDWARE_FAULT_DETECTED"
    PHASE_EXECUTION_CLAIMED = "PHASE_EXECUTION_CLAIMED"
    POWER_LOSS_DETECTED = "POWER_LOSS_DETECTED"
    RECOVERY_STARTED = "RECOVERY_STARTED"
    RECOVERY_COMPLETED = "RECOVERY_COMPLETED"
    FLUSH_STARTED = "FLUSH_STARTED"
    FLUSH_COMPLETED = "FLUSH_COMPLETED"


class MachineEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    sequence_number: int = Field(ge=1)
    occurred_at: datetime
    event_type: MachineEventType
    machine_state: MachineState
    run_id: str | None = None
    message: str
    reason: str | None = None
    runtime_fault_reason: RuntimeHardwareFaultReason | None = None
    hardware_outcome_unknown: bool = False
    carousel_position_untrusted: bool = False
    execution_id: str | None = None
    execution_phase: RunPhase | None = None

    @model_validator(mode="after")
    def validate_execution_metadata(self) -> "MachineEvent":
        if self.event_type is MachineEventType.PHASE_EXECUTION_CLAIMED:
            if self.machine_state is not MachineState.BUSY:
                raise ValueError(
                    "PHASE_EXECUTION_CLAIMED requires BUSY machine_state"
                )
            if self.run_id is None or not self.run_id.strip():
                raise ValueError(
                    "PHASE_EXECUTION_CLAIMED requires non-empty run_id"
                )
            if self.execution_id is None or not self.execution_id.strip():
                raise ValueError(
                    "PHASE_EXECUTION_CLAIMED requires non-empty execution_id"
                )
            if self.execution_phase is None:
                raise ValueError("PHASE_EXECUTION_CLAIMED requires execution_phase")
            if self.execution_phase not in HARDWARE_EXECUTION_PHASES:
                raise ValueError(
                    "execution_phase does not support hardware execution"
                )
            if (
                self.occurred_at.tzinfo is None
                or self.occurred_at.utcoffset() is None
            ):
                raise ValueError(
                    "PHASE_EXECUTION_CLAIMED occurred_at must be timezone-aware"
                )
        elif self.execution_id is not None or self.execution_phase is not None:
            raise ValueError(
                "execution metadata requires PHASE_EXECUTION_CLAIMED"
            )
        return self
