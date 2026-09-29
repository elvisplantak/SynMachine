from datetime import UTC, datetime
import sqlite3

import pytest

from app.demo.calibration_models import PumpCalibrationSet
from app.demo.column_fraction_collection_operation_plan import (
    ColumnFractionCollectionConfiguration,
    plan_column_fraction_collection_operations,
)
from app.demo.guided_demo_phase_executor import ColumnFractionCollectionReadiness
from app.demo.machine_models import MachineState
from app.demo.p1_solvent_operation_plan import plan_p1_solvent_to_reactor_operations
from app.demo.p1_reagent_operation_plan import plan_p1_reagent_to_reactor_operations
from app.demo.p2_reactor_to_sf_operation_plan import plan_p2_reactor_to_sf_operations
from app.demo.p2_sf_to_column_operation_plan import plan_p2_sf_to_column_operations
from app.demo.phases import RunPhase
from app.demo.run_models import RunStatus
from app.hardware.arduino_serial import ArduinoUnavailableError
from app.hardware.command_plan_store import PlanSource, SQLiteCommandPlanStore
from app.hardware.simulated_lifecycle import (
    SimulationLifecycleStore,
    SimulatedLifecycleCoordinator,
    provision_lifecycle,
)
from app.hardware.simulated_p1_runner import (
    SimulatedP1Device,
    SimulatedP1Runner,
    SimulationBlocked,
    provision_simulation,
)
from tests.test_command_planning import context
from tests.test_execution_coordinator import _started_service, _advance_to_phase

PHASES = [
    RunPhase.P1_TRANSFER_S_TO_REACTOR,
    RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
    RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
    RunPhase.P2_TRANSFER_REACTOR_TO_SF,
    RunPhase.P2_TRANSFER_SF_TO_COLUMN,
    RunPhase.COLUMN_FRACTION_COLLECTION,
]


def now():
    return datetime.now(UTC)


@pytest.fixture
def case(tmp_path):
    opened = []

    def create(phase=PHASES[0], suffix=""):
        sim = tmp_path / f"sim{suffix}.db"
        sid = provision_simulation(sim)
        life = tmp_path / f"life{suffix}.db"
        lid = provision_lifecycle(life, sid)
        store = SimulationLifecycleStore(life, lid, sid)
        opened.append(store)
        service = _started_service(store)
        _advance_to_phase(service, store, phase)
        run = store.load_demo_run("run-1")
        ctx = context()
        cals = PumpCalibrationSet(p1=ctx.pumps[0].calibration, p2=ctx.pumps[1].calibration)
        if phase == PHASES[0]:
            source = plan_p1_solvent_to_reactor_operations(run.fluid_plan, cals)
        elif phase in PHASES[1:3]:
            source = plan_p1_reagent_to_reactor_operations(phase, run.fluid_plan, cals)
        elif phase == PHASES[3]:
            source = plan_p2_reactor_to_sf_operations(run.fluid_plan, cals)
        elif phase == PHASES[4]:
            source = plan_p2_sf_to_column_operations(run.fluid_plan, cals)
        else:
            source = plan_column_fraction_collection_operations(
                ColumnFractionCollectionConfiguration.from_execution_settings(
                    run.execution_settings,
                    carousel_ready_confirmed=True,
                    column_bottom_valve_referenced_confirmed=True,
                )
            )
        with SQLiteCommandPlanStore(sim) as plans:
            plans.persist(
                PlanSource(run_id=run.run_id, run_event_sequence=run.event_sequence, plan=source),
                ctx,
            )
        device = SimulatedP1Device(ctx)
        runner = SimulatedP1Runner(sim, sid, device)
        opened.append(runner)
        coordinator = SimulatedLifecycleCoordinator(store, runner)
        return coordinator, service, sim, life, sid, lid, cals

    yield create
    for resource in reversed(opened):
        resource.close()


def execute(c):
    return c[0].execute(
        "test-phase-1", c[6], column_readiness=ColumnFractionCollectionReadiness(True, True)
    )


def owner(path):
    with sqlite3.connect(path) as db:
        return db.execute("SELECT phase_id FROM simulation_owner").fetchone()[0]


