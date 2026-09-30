from dataclasses import dataclass
from datetime import UTC, datetime
import sqlite3

import pytest

from app.demo.calibration_models import PumpCalibrationSet
from app.demo.guided_demo_phase_executor import (
    GuidedDemoPhaseExecutor,
    ColumnFractionCollectionReadiness,
)
from app.demo.phases import RunPhase
from app.demo.timed_sf_operation_plan import plan_timed_sf_operations
from app.demo.column_fraction_collection_operation_plan import (
    ColumnFractionCollectionConfiguration,
    plan_column_fraction_collection_operations,
)
from app.demo.hardware_contract import BottomValveState
from app.demo.operation_executor import ProtectedOperationError
from app.demo.run_models import RunStatus
from app.hardware.arduino_serial import ArduinoCommandFailedError, ArduinoUnavailableError
from app.hardware.command_plan_store import PlanSource, SQLiteCommandPlanStore
from app.hardware.owned_transfer_runner import OwnedTransferRunner, provision_execution
from app.hardware.sequence_ownership import HardwareOwnership, OwnershipBlocked, provision_ownership
from app.hardware.simulated_lifecycle import (
    PlanLifecycleCoordinator,
    SimulationLifecycleStore,
    provision_lifecycle,
)
from app.hardware.simulated_p1_runner import SimulatedP1Device, SimulationBlocked
from tests.test_command_planning import context
from tests.test_execution_coordinator import _advance_to_phase, _started_service
from tests.test_simulated_lifecycle import PHASES


@dataclass
class Case:
    coordinator: object
    service: object
    runner: object
    owner: object
    paths: tuple
    identities: tuple
    calibrations: object

    def execute(self):
        return self.coordinator.execute(
            "test-phase-1",
            self.calibrations,
            column_readiness=ColumnFractionCollectionReadiness(True, True),
        )

    def stop(self):
        self.service.request_stop_demo("run-1", datetime.now(UTC))

    def retained(self):
        with sqlite3.connect(self.paths[0]) as db:
            return db.execute("SELECT sequence_id FROM hardware_owner").fetchone()[0]

    def rows(self, table):
        with sqlite3.connect(self.paths[1]) as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(f"SELECT * FROM {table}")]


@pytest.fixture
def case(tmp_path):
    resources = []

    def create(phase=PHASES[0], *, settings=None, timer=None, mixer_running=None):
        directory = tmp_path / str(len(resources))
        directory.mkdir()
        paths = tuple(directory / name for name in ("owner.db", "execution.db", "life.db"))
        oid = provision_ownership(paths[0])
        eid = provision_execution(paths[1], oid)
        lid = provision_lifecycle(paths[2], eid)
        owner = HardwareOwnership(paths[0], oid)
        store = SimulationLifecycleStore(paths[2], lid, eid)
        resources.extend([owner, store])
        service = _started_service(store) if settings is None else _started_service(store, settings)
        _advance_to_phase(service, store, phase)
        run = store.load_demo_run("run-1")
        ctx = context()
        cals = PumpCalibrationSet(p1=ctx.pumps[0].calibration, p2=ctx.pumps[1].calibration)
        # Use the same source builders as the lifecycle coordinator.
        from app.demo.p1_solvent_operation_plan import plan_p1_solvent_to_reactor_operations
        from app.demo.p1_reagent_operation_plan import plan_p1_reagent_to_reactor_operations
        from app.demo.p2_reactor_to_sf_operation_plan import plan_p2_reactor_to_sf_operations
        from app.demo.p2_sf_to_column_operation_plan import plan_p2_sf_to_column_operations

        if phase == PHASES[0]:
            source = plan_p1_solvent_to_reactor_operations(run.fluid_plan, cals)
        elif phase in PHASES[1:3]:
            source = plan_p1_reagent_to_reactor_operations(phase, run.fluid_plan, cals)
        elif phase == PHASES[3]:
            source = plan_p2_reactor_to_sf_operations(run.fluid_plan, cals)
        elif phase == PHASES[4]:
            source = plan_p2_sf_to_column_operations(run.fluid_plan, cals)
        elif phase is RunPhase.COLUMN_FRACTION_COLLECTION:
            source = plan_column_fraction_collection_operations(
                ColumnFractionCollectionConfiguration.from_execution_settings(
                    run.execution_settings,
                    carousel_ready_confirmed=True,
                    column_bottom_valve_referenced_confirmed=True,
                )
            )
        else:
            source = plan_timed_sf_operations(run)
        if phase in PHASES:
            assert source.operations == GuidedDemoPhaseExecutor._build_current_phase_operations(
                run, cals, column_readiness=ColumnFractionCollectionReadiness(True, True)
            )
        with SQLiteCommandPlanStore(paths[1]) as plans:
            plans.persist(
                PlanSource(run_id=run.run_id, run_event_sequence=run.event_sequence, plan=source),
                ctx,
            )
        device = SimulatedP1Device(ctx)
        device.sf_mixer_running = mixer_running
        runner = OwnedTransferRunner(paths[1], eid, owner, device, timer=timer)
        resources.append(runner)
        return Case(
            PlanLifecycleCoordinator(store, runner),
            service,
            runner,
            owner,
            paths,
            (oid, eid, lid),
            cals,
        )

    yield create
    for resource in reversed(resources):
        resource.close()


