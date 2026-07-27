from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.demo.machine_models import (
    MachineState,
    PhaseExecutionOutcome,
    PhaseExecutionResult,
    RuntimeHardwareFaultReason,
)
from app.demo.phases import HARDWARE_EXECUTION_PHASES, RunPhase


class MachineEventType(StrEnum):
    MACHINE_CREATED = "MACHINE_CREATED"
    STARTUP_COMPLETED = "STARTUP_COMPLETED"
    RUN_STARTED = "RUN_STARTED"
    RUN_COMPLETED = "RUN_COMPLETED"
    STOP_DEMO_COMPLETED = "STOP_DEMO_COMPLETED"
    RUNTIME_HARDWARE_FAULT_DETECTED = "RUNTIME_HARDWARE_FAULT_DETECTED"
    PHASE_EXECUTION_CLAIMED = "PHASE_EXECUTION_CLAIMED"
    PHASE_EXECUTION_START_COMMITTED = "PHASE_EXECUTION_START_COMMITTED"
    PHASE_EXECUTION_RESOLVED = "PHASE_EXECUTION_RESOLVED"
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
    execution_outcome: PhaseExecutionOutcome | None = None
    execution_claimed_at: datetime | None = None
    failure_reason: str | None = None
    cleanup_failure_reason: str | None = None
    primary_failure_reason: str | None = None

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
            if any(
                value is not None
                for value in (
                    self.execution_outcome,
                    self.execution_claimed_at,
                    self.failure_reason,
                    self.cleanup_failure_reason,
                    self.primary_failure_reason,
                    self.runtime_fault_reason,
                )
            ):
                raise ValueError(
                    "PHASE_EXECUTION_CLAIMED rejects resolution metadata"
                )
        elif (
            self.event_type
            is MachineEventType.PHASE_EXECUTION_START_COMMITTED
        ):
            if (
                self.machine_state is not MachineState.BUSY
                or self.run_id is None
                or self.execution_id is None
                or self.execution_phase not in HARDWARE_EXECUTION_PHASES
                or self.execution_claimed_at is None
            ):
                raise ValueError(
                    "PHASE_EXECUTION_START_COMMITTED requires matching "
                    "BUSY execution metadata"
                )
            if self.occurred_at < self.execution_claimed_at:
                raise ValueError(
                    "PHASE_EXECUTION_START_COMMITTED precedes claimed_at"
                )
            if any(
                value is not None
                for value in (
                    self.execution_outcome,
                    self.failure_reason,
                    self.cleanup_failure_reason,
                    self.primary_failure_reason,
                    self.runtime_fault_reason,
                )
            ):
                raise ValueError(
                    "PHASE_EXECUTION_START_COMMITTED rejects result metadata"
                )
        elif self.event_type is MachineEventType.PHASE_EXECUTION_RESOLVED:
            if self.machine_state is not MachineState.BUSY:
                raise ValueError(
                    "PHASE_EXECUTION_RESOLVED requires BUSY machine_state"
                )
            if self.run_id is None or not self.run_id.strip():
                raise ValueError(
                    "PHASE_EXECUTION_RESOLVED requires non-empty run_id"
                )
            if self.execution_id is None or not self.execution_id.strip():
                raise ValueError(
                    "PHASE_EXECUTION_RESOLVED requires non-empty execution_id"
                )
            if self.execution_phase not in HARDWARE_EXECUTION_PHASES:
                raise ValueError(
                    "PHASE_EXECUTION_RESOLVED requires hardware execution_phase"
                )
            if self.execution_outcome is None or self.execution_claimed_at is None:
                raise ValueError(
                    "PHASE_EXECUTION_RESOLVED requires outcome and claimed_at"
                )
            if (
                self.execution_claimed_at.tzinfo is None
                or self.execution_claimed_at.utcoffset() is None
            ):
                raise ValueError(
                    "PHASE_EXECUTION_RESOLVED claimed_at must be timezone-aware"
                )
            PhaseExecutionResult(
                execution_id=self.execution_id,
                outcome=self.execution_outcome,
                reported_at=self.occurred_at,
                failure_reason=self.failure_reason,
                cleanup_failure_reason=self.cleanup_failure_reason,
                primary_failure_reason=self.primary_failure_reason,
                runtime_fault_reason=self.runtime_fault_reason,
            )
            if self.occurred_at < self.execution_claimed_at:
                raise ValueError(
                    "PHASE_EXECUTION_RESOLVED occurred_at precedes claimed_at"
                )
        elif any(
            value is not None
            for value in (
                self.execution_id,
                self.execution_phase,
                self.execution_outcome,
                self.execution_claimed_at,
                self.failure_reason,
                self.cleanup_failure_reason,
                self.primary_failure_reason,
            )
        ):
            raise ValueError(
                "execution metadata requires a phase execution event"
            )
        return self