@pytest.mark.parametrize("phase", PHASES)
def test_success_binds_real_lifecycle_and_durable_commands(case, phase, monkeypatch):
    import serial

    monkeypatch.setattr(serial, "Serial", lambda *a, **k: pytest.fail("Serial opened"))
    c = case(phase)
    coordinator = c[0]

    def check(_):
        intent = coordinator.store.load_machine_snapshot().active_execution
        assert intent.execution_id == "test-phase-1"
        assert intent.start_committed_at is not None
        assert owner(c[2]) == "test-phase-1"

    coordinator.runner.device.before_send = check
    coordinator.runner.device.before_sf_send = check
    result = execute(c)
    assert result.machine.active_execution is None
    assert result.run.phase != phase or result.run.status == RunStatus.COMPLETED
    assert owner(c[2]) is None
    with pytest.raises(SimulationBlocked):
        execute(c)


def test_stop_wins_between_claim_and_start_no_send(case, monkeypatch):
    c = case()
    store = c[0].store
    claim = store.claim_phase_execution

    def stop(**kw):
        intent = claim(**kw)
        c[1].request_stop_demo("run-1", now())
        return intent

    monkeypatch.setattr(store, "claim_phase_execution", stop)
    result = execute(c)
    assert result.run.status == RunStatus.ABORTED
    assert c[0].runner.device.calls == []
    assert c[0].runner.status("test-phase-1") == ("STOPPED", 0)
    assert owner(c[2]) == "test-phase-1"


@pytest.mark.parametrize("phase", [PHASES[0], PHASES[4], PHASES[5]])
def test_stop_during_execution_keeps_required_cleanup(case, phase):
    c = case(phase)
    device = c[0].runner.device

    def stop(_):
        run = c[0].store.load_demo_run("run-1")
        if run.status == RunStatus.RUNNING:
            c[1].request_stop_demo("run-1", now())

    if phase == PHASES[4]:
        device.before_sf_send = stop
    elif phase == PHASES[5]:
        device.during_wait = stop
    else:
        device.before_send = stop
    result = execute(c)
    assert result.run.status == RunStatus.ABORTED
    assert owner(c[2]) == "test-phase-1"
    if phase == PHASES[4]:
        assert device.sf_calls[-1]["state"] == "CLOSED"
    if phase == PHASES[5]:
        assert device.calls[-1]["arguments"] == {"position_degrees": 4}
        assert c[0].runner.status("test-phase-1")[0] == "COLLECTION_STOP_REQUESTED"


def test_unknown_keeps_active_execution_and_reopen_never_sends(case):
    c = case()

    def fail(_):
        raise ArduinoUnavailableError("timeout")

    c[0].runner.device.before_send = fail
    with pytest.raises(ArduinoUnavailableError):
        execute(c)
    assert c[0].store.load_machine_snapshot().active_execution is not None
    assert owner(c[2]) == "test-phase-1"
    before = (c[2].read_bytes(), c[3].read_bytes())
    with SimulationLifecycleStore(c[3], c[5], c[4]) as store:
        runner = SimulatedP1Runner(c[2], c[4], SimulatedP1Device(context()))
        try:
            with pytest.raises(SimulationBlocked):
                SimulatedLifecycleCoordinator(store, runner).execute("test-phase-1", c[6])
            assert not runner.device.calls
        finally:
            runner.close()
    assert before == (c[2].read_bytes(), c[3].read_bytes())
    result = c[0].store.reconcile_interrupted_phase_execution_at_startup(now())
    assert result.machine.state == MachineState.RECOVERY_REQUIRED


def test_resolution_failure_does_not_release_owner(case, monkeypatch):
    c = case()

    def fail(_):
        assert owner(c[2]) == "test-phase-1"
        raise OSError("result write failed")

    monkeypatch.setattr(c[0].store, "resolve_phase_execution", fail)
    with pytest.raises(OSError):
        execute(c)
    assert owner(c[2]) == "test-phase-1"
    assert c[0].runner.status("test-phase-1")[0] == "RUNNING"
    assert c[0].store.load_machine_snapshot().active_execution is not None


