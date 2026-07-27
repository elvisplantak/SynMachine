from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.demo.machine_events import MachineEvent, MachineEventType
from app.demo.machine_models import (
    MachineSnapshot,
    MachineState,
    RuntimeHardwareFaultReason,
)


class MachineTransitionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    machine: MachineSnapshot
    events: tuple[MachineEvent, ...]


class MachineTransitionError(ValueError):
    """Raised when a machine operation is invalid for the current machine state."""


def _reject(
    operation: str, machine: MachineSnapshot, reason: str
) -> MachineTransitionError:
    return MachineTransitionError(
        f"Cannot {operation} in machine state {machine.state.value}: {reason}"
    )


def _require_run_id(
    operation: str, machine: MachineSnapshot, run_id: str
) -> str:
    normalized_run_id = run_id.strip()
    if not normalized_run_id:
        raise _reject(operation, machine, "run_id must not be empty")
    return normalized_run_id


def _require_active_run(
    operation: str, machine: MachineSnapshot, run_id: str
) -> str:
    normalized_run_id = _require_run_id(operation, machine, run_id)
    if normalized_run_id != machine.active_run_id:
        raise _reject(
            operation,
            machine,
            f"run_id {normalized_run_id!r} does not match active_run_id "
            f"{machine.active_run_id!r}",
        )
    return normalized_run_id


def _require_no_active_execution(
    operation: str, machine: MachineSnapshot
) -> None:
    if machine.active_execution is not None:
        raise _reject(
            operation,
            machine,
            "active phase execution must be resolved by its matching token",
        )


def _event(
    machine: MachineSnapshot,
    *,
    offset: int,
    occurred_at: datetime,
    event_type: MachineEventType,
    state: MachineState,
    message: str,
    run_id: str | None = None,
    reason: str | None = None,
    runtime_fault_reason: RuntimeHardwareFaultReason | None = None,
    hardware_outcome_unknown: bool = False,
    carousel_position_untrusted: bool = False,
) -> MachineEvent:
    return MachineEvent(
        sequence_number=machine.event_sequence + offset,
        occurred_at=occurred_at,
        event_type=event_type,
        machine_state=state,
        run_id=run_id,
        message=message,
        reason=reason,
        runtime_fault_reason=runtime_fault_reason,
        hardware_outcome_unknown=hardware_outcome_unknown,
        carousel_position_untrusted=carousel_position_untrusted,
    )


def _result(
    machine: MachineSnapshot,
    *,
    state: MachineState,
    events: tuple[MachineEvent, ...],
    active_run_id: str | None = None,
    interrupted_run_id: str | None = None,
    runtime_fault_reason: RuntimeHardwareFaultReason | None = None,
    hardware_outcome_unknown: bool = False,
    carousel_position_untrusted: bool = False,
) -> MachineTransitionResult:
    updated_machine = MachineSnapshot(
        state=state,
        event_sequence=machine.event_sequence + len(events),
        active_run_id=active_run_id,
        interrupted_run_id=interrupted_run_id,
        runtime_fault_reason=runtime_fault_reason,
        hardware_outcome_unknown=hardware_outcome_unknown,
        carousel_position_untrusted=carousel_position_untrusted,
    )
    return MachineTransitionResult(machine=updated_machine, events=events)


def create_machine(occurred_at: datetime) -> MachineTransitionResult:
    machine = MachineSnapshot(state=MachineState.STARTING, event_sequence=0)
    event = _event(
        machine,
        offset=1,
        occurred_at=occurred_at,
        event_type=MachineEventType.MACHINE_CREATED,
        state=MachineState.STARTING,
        message="Machine lifecycle created",
    )
    return _result(machine, state=MachineState.STARTING, events=(event,))


def complete_startup(
    machine: MachineSnapshot, occurred_at: datetime
) -> MachineTransitionResult:
    if machine.state is not MachineState.STARTING:
        raise _reject("complete startup", machine, "startup completion requires STARTING")

    event = _event(
        machine,
        offset=1,
        occurred_at=occurred_at,
        event_type=MachineEventType.STARTUP_COMPLETED,
        state=MachineState.READY,
        message="Clean machine startup completed at domain level",
    )
    return _result(machine, state=MachineState.READY, events=(event,))


def start_run(
    machine: MachineSnapshot, run_id: str, occurred_at: datetime
) -> MachineTransitionResult:
    if machine.state is not MachineState.READY:
        raise _reject("start run", machine, "run start requires READY")
    normalized_run_id = _require_run_id("start run", machine, run_id)

    event = _event(
        machine,
        offset=1,
        occurred_at=occurred_at,
        event_type=MachineEventType.RUN_STARTED,
        state=MachineState.BUSY,
        run_id=normalized_run_id,
        message="Machine assigned to Guided Demo run",
    )
    return _result(
        machine,
        state=MachineState.BUSY,
        active_run_id=normalized_run_id,
        events=(event,),
    )


def complete_run(
    machine: MachineSnapshot, run_id: str, occurred_at: datetime
) -> MachineTransitionResult:
    if machine.state is not MachineState.BUSY:
        raise _reject("complete run", machine, "normal run completion requires BUSY")
    normalized_run_id = _require_active_run("complete run", machine, run_id)
    _require_no_active_execution("complete run", machine)

    event = _event(
        machine,
        offset=1,
        occurred_at=occurred_at,
        event_type=MachineEventType.RUN_COMPLETED,
        state=MachineState.READY,
        run_id=normalized_run_id,
        message="Guided Demo run completed normally at machine level",
    )
    return _result(machine, state=MachineState.READY, events=(event,))