def assert_restart_blocked(c):
    before = [p.read_bytes() for p in c.paths]
    owner = HardwareOwnership(c.paths[0], c.identities[0])
    store = SimulationLifecycleStore(c.paths[2], c.identities[2], c.identities[1])
    runner = OwnedTransferRunner(c.paths[1], c.identities[1], owner, SimulatedP1Device(context()))
    runner.device.sf_mixer_running = False
    try:
        with pytest.raises((SimulationBlocked, OwnershipBlocked)):
            PlanLifecycleCoordinator(store, runner).execute(
                "test-phase-1",
                c.calibrations,
                column_readiness=ColumnFractionCollectionReadiness(True, True),
            )
        with pytest.raises(OwnershipBlocked):
            runner.hardware.sf_service.set_state(BottomValveState.CLOSED)
        assert not runner.device.calls and not runner.device.sf_calls
    finally:
        runner.close()
        store.close()
        owner.close()
    assert before == [p.read_bytes() for p in c.paths]


@pytest.mark.parametrize("phase", PHASES[:5])
def test_whole_transfer_path_and_services_share_owner(case, phase, monkeypatch):
    import serial

    monkeypatch.setattr(serial, "Serial", lambda *a, **kw: pytest.fail("opened real Serial"))
    c = case(phase)

    def check(values):
        intent = c.coordinator.store.load_machine_snapshot().active_execution
        assert intent.execution_id == "test-phase-1" and intent.start_committed_at
        assert c.retained() == "test-phase-1"
        table = "sf_action_journal" if "state" in values else "arduino_command_journal"
        key = "action_id" if "state" in values else "operation_command_id"
        row = next(r for r in c.rows(table) if r[key] == values["operation_command_id"])
        assert row["state"] == "INTENT_PERSISTED"
        with pytest.raises(OwnershipBlocked):
            c.runner.hardware.sf_service.set_state(BottomValveState.CLOSED)
        with pytest.raises(OwnershipBlocked):
            c.runner.hardware.arduino_service.execute(
                phase_execution_id="service",
                operation_command_id="service-command",
                command="VALVE_HOME",
                arguments={"valve_id": "V1"},
            )

    c.runner.device.before_send = check
    c.runner.device.before_sf_send = check
    result = c.execute()
    assert result.machine.active_execution is None
    assert c.retained() is None
    assert all(r["state"] == "COMPLETED" for r in c.rows("arduino_command_journal"))
    assert all(r["state"] == "COMPLETED" for r in c.rows("sf_action_journal"))
    assert c.runner.device.calls
    if phase == PHASES[4]:
        assert c.runner.device.sf_calls[-1]["state"] == "CLOSED"
    # Same composition protects Service and durably records its SF commands too.
    c.runner.device.before_sf_send = lambda _: None
    c.runner.hardware.sf_service.set_state(BottomValveState.CLOSED)
    assert c.rows("sf_action_journal")[-1]["phase_id"].startswith("service.sf.")
    assert c.retained() is None


