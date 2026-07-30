from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.demo.application_service import GuidedDemoApplicationService
from app.demo.machine_lifecycle import (
    complete_recovery,
    complete_startup,
    create_machine,
    detect_interrupted_startup,
    record_runtime_hardware_fault,
    start_flush,
    start_run as start_machine_run,
)
from app.demo.machine_models import (
    MachineSnapshot,
    MachineState,
    RuntimeHardwareFaultReason,
)
from app.demo.models import AdditionOrder, DemoConfiguration, DemoExecutionSettings
from app.persistence.sqlite_store import SQLiteStore
from app.startup_bootstrap import (
    ProcessStartupDisposition,
    ProcessStartupResult,
    bootstrap_process_startup,
)

NOW = datetime(2026, 7, 30, 15, tzinfo=UTC)
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


def _state(store: SQLiteStore):
    return (
        store.load_machine_snapshot(),
        store.load_events("MACHINE", "machine"),
        store.load_events("RUN"),
    )


def _persist_active_run(
    store: SQLiteStore,
    *,
    active_execution: bool,
) -> None:
    service = GuidedDemoApplicationService(store)
    service.initialize_machine(NOW)
    service.complete_startup(NOW)
    service.create_run("run-1", CONFIGURATION, SETTINGS, NOW)
    service.start_run("run-1", NOW)
    if active_execution:
        run = store.load_demo_run("run-1")
        assert run is not None
        store.claim_phase_execution(
            run_id=run.run_id,
            execution_id="execution-1",
            claimed_at=NOW + timedelta(seconds=1),
            expected_run_event_sequence=run.event_sequence,
            expected_phase=run.phase,
        )


def _persist_machine_state(store: SQLiteStore, state: MachineState) -> None:
    created = create_machine(NOW)
    store.persist_machine_transition(created.machine, created.events)
    if state is MachineState.STARTING:
        return
    if state in {MachineState.RECOVERING, MachineState.FLUSH_REQUIRED}:
        recovering = detect_interrupted_startup(
            created.machine,
            "run-1",
            NOW,
        )
        store.persist_machine_transition(recovering.machine, recovering.events)
        if state is MachineState.RECOVERING:
            return
        flush_required = complete_recovery(recovering.machine, NOW)
        store.persist_machine_transition(
            flush_required.machine, flush_required.events
        )
        return
    ready = complete_startup(created.machine, NOW)
    store.persist_machine_transition(ready.machine, ready.events)
    if state is MachineState.READY:
        return
    if state is MachineState.FLUSHING:
        flushing = start_flush(ready.machine, NOW)
        store.persist_machine_transition(flushing.machine, flushing.events)
        return
    busy = start_machine_run(ready.machine, "run-1", NOW)
    store.persist_machine_transition(busy.machine, busy.events)
    if state is MachineState.RECOVERY_REQUIRED:
        recovery_required = record_runtime_hardware_fault(
            busy.machine,
            run_id="run-1",
            occurred_at=NOW,
            reason=RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED,
        )
        store.persist_machine_transition(
            recovery_required.machine, recovery_required.events
        )
        return


def test_uninitialized_bootstrap_is_read_only() -> None:
    with SQLiteStore() as store:
        before = _state(store)
        result = bootstrap_process_startup(store, NOW)

        assert result.disposition is ProcessStartupDisposition.UNINITIALIZED
        assert result.machine is None
        assert result.persistent_reconciliation_occurred is False
        assert _state(store) == before


@pytest.mark.parametrize(
    ("state", "disposition"),
    [
        (MachineState.STARTING, ProcessStartupDisposition.STARTUP_PENDING),
        (MachineState.READY, ProcessStartupDisposition.READY),
        (
            MachineState.RECOVERY_REQUIRED,
            ProcessStartupDisposition.RECOVERY_REQUIRED,
        ),
        (MachineState.RECOVERING, ProcessStartupDisposition.RECOVERING),
        (MachineState.FLUSH_REQUIRED, ProcessStartupDisposition.FLUSH_REQUIRED),
        (MachineState.FLUSHING, ProcessStartupDisposition.FLUSHING),
    ],
)
def test_non_busy_bootstrap_preserves_snapshot_and_history(
    state: MachineState,
    disposition: ProcessStartupDisposition,
) -> None:
    with SQLiteStore() as store:
        _persist_machine_state(store, state)
        before = _state(store)

        result = bootstrap_process_startup(store, NOW + timedelta(seconds=2))

        assert result.disposition is disposition
        assert result.machine == before[0]
        assert result.persistent_reconciliation_occurred is False
        assert _state(store) == before