def complete_stop_demo(
    machine: MachineSnapshot, run_id: str, occurred_at: datetime
) -> MachineTransitionResult:
    if machine.state is not MachineState.BUSY:
        raise _reject("complete Stop demo", machine, "Stop demo completion requires BUSY")
    normalized_run_id = _require_active_run("complete Stop demo", machine, run_id)
    _require_no_active_execution("complete Stop demo", machine)

    event = _event(
        machine,
        offset=1,
        occurred_at=occurred_at,
        event_type=MachineEventType.STOP_DEMO_COMPLETED,
        state=MachineState.FLUSH_REQUIRED,
        run_id=normalized_run_id,
        message="Stop demo completed after the current atomic operation",
    )
    return _result(machine, state=MachineState.FLUSH_REQUIRED, events=(event,))


def record_runtime_hardware_fault(
    machine: MachineSnapshot,
    *,
    run_id: str,
    occurred_at: datetime,
    reason: RuntimeHardwareFaultReason,
) -> MachineTransitionResult:
    if machine.state is not MachineState.BUSY:
        raise _reject(
            "record runtime hardware fault",
            machine,
            "runtime hardware fault requires BUSY",
        )
    normalized_run_id = _require_active_run(
        "record runtime hardware fault", machine, run_id
    )
    _require_no_active_execution("record runtime hardware fault", machine)
    carousel_position_untrusted = (
        reason is RuntimeHardwareFaultReason.CAROUSEL_MOVEMENT_FAILED
    )
    event = _event(
        machine,
        offset=1,
        occurred_at=occurred_at,
        event_type=MachineEventType.RUNTIME_HARDWARE_FAULT_DETECTED,
        state=MachineState.RECOVERY_REQUIRED,
        run_id=normalized_run_id,
        message="Runtime hardware fault detected; Service recovery is required",
        runtime_fault_reason=reason,
        hardware_outcome_unknown=True,
        carousel_position_untrusted=carousel_position_untrusted,
    )
    return _result(
        machine,
        state=MachineState.RECOVERY_REQUIRED,
        interrupted_run_id=normalized_run_id,
        runtime_fault_reason=reason,
        hardware_outcome_unknown=True,
        carousel_position_untrusted=carousel_position_untrusted,
        events=(event,),
    )


def detect_interrupted_startup(
    machine: MachineSnapshot,
    interrupted_run_id: str,
    occurred_at: datetime,
    reason: str | None = None,
) -> MachineTransitionResult:
    if machine.state is not MachineState.STARTING:
        raise _reject(
            "detect interrupted startup",
            machine,
            "interrupted startup detection requires STARTING",
        )
    normalized_run_id = _require_run_id(
        "detect interrupted startup", machine, interrupted_run_id
    )

    detected = _event(
        machine,
        offset=1,
        occurred_at=occurred_at,
        event_type=MachineEventType.POWER_LOSS_DETECTED,
        state=MachineState.STARTING,
        run_id=normalized_run_id,
        message="Incomplete Guided Demo run detected during startup",
        reason=reason,
    )
    recovery_started = _event(
        machine,
        offset=2,
        occurred_at=occurred_at,
        event_type=MachineEventType.RECOVERY_STARTED,
        state=MachineState.RECOVERING,
        run_id=normalized_run_id,
        message="Automatic recovery started at domain level",
    )
    return _result(
        machine,
        state=MachineState.RECOVERING,
        interrupted_run_id=normalized_run_id,
        events=(detected, recovery_started),
    )


def complete_recovery(
    machine: MachineSnapshot, occurred_at: datetime
) -> MachineTransitionResult:
    if machine.state is not MachineState.RECOVERING:
        raise _reject("complete recovery", machine, "recovery completion requires RECOVERING")

    event = _event(
        machine,
        offset=1,
        occurred_at=occurred_at,
        event_type=MachineEventType.RECOVERY_COMPLETED,
        state=MachineState.FLUSH_REQUIRED,
        run_id=machine.interrupted_run_id,
        message="Automatic recovery completed; operator flush is required",
    )
    return _result(
        machine,
        state=MachineState.FLUSH_REQUIRED,
        interrupted_run_id=machine.interrupted_run_id,
        events=(event,),
    )


def start_flush(
    machine: MachineSnapshot, occurred_at: datetime
) -> MachineTransitionResult:
    if machine.state not in {MachineState.READY, MachineState.FLUSH_REQUIRED}:
        raise _reject("start flush", machine, "flush start requires READY or FLUSH_REQUIRED")
    if machine.active_run_id is not None:
        raise _reject(
            "start flush",
            machine,
            f"active_run_id must be empty, got {machine.active_run_id!r}",
        )

    event = _event(
        machine,
        offset=1,
        occurred_at=occurred_at,
        event_type=MachineEventType.FLUSH_STARTED,
        state=MachineState.FLUSHING,
        run_id=machine.interrupted_run_id,
        message="Operator-triggered Flush system started at domain level",
    )
    return _result(
        machine,
        state=MachineState.FLUSHING,
        interrupted_run_id=machine.interrupted_run_id,
        events=(event,),
    )


def complete_flush(
    machine: MachineSnapshot, occurred_at: datetime
) -> MachineTransitionResult:
    if machine.state is not MachineState.FLUSHING:
        raise _reject("complete flush", machine, "flush completion requires FLUSHING")

    event = _event(
        machine,
        offset=1,
        occurred_at=occurred_at,
        event_type=MachineEventType.FLUSH_COMPLETED,
        state=MachineState.READY,
        run_id=machine.interrupted_run_id,
        message="Flush system completed at domain level",
    )
    return _result(machine, state=MachineState.READY, events=(event,))
