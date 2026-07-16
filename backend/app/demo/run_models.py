from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.demo.fluid_plan import FluidPlan
from app.demo.models import DemoConfiguration
from app.demo.phases import RunPhase


class RunStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ABORTING = "ABORTING"
    ABORTED = "ABORTED"
    COMPLETED = "COMPLETED"
    FAULTED = "FAULTED"


class DemoRun(BaseModel):
    """Immutable state for one run; cross-run exclusivity belongs to an application service."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    configuration: DemoConfiguration
    fluid_plan: FluidPlan
    status: RunStatus
    phase: RunPhase
    event_sequence: int
