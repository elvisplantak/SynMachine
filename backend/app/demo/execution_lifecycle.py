from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.demo.machine_events import MachineEvent, MachineEventType
from app.demo.machine_lifecycle import MachineTransitionResult
from app.demo.machine_models import (
    MachineSnapshot,
    MachineState,
    PhaseExecutionIntent,
)
from app.demo.phases import HARDWARE_EXECUTION_PHASES, RunPhase
from app.demo.run_models import DemoRun, RunStatus


class PhaseExecutionClaimError(ValueError):
    """Raised when current run and machine state cannot claim execution."""


class ExecutionIdAlreadyUsedError(PhaseExecutionClaimError):
    """Raised when an execution ID already exists in durable history."""


class PhaseExecutionStartCommitOutcome(StrEnum):
    START_COMMITTED = "START_COMMITTED"
    STOP_WON = "STOP_WON"


class PhaseExecutionStartCommitResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    outcome: PhaseExecutionStartCommitOutcome
    intent: PhaseExecutionIntent
    machine: MachineSnapshot
    events: tuple[MachineEvent, ...]


class PhaseExecutionStartCommitError(ValueError):
    """Raised when start permission cannot match current persisted state."""


def claim_phase_execution(
    run: DemoRun,
    machine: MachineSnapshot,
    *,
    execution_id: str,
    claimed_at: datetime,
) -> MachineTransitionResult:
    if run.status is not RunStatus.RUNNING:
        raise PhaseExecutionClaimError(
            f"phase execution claim requires RUNNING status, got {run.status.value}"
        )
    if run.phase not in HARDWARE_EXECUTION_PHASES:
        raise PhaseExecutionClaimError(
            f"phase {run.phase.value} does not support hardware execution"
        )
    if machine.state is not MachineState.BUSY:
        raise PhaseExecutionClaimError(
            f"phase execution claim requires BUSY machine, got {machine.state.value}"
        )
    if machine.active_run_id != run.run_id:
        raise PhaseExecutionClaimError(
            f"machine active_run_id {machine.active_run_id!r} does not match "
            f"run_id {run.run_id!r}"
        )
    if machine.active_execution is not None:
        raise PhaseExecutionClaimError(
            f"phase execution {machine.active_execution.execution_id!r} is already active"
        )

    intent = PhaseExecutionIntent(
        execution_id=execution_id,
        run_id=run.run_id,
        phase=run.phase,
        claimed_at=claimed_at,
    )
    event = MachineEvent(
        sequence_number=machine.event_sequence + 1,
        occurred_at=claimed_at,
        event_type=MachineEventType.PHASE_EXECUTION_CLAIMED,
        machine_state=MachineState.BUSY,
        run_id=run.run_id,
        message="Guided Demo phase execution claimed",
        execution_id=intent.execution_id,
        execution_phase=intent.phase,
    )
    updated_machine = MachineSnapshot.model_validate(
        {
            **machine.model_dump(mode="python"),
            "event_sequence": machine.event_sequence + 1,
            "active_execution": intent,
        }
    )
    return MachineTransitionResult(machine=updated_machine, events=(event,))


def commit_phase_execution_start(
    run: DemoRun,
    machine: MachineSnapshot,
    intent: PhaseExecutionIntent,
    *,
    expected_run_event_sequence: int,
    expected_phase: RunPhase,
    start_committed_at: datetime,
) -> PhaseExecutionStartCommitResult:
    active = machine.active_execution
    if active is None:
        raise PhaseExecutionStartCommitError("NO_ACTIVE_EXECUTION")
    if active != intent:
        raise PhaseExecutionStartCommitError(
            f"active_execution={active!r} does not match intent={intent!r}"
        )
    if (
        run.run_id != active.run_id
        or run.phase != active.phase
        or machine.active_run_id != run.run_id
    ):
        raise PhaseExecutionStartCommitError(
            "inconsistent start aggregate: "
            f"run_id={run.run_id!r}, run_phase={run.phase.value}, "
            f"active_run_id={machine.active_run_id!r}, intent={active!r}"
        )
    if active.phase != expected_phase:
        raise PhaseExecutionStartCommitError(
            f"active phase {active.phase.value} does not match expected "
            f"{expected_phase.value}"
        )
    if active.start_committed_at is not None:
        raise PhaseExecutionStartCommitError(
            f"execution {active.execution_id!r} start is already committed"
        )
    if run.status is RunStatus.ABORTING:
        return PhaseExecutionStartCommitResult(
            outcome=PhaseExecutionStartCommitOutcome.STOP_WON,
            intent=active,
            machine=machine,
            events=(),
        )
    if run.status is not RunStatus.RUNNING:
        raise PhaseExecutionStartCommitError(
            f"unsupported run status {run.status.value}"
        )
    if run.event_sequence != expected_run_event_sequence:
        raise PhaseExecutionStartCommitError(
            f"run event_sequence {run.event_sequence} does not match expected "
            f"{expected_run_event_sequence}"
        )

    started = PhaseExecutionIntent.model_validate(
        {
            **active.model_dump(mode="python"),
            "start_committed_at": start_committed_at,
        }
    )
    event = MachineEvent(
        sequence_number=machine.event_sequence + 1,
        occurred_at=start_committed_at,
        event_type=MachineEventType.PHASE_EXECUTION_START_COMMITTED,
        machine_state=MachineState.BUSY,
        run_id=run.run_id,
        message="Guided Demo phase execution start permission committed",
        execution_id=started.execution_id,
        execution_phase=started.phase,
        execution_claimed_at=started.claimed_at,
    )
    updated_machine = MachineSnapshot.model_validate(
        {
            **machine.model_dump(mode="python"),
            "event_sequence": machine.event_sequence + 1,
            "active_execution": started,
        }
    )
    return PhaseExecutionStartCommitResult(
        outcome=PhaseExecutionStartCommitOutcome.START_COMMITTED,
        intent=started,
        machine=updated_machine,
        events=(event,),
    )
