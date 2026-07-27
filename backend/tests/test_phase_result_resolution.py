from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.demo.execution_lifecycle import claim_phase_execution
from app.demo.lifecycle import (
    complete_current_phase,
    create_demo_run,
    request_abort,
    start_run,
)
from app.demo.machine_events import MachineEvent, MachineEventType
from app.demo.machine_lifecycle import (
    MachineTransitionError,
    complete_recovery,
    complete_startup,
    create_machine,
    start_run as start_machine_run,
)
from app.demo.machine_models import (
    MachineState,
    PhaseExecutionOutcome,
    PhaseExecutionResult,
    RuntimeHardwareFaultReason,
)
from app.demo.models import AdditionOrder, DemoConfiguration, DemoExecutionSettings
from app.demo.phase_result_resolution import (
    ExecutionIdMismatchError,
    InvalidExecutionResultError,
    NoActiveExecutionError,
    resolve_phase_execution,
)
from app.demo.phases import HARDWARE_EXECUTION_PHASES, RunPhase
from app.demo.run_models import RunStatus

NOW = datetime(2026, 7, 27, 12, tzinfo=UTC)
CONFIGURATION = DemoConfiguration(
    b1_ratio_percent="50",
    total_mixture_volume_ml="10",
    combined_b1_b2_volume_ml="4",
    addition_order=AdditionOrder.B1_THEN_B2,
    addition_speed_command_percent="50",
    reactor_mixing_command_percent="50",
    sf_mixing_command_percent="50",
    simulated_target_temperature_c="25",
    reaction_duration_seconds="60",
    delay_between_additions_seconds="5",
)
SETTINGS = DemoExecutionSettings(
    sf_settling_duration_seconds="10",
    fraction_count=3,
    fraction_duration_seconds="5",
)


def _active_aggregate(phase: RunPhase = RunPhase.P1_TRANSFER_S_TO_REACTOR):
    created = create_demo_run("run-1", CONFIGURATION, SETTINGS, NOW)
    run = start_run(created.run, NOW).run
    while run.phase is not phase:
        run = complete_current_phase(run, NOW).run
    machine = start_machine_run(
        complete_startup(create_machine(NOW).machine, NOW).machine,
        "run-1",
        NOW,
    ).machine
    claimed = claim_phase_execution(
        run, machine, execution_id="execution-1", claimed_at=NOW
    )
    return run, claimed.machine


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ({"execution_id": " "}, "execution_id must not be empty"),
        ({"reported_at": datetime(2026, 7, 27)}, "timezone-aware"),
        (
            {
                "outcome": PhaseExecutionOutcome.HARDWARE_COMMAND_FAILED,
                "failure_reason": None,
            },
            "requires failure_reason",
        ),
        (
            {
                "outcome": PhaseExecutionOutcome.REQUIRED_CLEANUP_FAILED,
                "cleanup_failure_reason": None,
            },
            "requires cleanup_failure_reason",
        ),
        (
            {
                "outcome": PhaseExecutionOutcome.COMPLETED,
                "failure_reason": "contradiction",
            },
            "rejects failure metadata",
        ),
    ],
)
def test_result_validation(values: dict[str, object], message: str) -> None:
    defaults = {
        "execution_id": "execution-1",
        "outcome": PhaseExecutionOutcome.COMPLETED,
        "reported_at": NOW,
    }
    with pytest.raises(ValidationError, match=message):
        PhaseExecutionResult(**(defaults | values))


def test_matching_result_rejections_preserve_aggregates() -> None:
    run, machine = _active_aggregate()
    original = (run, machine)
    with pytest.raises(ExecutionIdMismatchError, match="EXECUTION_ID_MISMATCH"):
        resolve_phase_execution(
            run,
            machine,
            PhaseExecutionResult(
                execution_id="stale",
                outcome=PhaseExecutionOutcome.COMPLETED,
                reported_at=NOW,
            ),
        )
    with pytest.raises(InvalidExecutionResultError, match="precedes claimed_at"):
        resolve_phase_execution(
            run,
            machine,
            PhaseExecutionResult(
                execution_id="execution-1",
                outcome=PhaseExecutionOutcome.COMPLETED,
                reported_at=NOW - timedelta(microseconds=1),
            ),
        )
    with pytest.raises(NoActiveExecutionError, match="NO_ACTIVE_EXECUTION"):
        resolve_phase_execution(
            run,
            machine.model_copy(update={"active_execution": None}),
            PhaseExecutionResult(
                execution_id="execution-1",
                outcome=PhaseExecutionOutcome.COMPLETED,
                reported_at=NOW,
            ),
        )
    assert (run, machine) == original


@pytest.mark.parametrize("phase", sorted(HARDWARE_EXECUTION_PHASES))
def test_every_hardware_phase_completed_resolves_without_next_claim(
    phase: RunPhase,
) -> None:
    run, machine = _active_aggregate(phase)
    resolution = resolve_phase_execution(
        run,
        machine,
        PhaseExecutionResult(
            execution_id="execution-1",
            outcome=PhaseExecutionOutcome.COMPLETED,
            reported_at=NOW,
        ),
    )
    assert resolution.machine.active_execution is None
    if phase is RunPhase.COLUMN_FRACTION_COLLECTION:
        assert (resolution.run.status, resolution.run.phase) == (
            RunStatus.COMPLETED,
            RunPhase.COMPLETED,
        )
        assert resolution.machine.state is MachineState.READY
    else:
        assert resolution.run.status is RunStatus.RUNNING
        assert resolution.run.phase is not phase
        assert resolution.machine.state is MachineState.BUSY


