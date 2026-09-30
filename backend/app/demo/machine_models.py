from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.demo.phases import EXECUTION_INTENT_PHASES, RunPhase


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


class StartupRecoveryReason(StrEnum):
    EXECUTION_OUTCOME_UNKNOWN_AT_STARTUP = (
        "EXECUTION_OUTCOME_UNKNOWN_AT_STARTUP"
    )
    CAROUSEL_POSITION_UNKNOWN_AT_STARTUP = (
        "CAROUSEL_POSITION_UNKNOWN_AT_STARTUP"
    )


class PhaseExecutionStartupInterruptionKind(StrEnum):
    CLAIMED_NOT_STARTED = "CLAIMED_NOT_STARTED"
    START_COMMITTED_OUTCOME_UNKNOWN = "START_COMMITTED_OUTCOME_UNKNOWN"


class PhaseExecutionOutcome(StrEnum):
    COMPLETED = "COMPLETED"
    STOPPED_AT_SAFE_BOUNDARY = "STOPPED_AT_SAFE_BOUNDARY"
    HARDWARE_COMMAND_FAILED = "HARDWARE_COMMAND_FAILED"
    REQUIRED_CLEANUP_FAILED = "REQUIRED_CLEANUP_FAILED"


class PhaseExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    execution_id: str
    outcome: PhaseExecutionOutcome
    reported_at: datetime
    failure_reason: str | None = None
    cleanup_failure_reason: str | None = None
    primary_failure_reason: str | None = None
    runtime_fault_reason: RuntimeHardwareFaultReason | None = None

    @field_validator("execution_id")
    @classmethod
    def validate_result_execution_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("execution_id must not be empty")
        return value

    @field_validator("reported_at")
    @classmethod
    def validate_reported_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("reported_at must be timezone-aware")
        return value

    @field_validator(
        "failure_reason", "cleanup_failure_reason", "primary_failure_reason"
    )
    @classmethod
    def validate_optional_reason(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("failure reasons must be non-empty when supplied")
        return value

    @model_validator(mode="after")
    def validate_failure_metadata(self) -> Self:
        if self.outcome is PhaseExecutionOutcome.HARDWARE_COMMAND_FAILED:
            if self.failure_reason is None:
                raise ValueError(
                    "HARDWARE_COMMAND_FAILED requires failure_reason"
                )
            if (
                self.cleanup_failure_reason is not None
                or self.primary_failure_reason is not None
            ):
                raise ValueError(
                    "HARDWARE_COMMAND_FAILED rejects cleanup failure metadata"
                )
            if self.runtime_fault_reason not in {
                RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED,
                RuntimeHardwareFaultReason.CAROUSEL_MOVEMENT_FAILED,
            }:
                raise ValueError(
                    "HARDWARE_COMMAND_FAILED requires a hardware runtime_fault_reason"
                )
        elif self.outcome is PhaseExecutionOutcome.REQUIRED_CLEANUP_FAILED:
            if self.cleanup_failure_reason is None:
                raise ValueError(
                    "REQUIRED_CLEANUP_FAILED requires cleanup_failure_reason"
                )
            if self.failure_reason is not None:
                raise ValueError(
                    "REQUIRED_CLEANUP_FAILED uses primary_failure_reason"
                )
            if (
                self.runtime_fault_reason
                is not RuntimeHardwareFaultReason.REQUIRED_FOLLOWUP_FAILED
            ):
                raise ValueError(
                    "REQUIRED_CLEANUP_FAILED requires REQUIRED_FOLLOWUP_FAILED"
                )
        elif any(
            reason is not None
            for reason in (
                self.failure_reason,
                self.cleanup_failure_reason,
                self.primary_failure_reason,
            )
        ):
            raise ValueError("non-failure outcome rejects failure metadata")
        elif self.runtime_fault_reason is not None:
            raise ValueError("non-failure outcome rejects runtime_fault_reason")
        return self


class PhaseExecutionIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    execution_id: str
    run_id: str
    phase: RunPhase
    claimed_at: datetime
    start_committed_at: datetime | None = None

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
        if value not in EXECUTION_INTENT_PHASES:
            raise ValueError("phase does not support hardware execution")
        return value

    @field_validator("claimed_at")
    @classmethod
    def validate_claimed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("claimed_at must be timezone-aware")
        return value

    @field_validator("start_committed_at")
    @classmethod
    def validate_start_committed_at(
        cls, value: datetime | None
    ) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("start_committed_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_start_commit_order(self) -> Self:
        if (
            self.start_committed_at is not None
            and self.start_committed_at < self.claimed_at
        ):
            raise ValueError("start_committed_at must not precede claimed_at")
        return self


class MachineSnapshot(BaseModel):
    """Immutable machine state; sequence zero means no machine event has been emitted yet."""

    model_config = ConfigDict(frozen=True)

    state: MachineState
    event_sequence: int = Field(ge=0)
    active_run_id: str | None = None
    interrupted_run_id: str | None = None
    runtime_fault_reason: RuntimeHardwareFaultReason | None = None
    startup_recovery_reason: StartupRecoveryReason | None = None
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
            recovery_causes = sum(
                reason is not None
                for reason in (
                    self.runtime_fault_reason,
                    self.startup_recovery_reason,
                )
            )
            if recovery_causes != 1:
                raise ValueError(
                    "RECOVERY_REQUIRED requires exactly one recovery reason"
                )
            if not self.hardware_outcome_unknown:
                raise ValueError("RECOVERY_REQUIRED requires hardware_outcome_unknown")
            carousel_untrusted_reason = (
                self.runtime_fault_reason
                is RuntimeHardwareFaultReason.CAROUSEL_MOVEMENT_FAILED
                or self.startup_recovery_reason
                is StartupRecoveryReason.CAROUSEL_POSITION_UNKNOWN_AT_STARTUP
            )
            if self.carousel_position_untrusted is not carousel_untrusted_reason:
                raise ValueError(
                    "carousel_position_untrusted must match a carousel recovery reason"
                )
        elif (
            self.runtime_fault_reason is not None
            or self.startup_recovery_reason is not None
            or self.hardware_outcome_unknown
            or self.carousel_position_untrusted
        ):
            raise ValueError(
                f"{self.state.value} requires default runtime fault metadata"
            )
        return self
