from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.demo.execution_lifecycle import (
    PhaseExecutionClaimError,
    PhaseExecutionStartCommitError,
    commit_phase_execution_start,
    claim_phase_execution,
)
from app.demo.lifecycle import create_demo_run, request_abort, start_run
from app.demo.machine_events import MachineEventType
from app.demo.machine_lifecycle import (
    complete_startup,
    create_machine,
    start_run as start_machine_run,
)
from app.demo.machine_models import (
    MachineSnapshot,
    MachineState,
    PhaseExecutionIntent,
)
from app.demo.models import (
    AdditionOrder,
    DemoConfiguration,
    DemoExecutionSettings,
)
from app.demo.phases import RunPhase

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
SETTINGS = DemoExecutionSettings(
    sf_settling_duration_seconds="12.5",
    fraction_count=4,
    fraction_duration_seconds="30.25",
)
CONFIGURATION = DemoConfiguration(
    b1_ratio_percent="40",
    total_mixture_volume_ml="10",
    combined_b1_b2_volume_ml="4",
    addition_order=AdditionOrder.B1_THEN_B2,
    addition_speed_command_percent="50",
    reactor_mixing_command_percent="60",
    sf_mixing_command_percent="40",
    simulated_target_temperature_c="25",
    reaction_duration_seconds="600",
    delay_between_additions_seconds="5",
)


def running_run():
    created = create_demo_run("run-1", CONFIGURATION, SETTINGS, NOW)
    return start_run(created.run, NOW).run


def busy_machine(run_id: str = "run-1"):
    created = create_machine(NOW)
    ready = complete_startup(created.machine, NOW)
    return start_machine_run(ready.machine, run_id, NOW).machine


def test_valid_running_hardware_phase_claim() -> None:
    run = running_run()
    machine = busy_machine()
    original_machine_dump = machine.model_dump(mode="python")

    result = claim_phase_execution(
        run,
        machine,
        execution_id="execution-1",
        claimed_at=NOW,
    )

    intent = result.machine.active_execution
    assert intent is not None
    assert (
        intent.execution_id,
        intent.run_id,
        intent.phase,
        intent.claimed_at,
    ) == ("execution-1", "run-1", run.phase, NOW)
    assert result.machine.state is MachineState.BUSY
    assert result.machine.active_run_id == "run-1"
    assert result.machine.event_sequence == machine.event_sequence + 1
    assert len(result.events) == 1
    event = result.events[0]
    assert event.event_type is MachineEventType.PHASE_EXECUTION_CLAIMED
    assert (event.run_id, event.execution_id, event.execution_phase) == (
        intent.run_id,
        intent.execution_id,
        intent.phase,
    )
    assert event.occurred_at == intent.claimed_at
    assert run == running_run()
    assert machine.model_dump(mode="python") == original_machine_dump
    assert result.machine.model_dump(mode="python") == {
        **original_machine_dump,
        "event_sequence": machine.event_sequence + 1,
        "active_execution": intent.model_dump(mode="python"),
    }


def test_claim_revalidates_resulting_machine_snapshot() -> None:
    invalid_machine = MachineState.BUSY
    machine = busy_machine()
    bypassed = type(machine).model_construct(
        **(
            machine.model_dump(mode="python")
            | {"interrupted_run_id": "run-interrupted"}
        ),
    )
    assert bypassed.state is invalid_machine

    with pytest.raises(ValidationError, match="cannot both be set"):
        claim_phase_execution(
            running_run(),
            bypassed,
            execution_id="execution-1",
            claimed_at=NOW,
        )


def test_claimed_intent_is_immutable() -> None:
    intent = claim_phase_execution(
        running_run(),
        busy_machine(),
        execution_id="execution-1",
        claimed_at=NOW,
    ).machine.active_execution
    assert intent is not None

    with pytest.raises(ValidationError):
        intent.execution_id = "changed"


def test_claim_rejects_blank_execution_id_with_specific_message() -> None:
    with pytest.raises(ValidationError, match="execution_id must not be empty"):
        claim_phase_execution(
            running_run(),
            busy_machine(),
            execution_id="   ",
            claimed_at=NOW,
        )


