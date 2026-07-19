from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.demo.events import DomainEvent, DomainEventType
from app.demo.fluid_plan import build_fluid_plan
from app.demo.models import DemoConfiguration, DemoExecutionSettings
from app.demo.phases import RunPhase
from app.demo.run_models import DemoRun, RunStatus

_ACTIVE_PHASES = (
    RunPhase.P1_ASPIRATE_S,
    RunPhase.P1_DISPENSE_S_TO_REACTOR,
    RunPhase.P1_ASPIRATE_FIRST_LIQUID,
    RunPhase.P1_DISPENSE_FIRST_LIQUID_TO_REACTOR,
    RunPhase.DELAY_BETWEEN_ADDITIONS,
    RunPhase.P1_ASPIRATE_SECOND_LIQUID,
    RunPhase.P1_DISPENSE_SECOND_LIQUID_TO_REACTOR,
    RunPhase.REACTION_HOLD,
    RunPhase.P2_ASPIRATE_REACTOR_CONTENTS,
    RunPhase.P2_DISPENSE_TO_SF,
    RunPhase.SF_MIXING,
    RunPhase.SF_SETTLING,
    RunPhase.TRANSFER_SF_TO_COLUMN,
    RunPhase.COLUMN_FRACTION_COLLECTION,
)
_PAUSABLE_PHASES = frozenset(
    {RunPhase.DELAY_BETWEEN_ADDITIONS, RunPhase.REACTION_HOLD}
)


class TransitionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run: DemoRun
    events: tuple[DomainEvent, ...]


class LifecycleTransitionError(ValueError):
    """Raised when a lifecycle operation is invalid for the current run state."""


def _reject(operation: str, run: DemoRun, reason: str) -> LifecycleTransitionError:
    return LifecycleTransitionError(
        f"Cannot {operation} run in status {run.status.value} and phase "
        f"{run.phase.value}: {reason}"
    )


def _event(
    run: DemoRun,
    *,
    offset: int,
    occurred_at: datetime,
    event_type: DomainEventType,
    status: RunStatus,
    phase: RunPhase,
    message: str,
    reason: str | None = None,
) -> DomainEvent:
    return DomainEvent(
        run_id=run.run_id,
        sequence_number=run.event_sequence + offset,
        occurred_at=occurred_at,
        event_type=event_type,
        run_status=status,
        run_phase=phase,
        message=message,
        reason=reason,
    )


def _result(
    run: DemoRun,
    *,
    status: RunStatus,
    phase: RunPhase,
    events: tuple[DomainEvent, ...],
) -> TransitionResult:
    updated_run = run.model_copy(
        update={"status": status, "phase": phase, "event_sequence": run.event_sequence + len(events)}
    )
    return TransitionResult(run=updated_run, events=events)


def create_demo_run(
    run_id: str,
    configuration: DemoConfiguration,
    execution_settings: DemoExecutionSettings,
    occurred_at: datetime,
) -> TransitionResult:
    if not run_id.strip():
        raise ValueError("run_id must not be empty")

    run = DemoRun(
        run_id=run_id,
        configuration=configuration,
        execution_settings=execution_settings,
        fluid_plan=build_fluid_plan(configuration),
        status=RunStatus.CREATED,
        phase=RunPhase.READY,
        event_sequence=0,
    )
    event = _event(
        run,
        offset=1,
        occurred_at=occurred_at,
        event_type=DomainEventType.RUN_CREATED,
        status=RunStatus.CREATED,
        phase=RunPhase.READY,
        message="Guided Demo run created",
    )
    return _result(
        run, status=RunStatus.CREATED, phase=RunPhase.READY, events=(event,)
    )


def start_run(run: DemoRun, occurred_at: datetime) -> TransitionResult:
    if run.status is not RunStatus.CREATED or run.phase is not RunPhase.READY:
        raise _reject("start", run, "start is allowed only from CREATED and READY")

    started = _event(
        run,
        offset=1,
        occurred_at=occurred_at,
        event_type=DomainEventType.RUN_STARTED,
        status=RunStatus.RUNNING,
        phase=RunPhase.READY,
        message="Guided Demo run started",
    )
    phase_started = _event(
        run,
        offset=2,
        occurred_at=occurred_at,
        event_type=DomainEventType.PHASE_STARTED,
        status=RunStatus.RUNNING,
        phase=RunPhase.P1_ASPIRATE_S,
        message="Phase P1_ASPIRATE_S started",
    )
    return _result(
        run,
        status=RunStatus.RUNNING,
        phase=RunPhase.P1_ASPIRATE_S,
        events=(started, phase_started),
    )


