from datetime import UTC, datetime
import json
import sqlite3
import subprocess
import sys

import pytest

from app.demo.calibration_models import PumpCalibrationSet
from app.demo.machine_models import MachineState
from app.demo.phases import RunPhase
from app.demo.run_models import RunStatus
from app.hardware.owned_offline_runtime import OwnedOfflineRuntime
from app.hardware.owned_startup_inspection import OfflineDatabaseBundle, inspect_owned_startup
from app.hardware.owned_transfer_runner import provision_execution
from app.hardware.sequence_ownership import provision_ownership
from app.hardware.simulated_lifecycle import provision_lifecycle
from app.hardware.simulated_p1_runner import SimulatedP1Device, SimulationBlocked
from tests.test_command_planning import context
from tests.test_execution_coordinator import CONFIGURATION
from tests.test_owned_phase_session import READINESS
from tests.test_owned_pausable_demo import Clock
from tests.test_owned_timed_execution import TIMED_SETTINGS


@pytest.fixture
def bundle(tmp_path):
    owner, execution, life = (tmp_path / name for name in ("owner.db", "exec.db", "life.db"))
    oid = provision_ownership(owner)
    eid = provision_execution(execution, oid)
    lid = provision_lifecycle(life, eid)
    return OfflineDatabaseBundle(owner, oid, execution, eid, life, lid)


def open_runtime(bundle, clock=None):
    device = SimulatedP1Device(context())
    device.sf_mixer_running = False
    return OwnedOfflineRuntime(bundle, device, timer=(clock or Clock()).timer())


def start(runtime):
    ctx = context()
    runtime.start_fresh_run(
        "run-1", CONFIGURATION, TIMED_SETTINGS,
        PumpCalibrationSet(p1=ctx.pumps[0].calibration, p2=ctx.pumps[1].calibration),
        occurred_at=datetime.now(UTC), column_readiness=READINESS,
    )


def interrupted_wait(runtime, *, paused=False, started=True):
    start(runtime)
    runtime.execute_next()
    runtime.execute_next()
    store = runtime._store
    run = store.load_demo_run("run-1")
    assert run.phase is RunPhase.DELAY_BETWEEN_ADDITIONS
    runtime._owner.claim("interrupted-wait")
    now = datetime.now(UTC)
    intent = store.claim_phase_execution(
        run_id=run.run_id, execution_id="interrupted-wait", claimed_at=now,
        expected_run_event_sequence=run.event_sequence, expected_phase=run.phase,
    )
    if started:
        store.commit_phase_execution_start(
            intent, expected_run_event_sequence=run.event_sequence,
            expected_phase=run.phase, start_committed_at=now,
        )
        runtime._runner._db.execute(
            "INSERT INTO execution_waits VALUES ('interrupted-wait',1,'5','INTENT_PERSISTED',0)"
        )
    if paused:
        store.set_wait_paused("interrupted-wait", paused=True, occurred_at=now)


def assert_no_send(runtime):
    assert runtime._runner.device.calls == []
    assert runtime._runner.device.sf_calls == []
    with pytest.raises(SimulationBlocked):
        runtime.execute_next()


def test_full_demo_uses_exclusive_composition(bundle):
    with open_runtime(bundle) as runtime:
        start(runtime)
        for _ in range(10):
            result = runtime.execute_next()
        assert result.run.status is RunStatus.COMPLETED
    with open_runtime(bundle) as restarted:
        assert restarted.reconcile_interruption(datetime.now(UTC)).state is MachineState.READY
        assert_no_send(restarted)
        with pytest.raises(SimulationBlocked, match="pristine"):
            start(restarted)


