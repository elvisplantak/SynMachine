from pydantic import BaseModel, ConfigDict

from app.demo.events import DomainEvent
from app.demo.lifecycle import complete_current_phase, confirm_abort, fault_run
from app.demo.machine_events import MachineEvent, MachineEventType
from app.demo.machine_lifecycle import (
    complete_run,
    complete_stop_demo,
    record_runtime_hardware_fault,
)
from app.demo.machine_models import (
    MachineSnapshot,
    MachineState,
    PhaseExecutionOutcome,
    PhaseExecutionResult,
)
from app.demo.phases import HARDWARE_EXECUTION_PHASES
from app.demo.run_models import DemoRun, RunStatus


class NoActiveExecutionError(ValueError):
    """Raised when a phase result has no active token to resolve."""


class ExecutionIdMismatchError(ValueError):
    """Raised when a phase result does not match the active token."""


class ExecutionAlreadyResolvedError(ValueError):
    """Raised by persistence when a token has a durable resolution event."""


class InvalidExecutionResultError(ValueError):
    """Raised when a matching result is invalid for the fresh aggregate."""


class PhaseExecutionResolution(BaseModel):
    model_config = ConfigDict(frozen=True)

    run: DemoRun
    machine: MachineSnapshot
    run_events: tuple[DomainEvent, ...]
    machine_events: tuple[MachineEvent, ...]


def resolve_phase_execution(
    run: DemoRun,
    machine: MachineSnapshot,
    result: PhaseExecutionResult,
) -> PhaseExecutionResolution:
    intent = machine.active_execution
    if intent is None:
        raise NoActiveExecutionError("NO_ACTIVE_EXECUTION")
    if result.execution_id != intent.execution_id:
        raise ExecutionIdMismatchError("EXECUTION_ID_MISMATCH")
    if result.reported_at < intent.claimed_at:
        raise InvalidExecutionResultError(
            "INVALID_EXECUTION_RESULT: reported_at precedes claimed_at"
        )
    if (
        machine.state is not MachineState.BUSY
        or machine.active_run_id != run.run_id
        or intent.run_id != run.run_id
        or intent.phase != run.phase
        or intent.phase not in HARDWARE_EXECUTION_PHASES
    ):
        raise InvalidExecutionResultError(
            "INVALID_EXECUTION_RESULT: inconsistent active aggregate"
        )
    if run.status not in {RunStatus.RUNNING, RunStatus.ABORTING}:
        raise InvalidExecutionResultError(
            "INVALID_EXECUTION_RESULT: unsupported run status"
        )
    if (
        result.outcome is PhaseExecutionOutcome.STOPPED_AT_SAFE_BOUNDARY
        and run.status is not RunStatus.ABORTING
    ):
        raise InvalidExecutionResultError(
            "INVALID_EXECUTION_RESULT: safe stop requires ABORTING status"
        )

    cleared = machine.model_copy(update={"active_execution": None})
    resolved_event = MachineEvent(
        sequence_number=machine.event_sequence + 1,
        occurred_at=result.reported_at,
        event_type=MachineEventType.PHASE_EXECUTION_RESOLVED,
        machine_state=MachineState.BUSY,
        run_id=run.run_id,
        message="Guided Demo phase execution resolved",
        execution_id=intent.execution_id,
        execution_phase=intent.phase,
        execution_outcome=result.outcome,
        execution_claimed_at=intent.claimed_at,
        failure_reason=result.failure_reason,
        cleanup_failure_reason=result.cleanup_failure_reason,
        primary_failure_reason=result.primary_failure_reason,
        runtime_fault_reason=result.runtime_fault_reason,
    )

    if result.outcome in {
        PhaseExecutionOutcome.HARDWARE_COMMAND_FAILED,
        PhaseExecutionOutcome.REQUIRED_CLEANUP_FAILED,
    }:
        fault_reason = (
            result.failure_reason
            if result.outcome is PhaseExecutionOutcome.HARDWARE_COMMAND_FAILED
            else result.cleanup_failure_reason
        )
        run_transition = fault_run(run, result.reported_at, fault_reason or "")
        machine_transition = record_runtime_hardware_fault(
            cleared.model_copy(
                update={"event_sequence": machine.event_sequence + 1}
            ),
            run_id=run.run_id,
            occurred_at=result.reported_at,
            reason=result.runtime_fault_reason,
        )
        return PhaseExecutionResolution(
            run=run_transition.run,
            machine=machine_transition.machine,
            run_events=run_transition.events,
            machine_events=(resolved_event, *machine_transition.events),
        )

    if run.status is RunStatus.ABORTING:
        run_transition = confirm_abort(run, result.reported_at)
        machine_transition = complete_stop_demo(
            cleared.model_copy(
                update={"event_sequence": machine.event_sequence + 1}
            ),
            run.run_id,
            result.reported_at,
        )
        return PhaseExecutionResolution(
            run=run_transition.run,
            machine=machine_transition.machine,
            run_events=run_transition.events,
            machine_events=(resolved_event, *machine_transition.events),
        )

    run_transition = complete_current_phase(run, result.reported_at)
    if run_transition.run.status is RunStatus.COMPLETED:
        machine_transition = complete_run(
            cleared.model_copy(
                update={"event_sequence": machine.event_sequence + 1}
            ),
            run.run_id,
            result.reported_at,
        )
        updated_machine = machine_transition.machine
        machine_events = (resolved_event, *machine_transition.events)
    else:
        updated_machine = cleared.model_copy(
            update={"event_sequence": machine.event_sequence + 1}
        )
        machine_events = (resolved_event,)
    return PhaseExecutionResolution(
        run=run_transition.run,
        machine=updated_machine,
        run_events=run_transition.events,
        machine_events=machine_events,
    )
