from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.demo.events import DomainEventType
from app.demo.lifecycle import (
    LifecycleTransitionError,
    complete_current_phase,
    confirm_abort,
    create_demo_run,
    fault_run,
    pause_run,
    request_abort,
    resume_run,
    start_run,
)
from app.demo.models import AdditionOrder, DemoConfiguration, DemoExecutionSettings
from app.demo.phases import RunPhase
from app.demo.run_models import DemoRun, RunStatus

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
EXECUTION_SETTINGS = DemoExecutionSettings(
    sf_settling_duration_seconds="12.345",
    fraction_count=6,
    fraction_duration_seconds="45.678",
)
WORKFLOW_PHASES = (
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
PAUSABLE_PHASES = {RunPhase.DELAY_BETWEEN_ADDITIONS, RunPhase.REACTION_HOLD}
DOWNSTREAM_PHASES = (
    RunPhase.SF_SETTLING,
    RunPhase.TRANSFER_SF_TO_COLUMN,
    RunPhase.COLUMN_FRACTION_COLLECTION,
)


@pytest.fixture
def configuration() -> DemoConfiguration:
    return DemoConfiguration(
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


def created_run(configuration: DemoConfiguration) -> DemoRun:
    return create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW).run


def running_at(configuration: DemoConfiguration, phase: RunPhase) -> DemoRun:
    run = start_run(created_run(configuration), NOW).run
    while run.phase is not phase:
        run = complete_current_phase(run, NOW).run
    return run


def test_creation_builds_immutable_run_and_configured_fluid_plan(
    configuration: DemoConfiguration,
) -> None:
    result = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)

    assert result.run.status is RunStatus.CREATED
    assert result.run.phase is RunPhase.READY
    assert result.run.configuration is configuration
    assert result.run.execution_settings is EXECUTION_SETTINGS
    assert result.run.fluid_plan.b1_configured_volume_ml == Decimal("1.6")
    assert result.run.fluid_plan.b2_configured_volume_ml == Decimal("2.4")
    assert result.run.fluid_plan.s_configured_volume_ml == Decimal("6")
    assert result.run.event_sequence == 1
    assert [event.event_type for event in result.events] == [DomainEventType.RUN_CREATED]
    with pytest.raises(ValidationError):
        result.run.status = RunStatus.RUNNING


def test_execution_settings_preserve_decimals_and_are_immutable() -> None:
    settings = DemoExecutionSettings(
        sf_settling_duration_seconds="0.0001",
        fraction_count=3,
        fraction_duration_seconds="10.123456789",
    )

    assert settings.sf_settling_duration_seconds == Decimal("0.0001")
    assert settings.fraction_duration_seconds == Decimal("10.123456789")
    with pytest.raises(ValidationError):
        settings.fraction_count = 4


def test_zero_settling_duration_is_accepted() -> None:
    settings = DemoExecutionSettings(
        sf_settling_duration_seconds="0",
        fraction_count=1,
        fraction_duration_seconds="1",
    )

    assert settings.sf_settling_duration_seconds == Decimal("0")


@pytest.mark.parametrize(
    "values",
    [
        {"sf_settling_duration_seconds": "-0.1"},
        {"fraction_duration_seconds": "0"},
        {"fraction_duration_seconds": "-0.1"},
        {"sf_settling_duration_seconds": "NaN"},
        {"fraction_duration_seconds": "Infinity"},
        {"fraction_count": 0},
        {"fraction_count": -1},
    ],
)
def test_invalid_execution_settings_are_rejected(values: dict) -> None:
    valid_values = {
        "sf_settling_duration_seconds": "1",
        "fraction_count": 1,
        "fraction_duration_seconds": "1",
    }

    with pytest.raises(ValidationError):
        DemoExecutionSettings(**(valid_values | values))


def test_runs_snapshot_execution_settings_independently(
    configuration: DemoConfiguration,
) -> None:
    first_settings = DemoExecutionSettings(
        sf_settling_duration_seconds="10.1",
        fraction_count=4,
        fraction_duration_seconds="20.2",
    )
    second_settings = DemoExecutionSettings(
        sf_settling_duration_seconds="30.3",
        fraction_count=8,
        fraction_duration_seconds="40.4",
    )

    first = create_demo_run("run-1", configuration, first_settings, NOW).run
    second = create_demo_run("run-2", configuration, second_settings, NOW).run

    assert first.execution_settings == first_settings
    assert second.execution_settings == second_settings
    assert first.execution_settings != second.execution_settings


def test_start_enters_first_phase_and_emits_ordered_events(
    configuration: DemoConfiguration,
) -> None:
    result = start_run(created_run(configuration), NOW)

    assert (result.run.status, result.run.phase) == (
        RunStatus.RUNNING,
        RunPhase.P1_ASPIRATE_S,
    )
    assert [event.event_type for event in result.events] == [
        DomainEventType.RUN_STARTED,
        DomainEventType.PHASE_STARTED,
    ]
    assert [(event.run_status, event.run_phase) for event in result.events] == [
        (RunStatus.RUNNING, RunPhase.READY),
        (RunStatus.RUNNING, RunPhase.P1_ASPIRATE_S),
    ]
    assert [event.sequence_number for event in result.events] == [2, 3]