@pytest.mark.parametrize("paused,started", [(False, False), (False, True), (True, True)])
def test_reconcile_wait_is_explicit_retains_owner_and_journals(bundle, paused, started):
    with open_runtime(bundle) as runtime:
        interrupted_wait(runtime, paused=paused, started=started)
        with pytest.raises(SimulationBlocked, match="original runtime"):
            runtime.reconcile_interruption(datetime.now(UTC))
    evidence = bundle.execution_path.read_bytes()
    ownership = bundle.ownership_path.read_bytes()
    with open_runtime(bundle) as restarted:
        assert restarted._store.load_demo_run("run-1").status is (
            RunStatus.PAUSED if paused else RunStatus.RUNNING
        )
        machine = restarted.reconcile_interruption(datetime.now(UTC))
        assert machine.state is (MachineState.RECOVERY_REQUIRED if started else MachineState.RECOVERING)
        assert restarted._store.load_demo_run("run-1").status is RunStatus.FAULTED
        assert machine.active_execution is None
        assert_no_send(restarted)
        snapshot = bundle.lifecycle_path.read_bytes()
        assert restarted.reconcile_interruption(datetime.now(UTC)) == machine
        assert snapshot == bundle.lifecycle_path.read_bytes()
    assert ownership == bundle.ownership_path.read_bytes()
    assert evidence == bundle.execution_path.read_bytes()


def test_gap_between_phases_gets_durable_block_before_faulting_run(bundle):
    with open_runtime(bundle) as runtime:
        start(runtime)
        runtime.execute_next()
    with open_runtime(bundle) as restarted:
        machine = restarted.reconcile_interruption(datetime.now(UTC))
        assert machine.state is MachineState.RECOVERING
        report = inspect_owned_startup(bundle)
        assert report.owner_state == "BLOCKED"
        assert report.owner_id.startswith("reconciliation-")
        assert report.runs[0].status is RunStatus.FAULTED
        assert_no_send(restarted)


def test_lifecycle_write_failure_keeps_reservation_and_original_state(bundle, monkeypatch):
    with open_runtime(bundle) as runtime:
        start(runtime)
    with open_runtime(bundle) as restarted:
        original = restarted._store._write_transition

        def fail(*args, **kwargs):
            raise sqlite3.OperationalError("disk failed")

        monkeypatch.setattr(restarted._store, "_write_transition", fail)
        before = bundle.lifecycle_path.read_bytes()
        with pytest.raises(sqlite3.OperationalError, match="disk failed"):
            restarted.reconcile_interruption(datetime.now(UTC))
        assert before == bundle.lifecycle_path.read_bytes()
        report = inspect_owned_startup(bundle)
        assert report.owner_state == "BLOCKED"
        assert report.runs[0].status is RunStatus.RUNNING
        assert_no_send(restarted)
        monkeypatch.setattr(restarted._store, "_write_transition", original)
        restarted.reconcile_interruption(datetime.now(UTC))
        assert inspect_owned_startup(bundle).owner_id == report.owner_id


def test_ownership_write_failure_prevents_lifecycle_changes(bundle, monkeypatch):
    with open_runtime(bundle) as runtime:
        start(runtime)
    with open_runtime(bundle) as restarted:
        def fail():
            raise sqlite3.OperationalError("owner write failed")
        monkeypatch.setattr(restarted._owner, "retain_for_reconciliation", fail)
        before = bundle.lifecycle_path.read_bytes()
        with pytest.raises(sqlite3.OperationalError):
            restarted.reconcile_interruption(datetime.now(UTC))
        assert before == bundle.lifecycle_path.read_bytes()
        assert_no_send(restarted)


def test_second_runtime_blocked_until_first_closes(bundle):
    first = open_runtime(bundle)
    try:
        with pytest.raises(SimulationBlocked, match="active runtime"):
            open_runtime(bundle)
    finally:
        first.close()
    with open_runtime(bundle):
        pass
    with pytest.raises(SimulationBlocked, match="closed"):
        first.execute_next()


def child_arguments(bundle):
    return json.dumps({
        name: str(getattr(bundle, name)) for name in bundle.__dataclass_fields__
    })


CHILD = '''
import json, os, sys
from pathlib import Path
from tests.test_owned_offline_runtime import open_runtime, interrupted_wait
from app.hardware.owned_startup_inspection import OfflineDatabaseBundle
from app.hardware.simulated_p1_runner import SimulationBlocked
values=json.loads(sys.argv[1])
for key in values:
    if key.endswith('_path'): values[key]=Path(values[key])
bundle=OfflineDatabaseBundle(**values)
try:
    with open_runtime(bundle) as runtime:
        if sys.argv[2] == 'crash':
            interrupted_wait(runtime, paused=True)
            os._exit(73)
except SimulationBlocked:
    sys.exit(42)
'''