@pytest.mark.parametrize("stage", ["claim", "during", "resolution"])
def test_stop_keeps_owner_across_lifecycle(case, stage, monkeypatch):
    c = case(PHASES[4])
    store = c.coordinator.store
    if stage == "during":

        def stop(values):
            if values["state"] == "OPEN":
                c.stop()

        c.runner.device.before_sf_send = stop
    else:
        name = "claim_phase_execution" if stage == "claim" else "resolve_phase_execution"
        original = getattr(store, name)

        def stop(*a, **kw):
            if stage == "resolution":
                c.stop()
            result = original(*a, **kw)
            if stage == "claim":
                c.stop()
            return result

        monkeypatch.setattr(store, name, stop)
    assert c.execute().run.status == RunStatus.ABORTED
    assert c.retained() == "test-phase-1"
    if stage == "claim":
        assert not c.runner.device.calls and not c.runner.device.sf_calls
    else:
        assert c.runner.device.sf_calls[-1]["state"] == "CLOSED"
    assert_restart_blocked(c)


@pytest.mark.parametrize("primary", ["ok", "failed", "unknown"])
@pytest.mark.parametrize("fault", ["intent", "result"])
def test_required_close_persistence_fault_through_whole_path(case, primary, fault):
    c = case(PHASES[4])
    error = (
        ArduinoCommandFailedError("PUMP_MOTION_TIMEOUT", True)
        if primary == "failed"
        else ArduinoUnavailableError("timeout")
    )
    original = c.runner._sf._db

    class Fault:
        def execute(self, sql, args=()):
            if (
                fault == "intent"
                and sql.startswith("INSERT INTO sf_action")
                and args[3] == "CLOSED"
                and any(v["state"] == "OPEN" for v in c.runner.device.sf_calls)
            ):
                raise sqlite3.OperationalError("CLOSE intent fault")
            if fault == "result" and "SET state='COMPLETED'" in sql:
                row = original.execute(
                    "SELECT target FROM sf_action_journal WHERE action_id=?", args
                ).fetchone()
                if row == ("CLOSED",) and any(
                    v["state"] == "OPEN" for v in c.runner.device.sf_calls
                ):
                    raise sqlite3.OperationalError("CLOSE result fault")
            return original.execute(sql, args)

    c.runner._sf._db = Fault()

    def fail(values):
        if c.runner.device.sf_calls and c.runner.device.sf_calls[-1]["state"] == "OPEN":
            if primary != "ok":
                raise error

    c.runner.device.before_send = fail
    expected = sqlite3.OperationalError if primary == "ok" else ProtectedOperationError
    with pytest.raises(expected) as caught:
        c.execute()
    if primary != "ok":
        assert caught.value.primary_error is error
        assert isinstance(caught.value.followup_error, sqlite3.OperationalError)
        assert c.rows("arduino_command_journal")[-1]["state"] == (
            "FAILED" if primary == "failed" else "OUTCOME_UNKNOWN"
        )
    assert c.retained() == "test-phase-1"
    assert c.coordinator.store.load_machine_snapshot().active_execution is not None
    rows = c.rows("sf_action_journal")
    if fault == "intent":
        assert rows[-1]["target"] == "OPEN"
        assert c.runner.device.sf_calls[-1]["state"] == "OPEN"
    else:
        assert [v["state"] for v in c.runner.device.sf_calls][-2:] == ["OPEN", "CLOSED"]
        assert rows[-1]["state"] == "INTENT_PERSISTED"
    assert_restart_blocked(c)


@pytest.mark.parametrize(
    "stage", ["claim_phase_execution", "commit_phase_execution_start", "resolve_phase_execution"]
)
def test_lifecycle_write_fault_retains_owner(case, monkeypatch, stage):
    c = case()

    def fail(*a, **kw):
        assert c.retained() == "test-phase-1"
        raise OSError(stage)

    monkeypatch.setattr(c.coordinator.store, stage, fail)
    with pytest.raises(OSError, match=stage):
        c.execute()
    if stage != "resolve_phase_execution":
        assert not c.runner.device.calls
    assert c.retained() == "test-phase-1"
    assert_restart_blocked(c)