@pytest.mark.parametrize("stage", ["claim_phase_execution", "commit_phase_execution_start"])
def test_lifecycle_write_failure_sends_nothing(case, monkeypatch, stage):
    c = case()

    def fail(*a, **kw):
        raise OSError("write failed")

    monkeypatch.setattr(c[0].store, stage, fail)
    with pytest.raises(OSError):
        execute(c)
    assert not c[0].runner.device.calls
    assert owner(c[2]) == "test-phase-1"


@pytest.mark.parametrize("bad", ["missing", "empty", "wrong_identity", "wrong_binding"])
def test_lifecycle_open_fails_without_creating_or_repairing(case, tmp_path, bad):
    c = case()
    path = c[3]
    lid, sid = c[5], c[4]
    if bad in ("missing", "empty"):
        path = tmp_path / "bad.db"
        if bad == "empty":
            path.touch()
    elif bad == "wrong_identity":
        lid = "wrong"
    else:
        sid = "wrong"
    before = path.read_bytes() if path.exists() else None
    with pytest.raises((SimulationBlocked, sqlite3.Error)):
        SimulationLifecycleStore(path, lid, sid)
    assert (path.read_bytes() if path.exists() else None) == before


def test_wrong_store_runner_pair_rejected(case):
    a, b = case(), case(suffix="other")
    with pytest.raises(SimulationBlocked):
        SimulatedLifecycleCoordinator(a[0].store, b[0].runner)


def test_stale_run_sends_nothing(case):
    c = case()
    c[1].request_stop_demo("run-1", now())
    with pytest.raises(SimulationBlocked):
        execute(c)
    assert c[0].runner.device.calls == []
    assert owner(c[2]) is None


def test_stop_racing_with_final_resolution_keeps_owner(case, monkeypatch):
    c = case()
    resolve = c[0].store.resolve_phase_execution

    def stop_then_resolve(result):
        c[1].request_stop_demo("run-1", now())
        return resolve(result)

    monkeypatch.setattr(c[0].store, "resolve_phase_execution", stop_then_resolve)
    result = execute(c)
    assert result.run.status == RunStatus.ABORTED
    assert owner(c[2]) == "test-phase-1"


def test_competing_coordinator_cannot_send_during_resolution(case, monkeypatch):
    c = case()
    resolve = c[0].store.resolve_phase_execution

    def compete(result):
        with SimulationLifecycleStore(c[3], c[5], c[4]) as store:
            runner = SimulatedP1Runner(c[2], c[4], SimulatedP1Device(context()))
            try:
                with pytest.raises(SimulationBlocked):
                    SimulatedLifecycleCoordinator(store, runner).execute("test-phase-1", c[6])
                assert not runner.device.calls
            finally:
                runner.close()
        return resolve(result)

    monkeypatch.setattr(c[0].store, "resolve_phase_execution", compete)
    execute(c)
    assert owner(c[2]) is None


def test_owner_release_write_failure_after_lifecycle_resolution_blocks_restart(case, monkeypatch):
    c = case()

    def fail(*a, **kw):
        raise OSError("owner result write failed")

    monkeypatch.setattr(c[0].runner, "_finish", fail)
    with pytest.raises(OSError):
        execute(c)
    assert c[0].store.load_machine_snapshot().active_execution is None
    assert c[0].store.load_demo_run("run-1").phase != PHASES[0]
    assert owner(c[2]) == "test-phase-1"
    count = len(c[0].runner.device.calls)
    with pytest.raises(SimulationBlocked):
        execute(c)
    assert len(c[0].runner.device.calls) == count


def test_calibration_mismatch_rejected_before_claim(case):
    c = case()
    changed = c[6].model_copy(
        update={"p1": c[6].p1.model_copy(update={"working_empty_chamber_position_steps": 4200})}
    )
    with pytest.raises(SimulationBlocked, match="calibration"):
        c[0].execute("test-phase-1", changed)
    assert owner(c[2]) is None
    assert c[0].store.load_machine_snapshot().active_execution is None


