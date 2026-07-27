import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier

import pytest

from app.demo.execution_lifecycle import ExecutionIdAlreadyUsedError
from app.demo.lifecycle import create_demo_run, request_abort, start_run
from app.demo.machine_events import MachineEvent, MachineEventType
from app.demo.machine_lifecycle import (
    complete_startup,
    create_machine,
    start_run as start_machine_run,
)
from app.demo.machine_models import (
    PhaseExecutionOutcome,
    PhaseExecutionResult,
    RuntimeHardwareFaultReason,
)
from app.demo.models import AdditionOrder, DemoConfiguration, DemoExecutionSettings
from app.demo.phase_result_resolution import (
    ExecutionAlreadyResolvedError,
    NoActiveExecutionError,
)
from app.persistence.sqlite_store import (
    PersistenceConflictError,
    PersistenceDataError,
    SQLiteStore,
)
import app.persistence.sqlite_store as sqlite_store_module

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


def _persist_claim(store: SQLiteStore) -> None:
    created = create_demo_run("run-1", CONFIGURATION, SETTINGS, NOW)
    started = start_run(created.run, NOW)
    machine = create_machine(NOW)
    ready = complete_startup(machine.machine, NOW)
    busy = start_machine_run(ready.machine, "run-1", NOW)
    store.persist_run_transition(created.run, created.events)
    store.persist_machine_transition(machine.machine, machine.events)
    store.persist_machine_transition(ready.machine, ready.events)
    store.persist_run_and_machine_transition(
        started.run, started.events, busy.machine, busy.events
    )
    store.claim_phase_execution(
        run_id="run-1", execution_id="execution-1", claimed_at=NOW
    )


def _completed_result() -> PhaseExecutionResult:
    return PhaseExecutionResult(
        execution_id="execution-1",
        outcome=PhaseExecutionOutcome.COMPLETED,
        reported_at=NOW,
    )


def test_resolution_is_atomic_and_auditable() -> None:
    with SQLiteStore() as store:
        _persist_claim(store)
        resolution = store.resolve_phase_execution(_completed_result())
        persisted_events = store.load_events("MACHINE", "machine")
        audit = next(
            event
            for event in persisted_events
            if isinstance(event, MachineEvent)
            and event.event_type is MachineEventType.PHASE_EXECUTION_RESOLVED
        )
        assert store.load_demo_run("run-1") == resolution.run
        assert store.load_machine_snapshot() == resolution.machine
        assert (
            audit.execution_id,
            audit.run_id,
            audit.execution_phase,
            audit.execution_outcome,
            audit.execution_claimed_at,
            audit.occurred_at,
        ) == (
            "execution-1",
            "run-1",
            resolution.run_events[0].run_phase,
            PhaseExecutionOutcome.COMPLETED,
            NOW,
            NOW,
        )


def test_replay_after_database_reopen_is_rejected(tmp_path) -> None:
    database = tmp_path / "resolved.db"
    with SQLiteStore(database) as store:
        _persist_claim(store)
        store.resolve_phase_execution(_completed_result())
        state = (
            store.load_demo_run("run-1"),
            store.load_machine_snapshot(),
            store.load_events(),
        )
    with SQLiteStore(database) as reopened:
        with pytest.raises(
            ExecutionAlreadyResolvedError, match="EXECUTION_ALREADY_RESOLVED"
        ):
            reopened.resolve_phase_execution(_completed_result())
        assert (
            reopened.load_demo_run("run-1"),
            reopened.load_machine_snapshot(),
            reopened.load_events(),
        ) == state


def test_no_active_execution_is_explicit_and_non_mutating() -> None:
    with SQLiteStore() as store:
        _persist_claim(store)
        store.resolve_phase_execution(_completed_result())
        different_result = _completed_result().model_copy(
            update={"execution_id": "never-claimed"}
        )
        before = (
            store.load_demo_run("run-1"),
            store.load_machine_snapshot(),
            store.load_events(),
        )
        with pytest.raises(NoActiveExecutionError, match="NO_ACTIVE_EXECUTION"):
            store.resolve_phase_execution(different_result)
        assert (
            store.load_demo_run("run-1"),
            store.load_machine_snapshot(),
            store.load_events(),
        ) == before


def test_second_matching_submission_has_exactly_one_winner() -> None:
    with SQLiteStore() as store:
        _persist_claim(store)
        store.resolve_phase_execution(_completed_result())
        with pytest.raises(ExecutionAlreadyResolvedError):
            store.resolve_phase_execution(
                _completed_result().model_copy(
                    update={
                        "outcome": PhaseExecutionOutcome.HARDWARE_COMMAND_FAILED,
                        "failure_reason": "late conflict",
                        "runtime_fault_reason": (
                            RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED
                        ),
                    }
                )
            )
        audits = [
            event
            for event in store.load_events("MACHINE", "machine")
            if isinstance(event, MachineEvent)
            and event.event_type is MachineEventType.PHASE_EXECUTION_RESOLVED
        ]
        assert len(audits) == 1


