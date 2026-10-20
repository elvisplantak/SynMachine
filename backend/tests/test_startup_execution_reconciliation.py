import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.demo import lifecycle
from app.demo.application_service import GuidedDemoApplicationService
from app.demo.execution_lifecycle import ExecutionIdAlreadyUsedError
from app.demo.machine_events import MachineEvent, MachineEventType
from app.demo.machine_models import (
    MachineSnapshot,
    MachineState,
    PhaseExecutionOutcome,
    PhaseExecutionResult,
    PhaseExecutionStartupInterruptionKind,
    RuntimeHardwareFaultReason,
    StartupRecoveryReason,
)
from app.demo.models import AdditionOrder, DemoConfiguration, DemoExecutionSettings
from app.demo.phase_result_resolution import ExecutionAlreadyResolvedError
from app.demo.phases import RunPhase
from app.demo.run_models import RunStatus
from app.persistence.sqlite_store import (
    PersistenceDataError,
    SQLiteStore,
    StartupExecutionReconciliationConflictError,
)

NOW = datetime(2026, 7, 29, 12, tzinfo=UTC)
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


def _persist_active_execution(
    store: SQLiteStore,
    *,
    phase: RunPhase = RunPhase.P1_TRANSFER_S_TO_REACTOR,
    aborting: bool = False,
    start_committed: bool = False,
) -> None:
    service = GuidedDemoApplicationService(store)
    service.initialize_machine(NOW)
    service.complete_startup(NOW)
    service.create_run("run-1", CONFIGURATION, SETTINGS, NOW)
    service.start_run("run-1", NOW)
    run = store.load_demo_run("run-1")
    assert run is not None
    while run.phase is not phase:
        transition = lifecycle.complete_current_phase(run, NOW)
        store.persist_run_transition(transition.run, transition.events)
        run = transition.run
    intent = store.claim_phase_execution(
        run_id="run-1",
        execution_id="execution-1",
        claimed_at=NOW + timedelta(seconds=1),
        expected_run_event_sequence=run.event_sequence,
        expected_phase=run.phase,
    )
    if start_committed:
        store.commit_phase_execution_start(
            intent,
            expected_run_event_sequence=run.event_sequence,
            expected_phase=run.phase,
            start_committed_at=NOW + timedelta(seconds=2),
        )
    if aborting:
        service.request_stop_demo("run-1", NOW + timedelta(seconds=3))


@pytest.mark.parametrize(
    ("aborting", "expected_status"),
    [(False, RunStatus.FAULTED), (True, RunStatus.ABORTED)],
)
def test_claimed_not_started_reconciliation(
    aborting: bool,
    expected_status: RunStatus,
) -> None:
    with SQLiteStore() as store:
        _persist_active_execution(store, aborting=aborting)

        result = store.reconcile_interrupted_phase_execution_at_startup(
            NOW + timedelta(seconds=4)
        )

        assert result.interruption_kind is (
            PhaseExecutionStartupInterruptionKind.CLAIMED_NOT_STARTED
        )
        assert result.run.status is expected_status
        assert result.machine.state is MachineState.RECOVERING
        assert result.machine.active_execution is None
        assert result.machine.active_run_id is None
        assert result.machine.interrupted_run_id == "run-1"
        assert result.machine.runtime_fault_reason is None
        assert result.machine.startup_recovery_reason is None
        assert result.machine.hardware_outcome_unknown is False
        assert result.machine.carousel_position_untrusted is False


@pytest.mark.parametrize("aborting", [False, True])
def test_start_committed_reconciliation_marks_outcome_unknown(
    aborting: bool,
) -> None:
    with SQLiteStore() as store:
        _persist_active_execution(
            store,
            aborting=aborting,
            start_committed=True,
        )

        result = store.reconcile_interrupted_phase_execution_at_startup(
            NOW + timedelta(seconds=4)
        )

        assert result.run.status is RunStatus.FAULTED
        assert result.interruption_kind is (
            PhaseExecutionStartupInterruptionKind.START_COMMITTED_OUTCOME_UNKNOWN
        )
        assert result.machine.state is MachineState.RECOVERY_REQUIRED
        assert result.machine.active_execution is None
        assert result.machine.hardware_outcome_unknown is True
        assert result.machine.startup_recovery_reason is (
            StartupRecoveryReason.EXECUTION_OUTCOME_UNKNOWN_AT_STARTUP
        )
        assert result.machine.carousel_position_untrusted is False


