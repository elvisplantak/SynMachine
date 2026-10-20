import json
import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.demo.execution_lifecycle import (
    PhaseExecutionClaimError,
    PhaseExecutionStartCommitError,
    PhaseExecutionStartCommitOutcome,
    claim_phase_execution,
)
from app.demo.events import DomainEvent
from app.demo.lifecycle import (
    complete_current_phase,
    create_demo_run,
    fault_run,
    request_abort,
    start_run,
)
from app.demo.machine_events import MachineEvent, MachineEventType
from app.demo.machine_lifecycle import (
    complete_startup,
    create_machine,
    record_runtime_hardware_fault,
    start_run as start_machine_run,
)
from app.demo.machine_models import MachineState, RuntimeHardwareFaultReason
from app.demo.models import AdditionOrder, DemoConfiguration, DemoExecutionSettings
from app.demo.phases import RunPhase
from app.demo.run_models import RunStatus
from app.persistence.sqlite_store import (
    PersistenceConflictError,
    PersistenceDataError,
    PersistenceSchemaError,
    SQLiteStore,
)

NOW = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
EXECUTION_SETTINGS = DemoExecutionSettings(
    sf_settling_duration_seconds="12.3456789",
    fraction_count=7,
    fraction_duration_seconds="45.0000001",
)


@pytest.fixture
def configuration() -> DemoConfiguration:
    return DemoConfiguration(
        b1_ratio_percent="33.333",
        total_mixture_volume_ml="9.999",
        combined_b1_b2_volume_ml="4.321",
        addition_order=AdditionOrder.B2_THEN_B1,
        addition_speed_command_percent="50.5",
        reactor_mixing_command_percent="60.25",
        sf_mixing_command_percent="40.125",
        simulated_target_temperature_c="25.75",
        reaction_duration_seconds="600.5",
        delay_between_additions_seconds="5.25",
    )


def test_empty_initialized_storage_has_no_snapshots_or_events() -> None:
    with SQLiteStore() as store:
        assert store.load_demo_run("missing") is None
        assert store.load_machine_snapshot() is None
        assert store.load_events() == ()


def test_demo_run_snapshot_round_trip_preserves_domain_values(
    configuration: DemoConfiguration,
) -> None:
    created = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)

    with SQLiteStore() as store:
        store.persist_run_transition(created.run, created.events)
        loaded = store.load_demo_run("run-1")

    assert loaded == created.run
    assert loaded is not None
    assert loaded.configuration.b1_ratio_percent == Decimal("33.333")
    assert loaded.fluid_plan.b1_b2_volume_ratio == (
        Decimal("33.333"),
        Decimal("66.667"),
    )
    assert isinstance(loaded.fluid_plan.b1_b2_volume_ratio, tuple)
    assert loaded.configuration.addition_order is AdditionOrder.B2_THEN_B1
    assert loaded.execution_settings.sf_settling_duration_seconds == Decimal(
        "12.3456789"
    )
    assert loaded.execution_settings.fraction_count == 7
    assert loaded.execution_settings.fraction_duration_seconds == Decimal("45.0000001")


def test_machine_snapshot_round_trip() -> None:
    created = create_machine(NOW)

    with SQLiteStore() as store:
        store.persist_machine_transition(created.machine, created.events)
        assert store.load_machine_snapshot() == created.machine


def test_runtime_hardware_fault_snapshot_and_event_round_trip() -> None:
    created = create_machine(NOW)
    ready = complete_startup(created.machine, NOW)
    busy = start_machine_run(ready.machine, "run-1", NOW)
    fault = record_runtime_hardware_fault(
        busy.machine,
        run_id="run-1",
        occurred_at=NOW,
        reason=RuntimeHardwareFaultReason.CAROUSEL_MOVEMENT_FAILED,
    )

    with SQLiteStore() as store:
        for transition in (created, ready, busy, fault):
            store.persist_machine_transition(
                transition.machine,
                transition.events,
            )

        assert store.load_machine_snapshot() == fault.machine
        assert store.load_events("MACHINE", "machine")[-1] == fault.events[0]


def test_legacy_machine_snapshot_and_event_json_use_runtime_fault_defaults(
    tmp_path,
) -> None:
    database = tmp_path / "legacy-machine-json.db"
    created = create_machine(NOW)
    with SQLiteStore(database) as store:
        store.persist_machine_transition(created.machine, created.events)

    with sqlite3.connect(database) as connection:
        snapshot_payload = json.loads(
            connection.execute(
                "SELECT snapshot_json FROM machine_snapshot"
            ).fetchone()[0]
        )
        event_payload = json.loads(
            connection.execute(
                "SELECT payload_json FROM domain_events"
            ).fetchone()[0]
        )
        for payload in (snapshot_payload, event_payload):
            payload.pop("runtime_fault_reason")
            payload.pop("hardware_outcome_unknown")
            payload.pop("carousel_position_untrusted")
        connection.execute(
            "UPDATE machine_snapshot SET snapshot_json = ?",
            (json.dumps(snapshot_payload),),
        )
        connection.execute(
            "UPDATE domain_events SET payload_json = ?",
            (json.dumps(event_payload),),
        )

    with SQLiteStore(database) as store:
        loaded_machine = store.load_machine_snapshot()
        loaded_event = store.load_events("MACHINE", "machine")[0]

    assert loaded_machine == created.machine
    assert loaded_event == created.events[0]
    assert loaded_machine is not None
    assert loaded_machine.runtime_fault_reason is None
    assert loaded_machine.hardware_outcome_unknown is False
    assert loaded_machine.carousel_position_untrusted is False
    assert loaded_event.runtime_fault_reason is None
    assert loaded_event.hardware_outcome_unknown is False
    assert loaded_event.carousel_position_untrusted is False


@pytest.mark.parametrize(
    ("event_update", "error"),
    [
        ({"run_status": RunStatus.RUNNING}, "final run event status"),
        ({"run_phase": RunPhase.P1_TRANSFER_S_TO_REACTOR}, "final run event phase"),
    ],
)
def test_final_run_event_must_match_snapshot_without_writing(
    configuration: DemoConfiguration, event_update: dict, error: str
) -> None:
    created = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)
    mismatched_event = created.events[-1].model_copy(update=event_update)

    with SQLiteStore() as store:
        with pytest.raises(PersistenceConflictError, match=error):
            store.persist_run_transition(created.run, (mismatched_event,))
        assert store.load_demo_run("run-1") is None
        assert store.load_events() == ()


