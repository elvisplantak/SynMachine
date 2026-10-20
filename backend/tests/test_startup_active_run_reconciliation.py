import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.demo import lifecycle
from app.demo import startup_active_run_reconciliation as active_run_reconciliation
from app.demo.application_service import GuidedDemoApplicationService
from app.demo.machine_events import MachineEvent, MachineEventType
from app.demo.machine_models import (
    MachineState,
    PhaseExecutionOutcome,
    PhaseExecutionStartupInterruptionKind,
)
from app.demo.models import AdditionOrder, DemoConfiguration, DemoExecutionSettings
from app.demo.phases import RunPhase
from app.demo.run_models import RunStatus
from app.demo.startup_active_run_reconciliation import (
    StartupActiveRunReconciliationError,
)
from app.persistence import sqlite_store as sqlite_store_module
from app.persistence.sqlite_store import (
    PersistenceConflictError,
    SQLiteStore,
    StartupActiveRunReconciliationConflictError,
)

NOW = datetime(2026, 7, 30, 12, tzinfo=UTC)
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
    fraction_count=2,
    fraction_duration_seconds="5",
)


def _persist_active_run(
    store: SQLiteStore,
    *,
    phase: RunPhase = RunPhase.P1_TRANSFER_S_TO_REACTOR,
    aborting: bool = False,
) -> None:
    service = GuidedDemoApplicationService(store)
    service.initialize_machine(NOW)
    service.complete_startup(NOW)
    service.create_run("run-1", CONFIGURATION, SETTINGS, NOW)
    service.start_run("run-1", NOW)
    run = store.load_demo_run("run-1")
    assert run is not None
    while run.phase is not phase:
        transition = lifecycle.complete_current_phase(run, NOW + timedelta(seconds=1))
        store.persist_run_transition(transition.run, transition.events)
        run = transition.run
    if aborting:
        service.request_stop_demo("run-1", NOW + timedelta(seconds=2))


def _state(store: SQLiteStore):
    return (
        store.load_demo_run("run-1"),
        store.load_machine_snapshot(),
        store.load_events("RUN", "run-1"),
        store.load_events("MACHINE", "machine"),
    )


@pytest.mark.parametrize(
    ("aborting", "expected_status"),
    [(False, RunStatus.FAULTED), (True, RunStatus.ABORTED)],
)
def test_reconciles_running_and_aborting_active_run(
    aborting: bool,
    expected_status: RunStatus,
) -> None:
    with SQLiteStore() as store:
        _persist_active_run(store, aborting=aborting)
        before = store.load_machine_snapshot()
        assert before is not None

        result = store.reconcile_interrupted_active_run_at_startup(
            NOW + timedelta(seconds=3)
        )

        assert result.run.status is expected_status
        assert result.machine.state is MachineState.RECOVERING
        assert result.machine.active_run_id is None
        assert result.machine.interrupted_run_id == "run-1"
        assert result.machine.active_execution is None
        assert result.machine.runtime_fault_reason is None
        assert result.machine.startup_recovery_reason is None
        assert result.machine.hardware_outcome_unknown is False
        assert result.machine.carousel_position_untrusted is False
        assert len(result.machine_events) == 1
        event = result.machine_events[0]
        assert event.event_type is MachineEventType.RUN_INTERRUPTED_AT_STARTUP
        assert event.sequence_number == before.event_sequence + 1
        assert event.run_id == "run-1"
        assert event.machine_state is result.machine.state
        assert event.execution_id is None
        assert event.execution_phase is None
        assert event.runtime_fault_reason is None
        assert event.startup_recovery_reason is None
        if not aborting:
            assert result.run_events[0].reason == (
                "Backend startup found an interrupted active run without an "
                "active phase execution"
            )