def test_second_start_is_rejected(configuration: DemoConfiguration) -> None:
    run = start_run(created_run(configuration), NOW).run

    with pytest.raises(LifecycleTransitionError, match="Cannot start.*RUNNING.*P1_ASPIRATE_S"):
        start_run(run, NOW)


def test_completes_all_phases_in_strict_order(configuration: DemoConfiguration) -> None:
    run = start_run(created_run(configuration), NOW).run
    visited = [run.phase]

    while run.status is RunStatus.RUNNING:
        result = complete_current_phase(run, NOW)
        run = result.run
        visited.append(run.phase)

    assert visited == [*WORKFLOW_PHASES, RunPhase.COMPLETED]
    assert (run.status, run.phase) == (RunStatus.COMPLETED, RunPhase.COMPLETED)
    assert [event.event_type for event in result.events] == [
        DomainEventType.PHASE_COMPLETED,
        DomainEventType.RUN_COMPLETED,
    ]
    assert [(event.run_status, event.run_phase) for event in result.events] == [
        (RunStatus.RUNNING, RunPhase.COLUMN_FRACTION_COLLECTION),
        (RunStatus.COMPLETED, RunPhase.COMPLETED),
    ]


@pytest.mark.parametrize(
    ("current_phase", "next_phase"),
    [
        (RunPhase.SF_MIXING, RunPhase.SF_SETTLING),
        (RunPhase.SF_SETTLING, RunPhase.TRANSFER_SF_TO_COLUMN),
        (RunPhase.TRANSFER_SF_TO_COLUMN, RunPhase.COLUMN_FRACTION_COLLECTION),
        (RunPhase.COLUMN_FRACTION_COLLECTION, RunPhase.COMPLETED),
    ],
)
def test_downstream_phases_advance_in_strict_order(
    configuration: DemoConfiguration,
    current_phase: RunPhase,
    next_phase: RunPhase,
) -> None:
    run = running_at(configuration, current_phase)
    result = complete_current_phase(run, NOW)

    assert result.run.phase is next_phase
    assert result.run.status is (
        RunStatus.COMPLETED
        if next_phase is RunPhase.COMPLETED
        else RunStatus.RUNNING
    )
    assert result.run.event_sequence == run.event_sequence + 2
    assert result.events[-1].run_phase is next_phase
    assert result.events[-1].run_status is result.run.status


def test_sf_mixing_cannot_advance_directly_to_completed(
    configuration: DemoConfiguration,
) -> None:
    result = complete_current_phase(running_at(configuration, RunPhase.SF_MIXING), NOW)

    assert (result.run.status, result.run.phase) == (
        RunStatus.RUNNING,
        RunPhase.SF_SETTLING,
    )
    assert all(event.event_type is not DomainEventType.RUN_COMPLETED for event in result.events)


@pytest.mark.parametrize("status", [status for status in RunStatus if status is not RunStatus.RUNNING])
def test_phase_completion_requires_running_status(
    configuration: DemoConfiguration, status: RunStatus
) -> None:
    run = running_at(configuration, RunPhase.REACTION_HOLD).model_copy(update={"status": status})

    with pytest.raises(LifecycleTransitionError, match="complete current phase"):
        complete_current_phase(run, NOW)


def test_phase_progression_after_completion_is_rejected(configuration: DemoConfiguration) -> None:
    run = running_at(configuration, RunPhase.COLUMN_FRACTION_COLLECTION)
    completed = complete_current_phase(run, NOW).run

    with pytest.raises(LifecycleTransitionError):
        complete_current_phase(completed, NOW)


@pytest.mark.parametrize("phase", sorted(PAUSABLE_PHASES, key=list(RunPhase).index))
def test_pause_and_resume_preserve_allowed_phase(
    configuration: DemoConfiguration, phase: RunPhase
) -> None:
    run = running_at(configuration, phase)
    paused = pause_run(run, NOW)

    assert (paused.run.status, paused.run.phase) == (RunStatus.PAUSED, phase)
    assert paused.events[0].event_type is DomainEventType.RUN_PAUSED
    with pytest.raises(LifecycleTransitionError):
        complete_current_phase(paused.run, NOW)

    resumed = resume_run(paused.run, NOW)
    assert (resumed.run.status, resumed.run.phase) == (RunStatus.RUNNING, phase)
    assert resumed.events[0].event_type is DomainEventType.RUN_RESUMED