def test_final_machine_event_must_match_snapshot_without_writing() -> None:
    created = create_machine(NOW)
    mismatched_event = created.events[-1].model_copy(
        update={"machine_state": MachineState.READY}
    )

    with SQLiteStore() as store:
        with pytest.raises(PersistenceConflictError, match="final machine event state"):
            store.persist_machine_transition(created.machine, (mismatched_event,))
        assert store.load_machine_snapshot() is None
        assert store.load_events() == ()


@pytest.mark.parametrize(
    ("event_update", "field_name"),
    [
        (
            {
                "runtime_fault_reason": (
                    RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED
                )
            },
            "runtime_fault_reason",
        ),
        ({"hardware_outcome_unknown": False}, "hardware_outcome_unknown"),
        ({"carousel_position_untrusted": False}, "carousel_position_untrusted"),
    ],
)
def test_final_runtime_fault_event_metadata_must_match_snapshot_without_writing(
    event_update: dict,
    field_name: str,
) -> None:
    created = create_machine(NOW)
    ready = complete_startup(created.machine, NOW)
    busy = start_machine_run(ready.machine, "run-1", NOW)
    fault = record_runtime_hardware_fault(
        busy.machine,
        run_id="run-1",
        occurred_at=NOW,
        reason=RuntimeHardwareFaultReason.CAROUSEL_MOVEMENT_FAILED,
    )
    mismatched_event = fault.events[-1].model_copy(update=event_update)

    with SQLiteStore() as store:
        for transition in (created, ready, busy):
            store.persist_machine_transition(
                transition.machine,
                transition.events,
            )
        original_events = store.load_events("MACHINE", "machine")

        with pytest.raises(PersistenceConflictError, match=field_name):
            store.persist_machine_transition(
                fault.machine,
                (mismatched_event,),
            )

        assert store.load_machine_snapshot() == busy.machine
        assert store.load_events("MACHINE", "machine") == original_events


def test_run_and_machine_events_round_trip_in_mixed_append_only_table(
    configuration: DemoConfiguration,
) -> None:
    run = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)
    machine = create_machine(NOW + timedelta(seconds=1))

    with SQLiteStore() as store:
        store.persist_run_transition(run.run, run.events)
        store.persist_machine_transition(machine.machine, machine.events)
        events = store.load_events()

        assert events == (*run.events, *machine.events)
        assert isinstance(events[0], DomainEvent)
        assert isinstance(events[1], MachineEvent)
        assert store.load_events("RUN", "run-1") == run.events
        assert store.load_events("MACHINE", "machine") == machine.events


def test_aware_event_timestamp_is_normalized_to_utc_in_metadata_and_json(
    tmp_path, configuration: DemoConfiguration
) -> None:
    database = tmp_path / "utc.db"
    local_time = datetime(2026, 7, 18, 14, 30, tzinfo=timezone(timedelta(hours=2)))
    created = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, local_time)

    with SQLiteStore(database) as store:
        store.persist_run_transition(created.run, created.events)
        loaded_event = store.load_events("RUN", "run-1")[0]

    with sqlite3.connect(database) as connection:
        metadata, payload = connection.execute(
            "SELECT occurred_at, payload_json FROM domain_events"
        ).fetchone()

    assert metadata == "2026-07-18T12:30:00Z"
    assert json.loads(payload)["occurred_at"] == "2026-07-18T12:30:00Z"
    assert loaded_event.occurred_at == datetime(2026, 7, 18, 12, 30, tzinfo=UTC)
    assert loaded_event.occurred_at.utcoffset() == timedelta(0)


def test_naive_event_timestamp_is_rejected_without_writing(
    configuration: DemoConfiguration,
) -> None:
    created = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)
    naive_event = created.events[0].model_copy(
        update={"occurred_at": datetime(2026, 7, 18, 12, 0)}
    )

    with SQLiteStore() as store:
        with pytest.raises(PersistenceDataError, match="timezone-aware"):
            store.persist_run_transition(created.run, (naive_event,))
        assert store.load_demo_run("run-1") is None
        assert store.load_events() == ()


def test_sequence_continuity_accepts_next_transition(
    configuration: DemoConfiguration,
) -> None:
    created = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)
    started = start_run(created.run, NOW + timedelta(seconds=1))

    with SQLiteStore() as store:
        store.persist_run_transition(created.run, created.events)
        store.persist_run_transition(started.run, started.events)

        assert store.load_demo_run("run-1") == started.run
        assert tuple(event.sequence_number for event in store.load_events()) == (1, 2, 3)


@pytest.mark.parametrize("phase", list(RunPhase))
def test_run_phase_round_trip_preserves_new_enum_values(
    configuration: DemoConfiguration, phase: RunPhase
) -> None:
    created = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)
    snapshot = created.run.model_copy(update={"phase": phase})
    event = created.events[0].model_copy(update={"run_phase": phase})

    with SQLiteStore() as store:
        store.persist_run_transition(snapshot, (event,))

        assert store.load_demo_run("run-1").phase is phase
        assert store.load_events("RUN", "run-1")[0].run_phase is phase


@pytest.mark.parametrize("conflict", ["replay", "skip", "overlap"])
def test_sequence_conflicts_leave_existing_data_unchanged(
    conflict: str, configuration: DemoConfiguration
) -> None:
    created = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)
    started = start_run(created.run, NOW + timedelta(seconds=1))

    with SQLiteStore() as store:
        store.persist_run_transition(created.run, created.events)
        if conflict == "replay":
            snapshot, events = created.run, created.events
        elif conflict == "skip":
            snapshot = started.run.model_copy(update={"event_sequence": 4})
            events = tuple(
                event.model_copy(update={"sequence_number": event.sequence_number + 1})
                for event in started.events
            )
        else:
            snapshot = started.run.model_copy(update={"event_sequence": 2})
            events = started.events

        with pytest.raises(PersistenceConflictError, match="sequence"):
            store.persist_run_transition(snapshot, events)

        assert store.load_demo_run("run-1") == created.run
        assert store.load_events("RUN", "run-1") == created.events