@pytest.mark.parametrize(
    "phase",
    [RunPhase.REACTION_HOLD, RunPhase.P1_TRANSFER_S_TO_REACTOR],
)
def test_reconciliation_does_not_continue_timer_or_unclaimed_hardware_phase(
    phase: RunPhase,
) -> None:
    with SQLiteStore() as store:
        _persist_active_run(store, phase=phase)
        before = store.load_demo_run("run-1")
        assert before is not None and before.phase is phase

        result = store.reconcile_interrupted_active_run_at_startup(
            NOW + timedelta(seconds=3)
        )

        assert result.run.status is RunStatus.FAULTED
        assert result.run.phase is phase
        assert result.run.event_sequence == before.event_sequence + 1
        assert all(
            event.event_type is not MachineEventType.PHASE_EXECUTION_RESOLVED
            for event in result.machine_events
        )


def test_reconciliation_survives_database_reopen_and_duplicate_is_read_only(
    tmp_path,
) -> None:
    database = tmp_path / "active-run-reconciliation.db"
    with SQLiteStore(database) as store:
        _persist_active_run(store, phase=RunPhase.SF_SETTLING)
        result = store.reconcile_interrupted_active_run_at_startup(
            NOW + timedelta(seconds=3)
        )
        reconciled = _state(store)
        with pytest.raises(
            StartupActiveRunReconciliationConflictError,
            match="requires BUSY machine",
        ):
            store.reconcile_interrupted_active_run_at_startup(
                NOW + timedelta(seconds=4)
            )
        assert _state(store) == reconciled

    with SQLiteStore(database) as reopened:
        assert _state(reopened) == reconciled
        machine_events = reopened.load_events("MACHINE", "machine")
        assert machine_events[-1] == result.machine_events[0]
        assert machine_events[-1].sequence_number == len(machine_events)


@pytest.mark.parametrize("failure", ["mismatch", "missing", "unsupported", "timestamp"])
def test_failed_reconciliation_rolls_back_both_aggregates(
    tmp_path,
    failure: str,
) -> None:
    database = tmp_path / f"{failure}.db"
    with SQLiteStore(database) as store:
        _persist_active_run(store)
        if failure == "unsupported":
            run = store.load_demo_run("run-1")
            assert run is not None
            transition = lifecycle.fault_run(
                run,
                NOW + timedelta(seconds=2),
                "Persisted terminal status",
            )
            store.persist_run_transition(transition.run, transition.events)

    if failure in {"mismatch", "missing"}:
        with sqlite3.connect(database) as connection:
            if failure == "mismatch":
                row = connection.execute(
                    "SELECT snapshot_json FROM machine_snapshot"
                ).fetchone()
                payload = json.loads(row[0])
                payload["active_run_id"] = "other-run"
                connection.execute(
                    "UPDATE machine_snapshot SET snapshot_json = ?",
                    (json.dumps(payload),),
                )
            else:
                connection.execute(
                    "DELETE FROM domain_events WHERE aggregate_type = 'RUN' "
                    "AND aggregate_id = 'run-1'"
                )
                connection.execute("DELETE FROM demo_runs WHERE run_id = 'run-1'")

    with SQLiteStore(database) as store:
        before = _state(store)
        error = (
            ValidationError
            if failure == "timestamp"
            else StartupActiveRunReconciliationConflictError
        )
        occurred_at = (
            datetime(2026, 7, 30, 12)
            if failure == "timestamp"
            else NOW + timedelta(seconds=3)
        )
        with pytest.raises(error):
            store.reconcile_interrupted_active_run_at_startup(occurred_at)
        assert _state(store) == before