@pytest.mark.parametrize("phase", [phase for phase in RunPhase if phase not in PAUSABLE_PHASES])
def test_pause_is_rejected_in_every_other_phase(
    configuration: DemoConfiguration, phase: RunPhase
) -> None:
    if phase is RunPhase.READY:
        run = created_run(configuration)
    elif phase is RunPhase.COMPLETED:
        run = complete_current_phase(
            running_at(configuration, RunPhase.COLUMN_FRACTION_COLLECTION), NOW
        ).run
    else:
        run = running_at(configuration, phase)

    with pytest.raises(LifecycleTransitionError, match="Cannot pause"):
        pause_run(run, NOW)


def test_resume_from_non_paused_status_is_rejected(configuration: DemoConfiguration) -> None:
    with pytest.raises(LifecycleTransitionError, match="Cannot resume"):
        resume_run(running_at(configuration, RunPhase.REACTION_HOLD), NOW)


@pytest.mark.parametrize("paused", [False, True])
def test_abort_request_preserves_phase_and_requires_confirmation(
    configuration: DemoConfiguration, paused: bool
) -> None:
    run = running_at(configuration, RunPhase.REACTION_HOLD)
    if paused:
        run = pause_run(run, NOW).run

    requested = request_abort(run, NOW)
    assert (requested.run.status, requested.run.phase) == (RunStatus.ABORTING, run.phase)
    assert requested.events[0].event_type is DomainEventType.ABORT_REQUESTED
    confirmed = confirm_abort(requested.run, NOW)
    assert (confirmed.run.status, confirmed.run.phase) == (RunStatus.ABORTED, run.phase)
    assert confirmed.events[0].event_type is DomainEventType.RUN_ABORTED
    with pytest.raises(LifecycleTransitionError):
        resume_run(confirmed.run, NOW)
    with pytest.raises(LifecycleTransitionError):
        complete_current_phase(confirmed.run, NOW)


def test_confirm_abort_requires_aborting_status(configuration: DemoConfiguration) -> None:
    with pytest.raises(LifecycleTransitionError, match="Cannot confirm abort"):
        confirm_abort(running_at(configuration, RunPhase.REACTION_HOLD), NOW)


@pytest.mark.parametrize("phase", DOWNSTREAM_PHASES)
def test_abort_remains_valid_in_new_active_phases(
    configuration: DemoConfiguration, phase: RunPhase
) -> None:
    run = running_at(configuration, phase)

    requested = request_abort(run, NOW)
    confirmed = confirm_abort(requested.run, NOW)

    assert (requested.run.status, requested.run.phase) == (RunStatus.ABORTING, phase)
    assert (confirmed.run.status, confirmed.run.phase) == (RunStatus.ABORTED, phase)


@pytest.mark.parametrize("phase", DOWNSTREAM_PHASES)
def test_fault_remains_valid_in_new_active_phases(
    configuration: DemoConfiguration, phase: RunPhase
) -> None:
    run = running_at(configuration, phase)

    result = fault_run(run, NOW, "Operator interlock opened")

    assert (result.run.status, result.run.phase) == (RunStatus.FAULTED, phase)
    assert result.events[0].event_type is DomainEventType.RUN_FAULTED


@pytest.mark.parametrize("status", [RunStatus.RUNNING, RunStatus.PAUSED, RunStatus.ABORTING])
def test_fault_from_allowed_status_preserves_phase_and_reason(
    configuration: DemoConfiguration, status: RunStatus
) -> None:
    run = running_at(configuration, RunPhase.REACTION_HOLD)
    if status is RunStatus.PAUSED:
        run = pause_run(run, NOW).run
    elif status is RunStatus.ABORTING:
        run = request_abort(run, NOW).run

    result = fault_run(run, NOW, "Operator interlock opened")
    assert (result.run.status, result.run.phase) == (RunStatus.FAULTED, run.phase)
    assert result.events[0].event_type is DomainEventType.RUN_FAULTED
    assert result.events[0].reason == "Operator interlock opened"
    with pytest.raises(LifecycleTransitionError):
        complete_current_phase(result.run, NOW)


def test_fault_requires_non_empty_reason(configuration: DemoConfiguration) -> None:
    run = running_at(configuration, RunPhase.REACTION_HOLD)

    with pytest.raises(LifecycleTransitionError, match="non-empty reason"):
        fault_run(run, NOW, "  ")


def test_events_use_caller_timestamp_and_strict_sequence(configuration: DemoConfiguration) -> None:
    created = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)
    later = NOW + timedelta(seconds=1)
    started = start_run(created.run, later)

    events = (*created.events, *started.events)
    assert [event.occurred_at for event in events] == [NOW, later, later]
    assert [event.sequence_number for event in events] == [1, 2, 3]
    assert started.run.event_sequence == 3


def test_events_contain_no_hardware_or_volume_claims(configuration: DemoConfiguration) -> None:
    run = start_run(created_run(configuration), NOW).run
    events = complete_current_phase(run, NOW).events
    forbidden_claims = ("ack", "delivered", "measured", "pin", "motor position")

    assert all(
        claim not in event.message.lower() for event in events for claim in forbidden_claims
    )