@pytest.mark.parametrize(
    ("trigger", "error"),
    [
        (
            "CREATE TRIGGER reject_resolution_run_event "
            "BEFORE INSERT ON domain_events "
            "WHEN NEW.aggregate_type = 'RUN' AND NEW.event_sequence = 4 "
            "BEGIN SELECT RAISE(ABORT, 'forced resolution run failure'); END",
            "forced resolution run failure",
        ),
        (
            "CREATE TRIGGER reject_resolution_machine_event "
            "BEFORE INSERT ON domain_events "
            "WHEN NEW.aggregate_type = 'MACHINE' AND NEW.event_sequence = 5 "
            "BEGIN SELECT RAISE(ABORT, 'forced resolution machine failure'); END",
            "forced resolution machine failure",
        ),
        (
            "CREATE TRIGGER reject_resolution_machine_snapshot "
            "BEFORE UPDATE ON machine_snapshot WHEN NEW.event_sequence = 5 "
            "BEGIN SELECT RAISE(ABORT, 'forced resolution snapshot failure'); END",
            "forced resolution snapshot failure",
        ),
    ],
)
def test_resolution_failure_rolls_back_complete_transaction(
    tmp_path, trigger: str, error: str
) -> None:
    database = tmp_path / "rollback.db"
    with SQLiteStore(database) as store:
        _persist_claim(store)
        before = (
            store.load_demo_run("run-1"),
            store.load_machine_snapshot(),
            store.load_events(),
        )
    with sqlite3.connect(database) as connection:
        connection.execute(trigger)
    with SQLiteStore(database) as store:
        with pytest.raises(sqlite3.IntegrityError, match=error):
            store.resolve_phase_execution(_completed_result())
        assert (
            store.load_demo_run("run-1"),
            store.load_machine_snapshot(),
            store.load_events(),
        ) == before


def test_corrupt_machine_json_blocks_resolution_without_writes(tmp_path) -> None:
    database = tmp_path / "corrupt.db"
    with SQLiteStore(database) as store:
        _persist_claim(store)
        events = store.load_events()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE machine_snapshot SET snapshot_json = '{not-json}'"
        )
    with SQLiteStore(database) as store:
        with pytest.raises(Exception, match="machine snapshot"):
            store.resolve_phase_execution(_completed_result())
        assert store.load_events() == events


def test_resolved_execution_id_cannot_be_reused_after_reopen(tmp_path) -> None:
    database = tmp_path / "unique-id.db"
    with SQLiteStore(database) as store:
        _persist_claim(store)
        store.resolve_phase_execution(_completed_result())
    with SQLiteStore(database) as reopened:
        before = (
            reopened.load_demo_run("run-1"),
            reopened.load_machine_snapshot(),
            reopened.load_events(),
        )
        with pytest.raises(ExecutionIdAlreadyUsedError, match="already used"):
            reopened.claim_phase_execution(
                run_id="run-1",
                execution_id="execution-1",
                claimed_at=NOW,
            )
        assert (
            reopened.load_demo_run("run-1"),
            reopened.load_machine_snapshot(),
            reopened.load_events(),
        ) == before


def test_resolved_execution_id_cannot_be_reused_in_same_session() -> None:
    with SQLiteStore() as store:
        _persist_claim(store)
        store.resolve_phase_execution(_completed_result())
        before = (
            store.load_demo_run("run-1"),
            store.load_machine_snapshot(),
            store.load_events(),
        )
        with pytest.raises(ExecutionIdAlreadyUsedError, match="already used"):
            store.claim_phase_execution(
                run_id="run-1",
                execution_id="execution-1",
                claimed_at=NOW,
            )
        assert (
            store.load_demo_run("run-1"),
            store.load_machine_snapshot(),
            store.load_events(),
        ) == before


