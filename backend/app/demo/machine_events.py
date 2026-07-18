from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.demo.machine_models import MachineState


class MachineEventType(StrEnum):
    MACHINE_CREATED = "MACHINE_CREATED"
    STARTUP_COMPLETED = "STARTUP_COMPLETED"
    RUN_STARTED = "RUN_STARTED"
    RUN_COMPLETED = "RUN_COMPLETED"
    STOP_DEMO_COMPLETED = "STOP_DEMO_COMPLETED"
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
