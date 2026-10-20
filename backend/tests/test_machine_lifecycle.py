from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.demo.machine_events import MachineEvent, MachineEventType
from app.demo.machine_lifecycle import (
    MachineTransitionError,
    complete_flush,
    complete_recovery,
    complete_run,
    complete_startup,
    complete_stop_demo,
    create_machine,
    detect_interrupted_startup,
    record_runtime_hardware_fault,
    start_flush,
    start_run,
)
from app.demo.machine_models import (
    MachineSnapshot,
    MachineState,
    PhaseExecutionIntent,
    RuntimeHardwareFaultReason,
)
from app.demo.phases import RunPhase

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize("values", [
    dict(state=MachineState.READY, interrupted_maintenance_id="orphan"),
    dict(state=MachineState.RECOVERING, interrupted_maintenance_id="orphan", interrupted_run_id="run"),
    dict(state=MachineState.RECOVERING, interrupted_maintenance_id=""),
    dict(state=MachineState.RECOVERING),
])
def test_machine_only_interruption_cannot_masquerade_as_ready_or_run_scope(values):
    with pytest.raises(ValidationError):
        MachineSnapshot(event_sequence=2, **values)


def test_ownership_interruption_event_requires_machine_scope():
    with pytest.raises(ValidationError, match="machine-only"):
        MachineEvent(sequence_number=1, occurred_at=NOW,
            event_type=MachineEventType.OWNERSHIP_INTERRUPTION_RECONCILED,
            machine_state=MachineState.READY, message="invalid")


def starting_machine() -> MachineSnapshot:
    return create_machine(NOW).machine


def ready_machine() -> MachineSnapshot:
    return complete_startup(starting_machine(), NOW).machine


def busy_machine(run_id: str = "run-1") -> MachineSnapshot:
    return start_run(ready_machine(), run_id, NOW).machine


def busy_machine_with_execution() -> MachineSnapshot:
    machine = busy_machine()
    return MachineSnapshot.model_validate(
        {
            **machine.model_dump(mode="python"),
            "active_execution": PhaseExecutionIntent(
                execution_id="execution-1",
                run_id="run-1",
                phase=RunPhase.P1_TRANSFER_S_TO_REACTOR,
                claimed_at=NOW,
            ),
        }
    )


def recovering_machine(run_id: str = "run-interrupted") -> MachineSnapshot:
    return detect_interrupted_startup(starting_machine(), run_id, NOW).machine


def recovery_required_machine(run_id: str = "run-1") -> MachineSnapshot:
    return record_runtime_hardware_fault(
        busy_machine(run_id),
        run_id=run_id,
        occurred_at=NOW,
        reason=RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED,
    ).machine


def _machine_for_state(state: MachineState) -> MachineSnapshot:
    if state is MachineState.BUSY:
        return MachineSnapshot(
            state=state, event_sequence=10, active_run_id="run-1"
        )
    if state is MachineState.RECOVERY_REQUIRED:
        return recovery_required_machine()
    if state in {
        MachineState.RECOVERING,
        MachineState.FLUSH_REQUIRED,
        MachineState.FLUSHING,
    }:
        return MachineSnapshot(
            state=state,
            event_sequence=10,
            interrupted_run_id="run-interrupted",
        )
    return MachineSnapshot(state=state, event_sequence=10)


def test_machine_state_contains_exactly_the_agreed_values() -> None:
    assert [state.value for state in MachineState] == [
        "STARTING",
        "READY",
        "BUSY",
        "RECOVERY_REQUIRED",
        "RECOVERING",
        "FLUSH_REQUIRED",
        "FLUSHING",
    ]


def test_creation_starts_immutable_machine_and_emits_first_event() -> None:
    result = create_machine(NOW)

    assert result.machine == MachineSnapshot(
        state=MachineState.STARTING,
        event_sequence=1,
        active_run_id=None,
        interrupted_run_id=None,
    )
    assert len(result.events) == 1
    assert result.events[0].event_type is MachineEventType.MACHINE_CREATED
    assert result.events[0].sequence_number == 1
    assert result.events[0].occurred_at == NOW
    with pytest.raises(ValidationError):
        result.machine.state = MachineState.READY
    with pytest.raises(ValidationError):
        result.events[0].message = "changed"