@pytest.mark.parametrize(
    "outcome",
    [
        PhaseExecutionOutcome.COMPLETED,
        PhaseExecutionOutcome.STOPPED_AT_SAFE_BOUNDARY,
    ],
)
def test_aborting_result_completes_stop_without_advancing(
    outcome: PhaseExecutionOutcome,
) -> None:
    run, machine = _active_aggregate()
    aborting = request_abort(run, NOW).run
    resolution = resolve_phase_execution(
        aborting,
        machine,
        PhaseExecutionResult(
            execution_id="execution-1",
            outcome=outcome,
            reported_at=NOW,
        ),
    )
    assert (resolution.run.status, resolution.run.phase) == (
        RunStatus.ABORTED,
        run.phase,
    )
    assert resolution.machine.state is MachineState.FLUSH_REQUIRED


def test_safe_stop_without_request_is_rejected() -> None:
    run, machine = _active_aggregate()
    with pytest.raises(InvalidExecutionResultError, match="requires ABORTING"):
        resolve_phase_execution(
            run,
            machine,
            PhaseExecutionResult(
                execution_id="execution-1",
                outcome=PhaseExecutionOutcome.STOPPED_AT_SAFE_BOUNDARY,
                reported_at=NOW,
            ),
        )


@pytest.mark.parametrize(
    ("outcome", "metadata", "runtime_reason"),
    [
        (
            PhaseExecutionOutcome.HARDWARE_COMMAND_FAILED,
            {
                "failure_reason": "pump failed",
                "runtime_fault_reason": (
                    RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED
                ),
            },
            RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED,
        ),
        (
            PhaseExecutionOutcome.REQUIRED_CLEANUP_FAILED,
            {
                "cleanup_failure_reason": "valve cleanup failed",
                "primary_failure_reason": "pump failed first",
                "runtime_fault_reason": (
                    RuntimeHardwareFaultReason.REQUIRED_FOLLOWUP_FAILED
                ),
            },
            RuntimeHardwareFaultReason.REQUIRED_FOLLOWUP_FAILED,
        ),
    ],
)
@pytest.mark.parametrize("aborting", [False, True])
def test_failures_fault_run_and_enter_recovery(
    outcome: PhaseExecutionOutcome,
    metadata: dict[str, str],
    runtime_reason: RuntimeHardwareFaultReason,
    aborting: bool,
) -> None:
    run, machine = _active_aggregate()
    if aborting:
        run = request_abort(run, NOW).run
    resolution = resolve_phase_execution(
        run,
        machine,
        PhaseExecutionResult(
            execution_id="execution-1",
            outcome=outcome,
            reported_at=NOW,
            **metadata,
        ),
    )
    assert resolution.run.status is RunStatus.FAULTED
    assert resolution.machine.state is MachineState.RECOVERY_REQUIRED
    assert resolution.machine.runtime_fault_reason is runtime_reason
    assert resolution.machine.active_execution is None
    assert resolution.machine.carousel_position_untrusted is False
    assert all(
        event.event_type is not MachineEventType.RECOVERY_STARTED
        for event in resolution.machine_events
    )
    with pytest.raises(MachineTransitionError, match="requires RECOVERING"):
        complete_recovery(resolution.machine, NOW)


def test_carousel_failure_preserves_untrusted_position_classification() -> None:
    run, machine = _active_aggregate()
    resolution = resolve_phase_execution(
        run,
        machine,
        PhaseExecutionResult(
            execution_id="execution-1",
            outcome=PhaseExecutionOutcome.HARDWARE_COMMAND_FAILED,
            reported_at=NOW,
            failure_reason="carousel did not reach target",
            runtime_fault_reason=(
                RuntimeHardwareFaultReason.CAROUSEL_MOVEMENT_FAILED
            ),
        ),
    )
    assert resolution.machine.state is MachineState.RECOVERY_REQUIRED
    assert resolution.machine.carousel_position_untrusted is True
    assert (
        resolution.machine_events[-1].runtime_fault_reason
        is RuntimeHardwareFaultReason.CAROUSEL_MOVEMENT_FAILED
    )
    assert (
        resolution.machine_events[0].runtime_fault_reason
        is RuntimeHardwareFaultReason.CAROUSEL_MOVEMENT_FAILED
    )


def test_claim_event_rejects_resolution_only_metadata() -> None:
    run, machine = _active_aggregate()
    claim_event = MachineEvent(
        sequence_number=machine.event_sequence,
        occurred_at=NOW,
        event_type=MachineEventType.PHASE_EXECUTION_CLAIMED,
        machine_state=MachineState.BUSY,
        run_id=run.run_id,
        message="claim",
        execution_id="execution-1",
        execution_phase=run.phase,
    )
    with pytest.raises(ValidationError, match="rejects resolution metadata"):
        MachineEvent.model_validate(
            {
                **claim_event.model_dump(mode="python"),
                "runtime_fault_reason": (
                    RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED
                ),
            }
        )


def test_resolution_event_requires_busy_machine_state() -> None:
    run, machine = _active_aggregate()
    resolution = resolve_phase_execution(
        run,
        machine,
        PhaseExecutionResult(
            execution_id="execution-1",
            outcome=PhaseExecutionOutcome.COMPLETED,
            reported_at=NOW,
        ),
    )
    with pytest.raises(ValidationError, match="requires BUSY machine_state"):
        MachineEvent.model_validate(
            {
                **resolution.machine_events[0].model_dump(mode="python"),
                "machine_state": MachineState.READY,
            }
        )
