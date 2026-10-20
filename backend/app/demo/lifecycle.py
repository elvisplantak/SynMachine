from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.demo.events import DomainEvent, DomainEventType
from app.demo.fluid_plan import build_fluid_plan
from app.demo.models import DemoConfiguration, DemoExecutionSettings
from app.demo.phases import RunPhase
from app.demo.run_models import DemoRun, RunStatus
from app.recipes.models import phase_for_step, validate_recipe_flow

_ACTIVE_PHASES = (
    RunPhase.P1_TRANSFER_S_TO_REACTOR,
    RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
    RunPhase.DELAY_BETWEEN_ADDITIONS,
    RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
    RunPhase.REACTION_HOLD,
    RunPhase.P2_TRANSFER_REACTOR_TO_SF,
    RunPhase.SF_MIXING,
    RunPhase.SF_SETTLING,
    RunPhase.P2_TRANSFER_SF_TO_COLUMN,
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
    recipe_step_index: int | None = None,
) -> TransitionResult:
    if recipe_step_index is not None:
        run = run.model_copy(update={"recipe_step_index": recipe_step_index})
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


def create_recipe_run(run_id, recipe, readiness, occurred_at):
    if not run_id.strip():
        raise ValueError("run_id must not be empty")
    validate_recipe_flow(recipe.definition)
    run = DemoRun(run_id=run_id, recipe=recipe, recipe_readiness=readiness,
        recipe_step_index=0, status=RunStatus.CREATED, phase=RunPhase.READY, event_sequence=0)
    event = _event(run, offset=1, occurred_at=occurred_at,
        event_type=DomainEventType.RUN_CREATED, status=run.status, phase=run.phase,
        message=f"UVP recipe {recipe.recipe_id} revision {recipe.revision} created")
    return _result(run, status=run.status, phase=run.phase, events=(event,))


def start_run(run: DemoRun, occurred_at: datetime) -> TransitionResult:
    if run.status is not RunStatus.CREATED or run.phase is not RunPhase.READY:
        raise _reject("start", run, "start is allowed only from CREATED and READY")

    first_phase = phase_for_step(run.recipe.definition.steps[0]) if run.recipe else _ACTIVE_PHASES[0]
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
        phase=first_phase,
        message=f"Phase {first_phase.value} started" + ("; UVP step 1" if run.recipe else ""),
    )
    return _result(
        run,
        status=RunStatus.RUNNING,
        phase=first_phase,
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
        message=f"Phase {run.phase.value} completed" + (f"; UVP step {run.recipe_step_index + 1}" if run.recipe else ""),
    )
    next_index = run.recipe_step_index + 1 if run.recipe else None
    final = next_index == len(run.recipe.definition.steps) if run.recipe else run.phase is RunPhase.COLUMN_FRACTION_COLLECTION
    if final:
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
            recipe_step_index=next_index,
        )

    next_phase = (phase_for_step(run.recipe.definition.steps[next_index]) if run.recipe
                  else _ACTIVE_PHASES[_ACTIVE_PHASES.index(run.phase) + 1])
    phase_started = _event(
        run,
        offset=2,
        occurred_at=occurred_at,
        event_type=DomainEventType.PHASE_STARTED,
        status=RunStatus.RUNNING,
        phase=next_phase,
        message=f"Phase {next_phase.value} started" + (f"; UVP step {next_index + 1}" if run.recipe else ""),
    )
    return _result(
        run,
        status=RunStatus.RUNNING,
        phase=next_phase,
        events=(completed, phase_started),
        recipe_step_index=next_index,
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