def test_duplicate_event_batch_is_rejected(configuration: DemoConfiguration) -> None:
    created = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)
    duplicate_batch = (created.events[0], created.events[0])
    snapshot = created.run.model_copy(update={"event_sequence": 2})

    with SQLiteStore() as store:
        with pytest.raises(PersistenceConflictError, match="sequence"):
            store.persist_run_transition(snapshot, duplicate_batch)
        assert store.load_demo_run("run-1") is None
        assert store.load_events() == ()


def test_event_metadata_json_mismatch_fails_fast(
    tmp_path, configuration: DemoConfiguration
) -> None:
    database = tmp_path / "metadata.db"
    created = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)
    with SQLiteStore(database) as store:
        store.persist_run_transition(created.run, created.events)

    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE domain_events SET event_type = 'RUN_STARTED'")
        connection.commit()

    with SQLiteStore(database) as store:
        with pytest.raises(PersistenceDataError, match="metadata does not match"):
            store.load_events()


@pytest.mark.parametrize("target", ["snapshot", "event"])
def test_corrupt_json_fails_fast(
    tmp_path, configuration: DemoConfiguration, target: str
) -> None:
    database = tmp_path / f"corrupt-{target}.db"
    created = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)
    with SQLiteStore(database) as store:
        store.persist_run_transition(created.run, created.events)

    with sqlite3.connect(database) as connection:
        if target == "snapshot":
            connection.execute("UPDATE demo_runs SET snapshot_json = '{broken'")
        else:
            connection.execute("UPDATE domain_events SET payload_json = '{broken'")
        connection.commit()

    with SQLiteStore(database) as store:
        with pytest.raises(PersistenceDataError, match="invalid"):
            if target == "snapshot":
                store.load_demo_run("run-1")
            else:
                store.load_events()


def test_snapshot_metadata_json_mismatch_fails_fast(
    tmp_path, configuration: DemoConfiguration
) -> None:
    database = tmp_path / "snapshot-metadata.db"
    created = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)
    with SQLiteStore(database) as store:
        store.persist_run_transition(created.run, created.events)

    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE demo_runs SET status = 'COMPLETED'")
        connection.commit()

    with SQLiteStore(database) as store:
        with pytest.raises(PersistenceDataError, match="metadata does not match"):
            store.load_demo_run("run-1")


def test_non_contiguous_persisted_event_history_fails_fast(
    tmp_path, configuration: DemoConfiguration
) -> None:
    database = tmp_path / "event-gap.db"
    created = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)
    started = start_run(created.run, NOW + timedelta(seconds=1))
    with SQLiteStore(database) as store:
        store.persist_run_transition(created.run, created.events)
        store.persist_run_transition(started.run, started.events)

    with sqlite3.connect(database) as connection:
        connection.execute(
            "DELETE FROM domain_events "
            "WHERE aggregate_type = 'RUN' AND aggregate_id = 'run-1' "
            "AND event_sequence = 2"
        )
        connection.commit()

    with SQLiteStore(database) as store:
        with pytest.raises(PersistenceDataError, match="non-contiguous event history"):
            store.load_events("RUN", "run-1")


def test_unsupported_schema_version_is_rejected(tmp_path) -> None:
    database = tmp_path / "unsupported.db"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA user_version = 2")

    with pytest.raises(PersistenceSchemaError, match="unsupported schema version 2"):
        SQLiteStore(database)


def test_version_one_with_incorrect_structure_is_rejected(tmp_path) -> None:
    database = tmp_path / "wrong-structure.db"
    with SQLiteStore(database):
        pass
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE machine_snapshot")
        connection.execute(
            "CREATE TABLE machine_snapshot "
            "(singleton_id INTEGER NOT NULL PRIMARY KEY, snapshot_json TEXT NOT NULL)"
        )

    with pytest.raises(PersistenceSchemaError, match="table 'machine_snapshot'.*structure"):
        SQLiteStore(database)


@pytest.mark.parametrize(
    ("table", "replacement_sql"),
    [
        (
            "machine_snapshot",
            "CREATE TABLE machine_snapshot ("
            "singleton_id INTEGER NOT NULL PRIMARY KEY, "
            "snapshot_json TEXT NOT NULL, event_sequence INTEGER NOT NULL, "
            "state TEXT NOT NULL)",
        ),
        (
            "domain_events",
            "CREATE TABLE domain_events ("
            "aggregate_type TEXT NOT NULL, aggregate_id TEXT NOT NULL, "
            "event_sequence INTEGER NOT NULL, event_type TEXT NOT NULL, "
            "occurred_at TEXT NOT NULL, run_status TEXT, run_phase TEXT, "
            "machine_state TEXT, payload_json TEXT NOT NULL, "
            "PRIMARY KEY (aggregate_type, aggregate_id, event_sequence))",
        ),
    ],
)
def test_version_one_schema_missing_required_check_is_rejected(
    tmp_path, table: str, replacement_sql: str
) -> None:
    database = tmp_path / f"missing-{table}-check.db"
    with SQLiteStore(database):
        pass
    with sqlite3.connect(database) as connection:
        connection.execute(f'DROP TABLE "{table}"')
        connection.execute(replacement_sql)

    with pytest.raises(
        PersistenceSchemaError, match=f"table '{table}'.*missing required CHECK"
    ):
        SQLiteStore(database)


def test_run_snapshot_read_rejects_missing_final_event(
    tmp_path, configuration: DemoConfiguration
) -> None:
    database = tmp_path / "run-sequence-mismatch.db"
    created = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)
    started = start_run(created.run, NOW + timedelta(seconds=1))
    with SQLiteStore(database) as store:
        store.persist_run_transition(created.run, created.events)
        store.persist_run_transition(started.run, started.events)

    with sqlite3.connect(database) as connection:
        connection.execute(
            "DELETE FROM domain_events WHERE aggregate_type = 'RUN' "
            "AND aggregate_id = 'run-1' AND event_sequence = 3"
        )
        connection.commit()

    with SQLiteStore(database) as store:
        with pytest.raises(PersistenceDataError, match="snapshot/event sequence mismatch"):
            store.load_demo_run("run-1")