def complete_current_phase(run: DemoRun, occurred_at: datetime) -> TransitionResult:
    if run.status is not RunStatus.RUNNING:
        raise _reject("complete current phase", run, "phase completion requires RUNNING status")
    if run.phase not in _ACTIVE_PHASES:
        raise _reject("complete current phase", run, "phase is not an active workflow phase")

    completed = _event(
        run,
        offset=1,
        occurred_at=occurred_at,
        event_type=DomainEventType.PHASE_COMPLETED,
        status=RunStatus.RUNNING,
        phase=run.phase,
        message=f"Phase {run.phase.value} completed",
    )
    if run.phase is RunPhase.COLUMN_FRACTION_COLLECTION:
        run_completed = _event(
            run,
            offset=2,
            occurred_at=occurred_at,
            event_type=DomainEventType.RUN_COMPLETED,
            status=RunStatus.COMPLETED,
            phase=RunPhase.COMPLETED,
            message="Guided Demo run completed",
        )
        return _result(
            run,
            status=RunStatus.COMPLETED,
            phase=RunPhase.COMPLETED,
            events=(completed, run_completed),
        )

    next_phase = _ACTIVE_PHASES[_ACTIVE_PHASES.index(run.phase) + 1]
    phase_started = _event(
        run,
        offset=2,
        occurred_at=occurred_at,
        event_type=DomainEventType.PHASE_STARTED,
        status=RunStatus.RUNNING,
        phase=next_phase,
        message=f"Phase {next_phase.value} started",
    )
    return _result(
        run,
        status=RunStatus.RUNNING,
        phase=next_phase,
        events=(completed, phase_started),
    )


def pause_run(run: DemoRun, occurred_at: datetime) -> TransitionResult:
    if run.status is not RunStatus.RUNNING:
        raise _reject("pause", run, "pause requires RUNNING status")
    if run.phase not in _PAUSABLE_PHASES:
        raise _reject("pause", run, "immediate pause is allowed only during delay or reaction hold")

    event = _event(
        run,
        offset=1,
        occurred_at=occurred_at,
        event_type=DomainEventType.RUN_PAUSED,
        status=RunStatus.PAUSED,
        phase=run.phase,
        message=f"Guided Demo run paused during {run.phase.value}",
    )
    return _result(run, status=RunStatus.PAUSED, phase=run.phase, events=(event,))


def resume_run(run: DemoRun, occurred_at: datetime) -> TransitionResult:
    if run.status is not RunStatus.PAUSED:
        raise _reject("resume", run, "resume requires PAUSED status")

    event = _event(
        run,
        offset=1,
        occurred_at=occurred_at,
        event_type=DomainEventType.RUN_RESUMED,
        status=RunStatus.RUNNING,
        phase=run.phase,
        message=f"Guided Demo run resumed during {run.phase.value}",
    )
    return _result(run, status=RunStatus.RUNNING, phase=run.phase, events=(event,))


def request_abort(run: DemoRun, occurred_at: datetime) -> TransitionResult:
    if run.status not in {RunStatus.RUNNING, RunStatus.PAUSED}:
        raise _reject("request abort", run, "abort request requires RUNNING or PAUSED status")

    event = _event(
        run,
        offset=1,
        occurred_at=occurred_at,
        event_type=DomainEventType.ABORT_REQUESTED,
        status=RunStatus.ABORTING,
        phase=run.phase,
        message="Abort requested; device stop is not yet confirmed",
    )
    return _result(run, status=RunStatus.ABORTING, phase=run.phase, events=(event,))


def confirm_abort(run: DemoRun, occurred_at: datetime) -> TransitionResult:
    if run.status is not RunStatus.ABORTING:
        raise _reject("confirm abort", run, "abort confirmation requires ABORTING status")

    event = _event(
        run,
        offset=1,
        occurred_at=occurred_at,
        event_type=DomainEventType.RUN_ABORTED,
        status=RunStatus.ABORTED,
        phase=run.phase,
        message="Guided Demo run abort confirmed at domain level",
    )
    return _result(run, status=RunStatus.ABORTED, phase=run.phase, events=(event,))


def fault_run(run: DemoRun, occurred_at: datetime, reason: str) -> TransitionResult:
    if run.status not in {RunStatus.RUNNING, RunStatus.PAUSED, RunStatus.ABORTING}:
        raise _reject("fault", run, "fault transition requires RUNNING, PAUSED, or ABORTING status")
    if not reason.strip():
        raise _reject("fault", run, "a non-empty reason is required")

    event = _event(
        run,
        offset=1,
        occurred_at=occurred_at,
        event_type=DomainEventType.RUN_FAULTED,
        status=RunStatus.FAULTED,
        phase=run.phase,
        message="Guided Demo run faulted",
        reason=reason,
    )
    return _result(run, status=RunStatus.FAULTED, phase=run.phase, events=(event,))
