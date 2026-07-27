from datetime import datetime

from app.demo.machine_events import MachineEvent, MachineEventType
from app.demo.machine_lifecycle import MachineTransitionResult
from app.demo.machine_models import (
    MachineSnapshot,
    MachineState,
    PhaseExecutionIntent,
)
from app.demo.phases import HARDWARE_EXECUTION_PHASES
from app.demo.run_models import DemoRun, RunStatus


class PhaseExecutionClaimError(ValueError):
    """Raised when current run and machine state cannot claim execution."""


class ExecutionIdAlreadyUsedError(PhaseExecutionClaimError):
    """Raised when an execution ID already exists in durable history."""


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
