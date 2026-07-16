from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.demo.phases import RunPhase
from app.demo.run_models import RunStatus


class DomainEventType(StrEnum):
    RUN_CREATED = "RUN_CREATED"
    RUN_STARTED = "RUN_STARTED"
    PHASE_STARTED = "PHASE_STARTED"
    PHASE_COMPLETED = "PHASE_COMPLETED"
    RUN_PAUSED = "RUN_PAUSED"
    RUN_RESUMED = "RUN_RESUMED"
    ABORT_REQUESTED = "ABORT_REQUESTED"
    RUN_ABORTED = "RUN_ABORTED"
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_FAULTED = "RUN_FAULTED"


class DomainEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    sequence_number: int
    occurred_at: datetime
    event_type: DomainEventType
    run_status: RunStatus
    run_phase: RunPhase
    message: str
    reason: str | None = None
