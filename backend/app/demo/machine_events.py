from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.demo.machine_models import (
    MachineState,
    PhaseExecutionStartupInterruptionKind,
    PhaseExecutionOutcome,
    PhaseExecutionResult,
    RuntimeHardwareFaultReason,
    StartupRecoveryReason,
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
    PHASE_EXECUTION_INTERRUPTED_AT_STARTUP = (
        "PHASE_EXECUTION_INTERRUPTED_AT_STARTUP"
    )
    RUN_INTERRUPTED_AT_STARTUP = "RUN_INTERRUPTED_AT_STARTUP"
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
    startup_recovery_reason: StartupRecoveryReason | None = None
    hardware_outcome_unknown: bool = False
    carousel_position_untrusted: bool = False
    execution_id: str | None = None
    execution_phase: RunPhase | None = None
    execution_outcome: PhaseExecutionOutcome | None = None
    execution_claimed_at: datetime | None = None
    execution_start_committed_at: datetime | None = None
    startup_interruption_kind: PhaseExecutionStartupInterruptionKind | None = None
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
        elif (
            self.event_type
            is MachineEventType.PHASE_EXECUTION_INTERRUPTED_AT_STARTUP
        ):
            if (
                self.run_id is None
                or not self.run_id.strip()
                or self.execution_id is None
                or not self.execution_id.strip()
                or self.execution_phase not in HARDWARE_EXECUTION_PHASES
                or self.execution_claimed_at is None
                or self.startup_interruption_kind is None
            ):
                raise ValueError(
                    "PHASE_EXECUTION_INTERRUPTED_AT_STARTUP requires matching "
                    "execution metadata"
                )
            if self.execution_claimed_at.tzinfo is None or (
                self.execution_claimed_at.utcoffset() is None
            ):
                raise ValueError("execution_claimed_at must be timezone-aware")
            if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
                raise ValueError("occurred_at must be timezone-aware")
            if self.occurred_at < self.execution_claimed_at:
                raise ValueError("startup interruption precedes claimed_at")
            if (
                self.startup_interruption_kind
                is PhaseExecutionStartupInterruptionKind.CLAIMED_NOT_STARTED
            ):
                if self.execution_start_committed_at is not None:
                    raise ValueError(
                        "CLAIMED_NOT_STARTED rejects execution_start_committed_at"
                    )
                if self.machine_state is not MachineState.RECOVERING:
                    raise ValueError("CLAIMED_NOT_STARTED requires RECOVERING")
                if self.startup_recovery_reason is not None:
                    raise ValueError(
                        "CLAIMED_NOT_STARTED rejects startup_recovery_reason"
                    )
                if self.hardware_outcome_unknown or self.carousel_position_untrusted:
                    raise ValueError(
                        "CLAIMED_NOT_STARTED requires trusted default metadata"
                    )
            else:
                if self.execution_start_committed_at is None:
                    raise ValueError(
                        "START_COMMITTED_OUTCOME_UNKNOWN requires "
                        "execution_start_committed_at"
                    )
                if (
                    self.execution_start_committed_at.tzinfo is None
                    or self.execution_start_committed_at.utcoffset() is None
                ):
                    raise ValueError(
                        "execution_start_committed_at must be timezone-aware"
                    )
                if self.occurred_at < self.execution_start_committed_at:
                    raise ValueError(
                        "startup interruption precedes start_committed_at"
                    )
                if self.machine_state is not MachineState.RECOVERY_REQUIRED:
                    raise ValueError(
                        "START_COMMITTED_OUTCOME_UNKNOWN requires RECOVERY_REQUIRED"
                    )
                if self.startup_recovery_reason is None:
                    raise ValueError(
                        "START_COMMITTED_OUTCOME_UNKNOWN requires "
                        "startup_recovery_reason"
                    )
                if not self.hardware_outcome_unknown:
                    raise ValueError(
                        "START_COMMITTED_OUTCOME_UNKNOWN requires "
                        "hardware_outcome_unknown"
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
                    "startup interruption rejects phase-result metadata"
                )
        elif self.event_type is MachineEventType.RUN_INTERRUPTED_AT_STARTUP:
            if any(
                value is not None
                for value in (
                    self.execution_id,
                    self.execution_phase,
                    self.execution_outcome,
                    self.execution_claimed_at,
                    self.execution_start_committed_at,
                    self.startup_interruption_kind,
                    self.failure_reason,
                    self.cleanup_failure_reason,
                    self.primary_failure_reason,
                )
            ):
                raise ValueError(
                    "RUN_INTERRUPTED_AT_STARTUP rejects phase-execution metadata"
                )
            if self.machine_state is not MachineState.RECOVERING:
                raise ValueError("RUN_INTERRUPTED_AT_STARTUP requires RECOVERING")
            if self.run_id is None or not self.run_id.strip():
                raise ValueError(
                    "RUN_INTERRUPTED_AT_STARTUP requires non-empty run_id"
                )
            if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
                raise ValueError(
                    "RUN_INTERRUPTED_AT_STARTUP occurred_at must be timezone-aware"
                )
            if (
                self.reason is not None
                or self.runtime_fault_reason is not None
                or self.startup_recovery_reason is not None
                or self.hardware_outcome_unknown
                or self.carousel_position_untrusted
            ):
                raise ValueError(
                    "RUN_INTERRUPTED_AT_STARTUP requires default recovery metadata"
                )
        elif any(
            value is not None
            for value in (
                self.execution_id,
                self.execution_phase,
                self.execution_outcome,
                self.execution_claimed_at,
                self.execution_start_committed_at,
                self.startup_interruption_kind,
                self.failure_reason,
                self.cleanup_failure_reason,
                self.primary_failure_reason,
            )
        ):
            raise ValueError(
                "execution metadata requires a phase execution event"
            )
        if (
            self.event_type
            is not MachineEventType.PHASE_EXECUTION_INTERRUPTED_AT_STARTUP
            and (
                self.execution_start_committed_at is not None
                or self.startup_interruption_kind is not None
                or self.startup_recovery_reason is not None
            )
        ):
            raise ValueError(
                "startup interruption metadata requires "
                "PHASE_EXECUTION_INTERRUPTED_AT_STARTUP"
            )
        return self
