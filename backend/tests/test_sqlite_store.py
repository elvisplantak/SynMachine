import json
import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.demo.events import DomainEvent
from app.demo.lifecycle import create_demo_run, start_run
from app.demo.machine_events import MachineEvent
from app.demo.machine_lifecycle import (
    complete_startup,
    create_machine,
    start_run as start_machine_run,
)
from app.demo.machine_models import MachineState
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


@pytest.mark.parametrize(
    ("event_update", "error"),
    [
        ({"run_status": RunStatus.RUNNING}, "final run event status"),
        ({"run_phase": RunPhase.P1_ASPIRATE_S}, "final run event phase"),
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