def test_complete_startup_enters_ready_and_increments_sequence() -> None:
    result = complete_startup(starting_machine(), NOW + timedelta(seconds=1))

    assert result.machine.state is MachineState.READY
    assert result.machine.event_sequence == 2
    assert result.events[0].event_type is MachineEventType.STARTUP_COMPLETED
    assert result.events[0].sequence_number == 2
    assert result.events[0].occurred_at == NOW + timedelta(seconds=1)


@pytest.mark.parametrize("state", [state for state in MachineState if state is not MachineState.STARTING])
def test_complete_startup_is_rejected_outside_starting(state: MachineState) -> None:
    machine = _machine_for_state(state)

    with pytest.raises(MachineTransitionError, match=f"complete startup.*{state.value}"):
        complete_startup(machine, NOW)


def test_start_run_enters_busy_and_stores_run_id() -> None:
    result = start_run(ready_machine(), "run-1", NOW)

    assert result.machine.state is MachineState.BUSY
    assert result.machine.active_run_id == "run-1"
    assert result.machine.interrupted_run_id is None
    assert result.events[0].event_type is MachineEventType.RUN_STARTED
    assert result.events[0].run_id == "run-1"


@pytest.mark.parametrize("run_id", ["", "   "])
def test_start_run_requires_non_empty_run_id(run_id: str) -> None:
    with pytest.raises(MachineTransitionError, match="start run.*run_id must not be empty"):
        start_run(ready_machine(), run_id, NOW)


def test_start_run_is_rejected_outside_ready() -> None:
    with pytest.raises(MachineTransitionError, match="start run.*BUSY"):
        start_run(busy_machine(), "run-2", NOW)


def test_complete_run_requires_matching_active_run_and_returns_ready() -> None:
    machine = busy_machine()

    with pytest.raises(MachineTransitionError, match="run-other.*active_run_id.*run-1"):
        complete_run(machine, "run-other", NOW)

    result = complete_run(machine, "run-1", NOW)
    assert result.machine.state is MachineState.READY
    assert result.machine.active_run_id is None
    assert result.events[0].event_type is MachineEventType.RUN_COMPLETED
    assert result.events[0].run_id == "run-1"


def test_complete_run_does_not_require_flush() -> None:
    assert complete_run(busy_machine(), "run-1", NOW).machine.state is MachineState.READY


def test_complete_run_rejects_active_execution() -> None:
    machine = busy_machine_with_execution()

    with pytest.raises(MachineTransitionError, match="matching token"):
        complete_run(machine, "run-1", NOW)
    assert machine.active_execution is not None


def test_complete_run_is_rejected_outside_busy() -> None:
    with pytest.raises(MachineTransitionError, match="complete run.*READY"):
        complete_run(ready_machine(), "run-1", NOW)


def test_complete_stop_demo_requires_matching_run_and_requires_flush() -> None:
    machine = busy_machine()

    with pytest.raises(MachineTransitionError, match="run-other.*active_run_id.*run-1"):
        complete_stop_demo(machine, "run-other", NOW)

    result = complete_stop_demo(machine, "run-1", NOW)
    assert result.machine.state is MachineState.FLUSH_REQUIRED
    assert result.machine.active_run_id is None
    assert result.events[0].event_type is MachineEventType.STOP_DEMO_COMPLETED
    assert result.events[0].run_id == "run-1"
    assert "current atomic operation" in result.events[0].message
    assert "immediate" not in result.events[0].message.lower()
    assert "hardware stop" not in result.events[0].message.lower()


def test_complete_stop_demo_rejects_active_execution() -> None:
    machine = busy_machine_with_execution()

    with pytest.raises(MachineTransitionError, match="matching token"):
        complete_stop_demo(machine, "run-1", NOW)
    assert machine.active_execution is not None


@pytest.mark.parametrize("state", [state for state in MachineState if state is not MachineState.BUSY])
def test_complete_stop_demo_is_rejected_outside_busy(state: MachineState) -> None:
    machine = _machine_for_state(state)

    with pytest.raises(MachineTransitionError, match=f"complete Stop demo.*{state.value}"):
        complete_stop_demo(machine, "run-1", NOW)