def test_specific_run_event_read_rejects_events_without_snapshot(
    tmp_path, configuration: DemoConfiguration
) -> None:
    database = tmp_path / "run-events-without-snapshot.db"
    created = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)
    with SQLiteStore(database) as store:
        store.persist_run_transition(created.run, created.events)

    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM demo_runs WHERE run_id = 'run-1'")
        connection.commit()

    with SQLiteStore(database) as store:
        with pytest.raises(PersistenceDataError, match="events exist without snapshot"):
            store.load_demo_run("run-1")
        with pytest.raises(PersistenceDataError, match="events exist without snapshot"):
            store.load_events("RUN", "run-1")


def test_machine_snapshot_read_rejects_missing_event_history(tmp_path) -> None:
    database = tmp_path / "machine-snapshot-without-events.db"
    created = create_machine(NOW)
    ready = complete_startup(created.machine, NOW + timedelta(seconds=1))
    with SQLiteStore(database) as store:
        store.persist_machine_transition(created.machine, created.events)
        store.persist_machine_transition(ready.machine, ready.events)

    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM domain_events WHERE aggregate_type = 'MACHINE'")
        connection.commit()

    with SQLiteStore(database) as store:
        with pytest.raises(PersistenceDataError, match="snapshot exists without event history"):
            store.load_machine_snapshot()


def test_specific_machine_event_read_rejects_events_without_snapshot(tmp_path) -> None:
    database = tmp_path / "machine-events-without-snapshot.db"
    created = create_machine(NOW)
    with SQLiteStore(database) as store:
        store.persist_machine_transition(created.machine, created.events)

    with sqlite3.connect(database) as connection:
        connection.execute("DELETE FROM machine_snapshot")
        connection.commit()

    with SQLiteStore(database) as store:
        with pytest.raises(PersistenceDataError, match="events exist without snapshot"):
            store.load_machine_snapshot()
        with pytest.raises(PersistenceDataError, match="events exist without snapshot"):
            store.load_events("MACHINE", "machine")


def test_transaction_rolls_back_partial_event_batch_and_snapshot(
    tmp_path, configuration: DemoConfiguration
) -> None:
    database = tmp_path / "rollback.db"
    created = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)
    started = start_run(created.run, NOW + timedelta(seconds=1))

    with SQLiteStore(database) as store:
        store.persist_run_transition(created.run, created.events)

    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TRIGGER reject_third_event BEFORE INSERT ON domain_events "
            "WHEN NEW.aggregate_type = 'RUN' AND NEW.event_sequence = 3 "
            "BEGIN SELECT RAISE(ABORT, 'forced event failure'); END"
        )

    with SQLiteStore(database) as store:
        with pytest.raises(sqlite3.IntegrityError, match="forced event failure"):
            store.persist_run_transition(started.run, started.events)
        assert store.load_demo_run("run-1") == created.run
        assert store.load_events("RUN", "run-1") == created.events


def test_transaction_rolls_back_events_when_snapshot_update_fails(
    tmp_path, configuration: DemoConfiguration
) -> None:
    database = tmp_path / "snapshot-rollback.db"
    created = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)
    started = start_run(created.run, NOW + timedelta(seconds=1))

    with SQLiteStore(database) as store:
        store.persist_run_transition(created.run, created.events)

    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TRIGGER reject_snapshot_update BEFORE UPDATE ON demo_runs "
            "WHEN NEW.event_sequence = 3 "
            "BEGIN SELECT RAISE(ABORT, 'forced snapshot failure'); END"
        )

    with SQLiteStore(database) as store:
        with pytest.raises(sqlite3.IntegrityError, match="forced snapshot failure"):
            store.persist_run_transition(started.run, started.events)
        assert store.load_demo_run("run-1") == created.run
        assert store.load_events("RUN", "run-1") == created.events


def test_file_backed_database_reopens_with_snapshots_and_events(
    tmp_path, configuration: DemoConfiguration
) -> None:
    database = tmp_path / "reopen.db"
    run = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)
    machine = create_machine(NOW)

    with SQLiteStore(database) as store:
        store.persist_run_transition(run.run, run.events)
        store.persist_machine_transition(machine.machine, machine.events)

    with SQLiteStore(database) as reopened:
        assert reopened.load_demo_run("run-1") == run.run
        assert reopened.load_machine_snapshot() == machine.machine
        assert reopened.load_events() == (*run.events, *machine.events)


def test_schema_version_is_one_and_initialization_creates_no_machine(tmp_path) -> None:
    database = tmp_path / "schema.db"
    with SQLiteStore(database) as store:
        assert store.load_machine_snapshot() is None

    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1


def test_snapshot_and_final_event_sequence_must_match(
    configuration: DemoConfiguration,
) -> None:
    created = create_demo_run("run-1", configuration, EXECUTION_SETTINGS, NOW)
    stale_snapshot = created.run.model_copy(update={"event_sequence": 2})

    with SQLiteStore() as store:
        with pytest.raises(PersistenceConflictError, match="final event sequence"):
            store.persist_run_transition(stale_snapshot, created.events)
        assert store.load_demo_run("run-1") is None
        assert store.load_events() == ()


def _persist_created_run_and_ready_machine(
    store: SQLiteStore, configuration: DemoConfiguration
):
    created_run = create_demo_run(
        "run-1", configuration, EXECUTION_SETTINGS, NOW
    )
    created_machine = create_machine(NOW)
    ready_machine = complete_startup(
        created_machine.machine, NOW + timedelta(seconds=1)
    )
    store.persist_run_transition(created_run.run, created_run.events)
    store.persist_machine_transition(created_machine.machine, created_machine.events)
    store.persist_machine_transition(ready_machine.machine, ready_machine.events)
    return created_run, ready_machine