def test_competing_process_cannot_open_bundle(bundle):
    with open_runtime(bundle):
        result = subprocess.run(
            [sys.executable, "-c", CHILD, child_arguments(bundle), "open"], timeout=10
        )
        assert result.returncode == 42


def test_process_death_releases_os_lock_but_not_durable_owner(bundle):
    result = subprocess.run(
        [sys.executable, "-c", CHILD, child_arguments(bundle), "crash"], timeout=10
    )
    assert result.returncode == 73
    with open_runtime(bundle) as restarted:
        assert restarted.initial_inspection.paused_run_ids == ("run-1",)
        assert restarted.initial_inspection.owner_id == "interrupted-wait"
        restarted.reconcile_interruption(datetime.now(UTC))
        assert inspect_owned_startup(bundle).owner_id == "interrupted-wait"
        assert_no_send(restarted)


def test_invalid_bundle_open_does_not_leak_locks(bundle):
    from dataclasses import replace
    from app.hardware.owned_startup_inspection import StartupInspectionError
    with pytest.raises(StartupInspectionError):
        open_runtime(replace(bundle, execution_id="wrong"))
    with open_runtime(bundle):
        pass


def test_existing_run_before_any_commands_cannot_be_adopted(bundle):
    with open_runtime(bundle) as runtime:
        start(runtime)
    with open_runtime(bundle) as restarted:
        with pytest.raises(SimulationBlocked, match="pristine"):
            start(restarted)
        assert_no_send(restarted)


def test_default_legacy_reconciliation_still_rejects_paused_wait(bundle):
    with open_runtime(bundle) as runtime:
        interrupted_wait(runtime, paused=True)
    with open_runtime(bundle) as restarted:
        before = bundle.lifecycle_path.read_bytes()
        with pytest.raises(ValueError):
            restarted._store.reconcile_interrupted_phase_execution_at_startup(datetime.now(UTC))
        assert before == bundle.lifecycle_path.read_bytes()
        assert restarted._store.load_demo_run("run-1").status is RunStatus.PAUSED


@pytest.mark.parametrize("statement", ["INSERT INTO hardware_sequences", "UPDATE hardware_owner", "COMMIT"])
def test_reservation_transaction_failure_rolls_back_before_lifecycle(bundle, monkeypatch, statement):
    with open_runtime(bundle) as runtime:
        start(runtime)
    with open_runtime(bundle) as restarted:
        original = restarted._owner._db

        class FaultConnection:
            def execute(self, sql, *args):
                if sql.startswith(statement):
                    raise sqlite3.OperationalError("reservation failed")
                return original.execute(sql, *args)

            def close(self):
                original.close()

        before = bundle.lifecycle_path.read_bytes()
        monkeypatch.setattr(restarted._owner, "_db", FaultConnection())
        with pytest.raises(sqlite3.OperationalError, match="reservation failed"):
            restarted.reconcile_interruption(datetime.now(UTC))
        assert before == bundle.lifecycle_path.read_bytes()
        assert inspect_owned_startup(bundle).owner_id is None
        assert_no_send(restarted)


def test_second_lifecycle_write_failure_rolls_back_run_and_machine(bundle, monkeypatch):
    with open_runtime(bundle) as runtime:
        interrupted_wait(runtime, paused=True)
    with open_runtime(bundle) as restarted:
        original = restarted._store._write_transition
        writes = []

        def fail_second(*args, **kwargs):
            writes.append(args[0])
            if len(writes) == 2:
                raise sqlite3.OperationalError("machine write failed")
            return original(*args, **kwargs)

        monkeypatch.setattr(restarted._store, "_write_transition", fail_second)
        before = bundle.lifecycle_path.read_bytes()
        with pytest.raises(sqlite3.OperationalError, match="machine write failed"):
            restarted.reconcile_interruption(datetime.now(UTC))
        assert writes == ["RUN", "MACHINE"]
        assert before == bundle.lifecycle_path.read_bytes()
        assert inspect_owned_startup(bundle).paused_run_ids == ("run-1",)
        assert_no_send(restarted)


