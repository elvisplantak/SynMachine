import sqlite3
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
    complete_recovery,
    complete_startup,
    create_machine,
    detect_interrupted_startup,
)
from app.demo.machine_models import MachineState
from app.demo.models import AdditionOrder, DemoConfiguration, DemoExecutionSettings
from app.demo.phases import RunPhase
from app.demo.run_models import RunStatus
from app.persistence.sqlite_store import PersistenceDataError, SQLiteStore
from app.persistence.sqlite_store import PersistenceConflictError

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


def persist_flush_required_machine(store: SQLiteStore) -> None:
    created = create_machine(NOW)
    recovering = detect_interrupted_startup(
        created.machine, "run-interrupted", NOW + timedelta(seconds=1)
    )
    flush_required = complete_recovery(
        recovering.machine, NOW + timedelta(seconds=2)
    )
    store.persist_machine_transition(created.machine, created.events)
    store.persist_machine_transition(recovering.machine, recovering.events)
    store.persist_machine_transition(flush_required.machine, flush_required.events)


def test_initialize_machine_persists_starting_without_creating_run() -> None:
    with SQLiteStore() as store:
        service = GuidedDemoApplicationService(store)

        result = service.initialize_machine(NOW)

        assert result.machine.state is MachineState.STARTING
        assert result.machine.event_sequence == 1
        assert result.machine_events[0].event_type is MachineEventType.MACHINE_CREATED
        assert result.machine_events[0].occurred_at == NOW
        assert result.machine_events[0].sequence_number == 1
        assert store.load_machine_snapshot() == result.machine
        assert store.load_demo_run("run-1") is None


def test_duplicate_machine_initialization_is_rejected_without_writes() -> None:
    with SQLiteStore() as store:
        service = GuidedDemoApplicationService(store)
        initialized = service.initialize_machine(NOW)
        original_events = store.load_events()

        with pytest.raises(GuidedDemoApplicationError, match="already exists"):
            service.initialize_machine(NOW + timedelta(seconds=1))

        assert store.load_machine_snapshot() == initialized.machine
        assert store.load_events() == original_events


def test_initialize_machine_preserves_corrupt_snapshot_error(tmp_path) -> None:
    database = tmp_path / "corrupt-machine.db"
    with SQLiteStore(database) as store:
        GuidedDemoApplicationService(store).initialize_machine(NOW)
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE machine_snapshot SET snapshot_json = '{broken'")

    with SQLiteStore(database) as store:
        service = GuidedDemoApplicationService(store)
        with pytest.raises(PersistenceDataError, match="invalid machine snapshot JSON"):
            service.initialize_machine(NOW)


def test_complete_startup_is_rejected_when_machine_is_missing() -> None:
    with SQLiteStore() as store:
        service = GuidedDemoApplicationService(store)

        with pytest.raises(GuidedDemoApplicationError, match="machine snapshot"):
            service.complete_startup(NOW)

        assert store.load_machine_snapshot() is None
        assert store.load_events() == ()


def test_complete_startup_persists_ready_with_caller_timestamp_and_sequence() -> None:
    with SQLiteStore() as store:
        service = GuidedDemoApplicationService(store)
        service.initialize_machine(NOW)
        completed_at = NOW + timedelta(seconds=1)

        result = service.complete_startup(completed_at)

        assert result.machine.state is MachineState.READY
        assert result.machine.event_sequence == 2
        assert result.machine_events[0].event_type is MachineEventType.STARTUP_COMPLETED
        assert result.machine_events[0].occurred_at == completed_at
        assert result.machine_events[0].sequence_number == 2
        assert store.load_machine_snapshot() == result.machine


def test_start_and_complete_flush_from_ready() -> None:
    with SQLiteStore() as store:
        service = GuidedDemoApplicationService(store)
        service.initialize_machine(NOW)
        service.complete_startup(NOW)

        started = service.start_flush(NOW + timedelta(seconds=1))
        completed = service.complete_flush(NOW + timedelta(seconds=2))

        assert started.machine.state is MachineState.FLUSHING
        assert started.machine.interrupted_run_id is None
        assert started.machine_events[0].event_type is MachineEventType.FLUSH_STARTED
        assert completed.machine.state is MachineState.READY
        assert completed.machine.interrupted_run_id is None
        assert completed.machine_events[0].event_type is MachineEventType.FLUSH_COMPLETED
        assert store.load_machine_snapshot() == completed.machine


