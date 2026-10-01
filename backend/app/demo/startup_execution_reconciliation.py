from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.demo.events import DomainEvent
from app.demo.lifecycle import confirm_abort, fault_run
from app.demo.machine_events import MachineEvent, MachineEventType
from app.demo.machine_models import (
    MachineSnapshot,
    MachineState,
    PhaseExecutionStartupInterruptionKind,
    StartupRecoveryReason,
)
from app.demo.phases import EXECUTION_INTENT_PHASES, PAUSABLE_EXECUTION_PHASES, RunPhase
from app.demo.run_models import DemoRun, RunStatus


class StartupExecutionReconciliationError(ValueError):
    """Raised when persisted aggregates cannot be reconciled at startup."""


class StartupExecutionReconciliationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    interruption_kind: PhaseExecutionStartupInterruptionKind
    run: DemoRun
    machine: MachineSnapshot
    run_events: tuple[DomainEvent, ...]
    machine_events: tuple[MachineEvent, ...]


def reconcile_interrupted_phase_execution_at_startup(
    run: DemoRun,
    machine: MachineSnapshot,
    occurred_at: datetime,
    *,
    allow_paused_wait: bool = False,
) -> StartupExecutionReconciliationResult:
    intent = machine.active_execution
    if (
        machine.state is not MachineState.BUSY
        or machine.active_run_id is None
        or intent is None
    ):
        raise StartupExecutionReconciliationError(
            "startup execution reconciliation requires BUSY machine with "
            "an active run and execution"
        )
    if (
        run.run_id != machine.active_run_id
        or run.run_id != intent.run_id
        or run.phase != intent.phase
        or run.phase not in EXECUTION_INTENT_PHASES
        or (
            run.status not in {RunStatus.RUNNING, RunStatus.ABORTING}
            and not (
                allow_paused_wait
                and run.status is RunStatus.PAUSED
                and run.phase in PAUSABLE_EXECUTION_PHASES
                and intent.start_committed_at is not None
            )
        )
    ):
        raise StartupExecutionReconciliationError(
            "startup execution reconciliation requires matching active aggregates"
        )

    if intent.start_committed_at is None:
        kind = PhaseExecutionStartupInterruptionKind.CLAIMED_NOT_STARTED
        if run.status is RunStatus.ABORTING:
            run_transition = confirm_abort(run, occurred_at)
        else:
            run_transition = fault_run(
                run,
                occurred_at,
                "Startup interrupted execution before durable start permission",
            )
        machine_state = MachineState.RECOVERING
        startup_recovery_reason = None
        hardware_outcome_unknown = False
        carousel_position_untrusted = False
    else:
        kind = (
            PhaseExecutionStartupInterruptionKind.START_COMMITTED_OUTCOME_UNKNOWN
        )
        run_transition = fault_run(
            run,
            occurred_at,
            "Startup found a start-committed execution with unknown physical outcome",
        )
        machine_state = MachineState.RECOVERY_REQUIRED
        if intent.phase is RunPhase.COLUMN_FRACTION_COLLECTION:
            startup_recovery_reason = (
                StartupRecoveryReason.CAROUSEL_POSITION_UNKNOWN_AT_STARTUP
            )
            carousel_position_untrusted = True
        else:
            startup_recovery_reason = (
                StartupRecoveryReason.EXECUTION_OUTCOME_UNKNOWN_AT_STARTUP
            )
            carousel_position_untrusted = False
        hardware_outcome_unknown = True

    event = MachineEvent(
        sequence_number=machine.event_sequence + 1,
        occurred_at=occurred_at,
        event_type=MachineEventType.PHASE_EXECUTION_INTERRUPTED_AT_STARTUP,
        machine_state=machine_state,
        run_id=run.run_id,
        message="Persisted phase execution reconciled as interrupted at startup",
        startup_recovery_reason=startup_recovery_reason,
        hardware_outcome_unknown=hardware_outcome_unknown,
        carousel_position_untrusted=carousel_position_untrusted,
        execution_id=intent.execution_id,
        execution_phase=intent.phase,
        execution_claimed_at=intent.claimed_at,
        execution_start_committed_at=intent.start_committed_at,
        startup_interruption_kind=kind,
    )
    updated_machine = MachineSnapshot(
        state=machine_state,
        event_sequence=machine.event_sequence + 1,
        interrupted_run_id=run.run_id,
        startup_recovery_reason=startup_recovery_reason,
        hardware_outcome_unknown=hardware_outcome_unknown,
        carousel_position_untrusted=carousel_position_untrusted,
    )
    return StartupExecutionReconciliationResult(
        interruption_kind=kind,
        run=run_transition.run,
        machine=updated_machine,
        run_events=run_transition.events,
        machine_events=(event,),
    )