def test_unknown_primary_successful_close_still_unresolved(case):
    c = case(PHASES[4])

    def fail(_):
        if c.runner.device.sf_calls and c.runner.device.sf_calls[-1]["state"] == "OPEN":
            raise ArduinoUnavailableError("primary unknown")

    c.runner.device.before_send = fail
    with pytest.raises(ArduinoUnavailableError):
        c.execute()
    assert c.rows("sf_action_journal")[-1]["state"] == "COMPLETED"
    assert c.runner.device.sf_calls[-1]["state"] == "CLOSED"
    assert c.coordinator.store.load_machine_snapshot().active_execution is not None
    assert_restart_blocked(c)


@pytest.mark.parametrize("bad", ["missing", "empty", "schema", "identity", "owner"])
def test_execution_store_rejects_wrong_database_without_repair(case, tmp_path, bad):
    c = case()
    path = c.paths[1]
    identity = c.identities[1]
    if bad in ("missing", "empty"):
        path = tmp_path / "bad.db"
        if bad == "empty":
            path.touch()
    elif bad == "schema":
        with sqlite3.connect(path) as db:
            db.execute("DROP TABLE sf_action_journal")
    elif bad == "identity":
        identity = "wrong"
    else:
        with sqlite3.connect(path) as db:
            db.execute("UPDATE execution_identity SET ownership_id='wrong'")
    before = path.read_bytes() if path.exists() else None
    with pytest.raises((SimulationBlocked, sqlite3.Error)):
        OwnedTransferRunner(path, identity, c.owner, SimulatedP1Device(context()))
    assert (path.read_bytes() if path.exists() else None) == before


def test_owner_release_failure_after_resolved_lifecycle_blocks_service(case, monkeypatch):
    c = case()

    def fail(_):
        assert c.coordinator.store.load_machine_snapshot().active_execution is None
        raise OSError("release failed")

    monkeypatch.setattr(c.owner, "complete", fail)
    with pytest.raises(OSError, match="release failed"):
        c.execute()
    assert c.retained() == "test-phase-1"
    assert_restart_blocked(c)


def test_session_change_after_sf_open_keeps_unknown_even_after_close(case):
    c = case(PHASES[4])

    def change(values):
        if values["state"] == "OPEN":
            c.runner.device.sf_session_id = "new-session"

    c.runner.device.before_sf_send = change
    with pytest.raises(ProtectedOperationError):
        c.execute()
    assert c.rows("sf_action_journal")[-1]["state"] == "OUTCOME_UNKNOWN"
    assert c.runner.device.sf_calls[-1]["state"] == "OPEN"
    assert_restart_blocked(c)