def test_start_committed_column_reconciliation_marks_carousel_untrusted() -> None:
    with SQLiteStore() as store:
        _persist_active_execution(
            store,
            phase=RunPhase.COLUMN_FRACTION_COLLECTION,
            start_committed=True,
        )

        result = store.reconcile_interrupted_phase_execution_at_startup(
            NOW + timedelta(seconds=4)
        )

        assert result.run.status is RunStatus.FAULTED
        assert result.machine.startup_recovery_reason is (
            StartupRecoveryReason.CAROUSEL_POSITION_UNKNOWN_AT_STARTUP
        )
        assert result.machine.runtime_fault_reason is None
        assert result.machine.carousel_position_untrusted is True


def test_reconciliation_audit_is_complete_and_survives_reopen(tmp_path) -> None:
    database = tmp_path / "startup-reconciliation.db"
    with SQLiteStore(database) as store:
        _persist_active_execution(store, start_committed=True)
        before = store.load_machine_snapshot()
        assert before is not None and before.active_execution is not None
        intent = before.active_execution
        result = store.reconcile_interrupted_phase_execution_at_startup(
            NOW + timedelta(seconds=4)
        )
        event = result.machine_events[0]
        assert event.event_type is (
            MachineEventType.PHASE_EXECUTION_INTERRUPTED_AT_STARTUP
        )
        assert event.sequence_number == before.event_sequence + 1
        assert event.machine_state is result.machine.state
        assert event.execution_id == intent.execution_id
        assert event.run_id == intent.run_id
        assert event.execution_phase == intent.phase
        assert event.execution_claimed_at == intent.claimed_at
        assert event.execution_start_committed_at == intent.start_committed_at
    with SQLiteStore(database) as reopened:
        assert reopened.load_demo_run("run-1") == result.run
        assert reopened.load_machine_snapshot() == result.machine
        assert reopened.load_events("MACHINE", "machine")[-1] == event


def test_duplicate_reconciliation_rolls_back_without_new_event() -> None:
    with SQLiteStore() as store:
        _persist_active_execution(store)
        store.reconcile_interrupted_phase_execution_at_startup(
            NOW + timedelta(seconds=4)
        )
        snapshots = (
            store.load_demo_run("run-1"),
            store.load_machine_snapshot(),
            store.load_events(),
        )

        with pytest.raises(
            StartupExecutionReconciliationConflictError,
            match="requires BUSY machine",
        ):
            store.reconcile_interrupted_phase_execution_at_startup(
                NOW + timedelta(seconds=5)
            )

        assert (
            store.load_demo_run("run-1"),
            store.load_machine_snapshot(),
            store.load_events(),
        ) == snapshots


def test_interrupted_execution_id_cannot_be_reused_or_resolved() -> None:
    with SQLiteStore() as store:
        _persist_active_execution(store, start_committed=True)
        store.reconcile_interrupted_phase_execution_at_startup(
            NOW + timedelta(seconds=4)
        )
        run = store.load_demo_run("run-1")
        assert run is not None
        with pytest.raises(ExecutionIdAlreadyUsedError, match="already used"):
            store.claim_phase_execution(
                run_id="run-1",
                execution_id="execution-1",
                claimed_at=NOW + timedelta(seconds=5),
                expected_run_event_sequence=run.event_sequence,
                expected_phase=run.phase,
            )
        with pytest.raises(
            ExecutionAlreadyResolvedError,
            match="EXECUTION_ALREADY_TERMINALLY_CONSUMED",
        ):
            store.resolve_phase_execution(
                PhaseExecutionResult(
                    execution_id="execution-1",
                    outcome=PhaseExecutionOutcome.COMPLETED,
                    reported_at=NOW + timedelta(seconds=5),
                )
            )