@pytest.mark.parametrize(
    ("reason", "carousel_position_untrusted"),
    [
        (RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED, False),
        (RuntimeHardwareFaultReason.REQUIRED_FOLLOWUP_FAILED, False),
        (RuntimeHardwareFaultReason.CAROUSEL_MOVEMENT_FAILED, True),
    ],
)
def test_runtime_hardware_fault_requires_recovery_with_truthful_metadata(
    reason: RuntimeHardwareFaultReason,
    carousel_position_untrusted: bool,
) -> None:
    result = record_runtime_hardware_fault(
        busy_machine(),
        run_id=" run-1 ",
        occurred_at=NOW,
        reason=reason,
    )

    assert result.machine.state is MachineState.RECOVERY_REQUIRED
    assert result.machine.active_run_id is None
    assert result.machine.interrupted_run_id == "run-1"
    assert result.machine.runtime_fault_reason is reason
    assert result.machine.hardware_outcome_unknown is True
    assert (
        result.machine.carousel_position_untrusted
        is carousel_position_untrusted
    )
    assert len(result.events) == 1
    event = result.events[0]
    assert event.event_type is MachineEventType.RUNTIME_HARDWARE_FAULT_DETECTED
    assert event.machine_state is result.machine.state
    assert event.run_id == result.machine.interrupted_run_id
    assert event.runtime_fault_reason is result.machine.runtime_fault_reason
    assert event.hardware_outcome_unknown is result.machine.hardware_outcome_unknown
    assert (
        event.carousel_position_untrusted
        is result.machine.carousel_position_untrusted
    )
    assert event.message == (
        "Runtime hardware fault detected; Service recovery is required"
    )
    assert event.reason is None


def test_runtime_hardware_fault_rejects_active_execution() -> None:
    machine = busy_machine_with_execution()

    with pytest.raises(MachineTransitionError, match="matching token"):
        record_runtime_hardware_fault(
            machine,
            run_id="run-1",
            occurred_at=NOW,
            reason=RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED,
        )
    assert machine.active_execution is not None


@pytest.mark.parametrize("run_id", ["", "   ", "run-other"])
def test_runtime_hardware_fault_requires_matching_non_empty_run_id(
    run_id: str,
) -> None:
    with pytest.raises(MachineTransitionError):
        record_runtime_hardware_fault(
            busy_machine(),
            run_id=run_id,
            occurred_at=NOW,
            reason=RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED,
        )


@pytest.mark.parametrize(
    "state", [state for state in MachineState if state is not MachineState.BUSY]
)
def test_runtime_hardware_fault_is_rejected_outside_busy(
    state: MachineState,
) -> None:
    with pytest.raises(
        MachineTransitionError,
        match=f"record runtime hardware fault.*{state.value}",
    ):
        record_runtime_hardware_fault(
            _machine_for_state(state),
            run_id="run-1",
            occurred_at=NOW,
            reason=RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED,
        )


def test_interrupted_startup_emits_ordered_recovery_events() -> None:
    result = detect_interrupted_startup(
        starting_machine(), "run-interrupted", NOW, reason="Unclean shutdown marker"
    )

    assert result.machine.state is MachineState.RECOVERING
    assert result.machine.active_run_id is None
    assert result.machine.interrupted_run_id == "run-interrupted"
    assert [event.event_type for event in result.events] == [
        MachineEventType.POWER_LOSS_DETECTED,
        MachineEventType.RECOVERY_STARTED,
    ]
    assert [event.sequence_number for event in result.events] == [2, 3]
    assert [event.machine_state for event in result.events] == [
        MachineState.STARTING,
        MachineState.RECOVERING,
    ]
    assert result.events[0].reason == "Unclean shutdown marker"


@pytest.mark.parametrize("run_id", ["", "  "])
def test_interrupted_startup_requires_non_empty_run_id(run_id: str) -> None:
    with pytest.raises(MachineTransitionError, match="run_id must not be empty"):
        detect_interrupted_startup(starting_machine(), run_id, NOW)