def test_flush_required_preserves_interrupted_run_until_flush_completes() -> None:
    with SQLiteStore() as store:
        persist_flush_required_machine(store)
        service = GuidedDemoApplicationService(store)
        started_at = NOW + timedelta(seconds=3)

        started = service.start_flush(started_at)

        assert started.machine.state is MachineState.FLUSHING
        assert started.machine.interrupted_run_id == "run-interrupted"
        assert started.machine_events[0].run_id == "run-interrupted"
        assert started.machine_events[0].occurred_at == started_at
        assert started.machine_events[0].sequence_number == 5
        completed = service.complete_flush(NOW + timedelta(seconds=4))
        assert completed.machine.state is MachineState.READY
        assert completed.machine.interrupted_run_id is None
        assert completed.machine_events[0].sequence_number == 6


@pytest.mark.parametrize(
    ("operation", "ready_required"),
    [
        ("complete_startup", True),
        ("start_flush", False),
        ("complete_flush", True),
    ],
)
def test_invalid_machine_operation_preserves_snapshot_and_events(
    operation: str, ready_required: bool
) -> None:
    with SQLiteStore() as store:
        service = GuidedDemoApplicationService(store)
        service.initialize_machine(NOW)
        if ready_required:
            service.complete_startup(NOW)
        original_machine = store.load_machine_snapshot()
        original_events = store.load_events()

        with pytest.raises(MachineTransitionError):
            getattr(service, operation)(NOW)

        assert store.load_machine_snapshot() == original_machine
        assert store.load_events() == original_events


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
            RunPhase.P1_TRANSFER_S_TO_REACTOR,
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
            RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
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