@pytest.mark.parametrize(
    "corruption",
    ["run_id", "phase", "claim", "start_commit"],
)
def test_mismatched_persisted_state_rolls_back(
    tmp_path,
    corruption: str,
) -> None:
    database = tmp_path / f"{corruption}.db"
    with SQLiteStore(database) as store:
        _persist_active_execution(store, start_committed=corruption == "start_commit")
    with sqlite3.connect(database) as connection:
        if corruption in {"run_id", "phase"}:
            row = connection.execute(
                "SELECT snapshot_json FROM machine_snapshot"
            ).fetchone()
            payload = json.loads(row[0])
            if corruption == "run_id":
                payload["active_run_id"] = "other-run"
                payload["active_execution"]["run_id"] = "other-run"
            else:
                payload["active_execution"]["phase"] = (
                    RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR
                )
            connection.execute(
                "UPDATE machine_snapshot SET snapshot_json = ?",
                (json.dumps(payload),),
            )
        else:
            event_type = (
                "PHASE_EXECUTION_CLAIMED"
                if corruption == "claim"
                else "PHASE_EXECUTION_START_COMMITTED"
            )
            row = connection.execute(
                "SELECT rowid, payload_json FROM domain_events "
                "WHERE event_type = ?",
                (event_type,),
            ).fetchone()
            payload = json.loads(row[1])
            payload["run_id"] = "other-run"
            connection.execute(
                "UPDATE domain_events SET payload_json = ? WHERE rowid = ?",
                (json.dumps(payload), row[0]),
            )
    with SQLiteStore(database) as store:
        state_before_attempt = (
            store.load_demo_run("run-1"),
            store.load_machine_snapshot(),
            store.load_events(),
        )
        with pytest.raises(
            (
                PersistenceDataError,
                StartupExecutionReconciliationConflictError,
            )
        ):
            store.reconcile_interrupted_phase_execution_at_startup(
                NOW + timedelta(seconds=4)
            )
        assert (
            store.load_demo_run("run-1"),
            store.load_machine_snapshot(),
            store.load_events(),
        ) == state_before_attempt


def test_invalid_reconciliation_timestamp_rolls_back() -> None:
    with SQLiteStore() as store:
        _persist_active_execution(store, start_committed=True)
        original = (
            store.load_demo_run("run-1"),
            store.load_machine_snapshot(),
            store.load_events(),
        )
        with pytest.raises(ValidationError, match="startup interruption precedes"):
            store.reconcile_interrupted_phase_execution_at_startup(NOW)
        assert (
            store.load_demo_run("run-1"),
            store.load_machine_snapshot(),
            store.load_events(),
        ) == original


@pytest.mark.parametrize("unsupported_status", [RunStatus.ABORTED, RunStatus.FAULTED])
def test_unsupported_run_status_reconciliation_rolls_back_without_writes(
    unsupported_status: RunStatus,
) -> None:
    with SQLiteStore() as store:
        _persist_active_execution(store)
        run = store.load_demo_run("run-1")
        assert run is not None
        if unsupported_status is RunStatus.ABORTED:
            aborting = lifecycle.request_abort(run, NOW + timedelta(seconds=2))
            store.persist_run_transition(aborting.run, aborting.events)
            unsupported = lifecycle.confirm_abort(
                aborting.run, NOW + timedelta(seconds=3)
            )
        else:
            unsupported = lifecycle.fault_run(
                run,
                NOW + timedelta(seconds=3),
                "Persisted fault before startup reconciliation",
            )
        store.persist_run_transition(unsupported.run, unsupported.events)
        original_run = store.load_demo_run("run-1")
        original_machine = store.load_machine_snapshot()
        original_run_events = store.load_events("RUN", "run-1")
        original_machine_events = store.load_events("MACHINE", "machine")
        assert original_machine is not None
        original_execution = original_machine.active_execution

        with pytest.raises(
            StartupExecutionReconciliationConflictError,
            match=(
                "startup execution reconciliation requires matching "
                "active aggregates"
            ),
        ):
            store.reconcile_interrupted_phase_execution_at_startup(
                NOW + timedelta(seconds=4)
            )

        assert store.load_demo_run("run-1") == original_run
        assert store.load_machine_snapshot() == original_machine
        assert store.load_events("RUN", "run-1") == original_run_events
        assert store.load_events("MACHINE", "machine") == original_machine_events
        assert store.load_machine_snapshot().active_execution == original_execution
        assert all(
            event.event_type
            is not MachineEventType.PHASE_EXECUTION_INTERRUPTED_AT_STARTUP
            for event in store.load_events("MACHINE", "machine")
        )