def test_atomic_run_and_machine_transition_succeeds(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        created, ready = _persist_created_run_and_ready_machine(store, configuration)
        started_run = start_run(created.run, NOW + timedelta(seconds=2))
        busy_machine = start_machine_run(
            ready.machine, "run-1", NOW + timedelta(seconds=2)
        )

        store.persist_run_and_machine_transition(
            started_run.run,
            started_run.events,
            busy_machine.machine,
            busy_machine.events,
        )

        assert store.load_demo_run("run-1") == started_run.run
        assert store.load_machine_snapshot() == busy_machine.machine
        assert store.load_events("RUN", "run-1") == (
            *created.events,
            *started_run.events,
        )
        assert store.load_events("MACHINE", "machine")[-1] == busy_machine.events[-1]


def test_atomic_transition_rejects_runtime_fault_metadata_conflict(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        created, ready = _persist_created_run_and_ready_machine(store, configuration)
        started_run = start_run(created.run, NOW)
        busy_machine = start_machine_run(ready.machine, "run-1", NOW)
        store.persist_run_and_machine_transition(
            started_run.run,
            started_run.events,
            busy_machine.machine,
            busy_machine.events,
        )
        run_fault = fault_run(started_run.run, NOW, "Hardware command failed")
        machine_fault = record_runtime_hardware_fault(
            busy_machine.machine,
            run_id="run-1",
            occurred_at=NOW,
            reason=RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED,
        )
        mismatched_event = machine_fault.events[-1].model_copy(
            update={"hardware_outcome_unknown": False}
        )
        original_events = store.load_events()

        with pytest.raises(
            PersistenceConflictError,
            match="hardware_outcome_unknown",
        ):
            store.persist_run_and_machine_transition(
                run_fault.run,
                run_fault.events,
                machine_fault.machine,
                (mismatched_event,),
            )

        assert store.load_demo_run("run-1") == started_run.run
        assert store.load_machine_snapshot() == busy_machine.machine
        assert store.load_events() == original_events


def test_atomic_transition_run_conflict_leaves_machine_unchanged(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        created, ready = _persist_created_run_and_ready_machine(store, configuration)
        busy_machine = start_machine_run(ready.machine, "run-1", NOW)

        with pytest.raises(PersistenceConflictError, match="sequence"):
            store.persist_run_and_machine_transition(
                created.run,
                created.events,
                busy_machine.machine,
                busy_machine.events,
            )

        assert store.load_demo_run("run-1") == created.run
        assert store.load_machine_snapshot() == ready.machine


def test_atomic_transition_machine_conflict_leaves_run_unchanged(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        created, ready = _persist_created_run_and_ready_machine(store, configuration)
        started_run = start_run(created.run, NOW)

        with pytest.raises(PersistenceConflictError, match="sequence"):
            store.persist_run_and_machine_transition(
                started_run.run,
                started_run.events,
                ready.machine,
                ready.events,
            )

        assert store.load_demo_run("run-1") == created.run
        assert store.load_machine_snapshot() == ready.machine


def test_atomic_transition_second_snapshot_failure_rolls_back_everything(
    tmp_path, configuration: DemoConfiguration
) -> None:
    database = tmp_path / "dual-snapshot-rollback.db"
    with SQLiteStore(database) as store:
        created, ready = _persist_created_run_and_ready_machine(store, configuration)

    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TRIGGER reject_dual_machine_update "
            "BEFORE UPDATE ON machine_snapshot WHEN NEW.event_sequence = 3 "
            "BEGIN SELECT RAISE(ABORT, 'forced dual machine failure'); END"
        )

    started_run = start_run(created.run, NOW)
    busy_machine = start_machine_run(ready.machine, "run-1", NOW)
    with SQLiteStore(database) as store:
        original_events = store.load_events()
        with pytest.raises(sqlite3.IntegrityError, match="forced dual machine failure"):
            store.persist_run_and_machine_transition(
                started_run.run,
                started_run.events,
                busy_machine.machine,
                busy_machine.events,
            )

        assert store.load_demo_run("run-1") == created.run
        assert store.load_machine_snapshot() == ready.machine
        assert store.load_events() == original_events


def _persist_running_run_and_busy_machine(
    store: SQLiteStore,
    configuration: DemoConfiguration,
):
    created, ready = _persist_created_run_and_ready_machine(store, configuration)
    started_run = start_run(created.run, NOW)
    busy_machine = start_machine_run(ready.machine, "run-1", NOW)
    store.persist_run_and_machine_transition(
        started_run.run,
        started_run.events,
        busy_machine.machine,
        busy_machine.events,
    )
    return started_run, busy_machine


def test_atomic_phase_execution_claim_persists_event_and_snapshot(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        started, busy = _persist_running_run_and_busy_machine(
            store, configuration
        )

        intent = store.claim_phase_execution(
            run_id="run-1",
            execution_id="execution-1",
            claimed_at=NOW,
            expected_run_event_sequence=started.run.event_sequence,
            expected_phase=started.run.phase,
        )

        machine = store.load_machine_snapshot()
        assert machine.active_execution == intent
        assert intent.start_committed_at is None
        assert machine.event_sequence == busy.machine.event_sequence + 1
        assert store.load_demo_run("run-1") == started.run
        event = store.load_events("MACHINE", "machine")[-1]
        assert event.event_type is MachineEventType.PHASE_EXECUTION_CLAIMED
        assert (event.execution_id, event.run_id, event.execution_phase) == (
            intent.execution_id,
            intent.run_id,
            intent.phase,
        )


def test_start_commit_is_atomic_audited_and_not_replayable(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        started, _ = _persist_running_run_and_busy_machine(
            store, configuration
        )
        intent = store.claim_phase_execution(
            run_id="run-1",
            execution_id="execution-start",
            claimed_at=NOW,
            expected_run_event_sequence=started.run.event_sequence,
            expected_phase=started.run.phase,
        )
        committed_at = NOW + timedelta(seconds=1)

        result = store.commit_phase_execution_start(
            intent,
            expected_run_event_sequence=started.run.event_sequence,
            expected_phase=started.run.phase,
            start_committed_at=committed_at,
        )

        assert result.outcome is PhaseExecutionStartCommitOutcome.START_COMMITTED
        assert result.intent.start_committed_at == committed_at
        assert store.load_machine_snapshot().active_execution == result.intent
        event = store.load_events("MACHINE", "machine")[-1]
        assert event.event_type is (
            MachineEventType.PHASE_EXECUTION_START_COMMITTED
        )
        assert event.execution_id == intent.execution_id
        assert event.occurred_at == committed_at

        with pytest.raises(
            PhaseExecutionStartCommitError, match="already committed"
        ):
            store.commit_phase_execution_start(
                result.intent,
                expected_run_event_sequence=started.run.event_sequence,
                expected_phase=started.run.phase,
                start_committed_at=committed_at,
            )


def test_start_commit_rejects_mismatched_token_without_writes(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        started, _ = _persist_running_run_and_busy_machine(
            store, configuration
        )
        intent = store.claim_phase_execution(
            run_id="run-1",
            execution_id="execution-start",
            claimed_at=NOW,
            expected_run_event_sequence=started.run.event_sequence,
            expected_phase=started.run.phase,
        )
        mismatched = intent.model_copy(
            update={"execution_id": "execution-other"}
        )
        events = store.load_events()

        with pytest.raises(PhaseExecutionStartCommitError, match="does not match"):
            store.commit_phase_execution_start(
                mismatched,
                expected_run_event_sequence=started.run.event_sequence,
                expected_phase=started.run.phase,
                start_committed_at=NOW + timedelta(seconds=1),
            )

        assert store.load_machine_snapshot().active_execution == intent
        assert store.load_events() == events


@pytest.mark.parametrize(
    ("sequence_offset", "phase", "message"),
    [
        (-1, RunPhase.P1_TRANSFER_S_TO_REACTOR, "event_sequence"),
        (0, RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR, "phase"),
    ],
)
def test_start_commit_rejects_stale_preparation_without_writes(
    configuration: DemoConfiguration,
    sequence_offset: int,
    phase: RunPhase,
    message: str,
) -> None:
    with SQLiteStore() as store:
        started, _ = _persist_running_run_and_busy_machine(
            store, configuration
        )
        intent = store.claim_phase_execution(
            run_id="run-1",
            execution_id="execution-stale",
            claimed_at=NOW,
            expected_run_event_sequence=started.run.event_sequence,
            expected_phase=started.run.phase,
        )
        events = store.load_events()

        with pytest.raises(PhaseExecutionStartCommitError, match=message):
            store.commit_phase_execution_start(
                intent,
                expected_run_event_sequence=(
                    started.run.event_sequence + sequence_offset
                ),
                expected_phase=phase,
                start_committed_at=NOW + timedelta(seconds=1),
            )

        assert store.load_machine_snapshot().active_execution == intent
        assert store.load_events() == events


def test_stop_wins_before_start_without_start_write(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        started, _ = _persist_running_run_and_busy_machine(
            store, configuration
        )
        intent = store.claim_phase_execution(
            run_id="run-1",
            execution_id="execution-stop",
            claimed_at=NOW,
            expected_run_event_sequence=started.run.event_sequence,
            expected_phase=started.run.phase,
        )
        stopped = request_abort(started.run, NOW + timedelta(seconds=1))
        store.persist_run_transition_and_load_machine(
            stopped.run, stopped.events
        )
        events = store.load_events()

        result = store.commit_phase_execution_start(
            intent,
            expected_run_event_sequence=started.run.event_sequence,
            expected_phase=started.run.phase,
            start_committed_at=NOW + timedelta(seconds=2),
        )

        assert result.outcome is PhaseExecutionStartCommitOutcome.STOP_WON
        assert result.intent.start_committed_at is None
        assert store.load_machine_snapshot().active_execution == intent
        assert store.load_events() == events


@pytest.mark.parametrize(
    ("expected_sequence_offset", "expected_phase", "message"),
    [
        (0, RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR, "phase"),
        (-1, RunPhase.P1_TRANSFER_S_TO_REACTOR, "event sequence"),
    ],
)
def test_atomic_claim_rejects_stale_prepared_run_without_writes(
    configuration: DemoConfiguration,
    expected_sequence_offset: int,
    expected_phase: RunPhase,
    message: str,
) -> None:
    with SQLiteStore() as store:
        started, _ = _persist_running_run_and_busy_machine(
            store, configuration
        )
        original_events = store.load_events()

        with pytest.raises(PersistenceConflictError, match=message):
            store.claim_phase_execution(
                run_id="run-1",
                execution_id="stale-preparation",
                claimed_at=NOW,
                expected_run_event_sequence=(
                    started.run.event_sequence + expected_sequence_offset
                ),
                expected_phase=expected_phase,
            )

        assert store.load_machine_snapshot().active_execution is None
        assert store.load_events() == original_events


@pytest.mark.parametrize("missing", ["run", "machine"])
def test_atomic_claim_rejects_missing_state_without_writes(
    missing: str, configuration: DemoConfiguration
) -> None:
    with SQLiteStore() as store:
        if missing == "run":
            created = create_machine(NOW)
            store.persist_machine_transition(created.machine, created.events)
        else:
            created = create_demo_run(
                "run-1", configuration, EXECUTION_SETTINGS, NOW
            )
            store.persist_run_transition(created.run, created.events)
        original_events = store.load_events()

        with pytest.raises(PhaseExecutionClaimError, match="not found"):
            store.claim_phase_execution(
                run_id="run-1",
                execution_id="execution-1",
                claimed_at=NOW,
                expected_run_event_sequence=(
                    created.run.event_sequence if missing == "machine" else 0
                ),
                expected_phase=(
                    created.run.phase
                    if missing == "machine"
                    else RunPhase.P1_TRANSFER_S_TO_REACTOR
                ),
            )

        assert store.load_events() == original_events


def test_duplicate_claim_allows_exactly_one_winner(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        started, _ = _persist_running_run_and_busy_machine(
            store, configuration
        )
        first = store.claim_phase_execution(
            run_id="run-1",
            execution_id="execution-1",
            claimed_at=NOW,
            expected_run_event_sequence=started.run.event_sequence,
            expected_phase=started.run.phase,
        )
        events_after_first = store.load_events()

        with pytest.raises(PhaseExecutionClaimError, match="already active"):
            store.claim_phase_execution(
                run_id="run-1",
                execution_id="execution-2",
                claimed_at=NOW,
                expected_run_event_sequence=started.run.event_sequence,
                expected_phase=started.run.phase,
            )

        assert store.load_machine_snapshot().active_execution == first
        assert store.load_events() == events_after_first


def test_unresolved_execution_survives_database_reopen(
    tmp_path, configuration: DemoConfiguration
) -> None:
    database = tmp_path / "active-execution.db"
    with SQLiteStore(database) as store:
        started, _ = _persist_running_run_and_busy_machine(
            store, configuration
        )
        intent = store.claim_phase_execution(
            run_id="run-1",
            execution_id="execution-1",
            claimed_at=NOW,
            expected_run_event_sequence=started.run.event_sequence,
            expected_phase=started.run.phase,
        )

    with SQLiteStore(database) as reopened:
        machine = reopened.load_machine_snapshot()
        assert machine.active_execution == intent
        assert machine.state is MachineState.BUSY


def test_legacy_persisted_execution_defaults_start_commit_to_none(
    tmp_path, configuration: DemoConfiguration
) -> None:
    database = tmp_path / "legacy-active-execution.db"
    with SQLiteStore(database) as store:
        started, _ = _persist_running_run_and_busy_machine(
            store, configuration
        )
        store.claim_phase_execution(
            run_id="run-1",
            execution_id="execution-legacy",
            claimed_at=NOW,
            expected_run_event_sequence=started.run.event_sequence,
            expected_phase=started.run.phase,
        )
    with sqlite3.connect(database) as connection:
        payload = json.loads(
            connection.execute(
                "SELECT snapshot_json FROM machine_snapshot"
            ).fetchone()[0]
        )
        del payload["active_execution"]["start_committed_at"]
        connection.execute(
            "UPDATE machine_snapshot SET snapshot_json = ?",
            (json.dumps(payload),),
        )

    with SQLiteStore(database) as reopened:
        active = reopened.load_machine_snapshot().active_execution
        assert active is not None
        assert active.start_committed_at is None


def test_forced_claim_snapshot_failure_rolls_back_event(
    tmp_path, configuration: DemoConfiguration
) -> None:
    database = tmp_path / "claim-rollback.db"
    with SQLiteStore(database) as store:
        _, busy = _persist_running_run_and_busy_machine(store, configuration)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TRIGGER reject_execution_claim "
            "BEFORE UPDATE ON machine_snapshot WHEN NEW.event_sequence = 4 "
            "BEGIN SELECT RAISE(ABORT, 'forced claim failure'); END"
        )

    with SQLiteStore(database) as store:
        original_events = store.load_events()
        run = store.load_demo_run("run-1")
        assert run is not None
        with pytest.raises(sqlite3.IntegrityError, match="forced claim failure"):
            store.claim_phase_execution(
                run_id="run-1",
                execution_id="execution-1",
                claimed_at=NOW,
                expected_run_event_sequence=run.event_sequence,
                expected_phase=run.phase,
            )
        assert store.load_machine_snapshot() == busy.machine
        assert store.load_events() == original_events


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("execution_id", "execution-other"),
        ("run_id", "run-other"),
        ("execution_phase", RunPhase.P2_TRANSFER_REACTOR_TO_SF),
        ("occurred_at", NOW + timedelta(seconds=1)),
    ],
)
def test_claim_event_metadata_must_match_snapshot(
    field_name: str,
    replacement: object,
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        started, busy = _persist_running_run_and_busy_machine(
            store, configuration
        )
        claim = claim_phase_execution(
            started.run,
            busy.machine,
            execution_id="execution-1",
            claimed_at=NOW,
        )
        mismatched = claim.events[0].model_copy(
            update={field_name: replacement}
        )

        with pytest.raises(PersistenceConflictError, match=field_name):
            store.persist_machine_transition(claim.machine, (mismatched,))


def test_claim_snapshot_and_final_event_must_agree(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        started, busy = _persist_running_run_and_busy_machine(
            store, configuration
        )
        claim = claim_phase_execution(
            started.run,
            busy.machine,
            execution_id="execution-1",
            claimed_at=NOW,
        )
        non_claim = claim.events[0].model_copy(
            update={
                "event_type": MachineEventType.RUN_STARTED,
                "execution_id": None,
                "execution_phase": None,
            }
        )

        with pytest.raises(
            PersistenceConflictError, match="active_execution requires"
        ):
            store.persist_machine_transition(claim.machine, (non_claim,))


def test_claim_event_requires_snapshot_intent(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        started, busy = _persist_running_run_and_busy_machine(
            store, configuration
        )
        claim = claim_phase_execution(
            started.run,
            busy.machine,
            execution_id="execution-1",
            claimed_at=NOW,
        )
        snapshot_without_intent = claim.machine.model_copy(
            update={"active_execution": None}
        )

        with pytest.raises(PersistenceConflictError, match="requires snapshot"):
            store.persist_machine_transition(
                snapshot_without_intent, claim.events
            )


def test_non_claim_event_rejects_execution_metadata(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        _, busy = _persist_running_run_and_busy_machine(store, configuration)
        non_claim = busy.events[0].model_copy(
            update={
                "sequence_number": busy.machine.event_sequence + 1,
                "execution_id": "execution-1",
                "execution_phase": RunPhase.P1_TRANSFER_S_TO_REACTOR,
            }
        )
        next_machine = busy.machine.model_copy(
            update={"event_sequence": busy.machine.event_sequence + 1}
        )

        with pytest.raises(PersistenceConflictError, match="non-claim"):
            store.persist_machine_transition(next_machine, (non_claim,))


def test_run_transition_machine_sequence_precondition(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        started, busy = _persist_running_run_and_busy_machine(
            store, configuration
        )
        next_run = started.run.model_copy(
            update={
                "event_sequence": started.run.event_sequence + 1,
                "phase": RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
            }
        )
        event = DomainEvent(
            run_id="run-1",
            sequence_number=next_run.event_sequence,
            occurred_at=NOW,
            event_type="PHASE_STARTED",
            run_status=RunStatus.RUNNING,
            run_phase=next_run.phase,
            message="test transition",
        )

        with pytest.raises(
            PersistenceConflictError, match="machine event sequence"
        ):
            store.persist_run_transition_with_machine_precondition(
                next_run,
                (event,),
                expected_machine_event_sequence=busy.machine.event_sequence - 1,
            )

        assert store.load_demo_run("run-1") == started.run


def test_run_transition_machine_precondition_validates_complete_aggregate(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        started, busy = _persist_running_run_and_busy_machine(
            store, configuration
        )
        advanced = complete_current_phase(started.run, NOW)
        machine_events = store.load_events("MACHINE", "machine")

        store.persist_run_transition_with_machine_precondition(
            advanced.run,
            advanced.events,
            expected_machine_event_sequence=busy.machine.event_sequence,
        )

        assert store.load_demo_run("run-1") == advanced.run
        assert store.load_machine_snapshot() == busy.machine
        assert store.load_events("MACHINE", "machine") == machine_events


def test_machine_snapshot_corruption_rolls_back_preconditioned_run_transition(
    tmp_path, configuration: DemoConfiguration
) -> None:
    database = tmp_path / "precondition-corrupt-machine.db"
    with SQLiteStore(database) as store:
        started, busy = _persist_running_run_and_busy_machine(
            store, configuration
        )
        advanced = complete_current_phase(started.run, NOW)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE machine_snapshot SET snapshot_json = '{broken'"
        )

    with SQLiteStore(database) as store:
        original_run_events = store.load_events("RUN", "run-1")
        with pytest.raises(PersistenceDataError, match="invalid machine snapshot JSON"):
            store.persist_run_transition_with_machine_precondition(
                advanced.run,
                advanced.events,
                expected_machine_event_sequence=busy.machine.event_sequence,
            )
        assert store.load_demo_run("run-1") == started.run
        assert store.load_events("RUN", "run-1") == original_run_events


def test_machine_event_history_corruption_rolls_back_preconditioned_transition(
    tmp_path, configuration: DemoConfiguration
) -> None:
    database = tmp_path / "precondition-machine-history.db"
    with SQLiteStore(database) as store:
        started, busy = _persist_running_run_and_busy_machine(
            store, configuration
        )
        advanced = complete_current_phase(started.run, NOW)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "DELETE FROM domain_events WHERE aggregate_type = 'MACHINE' "
            "AND event_sequence = 2"
        )

    with SQLiteStore(database) as store:
        original_run_events = store.load_events("RUN", "run-1")
        with pytest.raises(PersistenceDataError, match="non-contiguous"):
            store.persist_run_transition_with_machine_precondition(
                advanced.run,
                advanced.events,
                expected_machine_event_sequence=busy.machine.event_sequence,
            )
        assert store.load_demo_run("run-1") == started.run
        assert store.load_events("RUN", "run-1") == original_run_events


def test_run_transition_persists_and_returns_current_machine(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        started, busy = _persist_running_run_and_busy_machine(
            store, configuration
        )
        stopped = request_abort(started.run, NOW)
        machine_events = store.load_events("MACHINE", "machine")

        returned_machine = store.persist_run_transition_and_load_machine(
            stopped.run,
            stopped.events,
        )

        assert returned_machine == busy.machine
        assert store.load_demo_run("run-1") == stopped.run
        assert store.load_machine_snapshot() == busy.machine
        assert store.load_events("MACHINE", "machine") == machine_events


def test_run_transition_returns_existing_active_execution_unchanged(
    configuration: DemoConfiguration,
) -> None:
    with SQLiteStore() as store:
        started, _ = _persist_running_run_and_busy_machine(
            store, configuration
        )
        intent = store.claim_phase_execution(
            run_id="run-1",
            execution_id="execution-1",
            claimed_at=NOW,
            expected_run_event_sequence=started.run.event_sequence,
            expected_phase=started.run.phase,
        )
        machine_before_stop = store.load_machine_snapshot()
        machine_events = store.load_events("MACHINE", "machine")
        stopped = request_abort(started.run, NOW)

        returned_machine = store.persist_run_transition_and_load_machine(
            stopped.run,
            stopped.events,
        )

        assert returned_machine == machine_before_stop
        assert returned_machine.active_execution == intent
        assert store.load_events("MACHINE", "machine") == machine_events


def test_missing_machine_rolls_back_run_transition(
    configuration: DemoConfiguration,
) -> None:
    created = create_demo_run(
        "run-1", configuration, EXECUTION_SETTINGS, NOW
    )
    started = start_run(created.run, NOW)
    stopped = request_abort(started.run, NOW)
    with SQLiteStore() as store:
        store.persist_run_transition(created.run, created.events)
        store.persist_run_transition(started.run, started.events)
        original_events = store.load_events("RUN", "run-1")

        with pytest.raises(PersistenceConflictError, match="machine snapshot"):
            store.persist_run_transition_and_load_machine(
                stopped.run,
                stopped.events,
            )

        assert store.load_demo_run("run-1") == started.run
        assert store.load_events("RUN", "run-1") == original_events


def test_forced_stop_snapshot_failure_rolls_back_run_event(
    tmp_path, configuration: DemoConfiguration
) -> None:
    database = tmp_path / "stop-machine-read.db"
    with SQLiteStore(database) as store:
        started, _ = _persist_running_run_and_busy_machine(
            store, configuration
        )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TRIGGER reject_stop_snapshot "
            "BEFORE UPDATE ON demo_runs WHEN NEW.status = 'ABORTING' "
            "BEGIN SELECT RAISE(ABORT, 'forced Stop failure'); END"
        )

    stopped = request_abort(started.run, NOW)
    with SQLiteStore(database) as store:
        original_events = store.load_events()
        with pytest.raises(sqlite3.IntegrityError, match="forced Stop failure"):
            store.persist_run_transition_and_load_machine(
                stopped.run,
                stopped.events,
            )
        assert store.load_demo_run("run-1") == started.run
        assert store.load_events() == original_events


def test_corrupt_machine_aggregate_rolls_back_stop_transition(
    tmp_path, configuration: DemoConfiguration
) -> None:
    database = tmp_path / "stop-corrupt-machine.db"
    with SQLiteStore(database) as store:
        started, _ = _persist_running_run_and_busy_machine(
            store, configuration
        )
        stopped = request_abort(started.run, NOW)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "DELETE FROM domain_events WHERE aggregate_type = 'MACHINE' "
            "AND event_sequence = 2"
        )

    with SQLiteStore(database) as store:
        original_run_events = store.load_events("RUN", "run-1")
        with pytest.raises(PersistenceDataError, match="non-contiguous"):
            store.persist_run_transition_and_load_machine(
                stopped.run,
                stopped.events,
            )
        assert store.load_demo_run("run-1") == started.run
        assert store.load_events("RUN", "run-1") == original_run_events