@pytest.mark.parametrize(
    ("active_execution", "disposition"),
    [
        (
            True,
            ProcessStartupDisposition.PHASE_EXECUTION_RECONCILED,
        ),
        (
            False,
            ProcessStartupDisposition.ACTIVE_RUN_RECONCILED,
        ),
    ],
)
def test_busy_bootstrap_delegates_to_existing_reconciliation(
    active_execution: bool,
    disposition: ProcessStartupDisposition,
) -> None:
    with SQLiteStore() as store:
        _persist_active_run(store, active_execution=active_execution)

        result = bootstrap_process_startup(store, NOW + timedelta(seconds=2))

        assert result.disposition is disposition
        assert result.machine is not None
        assert result.machine.state is MachineState.RECOVERING
        assert result.persistent_reconciliation_occurred is True
        assert store.load_machine_snapshot() == result.machine


@pytest.mark.parametrize("active_execution", [True, False])
def test_repeated_bootstrap_does_not_reconcile_twice(
    active_execution: bool,
) -> None:
    with SQLiteStore() as store:
        _persist_active_run(store, active_execution=active_execution)
        first = bootstrap_process_startup(store, NOW + timedelta(seconds=2))
        after_first = _state(store)

        second = bootstrap_process_startup(store, NOW + timedelta(seconds=3))

        assert first.persistent_reconciliation_occurred is True
        assert second.disposition is ProcessStartupDisposition.RECOVERING
        assert second.persistent_reconciliation_occurred is False
        assert _state(store) == after_first


def test_bootstrap_rejects_naive_timestamp_without_writes() -> None:
    with SQLiteStore() as store:
        _persist_machine_state(store, MachineState.READY)
        before = _state(store)

        with pytest.raises(
            ValueError,
            match="process startup occurred_at must be timezone-aware",
        ):
            bootstrap_process_startup(store, datetime(2026, 7, 30, 15))

        assert _state(store) == before


@pytest.mark.parametrize(
    ("disposition", "machine", "reconciled", "message"),
    [
        (
            ProcessStartupDisposition.UNINITIALIZED,
            MachineSnapshot(state=MachineState.READY, event_sequence=0),
            False,
            "UNINITIALIZED requires machine to be None",
        ),
        (
            ProcessStartupDisposition.UNINITIALIZED,
            None,
            True,
            "UNINITIALIZED rejects persistent reconciliation",
        ),
        (
            ProcessStartupDisposition.READY,
            None,
            False,
            "READY requires a machine snapshot",
        ),
        (
            ProcessStartupDisposition.READY,
            MachineSnapshot(state=MachineState.READY, event_sequence=0),
            True,
            "READY requires persistent_reconciliation_occurred=False",
        ),
        (
            ProcessStartupDisposition.ACTIVE_RUN_RECONCILED,
            None,
            True,
            "ACTIVE_RUN_RECONCILED requires a machine snapshot",
        ),
        (
            ProcessStartupDisposition.ACTIVE_RUN_RECONCILED,
            MachineSnapshot(
                state=MachineState.RECOVERING,
                event_sequence=1,
                interrupted_run_id="run-1",
            ),
            False,
            "ACTIVE_RUN_RECONCILED requires "
            "persistent_reconciliation_occurred=True",
        ),
        (
            ProcessStartupDisposition.PHASE_EXECUTION_RECONCILED,
            MachineSnapshot(
                state=MachineState.RECOVERING,
                event_sequence=1,
                interrupted_run_id="run-1",
            ),
            False,
            "PHASE_EXECUTION_RECONCILED requires "
            "persistent_reconciliation_occurred=True",
        ),
    ],
)
def test_process_startup_result_rejects_inconsistent_fields(
    disposition: ProcessStartupDisposition,
    machine: MachineSnapshot | None,
    reconciled: bool,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        ProcessStartupResult(
            disposition=disposition,
            machine=machine,
            persistent_reconciliation_occurred=reconciled,
        )