@pytest.mark.parametrize("state", [MachineState.READY, MachineState.BUSY])
def test_recovery_cannot_start_from_ready_or_busy(state: MachineState) -> None:
    machine = _machine_for_state(state)

    with pytest.raises(
        MachineTransitionError, match=f"detect interrupted startup.*{state.value}"
    ):
        detect_interrupted_startup(machine, "run-interrupted", NOW)


def test_recovery_completion_requires_flush_and_retains_interrupted_run() -> None:
    result = complete_recovery(recovering_machine(), NOW)

    assert result.machine.state is MachineState.FLUSH_REQUIRED
    assert result.machine.interrupted_run_id == "run-interrupted"
    assert [event.event_type for event in result.events] == [
        MachineEventType.RECOVERY_COMPLETED
    ]
    assert all(event.event_type is not MachineEventType.FLUSH_STARTED for event in result.events)


@pytest.mark.parametrize("state", [state for state in MachineState if state is not MachineState.RECOVERING])
def test_recovery_completion_is_rejected_outside_recovering(state: MachineState) -> None:
    machine = _machine_for_state(state)

    with pytest.raises(MachineTransitionError, match=f"complete recovery.*{state.value}"):
        complete_recovery(machine, NOW)


@pytest.mark.parametrize("state", [MachineState.READY, MachineState.FLUSH_REQUIRED])
def test_flush_may_start_from_ready_or_flush_required(state: MachineState) -> None:
    machine = MachineSnapshot(
        state=state,
        event_sequence=5,
        interrupted_run_id="run-interrupted" if state is MachineState.FLUSH_REQUIRED else None,
    )

    result = start_flush(machine, NOW)
    assert result.machine.state is MachineState.FLUSHING
    assert result.machine.active_run_id is None
    assert result.machine.interrupted_run_id == machine.interrupted_run_id
    assert result.events[0].event_type is MachineEventType.FLUSH_STARTED


@pytest.mark.parametrize(
    "state",
    [
        MachineState.STARTING,
        MachineState.BUSY,
        MachineState.RECOVERY_REQUIRED,
        MachineState.RECOVERING,
        MachineState.FLUSHING,
    ],
)
def test_flush_is_rejected_from_disallowed_states(state: MachineState) -> None:
    machine = _machine_for_state(state)

    with pytest.raises(MachineTransitionError, match=f"start flush.*{state.value}"):
        start_flush(machine, NOW)


def test_ready_snapshot_rejects_active_run_id() -> None:
    with pytest.raises(ValidationError, match="READY requires active_run_id to be empty"):
        MachineSnapshot(
            state=MachineState.READY, event_sequence=4, active_run_id="run-1"
        )


def test_active_execution_is_allowed_only_for_matching_busy_run() -> None:
    intent = PhaseExecutionIntent(
        execution_id="execution-1",
        run_id="run-1",
        phase=RunPhase.P1_TRANSFER_S_TO_REACTOR,
        claimed_at=NOW,
    )
    machine = MachineSnapshot(
        state=MachineState.BUSY,
        event_sequence=4,
        active_run_id="run-1",
        active_execution=intent,
    )

    assert machine.active_execution == intent
    with pytest.raises(ValidationError, match="must match active_run_id"):
        MachineSnapshot(
            state=MachineState.BUSY,
            event_sequence=4,
            active_run_id="run-other",
            active_execution=intent,
        )
    with pytest.raises(ValidationError, match="active_execution to be empty"):
        MachineSnapshot(
            state=MachineState.READY,
            event_sequence=4,
            active_execution=intent,
        )


def test_legacy_machine_snapshot_defaults_active_execution_to_none() -> None:
    machine = MachineSnapshot.model_validate(
        {
            "state": "BUSY",
            "event_sequence": 4,
            "active_run_id": "run-1",
        }
    )

    assert machine.active_execution is None


def test_execution_intent_rejects_unsupported_phase() -> None:
    with pytest.raises(ValidationError, match="does not support"):
        PhaseExecutionIntent(
            execution_id="execution-1",
            run_id="run-1",
            phase=RunPhase.READY,
            claimed_at=NOW,
        )