@pytest.mark.parametrize("stage", ["arduino", "sf"])
def test_process_death_persists_intent_and_restart_sends_nothing(case, stage):
    import subprocess
    import sys

    c = case(PHASES[4] if stage == "sf" else PHASES[0])
    code = """
import os, sys
from pathlib import Path
from app.hardware.owned_transfer_runner import OwnedTransferRunner
from app.hardware.sequence_ownership import HardwareOwnership
from app.hardware.simulated_lifecycle import PlanLifecycleCoordinator, SimulationLifecycleStore
from app.hardware.simulated_p1_runner import SimulatedP1Device
from app.demo.calibration_models import PumpCalibrationSet
from tests.test_command_planning import context
ctx = context()
owner = HardwareOwnership(Path(sys.argv[1]), sys.argv[4])
store = SimulationLifecycleStore(Path(sys.argv[3]), sys.argv[6], sys.argv[5])
device = SimulatedP1Device(ctx)
if sys.argv[7] == 'arduino':
    device.before_send = lambda _: os._exit(73)
else:
    device.before_sf_send = lambda values: os._exit(73) if values['state'] == 'OPEN' else None
runner = OwnedTransferRunner(Path(sys.argv[2]), sys.argv[5], owner, device)
cals = PumpCalibrationSet(p1=ctx.pumps[0].calibration, p2=ctx.pumps[1].calibration)
PlanLifecycleCoordinator(store, runner).execute('test-phase-1', cals)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, *map(str, c.paths), *c.identities, stage], timeout=20
    )
    assert result.returncode == 73
    assert c.retained() == "test-phase-1"
    assert c.coordinator.store.load_machine_snapshot().active_execution.start_committed_at
    table = "sf_action_journal" if stage == "sf" else "arduino_command_journal"
    assert c.rows(table)[-1]["state"] == "INTENT_PERSISTED"
    assert_restart_blocked(c)


@pytest.mark.parametrize("target", ["arduino", "sf"])
def test_service_work_invalidates_initial_fixture_before_plan(case, target):
    c = case()
    if target == "sf":
        c.runner.hardware.sf_service.set_state(BottomValveState.CLOSED)
    else:
        from uuid import uuid4

        c.runner.hardware.arduino_service.execute(
            phase_execution_id="service",
            operation_command_id=str(uuid4()),
            command="VALVE_SET_POSITION",
            arguments={"valve_id": "V1", "position_degrees": 90},
        )
    before = (len(c.runner.device.calls), len(c.runner.device.sf_calls))
    with pytest.raises(SimulationBlocked, match="fixture"):
        c.execute()
    assert before == (len(c.runner.device.calls), len(c.runner.device.sf_calls))
    assert c.retained() is None


@pytest.mark.parametrize("bad", ["calibration", "run", "context", "boot", "sf_session", "absent"])
def test_preflight_rejects_stale_inputs_without_claim_or_send(case, bad):
    c = case()
    phase_id = "test-phase-1"
    if bad == "calibration":
        c.calibrations = c.calibrations.model_copy(
            update={
                "p1": c.calibrations.p1.model_copy(
                    update={"working_empty_chamber_position_steps": 4200}
                )
            }
        )
    elif bad == "run":
        c.stop()
    elif bad == "context":
        c.runner.device.current = context(phase_execution_id="different")
    elif bad == "boot":
        c.runner.device.controller_boot_id += 1
    elif bad == "sf_session":
        c.runner.device.sf_session_id = "changed"
    else:
        phase_id = "absent"
    with pytest.raises(SimulationBlocked):
        c.coordinator.execute(phase_id, c.calibrations)
    assert not c.runner.device.calls and not c.runner.device.sf_calls
    assert c.retained() is None


def test_sf_error_preserved_when_unknown_persistence_also_fails(case):
    c = case(PHASES[4])
    error = OSError("SF transport disconnected")
    original = c.runner._sf._db

    class Fault:
        def execute(self, sql, args=()):
            if "SET state='OUTCOME_UNKNOWN'" in sql:
                raise sqlite3.OperationalError("cannot record SF error")
            return original.execute(sql, args)

    c.runner._sf._db = Fault()

    def fail(values):
        if values["state"] == "OPEN":
            raise error

    c.runner.device.before_sf_send = fail
    with pytest.raises(OSError) as caught:
        c.execute()
    assert caught.value is error
    assert any("SF outcome persistence failed" in note for note in error.__notes__)
    assert any(
        r["state"] == "INTENT_PERSISTED" and r["target"] == "OPEN"
        for r in c.rows("sf_action_journal")
    )
    assert c.runner.device.sf_calls[-1]["state"] == "CLOSED"
    assert_restart_blocked(c)


def test_sf_duplicate_intent_never_replays_even_completed(case):
    from uuid import uuid4

    c = case()
    action_id = str(uuid4())
    values = dict(
        phase_execution_id="sf-sequence",
        operation_command_id=action_id,
        state=BottomValveState.CLOSED,
    )
    lease = c.owner.claim("sf-sequence")
    c.runner.hardware.run_operation(lease, lambda commands: commands.execute_sf(**values))
    with pytest.raises(sqlite3.IntegrityError):
        c.runner.hardware.run_operation(lease, lambda commands: commands.execute_sf(**values))
    assert len(c.runner.device.sf_calls) == 1
    with pytest.raises(OwnershipBlocked):
        c.owner.complete(lease)


def test_service_winning_between_preflight_and_claim_blocks_stale_plan(case, monkeypatch):
    c = case()
    claim = c.owner.claim

    def race(sequence_id, **kw):
        if sequence_id == "test-phase-1":
            c.runner.hardware.sf_service.set_state(BottomValveState.CLOSED)
        return claim(sequence_id, **kw)

    monkeypatch.setattr(c.owner, "claim", race)
    with pytest.raises(SimulationBlocked, match="fixture"):
        c.execute()
    assert c.retained() == "test-phase-1"
    assert not c.runner.device.calls
    assert len(c.runner.device.sf_calls) == 1
    assert c.coordinator.store.load_machine_snapshot().active_execution is None
    assert_restart_blocked(c)
