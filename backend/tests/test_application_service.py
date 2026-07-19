from datetime import UTC, datetime, timedelta

import pytest

from app.demo.application_service import (
    GuidedDemoApplicationError,
    GuidedDemoApplicationService,
)
from app.demo.events import DomainEventType
from app.demo.machine_events import MachineEventType
from app.demo.machine_lifecycle import (
    MachineTransitionError,
    complete_startup,
    create_machine,
)
from app.demo.machine_models import MachineState
from app.demo.models import AdditionOrder, DemoConfiguration, DemoExecutionSettings
from app.demo.phases import RunPhase
from app.demo.run_models import RunStatus
from app.persistence.sqlite_store import SQLiteStore

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)
SETTINGS = DemoExecutionSettings(
    sf_settling_duration_seconds="12.5",
    fraction_count=4,
    fraction_duration_seconds="30.25",
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


def persist_ready_machine(store: SQLiteStore) -> None:
    created = create_machine(NOW)
    ready = complete_startup(created.machine, NOW + timedelta(seconds=1))
    store.persist_machine_transition(created.machine, created.events)
    store.persist_machine_transition(ready.machine, ready.events)


def create_and_start_run(
    service: GuidedDemoApplicationService,
    configuration: DemoConfiguration,
):
    service.create_run("run-1", configuration, SETTINGS, NOW)
    return service.start_run("run-1", NOW + timedelta(seconds=2))


def test_create_run_persists_run_without_creating_machine(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        service = GuidedDemoApplicationService(store)
        result = service.create_run("run-1", configuration, SETTINGS, NOW)

        assert store.load_demo_run("run-1") == result.run
        assert store.load_machine_snapshot() is None
        assert result.machine is None
        assert result.run_events[0].event_type is DomainEventType.RUN_CREATED


def test_start_run_atomically_starts_run_and_assigns_machine(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        persist_ready_machine(store)
        service = GuidedDemoApplicationService(store)
        service.create_run("run-1", configuration, SETTINGS, NOW)

        result = service.start_run("run-1", NOW + timedelta(seconds=2))

        assert (result.run.status, result.run.phase) == (
            RunStatus.RUNNING,
            RunPhase.P1_ASPIRATE_S,
        )
        assert result.machine is not None
        assert (result.machine.state, result.machine.active_run_id) == (
            MachineState.BUSY,
            "run-1",
        )
        assert [event.sequence_number for event in result.run_events] == [2, 3]
        assert result.machine_events[0].sequence_number == 3
        assert store.load_demo_run("run-1") == result.run
        assert store.load_machine_snapshot() == result.machine


def test_start_run_is_rejected_when_machine_is_missing(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        service = GuidedDemoApplicationService(store)
        created = service.create_run("run-1", configuration, SETTINGS, NOW)

        with pytest.raises(GuidedDemoApplicationError, match="machine snapshot"):
            service.start_run("run-1", NOW)

        assert store.load_demo_run("run-1") == created.run
        assert store.load_machine_snapshot() is None


def test_start_run_is_rejected_when_run_is_missing() -> None:
    with SQLiteStore() as store:
        persist_ready_machine(store)
        service = GuidedDemoApplicationService(store)
        original_machine = store.load_machine_snapshot()
        original_events = store.load_events()

        with pytest.raises(GuidedDemoApplicationError, match="was not found"):
            service.start_run("missing", NOW)

        assert store.load_demo_run("missing") is None
        assert store.load_machine_snapshot() == original_machine
        assert store.load_events() == original_events


def test_start_run_is_rejected_when_machine_is_not_ready(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        created_machine = create_machine(NOW)
        store.persist_machine_transition(
            created_machine.machine, created_machine.events
        )
        service = GuidedDemoApplicationService(store)
        created_run = service.create_run("run-1", configuration, SETTINGS, NOW)

        with pytest.raises(MachineTransitionError, match="run start requires READY"):
            service.start_run("run-1", NOW)

        assert store.load_demo_run("run-1") == created_run.run
        assert store.load_machine_snapshot() == created_machine.machine


def test_intermediate_phase_completion_changes_only_run(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        persist_ready_machine(store)
        service = GuidedDemoApplicationService(store)
        started = create_and_start_run(service, configuration)

        result = service.complete_current_phase("run-1", NOW + timedelta(seconds=3))

        assert (result.run.status, result.run.phase) == (
            RunStatus.RUNNING,
            RunPhase.P1_DISPENSE_S_TO_REACTOR,
        )
        assert result.machine == started.machine
        assert result.machine_events == ()
        assert store.load_machine_snapshot() == started.machine
        assert result.run_events[-1].sequence_number == 5


def test_final_phase_completion_atomically_completes_run_and_releases_machine(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        persist_ready_machine(store)
        service = GuidedDemoApplicationService(store)
        result = create_and_start_run(service, configuration)
        while result.run.phase is not RunPhase.COLUMN_FRACTION_COLLECTION:
            result = service.complete_current_phase("run-1", NOW)

        result = service.complete_current_phase("run-1", NOW)

        assert (result.run.status, result.run.phase) == (
            RunStatus.COMPLETED,
            RunPhase.COMPLETED,
        )
        assert result.machine is not None
        assert (result.machine.state, result.machine.active_run_id) == (
            MachineState.READY,
            None,
        )
        assert result.run_events[-1].event_type is DomainEventType.RUN_COMPLETED
        assert result.machine_events[-1].event_type is MachineEventType.RUN_COMPLETED
        assert store.load_demo_run("run-1") == result.run
        assert store.load_machine_snapshot() == result.machine


def test_request_stop_demo_keeps_machine_busy(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        persist_ready_machine(store)
        service = GuidedDemoApplicationService(store)
        started = create_and_start_run(service, configuration)

        result = service.request_stop_demo("run-1", NOW)

        assert result.run.status is RunStatus.ABORTING
        assert result.machine == started.machine
        assert result.machine is not None
        assert result.machine.state is MachineState.BUSY
        assert result.machine_events == ()
        assert result.run_events[0].event_type is DomainEventType.ABORT_REQUESTED


def test_confirm_stop_demo_atomically_aborts_run_and_requires_flush(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        persist_ready_machine(store)
        service = GuidedDemoApplicationService(store)
        create_and_start_run(service, configuration)
        service.request_stop_demo("run-1", NOW)

        result = service.confirm_stop_demo("run-1", NOW)

        assert result.run.status is RunStatus.ABORTED
        assert result.machine is not None
        assert (result.machine.state, result.machine.active_run_id) == (
            MachineState.FLUSH_REQUIRED,
            None,
        )
        assert result.run_events[0].event_type is DomainEventType.RUN_ABORTED
        assert (
            result.machine_events[0].event_type
            is MachineEventType.STOP_DEMO_COMPLETED
        )
        assert store.load_demo_run("run-1") == result.run
        assert store.load_machine_snapshot() == result.machine


def test_wrong_active_run_is_rejected_without_writes(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        persist_ready_machine(store)
        service = GuidedDemoApplicationService(store)
        create_and_start_run(service, configuration)
        other = service.create_run("run-2", configuration, SETTINGS, NOW)
        original_machine = store.load_machine_snapshot()
        original_events = store.load_events()

        with pytest.raises(GuidedDemoApplicationError, match="does not match"):
            service.complete_current_phase("run-2", NOW)

        assert store.load_demo_run("run-2") == other.run
        assert store.load_machine_snapshot() == original_machine
        assert store.load_events() == original_events