@pytest.mark.parametrize(
    "values",
    [
        {
            "runtime_fault_reason": RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED,
            "startup_recovery_reason": (
                StartupRecoveryReason.EXECUTION_OUTCOME_UNKNOWN_AT_STARTUP
            ),
        },
        {"hardware_outcome_unknown": False},
        {
            "startup_recovery_reason": (
                StartupRecoveryReason.CAROUSEL_POSITION_UNKNOWN_AT_STARTUP
            ),
            "carousel_position_untrusted": False,
        },
    ],
)
def test_machine_snapshot_rejects_invalid_startup_recovery_metadata(values) -> None:
    defaults = {
        "state": MachineState.RECOVERY_REQUIRED,
        "event_sequence": 1,
        "interrupted_run_id": "run-1",
        "startup_recovery_reason": (
            StartupRecoveryReason.EXECUTION_OUTCOME_UNKNOWN_AT_STARTUP
        ),
        "hardware_outcome_unknown": True,
        "carousel_position_untrusted": False,
    }
    with pytest.raises(ValidationError):
        MachineSnapshot(**(defaults | values))


def test_non_recovery_required_rejects_startup_recovery_reason() -> None:
    with pytest.raises(ValidationError, match="default runtime fault metadata"):
        MachineSnapshot(
            state=MachineState.RECOVERING,
            event_sequence=1,
            interrupted_run_id="run-1",
            startup_recovery_reason=(
                StartupRecoveryReason.EXECUTION_OUTCOME_UNKNOWN_AT_STARTUP
            ),
        )


def test_startup_interruption_event_validates_kind_and_timestamp() -> None:
    defaults = {
        "sequence_number": 1,
        "occurred_at": NOW + timedelta(seconds=2),
        "event_type": MachineEventType.PHASE_EXECUTION_INTERRUPTED_AT_STARTUP,
        "machine_state": MachineState.RECOVERING,
        "run_id": "run-1",
        "message": "interrupted",
        "execution_id": "execution-1",
        "execution_phase": RunPhase.P1_TRANSFER_S_TO_REACTOR,
        "execution_claimed_at": NOW + timedelta(seconds=1),
        "startup_interruption_kind": (
            PhaseExecutionStartupInterruptionKind.CLAIMED_NOT_STARTED
        ),
    }
    with pytest.raises(ValidationError, match="rejects execution_start_committed_at"):
        MachineEvent(
            **(
                defaults
                | {"execution_start_committed_at": NOW + timedelta(seconds=1)}
            )
        )
    with pytest.raises(ValidationError, match="precedes claimed_at"):
        MachineEvent(**(defaults | {"occurred_at": NOW}))
    with pytest.raises(
        ValidationError,
        match="START_COMMITTED_OUTCOME_UNKNOWN requires execution_start_committed_at",
    ):
        MachineEvent(
            **(
                defaults
                | {
                    "machine_state": MachineState.RECOVERY_REQUIRED,
                    "startup_recovery_reason": (
                        StartupRecoveryReason.EXECUTION_OUTCOME_UNKNOWN_AT_STARTUP
                    ),
                    "hardware_outcome_unknown": True,
                    "startup_interruption_kind": (
                        PhaseExecutionStartupInterruptionKind
                        .START_COMMITTED_OUTCOME_UNKNOWN
                    ),
                }
            )
        )