def test_claim_uses_injected_id_and_persists_without_executing_hardware(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        persist_ready_machine(store)
        service = GuidedDemoApplicationService(
            store, execution_id_factory=lambda: "execution-1"
        )
        create_and_start_run(service, configuration)

        intent = service.claim_current_phase_execution(
            "run-1", occurred_at=NOW
        )

        assert intent.execution_id == "execution-1"
        assert store.load_machine_snapshot().active_execution == intent
        assert store.load_demo_run("run-1").phase == intent.phase


def test_duplicate_claim_preserves_first_token(
    configuration: DemoConfiguration,
) -> None:
    identifiers = iter(("execution-1", "execution-2"))
    with SQLiteStore() as store:
        persist_ready_machine(store)
        service = GuidedDemoApplicationService(
            store, execution_id_factory=lambda: next(identifiers)
        )
        create_and_start_run(service, configuration)
        first = service.claim_current_phase_execution("run-1", occurred_at=NOW)

        with pytest.raises(ValueError, match="already active"):
            service.claim_current_phase_execution("run-1", occurred_at=NOW)

        assert store.load_machine_snapshot().active_execution == first


def test_stop_before_claim_rejects_without_execution_write(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        persist_ready_machine(store)
        service = GuidedDemoApplicationService(
            store, execution_id_factory=lambda: "execution-1"
        )
        create_and_start_run(service, configuration)
        service.request_stop_demo("run-1", NOW)
        original_events = store.load_events()

        with pytest.raises(ValueError, match="RUNNING"):
            service.claim_current_phase_execution("run-1", occurred_at=NOW)

        assert store.load_machine_snapshot().active_execution is None
        assert store.load_events() == original_events


def test_stop_after_claim_preserves_active_execution(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        persist_ready_machine(store)
        service = GuidedDemoApplicationService(
            store, execution_id_factory=lambda: "execution-1"
        )
        create_and_start_run(service, configuration)
        intent = service.claim_current_phase_execution("run-1", occurred_at=NOW)

        stopped = service.request_stop_demo("run-1", NOW)

        assert stopped.run.status is RunStatus.ABORTING
        assert stopped.machine.active_execution == intent
        assert store.load_machine_snapshot().active_execution == intent


def test_stop_returns_claim_committed_after_initial_machine_load(
    configuration: DemoConfiguration,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with SQLiteStore() as store:
        persist_ready_machine(store)
        service = GuidedDemoApplicationService(store)
        create_and_start_run(service, configuration)
        original_persist = store.persist_run_transition_and_load_machine
        claimed_intent = None
        machine_event_count_after_claim = 0

        def claim_then_persist(*args, **kwargs):
            nonlocal claimed_intent, machine_event_count_after_claim
            claimed_intent = store.claim_phase_execution(
                run_id="run-1",
                execution_id="execution-race",
                claimed_at=NOW,
            )
            machine_event_count_after_claim = len(
                store.load_events("MACHINE", "machine")
            )
            return original_persist(*args, **kwargs)

        monkeypatch.setattr(
            store,
            "persist_run_transition_and_load_machine",
            claim_then_persist,
        )

        result = service.request_stop_demo("run-1", NOW)

        assert result.run.status is RunStatus.ABORTING
        assert result.machine.state is MachineState.BUSY
        assert result.machine.active_execution == claimed_intent
        assert store.load_machine_snapshot().active_execution == claimed_intent
        assert (
            len(store.load_events("MACHINE", "machine"))
            == machine_event_count_after_claim
        )


def test_active_execution_blocks_phase_completion_and_stop_confirmation(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        persist_ready_machine(store)
        service = GuidedDemoApplicationService(
            store, execution_id_factory=lambda: "execution-1"
        )
        create_and_start_run(service, configuration)
        service.claim_current_phase_execution("run-1", occurred_at=NOW)
        original_run = store.load_demo_run("run-1")
        original_events = store.load_events()

        with pytest.raises(GuidedDemoApplicationError, match="execution-1"):
            service.complete_current_phase("run-1", NOW)
        service.request_stop_demo("run-1", NOW)
        events_after_stop = store.load_events()
        with pytest.raises(GuidedDemoApplicationError, match="execution-1"):
            service.confirm_stop_demo("run-1", NOW)

        assert store.load_demo_run("run-1").status is RunStatus.ABORTING
        assert store.load_demo_run("run-1").phase == original_run.phase
        assert store.load_events() == events_after_stop
        assert len(events_after_stop) == len(original_events) + 1


def test_active_execution_blocks_final_phase_completion(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        persist_ready_machine(store)
        service = GuidedDemoApplicationService(
            store, execution_id_factory=lambda: "execution-final"
        )
        result = create_and_start_run(service, configuration)
        while result.run.phase is not RunPhase.COLUMN_FRACTION_COLLECTION:
            result = service.complete_current_phase("run-1", NOW)
        service.claim_current_phase_execution("run-1", occurred_at=NOW)
        original_events = store.load_events()

        with pytest.raises(GuidedDemoApplicationError, match="execution-final"):
            service.complete_current_phase("run-1", NOW)

        assert store.load_demo_run("run-1") == result.run
        assert store.load_events() == original_events


def test_final_phase_completion_rolls_back_after_concurrent_claim(
    configuration: DemoConfiguration,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with SQLiteStore() as store:
        persist_ready_machine(store)
        service = GuidedDemoApplicationService(store)
        result = create_and_start_run(service, configuration)
        while result.run.phase is not RunPhase.COLUMN_FRACTION_COLLECTION:
            result = service.complete_current_phase("run-1", NOW)
        final_run = result.run
        original_persist = store.persist_run_and_machine_transition

        def claim_then_persist(*args, **kwargs) -> None:
            store.claim_phase_execution(
                run_id="run-1",
                execution_id="execution-final-race",
                claimed_at=NOW,
            )
            original_persist(*args, **kwargs)

        monkeypatch.setattr(
            store,
            "persist_run_and_machine_transition",
            claim_then_persist,
        )

        with pytest.raises(PersistenceConflictError, match="sequence"):
            service.complete_current_phase("run-1", NOW)

        persisted_run = store.load_demo_run("run-1")
        persisted_machine = store.load_machine_snapshot()
        assert persisted_run == final_run
        assert persisted_run.status is RunStatus.RUNNING
        assert persisted_run.phase is RunPhase.COLUMN_FRACTION_COLLECTION
        assert persisted_machine.state is MachineState.BUSY
        assert (
            persisted_machine.active_execution.execution_id
            == "execution-final-race"
        )
        machine_events = store.load_events("MACHINE", "machine")
        assert machine_events[-1].event_type is MachineEventType.PHASE_EXECUTION_CLAIMED
        assert all(
            event.event_type is not MachineEventType.RUN_COMPLETED
            for event in machine_events
        )


def test_intermediate_completion_rejects_concurrent_machine_change(
    configuration: DemoConfiguration,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with SQLiteStore() as store:
        persist_ready_machine(store)
        service = GuidedDemoApplicationService(store)
        started = create_and_start_run(service, configuration)
        original_persist = (
            store.persist_run_transition_with_machine_precondition
        )

        def claim_then_persist(*args, **kwargs) -> None:
            store.claim_phase_execution(
                run_id="run-1",
                execution_id="execution-race",
                claimed_at=NOW,
            )
            original_persist(*args, **kwargs)

        monkeypatch.setattr(
            store,
            "persist_run_transition_with_machine_precondition",
            claim_then_persist,
        )

        with pytest.raises(PersistenceConflictError, match="machine event sequence"):
            service.complete_current_phase("run-1", NOW)

        assert store.load_demo_run("run-1") == started.run
        assert (
            store.load_machine_snapshot().active_execution.execution_id
            == "execution-race"
        )


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