def test_active_execution_is_rejected_by_new_reconciliation() -> None:
    with SQLiteStore() as store:
        _persist_active_run(store)
        run = store.load_demo_run("run-1")
        assert run is not None
        store.claim_phase_execution(
            run_id=run.run_id,
            execution_id="execution-1",
            claimed_at=NOW + timedelta(seconds=1),
            expected_run_event_sequence=run.event_sequence,
            expected_phase=run.phase,
        )
        before = _state(store)

        with pytest.raises(
            StartupActiveRunReconciliationConflictError,
            match="no active execution",
        ):
            store.reconcile_interrupted_active_run_at_startup(
                NOW + timedelta(seconds=2)
            )
        assert _state(store) == before

        execution_result = store.reconcile_interrupted_phase_execution_at_startup(
            NOW + timedelta(seconds=2)
        )
        assert execution_result.machine_events[0].event_type is (
            MachineEventType.PHASE_EXECUTION_INTERRUPTED_AT_STARTUP
        )


def test_domain_reconciliation_rejects_mismatched_run_id() -> None:
    with SQLiteStore() as store:
        _persist_active_run(store)
        machine = store.load_machine_snapshot()
        run = store.load_demo_run("run-1")
        assert machine is not None
        assert run is not None

        with pytest.raises(
            StartupActiveRunReconciliationError,
            match=(
                "startup active-run reconciliation requires matching "
                "active aggregates"
            ),
        ):
            active_run_reconciliation.reconcile_interrupted_active_run_at_startup(
                run.model_copy(update={"run_id": "other-run"}),
                machine,
                NOW + timedelta(seconds=3),
            )


def test_persistence_rejects_event_snapshot_run_id_divergence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with SQLiteStore() as store:
        _persist_active_run(store)
        before = _state(store)
        original_transition = sqlite_store_module.reconcile_active_run_transition

        def divergent_transition(run, machine, occurred_at):
            reconciliation = original_transition(run, machine, occurred_at)
            event = reconciliation.machine_events[0].model_copy(
                update={"run_id": "other-run"}
            )
            return reconciliation.model_copy(update={"machine_events": (event,)})

        monkeypatch.setattr(
            sqlite_store_module,
            "reconcile_active_run_transition",
            divergent_transition,
        )

        with pytest.raises(
            PersistenceConflictError,
            match="audit event run ID mismatch",
        ):
            store.reconcile_interrupted_active_run_at_startup(
                NOW + timedelta(seconds=3)
            )

        assert _state(store) == before
        assert all(
            event.event_type is not MachineEventType.RUN_INTERRUPTED_AT_STARTUP
            for event in store.load_events("MACHINE", "machine")
        )


@pytest.mark.parametrize(
    "metadata",
    [
        {"execution_id": "execution-1"},
        {"execution_phase": RunPhase.P1_TRANSFER_S_TO_REACTOR},
        {"execution_outcome": PhaseExecutionOutcome.COMPLETED},
        {"execution_claimed_at": NOW},
        {"execution_start_committed_at": NOW},
        {
            "startup_interruption_kind": (
                PhaseExecutionStartupInterruptionKind.CLAIMED_NOT_STARTED
            )
        },
        {"failure_reason": "failure"},
        {"cleanup_failure_reason": "cleanup failure"},
        {"primary_failure_reason": "primary failure"},
    ],
)
def test_run_interrupted_at_startup_rejects_phase_execution_metadata(
    metadata,
) -> None:
    with pytest.raises(
        ValidationError,
        match="RUN_INTERRUPTED_AT_STARTUP rejects phase-execution metadata",
    ):
        MachineEvent(
            sequence_number=1,
            occurred_at=NOW,
            event_type=MachineEventType.RUN_INTERRUPTED_AT_STARTUP,
            machine_state=MachineState.RECOVERING,
            run_id="run-1",
            message="Interrupted active run",
            **metadata,
        )


def test_run_interrupted_at_startup_accepts_valid_event() -> None:
    event = MachineEvent(
        sequence_number=1,
        occurred_at=NOW,
        event_type=MachineEventType.RUN_INTERRUPTED_AT_STARTUP,
        machine_state=MachineState.RECOVERING,
        run_id="run-1",
        message="Interrupted active run",
    )

    assert event.event_type is MachineEventType.RUN_INTERRUPTED_AT_STARTUP
