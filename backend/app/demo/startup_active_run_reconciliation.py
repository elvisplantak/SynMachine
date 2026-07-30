from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.demo.events import DomainEvent
from app.demo.lifecycle import confirm_abort, fault_run
from app.demo.machine_events import MachineEvent, MachineEventType
from app.demo.machine_models import MachineSnapshot, MachineState
from app.demo.run_models import DemoRun, RunStatus


class StartupActiveRunReconciliationError(ValueError):
    """Raised when persisted active aggregates cannot be reconciled at startup."""


class StartupActiveRunReconciliationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run: DemoRun
    machine: MachineSnapshot
    run_events: tuple[DomainEvent, ...]
    machine_events: tuple[MachineEvent, ...]


def reconcile_interrupted_active_run_at_startup(
    run: DemoRun,
    machine: MachineSnapshot,
    occurred_at: datetime,
) -> StartupActiveRunReconciliationResult:
    if (
        machine.state is not MachineState.BUSY
        or machine.active_run_id is None
        or machine.active_execution is not None
    ):
        raise StartupActiveRunReconciliationError(
            "startup active-run reconciliation requires BUSY machine with "
            "an active run and no active execution"
        )
    if (
        run.run_id != machine.active_run_id
        or run.status not in {RunStatus.RUNNING, RunStatus.ABORTING}
    ):
        raise StartupActiveRunReconciliationError(
            "startup active-run reconciliation requires matching active aggregates"
        )

    if run.status is RunStatus.ABORTING:
        run_transition = confirm_abort(run, occurred_at)
    else:
        run_transition = fault_run(
            run,
            occurred_at,
            "Backend startup found an interrupted active run without an active "
            "phase execution",
        )

    event = MachineEvent(
        sequence_number=machine.event_sequence + 1,
        occurred_at=occurred_at,
        event_type=MachineEventType.RUN_INTERRUPTED_AT_STARTUP,
        machine_state=MachineState.RECOVERING,
        run_id=run.run_id,
        message="Persisted active run reconciled as interrupted at startup",
    )
    updated_machine = MachineSnapshot(
        state=MachineState.RECOVERING,
        event_sequence=machine.event_sequence + 1,
        interrupted_run_id=run.run_id,
    )
    return StartupActiveRunReconciliationResult(
        run=run_transition.run,
        machine=updated_machine,
        run_events=run_transition.events,
        machine_events=(event,),
    )