@pytest.mark.parametrize(
    ("field_name", "expected_message"),
    [
        ("execution_id", "execution_id must not be empty"),
        ("run_id", "run_id must not be empty"),
    ],
)
def test_execution_intent_rejects_blank_identifier_with_specific_message(
    field_name: str, expected_message: str
) -> None:
    values = {
        "execution_id": "execution-1",
        "run_id": "run-1",
        "phase": RunPhase.P1_TRANSFER_S_TO_REACTOR,
        "claimed_at": NOW,
    }
    values[field_name] = "   "

    with pytest.raises(ValidationError, match=expected_message):
        PhaseExecutionIntent(**values)


def valid_execution_claim_event(**updates: object) -> MachineEvent:
    values = {
        "sequence_number": 4,
        "occurred_at": NOW,
        "event_type": MachineEventType.PHASE_EXECUTION_CLAIMED,
        "machine_state": MachineState.BUSY,
        "run_id": "run-1",
        "message": "Guided Demo phase execution claimed",
        "execution_id": "execution-1",
        "execution_phase": RunPhase.P1_TRANSFER_S_TO_REACTOR,
    }
    values.update(updates)
    return MachineEvent(**values)


def test_valid_execution_claim_event_is_accepted() -> None:
    event = valid_execution_claim_event()

    assert event.event_type is MachineEventType.PHASE_EXECUTION_CLAIMED


@pytest.mark.parametrize(
    ("updates", "expected_message"),
    [
        ({"machine_state": MachineState.READY}, "BUSY machine_state"),
        ({"run_id": None}, "non-empty run_id"),
        ({"run_id": "   "}, "non-empty run_id"),
        ({"execution_id": None}, "non-empty execution_id"),
        ({"execution_id": "   "}, "non-empty execution_id"),
        ({"execution_phase": None}, "requires execution_phase"),
        (
            {"execution_phase": RunPhase.READY},
            "execution_phase does not support",
        ),
        (
            {"occurred_at": datetime(2026, 7, 18, 12, 0)},
            "occurred_at must be timezone-aware",
        ),
    ],
)
def test_execution_claim_event_rejects_invalid_invariant(
    updates: dict[str, object], expected_message: str
) -> None:
    with pytest.raises(ValidationError, match=expected_message):
        valid_execution_claim_event(**updates)


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("execution_id", "execution-1"),
        ("execution_phase", RunPhase.P1_TRANSFER_S_TO_REACTOR),
    ],
)
def test_non_claim_event_rejects_execution_metadata(
    field_name: str, value: object
) -> None:
    values = {
        "sequence_number": 1,
        "occurred_at": NOW,
        "event_type": MachineEventType.MACHINE_CREATED,
        "machine_state": MachineState.STARTING,
        "message": "Machine lifecycle created",
        field_name: value,
    }

    with pytest.raises(ValidationError, match="execution metadata requires"):
        MachineEvent(**values)