def test_close_and_reconcile_cannot_interrupt_active_execution(bundle):
    clock = Clock()
    with open_runtime(bundle, clock) as runtime:
        start(runtime)
        runtime.execute_next()
        runtime.execute_next()
        attempts = []

        def attempt():
            with pytest.raises(SimulationBlocked, match="during runtime operation"):
                runtime.close()
            with pytest.raises(SimulationBlocked, match="operation already active"):
                runtime.reconcile_interruption(datetime.now(UTC))
            with pytest.raises(SimulationBlocked, match="active runtime"):
                open_runtime(bundle)
            attempts.append(True)

        clock.hook = attempt
        runtime.execute_next()
        assert attempts
        assert runtime._store.load_demo_run("run-1").status is RunStatus.RUNNING


def test_partial_bundle_overlap_cannot_bypass_process_lock(bundle, tmp_path):
    from dataclasses import replace
    other_path = tmp_path / "other-owner.db"
    other_id = provision_ownership(other_path)
    with open_runtime(bundle):
        with pytest.raises(SimulationBlocked, match="active runtime"):
            open_runtime(replace(bundle, ownership_path=other_path, ownership_id=other_id))


def test_stopped_run_is_not_resumed_by_reconciliation(bundle):
    from app.demo.application_service import GuidedDemoApplicationService
    with open_runtime(bundle) as runtime:
        start(runtime)
        GuidedDemoApplicationService(runtime._store).request_stop_demo("run-1", datetime.now(UTC))
    with open_runtime(bundle) as restarted:
        restarted.reconcile_interruption(datetime.now(UTC))
        report = inspect_owned_startup(bundle)
        assert report.runs[0].status is RunStatus.ABORTED
        assert report.owner_state == "BLOCKED"
        assert_no_send(restarted)


def test_failure_after_phase_resolution_keeps_old_owner_and_faults_run(bundle, monkeypatch):
    with open_runtime(bundle) as runtime:
        start(runtime)

        def fail_complete(lease):
            raise sqlite3.OperationalError("owner release failed")

        monkeypatch.setattr(runtime._owner, "complete", fail_complete)
        with pytest.raises(sqlite3.OperationalError, match="owner release failed"):
            runtime.execute_next()
        report = inspect_owned_startup(bundle)
        assert report.machine.active_execution is None
        assert report.owner_id is not None
    with open_runtime(bundle) as restarted:
        restarted.reconcile_interruption(datetime.now(UTC))
        after = inspect_owned_startup(bundle)
        assert after.owner_id == report.owner_id
        assert after.runs[0].status is RunStatus.FAULTED
        assert_no_send(restarted)


def test_death_after_reservation_before_lifecycle_commit_is_repeatable(bundle):
    with open_runtime(bundle) as runtime:
        start(runtime)
    script = CHILD.replace(
        "if sys.argv[2] == 'crash':",
        "if sys.argv[2] == 'reserve':\n"
        "            runtime._owner.retain_for_reconciliation()\n"
        "            os._exit(74)\n"
        "        if sys.argv[2] == 'crash':",
    )
    result = subprocess.run(
        [sys.executable, "-c", script, child_arguments(bundle), "reserve"], timeout=10
    )
    assert result.returncode == 74
    before = inspect_owned_startup(bundle)
    assert before.owner_state == "BLOCKED" and before.runs[0].status is RunStatus.RUNNING
    with open_runtime(bundle) as restarted:
        restarted.reconcile_interruption(datetime.now(UTC))
        assert inspect_owned_startup(bundle).owner_id == before.owner_id
        assert_no_send(restarted)


def test_paused_unstarted_intent_is_rejected_without_lifecycle_mutation(bundle):
    from app.demo.lifecycle import pause_run
    with open_runtime(bundle) as runtime:
        interrupted_wait(runtime, started=False)
        transition = pause_run(runtime._store.load_demo_run("run-1"), datetime.now(UTC))
        runtime._store.persist_run_transition(transition.run, transition.events)
    with open_runtime(bundle) as restarted:
        before = bundle.lifecycle_path.read_bytes()
        with pytest.raises(ValueError):
            restarted.reconcile_interruption(datetime.now(UTC))
        assert before == bundle.lifecycle_path.read_bytes()
        assert inspect_owned_startup(bundle).owner_id == "interrupted-wait"
        assert_no_send(restarted)