def test_claim_rejects_naive_claimed_at() -> None:
    with pytest.raises(ValidationError, match="claimed_at must be timezone-aware"):
        claim_phase_execution(
            running_run(),
            busy_machine(),
            execution_id="execution-1",
            claimed_at=datetime(2026, 7, 27, 12, 0),
        )


def test_legacy_execution_intent_defaults_start_commit_to_none() -> None:
    intent = PhaseExecutionIntent.model_validate(
        {
            "execution_id": "execution-legacy",
            "run_id": "run-1",
            "phase": RunPhase.P1_TRANSFER_S_TO_REACTOR,
            "claimed_at": NOW,
        }
    )

    assert intent.start_committed_at is None


def test_stop_won_still_requires_matching_prepared_phase() -> None:
    created = create_demo_run("run-1", CONFIGURATION, SETTINGS, NOW)
    running = start_run(created.run, NOW).run
    aborting = request_abort(running, NOW).run
    machine = start_machine_run(
        complete_startup(create_machine(NOW).machine, NOW).machine,
        "run-1",
        NOW,
    ).machine
    claimed = claim_phase_execution(
        running,
        machine,
        execution_id="execution-1",
        claimed_at=NOW,
    )
    intent = claimed.machine.active_execution
    assert intent is not None

    with pytest.raises(PhaseExecutionStartCommitError, match="active phase"):
        commit_phase_execution_start(
            aborting,
            claimed.machine,
            intent,
            expected_run_event_sequence=running.event_sequence,
            expected_phase=RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
            start_committed_at=NOW,
        )


def test_start_commit_revalidates_machine_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created = create_demo_run("run-1", CONFIGURATION, SETTINGS, NOW)
    running = start_run(created.run, NOW).run
    machine = start_machine_run(
        complete_startup(create_machine(NOW).machine, NOW).machine,
        "run-1",
        NOW,
    ).machine
    claimed = claim_phase_execution(
        running,
        machine,
        execution_id="execution-1",
        claimed_at=NOW,
    )
    intent = claimed.machine.active_execution
    assert intent is not None
    original_validate = MachineSnapshot.model_validate
    validated_values: list[object] = []

    def recording_validate(value: object):
        validated_values.append(value)
        return original_validate(value)

    monkeypatch.setattr(
        MachineSnapshot,
        "model_validate",
        staticmethod(recording_validate),
    )

    result = commit_phase_execution_start(
        running,
        claimed.machine,
        intent,
        expected_run_event_sequence=running.event_sequence,
        expected_phase=running.phase,
        start_committed_at=NOW,
    )

    assert validated_values
    assert result.machine.active_execution.start_committed_at == NOW


def test_claim_rejects_non_busy_machine() -> None:
    created = create_machine(NOW)
    ready = complete_startup(created.machine, NOW).machine

    with pytest.raises(PhaseExecutionClaimError, match="BUSY"):
        claim_phase_execution(
            running_run(),
            ready,
            execution_id="execution-1",
            claimed_at=NOW,
        )


def test_claim_rejects_wrong_active_run() -> None:
    with pytest.raises(PhaseExecutionClaimError, match="does not match"):
        claim_phase_execution(
            running_run(),
            busy_machine("run-other"),
            execution_id="execution-1",
            claimed_at=NOW,
        )


def test_claim_rejects_aborting_run() -> None:
    aborting = request_abort(running_run(), NOW).run

    with pytest.raises(PhaseExecutionClaimError, match="RUNNING"):
        claim_phase_execution(
            aborting,
            busy_machine(),
            execution_id="execution-1",
            claimed_at=NOW,
        )


def test_claim_rejects_unsupported_ready_phase() -> None:
    timed = running_run().model_copy(update={"phase": RunPhase.READY})

    with pytest.raises(PhaseExecutionClaimError, match="does not support"):
        claim_phase_execution(
            timed,
            busy_machine(),
            execution_id="execution-1",
            claimed_at=NOW,
        )


def test_claim_rejects_duplicate_active_execution() -> None:
    first = claim_phase_execution(
        running_run(),
        busy_machine(),
        execution_id="execution-1",
        claimed_at=NOW,
    )

    with pytest.raises(PhaseExecutionClaimError, match="already active"):
        claim_phase_execution(
            running_run(),
            first.machine,
            execution_id="execution-2",
            claimed_at=NOW,
        )