def test_historically_resolved_active_token_is_persisted_corruption(
    tmp_path,
) -> None:
    database = tmp_path / "resolved-active.db"
    with SQLiteStore(database) as store:
        _persist_claim(store)
        intent = store.load_machine_snapshot().active_execution
        store.resolve_phase_execution(_completed_result())
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT snapshot_json FROM machine_snapshot"
        ).fetchone()
        import json

        payload = json.loads(row[0])
        payload["active_execution"] = intent.model_dump(mode="json")
        connection.execute(
            "UPDATE machine_snapshot SET snapshot_json = ?",
            (json.dumps(payload),),
        )
    with SQLiteStore(database) as store:
        events = store.load_events()
        with pytest.raises(PersistenceDataError, match="historically resolved"):
            store.resolve_phase_execution(_completed_result())
        assert store.load_events() == events


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("execution_id", "malformed-id"),
        ("execution_phase", "P2_TRANSFER_REACTOR_TO_SF"),
        ("execution_claimed_at", datetime(2026, 7, 27, 13, tzinfo=UTC)),
        ("execution_outcome", PhaseExecutionOutcome.STOPPED_AT_SAFE_BOUNDARY),
        (
            "runtime_fault_reason",
            RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED,
        ),
    ],
)
def test_malformed_domain_resolution_audit_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    replacement: object,
) -> None:
    with SQLiteStore() as store:
        _persist_claim(store)
        before = (
            store.load_demo_run("run-1"),
            store.load_machine_snapshot(),
            store.load_events(),
        )
        original = sqlite_store_module.resolve_phase_execution_transition

        def malformed(*args, **kwargs):
            resolution = original(*args, **kwargs)
            event = resolution.machine_events[0].model_copy(
                update={field_name: replacement}
            )
            return resolution.model_copy(
                update={
                    "machine_events": (
                        event,
                        *resolution.machine_events[1:],
                    )
                }
            )

        monkeypatch.setattr(
            sqlite_store_module,
            "resolve_phase_execution_transition",
            malformed,
        )
        with pytest.raises(PersistenceConflictError, match=field_name):
            store.resolve_phase_execution(_completed_result())
        assert (
            store.load_demo_run("run-1"),
            store.load_machine_snapshot(),
            store.load_events(),
        ) == before


def test_two_connections_resolving_same_token_have_one_winner(tmp_path) -> None:
    database = tmp_path / "race.db"
    with SQLiteStore(database) as store:
        _persist_claim(store)
    barrier = Barrier(2)

    def submit() -> str:
        with SQLiteStore(database) as store:
            barrier.wait()
            try:
                store.resolve_phase_execution(_completed_result())
            except (ExecutionAlreadyResolvedError, PersistenceConflictError):
                return "loser"
            return "winner"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = tuple(executor.map(lambda _: submit(), range(2)))
    assert sorted(outcomes) == ["loser", "winner"]
    with SQLiteStore(database) as store:
        audits = [
            event
            for event in store.load_events("MACHINE", "machine")
            if isinstance(event, MachineEvent)
            and event.event_type is MachineEventType.PHASE_EXECUTION_RESOLVED
        ]
        assert len(audits) == 1


def test_stop_then_result_and_result_then_stop_are_serialized() -> None:
    with SQLiteStore() as store:
        _persist_claim(store)
        original_phase = store.load_demo_run("run-1").phase
        aborting = request_abort(store.load_demo_run("run-1"), NOW)
        store.persist_run_transition_and_load_machine(
            aborting.run, aborting.events
        )
        stopped = store.resolve_phase_execution(_completed_result())
        assert stopped.run.status.value == "ABORTED"
        assert stopped.run.phase is original_phase
        assert stopped.machine.state.value == "FLUSH_REQUIRED"

    with SQLiteStore() as store:
        _persist_claim(store)
        resolved = store.resolve_phase_execution(_completed_result())
        advanced_phase = resolved.run.phase
        aborting = request_abort(store.load_demo_run("run-1"), NOW)
        machine = store.persist_run_transition_and_load_machine(
            aborting.run, aborting.events
        )
        assert aborting.run.phase is advanced_phase
        assert aborting.run.status.value == "ABORTING"
        assert machine == resolved.machine


def test_replay_does_not_bypass_corrupt_machine_json(tmp_path) -> None:
    database = tmp_path / "corrupt-replay.db"
    with SQLiteStore(database) as store:
        _persist_claim(store)
        store.resolve_phase_execution(_completed_result())
        events = store.load_events()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE machine_snapshot SET snapshot_json = '{not-json}'"
        )
    with SQLiteStore(database) as store:
        with pytest.raises(Exception, match="machine snapshot"):
            store.resolve_phase_execution(_completed_result())
        assert store.load_events() == events


def test_resolution_blocks_machine_metadata_and_history_corruption(
    tmp_path,
) -> None:
    metadata_database = tmp_path / "metadata.db"
    with SQLiteStore(metadata_database) as store:
        _persist_claim(store)
    with sqlite3.connect(metadata_database) as connection:
        connection.execute(
            "UPDATE machine_snapshot SET state = 'READY'"
        )
    with SQLiteStore(metadata_database) as store:
        with pytest.raises(PersistenceDataError, match="metadata"):
            store.resolve_phase_execution(_completed_result())

    history_database = tmp_path / "history.db"
    with SQLiteStore(history_database) as store:
        _persist_claim(store)
    with sqlite3.connect(history_database) as connection:
        connection.execute(
            "DELETE FROM domain_events "
            "WHERE aggregate_type = 'MACHINE' AND event_sequence = 2"
        )
    with SQLiteStore(history_database) as store:
        with pytest.raises(PersistenceDataError, match="non-contiguous"):
            store.resolve_phase_execution(_completed_result())