def test_naive_timestamp_rejected_before_reservation(bundle):
    with open_runtime(bundle) as runtime:
        start(runtime)
    with open_runtime(bundle) as restarted:
        before = bundle.ownership_path.read_bytes()
        with pytest.raises(ValueError, match="timezone"):
            restarted.reconcile_interruption(datetime(2026, 10, 1))
        assert before == bundle.ownership_path.read_bytes()


@pytest.mark.parametrize("missing", ["ownership_path", "execution_path", "lifecycle_path"])
def test_missing_bundle_file_is_not_created(bundle, tmp_path, missing):
    from dataclasses import replace
    missing_path = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        open_runtime(replace(bundle, **{missing: missing_path}))
    assert not missing_path.exists()
    with open_runtime(bundle):
        pass


def test_local_live_lease_cannot_be_reconciled(bundle):
    from app.hardware.sequence_ownership import OwnershipBlocked
    with open_runtime(bundle) as runtime:
        runtime._owner.claim("live-lease")
        before = bundle.ownership_path.read_bytes()
        with pytest.raises(OwnershipBlocked, match="fresh ownership"):
            runtime._owner.retain_for_reconciliation()
        assert before == bundle.ownership_path.read_bytes()


def test_process_dies_inside_actual_paused_execution(bundle):
    script = CHILD.replace(
        "interrupted_wait(runtime, paused=True)\n            os._exit(73)",
        "from tests.test_owned_offline_runtime import start\n"
        "            start(runtime)\n"
        "            runtime.execute_next()\n"
        "            runtime.execute_next()\n"
        "            def pause_and_die(seconds):\n"
        "                from datetime import datetime, UTC\n"
        "                intent = runtime._store.load_machine_snapshot().active_execution\n"
        "                runtime._store.set_wait_paused(\n"
        "                    intent.execution_id, paused=True, occurred_at=datetime.now(UTC))\n"
        "                os._exit(75)\n"
        "            from app.hardware.execution_timer import MonotonicExecutionTimer\n"
        "            runtime._runner._timer = MonotonicExecutionTimer(sleeper=pause_and_die)\n"
        "            runtime.execute_next()",
    )
    result = subprocess.run(
        [sys.executable, "-c", script, child_arguments(bundle), "crash"], timeout=10
    )
    assert result.returncode == 75
    before = inspect_owned_startup(bundle)
    assert before.paused_run_ids == ("run-1",)
    assert before.owner_id is not None
    assert before.journals[-1].non_successful
    evidence = bundle.execution_path.read_bytes()
    with open_runtime(bundle) as restarted:
        restarted.reconcile_interruption(datetime.now(UTC))
        after = inspect_owned_startup(bundle)
        assert after.owner_id == before.owner_id
        assert after.runs[0].status is RunStatus.FAULTED
        assert_no_send(restarted)
    assert evidence == bundle.execution_path.read_bytes()


def test_process_dies_after_lifecycle_reconciliation_does_not_repeat_it(bundle):
    with open_runtime(bundle) as runtime:
        start(runtime)
    script = CHILD.replace(
        "interrupted_wait(runtime, paused=True)\n            os._exit(73)",
        "from datetime import datetime, UTC\n"
        "            runtime.reconcile_interruption(datetime.now(UTC))\n"
        "            os._exit(76)",
    )
    result = subprocess.run(
        [sys.executable, "-c", script, child_arguments(bundle), "crash"], timeout=10
    )
    assert result.returncode == 76
    paths = (bundle.ownership_path, bundle.execution_path, bundle.lifecycle_path)
    before = tuple(path.read_bytes() for path in paths)
    with open_runtime(bundle) as restarted:
        restarted.reconcile_interruption(datetime.now(UTC))
        assert_no_send(restarted)
    assert before == tuple(path.read_bytes() for path in paths)