def test_source_operations_mismatch_actual_run_rejected_before_claim(case):
    from app.demo.fluid_plan import build_fluid_plan
    from tests.test_p1_solvent_operation_plan import configuration

    c = case()
    # A different valid solvent plan shares the run/sequence identity but not volumes.
    run = c[0].store.load_demo_run("run-1")
    ctx = context(phase_execution_id="other-plan")
    with SQLiteCommandPlanStore(c[2]) as plans:
        different = plan_p1_solvent_to_reactor_operations(
            build_fluid_plan(configuration(total_mixture_volume_ml="12")), c[6]
        )
        plans.persist(
            PlanSource(run_id=run.run_id, run_event_sequence=run.event_sequence, plan=different),
            ctx,
        )
    with pytest.raises(SimulationBlocked, match="operations"):
        c[0].execute("other-plan", c[6])
    assert owner(c[2]) is None


def test_process_death_during_send_keeps_start_and_blocks_restart(case):
    import subprocess
    import sys

    c = case()
    code = """
import os, sys
from pathlib import Path
from app.hardware.simulated_lifecycle import SimulationLifecycleStore, SimulatedLifecycleCoordinator
from app.hardware.simulated_p1_runner import SimulatedP1Runner, SimulatedP1Device
from app.demo.calibration_models import PumpCalibrationSet
from tests.test_command_planning import context
ctx = context()
cals = PumpCalibrationSet(p1=ctx.pumps[0].calibration, p2=ctx.pumps[1].calibration)
store = SimulationLifecycleStore(Path(sys.argv[2]), sys.argv[4], sys.argv[3])
device = SimulatedP1Device(ctx)
device.before_send = lambda _: os._exit(73)
runner = SimulatedP1Runner(Path(sys.argv[1]), sys.argv[3], device)
SimulatedLifecycleCoordinator(store, runner).execute('test-phase-1', cals)
"""
    process = subprocess.run([sys.executable, "-c", code, str(c[2]), str(c[3]), c[4], c[5]])
    assert process.returncode == 73
    assert c[0].store.load_machine_snapshot().active_execution.start_committed_at is not None
    assert owner(c[2]) == "test-phase-1"
    before = (c[2].read_bytes(), c[3].read_bytes())
    with pytest.raises(SimulationBlocked):
        execute(c)
    assert c[0].runner.device.calls == []
    assert before == (c[2].read_bytes(), c[3].read_bytes())


def test_absent_plan_is_distinct_from_wrong_database(case):
    c = case()
    with pytest.raises(SimulationBlocked, match="plan is absent"):
        c[0].execute("absent", c[6])
    assert owner(c[2]) is None
    assert c[0].store.load_machine_snapshot().active_execution is None


@pytest.mark.parametrize(
    "mutation",
    [
        "PRAGMA user_version=999",
        "DROP TABLE demo_runs",
        "INSERT INTO offline_lifecycle_identity SELECT * FROM offline_lifecycle_identity",
    ],
)
def test_incompatible_lifecycle_database_never_repaired(case, mutation):
    c = case()
    with sqlite3.connect(c[3]) as db:
        db.execute(mutation)
    before = c[3].read_bytes()
    from app.persistence.sqlite_store import PersistenceSchemaError

    with pytest.raises((SimulationBlocked, PersistenceSchemaError)):
        SimulationLifecycleStore(c[3], c[5], c[4])
    assert before == c[3].read_bytes()


def test_definitive_failure_preserves_exception_and_requires_reconciliation(case):
    from app.hardware.arduino_serial import ArduinoCommandFailedError

    c = case()
    error = ArduinoCommandFailedError("PUMP_MOTION_TIMEOUT", True)

    def fail(_):
        raise error

    c[0].runner.device.before_send = fail
    with pytest.raises(ArduinoCommandFailedError) as caught:
        execute(c)
    assert caught.value is error
    assert c[0].runner.status("test-phase-1") == ("FAILED", 0)
    assert c[0].store.load_machine_snapshot().active_execution is not None
    assert owner(c[2]) == "test-phase-1"