@pytest.mark.parametrize(
    ("snapshot_data", "message"),
    [
        (
            {"state": MachineState.READY, "event_sequence": -1},
            "greater than or equal to 0",
        ),
        (
            {
                "state": MachineState.READY,
                "event_sequence": 1,
                "interrupted_run_id": "run-1",
            },
            "READY requires interrupted_run_id to be empty",
        ),
        (
            {"state": MachineState.BUSY, "event_sequence": 1},
            "BUSY requires active_run_id",
        ),
        (
            {
                "state": MachineState.BUSY,
                "event_sequence": 1,
                "active_run_id": "run-1",
                "interrupted_run_id": "run-old",
            },
            "active_run_id and interrupted_run_id cannot both be set",
        ),
        (
            {"state": MachineState.RECOVERING, "event_sequence": 1},
            "RECOVERING requires interrupted_run_id",
        ),
        (
            {"state": MachineState.RECOVERY_REQUIRED, "event_sequence": 1},
            "RECOVERY_REQUIRED requires interrupted_run_id",
        ),
        (
            {
                "state": MachineState.RECOVERY_REQUIRED,
                "event_sequence": 1,
                "interrupted_run_id": "run-1",
            },
            "RECOVERY_REQUIRED requires exactly one recovery reason",
        ),
        (
            {
                "state": MachineState.RECOVERY_REQUIRED,
                "event_sequence": 1,
                "interrupted_run_id": "run-1",
                "runtime_fault_reason": RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED,
            },
            "RECOVERY_REQUIRED requires hardware_outcome_unknown",
        ),
        (
            {
                "state": MachineState.RECOVERY_REQUIRED,
                "event_sequence": 1,
                "interrupted_run_id": "run-1",
                "runtime_fault_reason": RuntimeHardwareFaultReason.CAROUSEL_MOVEMENT_FAILED,
                "hardware_outcome_unknown": True,
            },
            "carousel_position_untrusted must match",
        ),
        (
            {
                "state": MachineState.RECOVERY_REQUIRED,
                "event_sequence": 1,
                "interrupted_run_id": "run-1",
                "runtime_fault_reason": RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED,
                "hardware_outcome_unknown": True,
                "carousel_position_untrusted": True,
            },
            "carousel_position_untrusted must match",
        ),
        (
            {
                "state": MachineState.RECOVERING,
                "event_sequence": 1,
                "active_run_id": "run-1",
                "interrupted_run_id": "run-old",
            },
            "active_run_id and interrupted_run_id cannot both be set",
        ),
        (
            {
                "state": MachineState.FLUSH_REQUIRED,
                "event_sequence": 1,
                "active_run_id": "run-1",
            },
            "FLUSH_REQUIRED requires active_run_id to be empty",
        ),
        (
            {
                "state": MachineState.FLUSHING,
                "event_sequence": 1,
                "active_run_id": "run-1",
            },
            "FLUSHING requires active_run_id to be empty",
        ),
        (
            {
                "state": MachineState.BUSY,
                "event_sequence": 1,
                "active_run_id": "   ",
            },
            "run identifier must not be empty",
        ),
        (
            {
                "state": MachineState.FLUSH_REQUIRED,
                "event_sequence": 1,
                "interrupted_run_id": "",
            },
            "run identifier must not be empty",
        ),
    ],
)
def test_machine_snapshot_rejects_invalid_domain_invariants(
    snapshot_data: dict, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        MachineSnapshot(**snapshot_data)


@pytest.mark.parametrize(
    "metadata",
    [
        {"runtime_fault_reason": RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED},
        {"hardware_outcome_unknown": True},
        {"carousel_position_untrusted": True},
    ],
)
@pytest.mark.parametrize(
    "state",
    [state for state in MachineState if state is not MachineState.RECOVERY_REQUIRED],
)
def test_existing_states_reject_runtime_fault_metadata(
    state: MachineState,
    metadata: dict,
) -> None:
    snapshot_data = _machine_for_state(state).model_dump()
    snapshot_data.update(metadata)

    with pytest.raises(
        ValidationError,
        match=f"{state.value} requires default runtime fault metadata",
    ):
        MachineSnapshot(**snapshot_data)


def test_machine_event_sequence_starts_at_one() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 1"):
        MachineEvent(
            sequence_number=0,
            occurred_at=NOW,
            event_type=MachineEventType.MACHINE_CREATED,
            machine_state=MachineState.STARTING,
            message="Machine lifecycle created",
        )


def test_flush_completion_returns_ready_and_clears_interrupted_run() -> None:
    flush_required = complete_recovery(recovering_machine(), NOW).machine
    flushing = start_flush(flush_required, NOW).machine
    result = complete_flush(flushing, NOW)

    assert result.machine.state is MachineState.READY
    assert result.machine.active_run_id is None
    assert result.machine.interrupted_run_id is None
    assert result.events[0].event_type is MachineEventType.FLUSH_COMPLETED


@pytest.mark.parametrize("state", [state for state in MachineState if state is not MachineState.FLUSHING])
def test_flush_completion_is_rejected_outside_flushing(state: MachineState) -> None:
    machine = _machine_for_state(state)

    with pytest.raises(MachineTransitionError, match=f"complete flush.*{state.value}"):
        complete_flush(machine, NOW)


def test_event_timestamps_and_sequences_are_caller_controlled_and_strict() -> None:
    created = create_machine(NOW)
    startup_time = NOW + timedelta(seconds=1)
    started_time = NOW + timedelta(seconds=2)
    startup = complete_startup(created.machine, startup_time)
    started = start_run(startup.machine, "run-1", started_time)
    events = (*created.events, *startup.events, *started.events)

    assert [event.sequence_number for event in events] == [1, 2, 3]
    assert [event.occurred_at for event in events] == [NOW, startup_time, started_time]
    assert started.machine.event_sequence == 3


def test_events_have_transition_state_and_no_hardware_or_volume_claims() -> None:
    transitions = (
        complete_stop_demo(busy_machine(), "run-1", NOW),
        detect_interrupted_startup(starting_machine(), "run-interrupted", NOW),
        start_flush(ready_machine(), NOW),
    )
    forbidden = (
        "ack",
        "serial",
        "valve position",
        "motor position",
        "delivered volume",
        "measured volume",
    )

    expected_event_states = (
        (MachineState.FLUSH_REQUIRED,),
        (MachineState.STARTING, MachineState.RECOVERING),
        (MachineState.FLUSHING,),
    )
    for result, event_states in zip(transitions, expected_event_states, strict=True):
        assert tuple(event.machine_state for event in result.events) == event_states
        assert all(
            claim not in event.message.lower()
            for event in result.events
            for claim in forbidden
        )


def _complete_startup(machine: MachineSnapshot):
    return complete_startup(machine, NOW)


def _detect_interrupted_startup(machine: MachineSnapshot):
    return detect_interrupted_startup(machine, "run-interrupted", NOW)


def _start_run(machine: MachineSnapshot):
    return start_run(machine, "run-1", NOW)


def _complete_run(machine: MachineSnapshot):
    return complete_run(machine, "run-1", NOW)


def _complete_stop_demo(machine: MachineSnapshot):
    return complete_stop_demo(machine, "run-1", NOW)


def _record_runtime_hardware_fault(machine: MachineSnapshot):
    return record_runtime_hardware_fault(
        machine,
        run_id="run-1",
        occurred_at=NOW,
        reason=RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED,
    )


def _complete_recovery(machine: MachineSnapshot):
    return complete_recovery(machine, NOW)


def _start_flush(machine: MachineSnapshot):
    return start_flush(machine, NOW)


def _complete_flush(machine: MachineSnapshot):
    return complete_flush(machine, NOW)


TRANSITION_OPERATIONS = (
    ("complete startup", _complete_startup, {MachineState.STARTING: MachineState.READY}),
    (
        "detect interrupted startup",
        _detect_interrupted_startup,
        {MachineState.STARTING: MachineState.RECOVERING},
    ),
    ("start run", _start_run, {MachineState.READY: MachineState.BUSY}),
    ("complete run", _complete_run, {MachineState.BUSY: MachineState.READY}),
    (
        "complete Stop demo",
        _complete_stop_demo,
        {MachineState.BUSY: MachineState.FLUSH_REQUIRED},
    ),
    (
        "record runtime hardware fault",
        _record_runtime_hardware_fault,
        {MachineState.BUSY: MachineState.RECOVERY_REQUIRED},
    ),
    (
        "complete recovery",
        _complete_recovery,
        {MachineState.RECOVERING: MachineState.FLUSH_REQUIRED},
    ),
    (
        "start flush",
        _start_flush,
        {
            MachineState.READY: MachineState.FLUSHING,
            MachineState.FLUSH_REQUIRED: MachineState.FLUSHING,
        },
    ),
    ("complete flush", _complete_flush, {MachineState.FLUSHING: MachineState.READY}),
)


@pytest.mark.parametrize(
    ("operation_name", "operation", "allowed_transitions"), TRANSITION_OPERATIONS
)
@pytest.mark.parametrize("source_state", list(MachineState))
def test_public_operations_allow_only_the_exact_transition_matrix(
    operation_name, operation, allowed_transitions, source_state: MachineState
) -> None:
    machine = _machine_for_state(source_state)
    original = machine.model_copy(deep=True)
    expected_state = allowed_transitions.get(source_state)

    if expected_state is None:
        with pytest.raises(MachineTransitionError, match=source_state.value):
            operation(machine)
        assert machine == original
        return

    result = operation(machine)
    assert result.machine.state is expected_state, operation_name
    expected_event_count = 2 if operation_name == "detect interrupted startup" else 1
    assert len(result.events) == expected_event_count
    assert machine == original
