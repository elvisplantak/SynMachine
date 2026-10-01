"""Contiguous fake execution without resetting device state between phases."""

from decimal import Decimal
import sqlite3
import subprocess
import sys
from uuid import uuid4

import pytest

from app.demo.calibration_models import PumpCalibrationSet
from app.demo.guided_demo_phase_executor import ColumnFractionCollectionReadiness
from app.demo.hardware_contract import BottomValveState
from app.demo.operation_executor import ProtectedOperationError
from app.demo.phases import RunPhase
from app.demo.run_models import RunStatus
from app.hardware.arduino_serial import ArduinoUnavailableError
from app.hardware.owned_phase_session import OwnedPhaseSession, source_for_run
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
from tests.test_owned_timed_execution import TIMED_SETTINGS
from tests.test_owned_transfer_slice import Case

LATE_PHASES = (
    RunPhase.P2_TRANSFER_REACTOR_TO_SF,
    RunPhase.SF_MIXING,
    RunPhase.SF_SETTLING,
    RunPhase.P2_TRANSFER_SF_TO_COLUMN,
    RunPhase.COLUMN_FRACTION_COLLECTION,
)
READINESS = ColumnFractionCollectionReadiness(True, True)


@pytest.fixture
def session_case(tmp_path):
    resources = []

    def create(phase=LATE_PHASES[0], *, bind=True, timer=None):
        directory = tmp_path / str(len(resources))
        directory.mkdir()
        paths = tuple(directory / name for name in ("owner.db", "execution.db", "life.db"))
        oid = provision_ownership(paths[0])
        eid = provision_execution(paths[1], oid)
        lid = provision_lifecycle(paths[2], eid)
        owner = HardwareOwnership(paths[0], oid)
        store = SimulationLifecycleStore(paths[2], lid, eid)
        resources.extend([owner, store])
        service = _started_service(store, TIMED_SETTINGS)
        # Fixture setup only; preceding phases are not claimed as hardware evidence.
        _advance_to_phase(service, store, phase)
        ctx = context()
        cals = PumpCalibrationSet(p1=ctx.pumps[0].calibration, p2=ctx.pumps[1].calibration)
        device = SimulatedP1Device(ctx)
        device.sf_mixer_running = False
        runner = OwnedTransferRunner(paths[1], eid, owner, device, timer=timer)
        resources.append(runner)
        c = Case(
            PlanLifecycleCoordinator(store, runner),
            service,
            runner,
            owner,
            paths,
            (oid, eid, lid),
            cals,
        )
        session = (
            OwnedPhaseSession(c.coordinator, "run-1", cals, column_readiness=READINESS)
            if bind
            else None
        )
        return c, session

    yield create
    for resource in reversed(resources):
        resource.close()


def counts(c):
    return len(c.runner.device.calls), len(c.runner.device.sf_calls)


def blocked_again(c, session):
    before = counts(c)
    with pytest.raises((SimulationBlocked, OwnershipBlocked)):
        session.execute_next()
    assert counts(c) == before


def restart_rejected(c):
    before = [p.read_bytes() for p in c.paths]
    owner = HardwareOwnership(c.paths[0], c.identities[0])
    store = SimulationLifecycleStore(c.paths[2], c.identities[2], c.identities[1])
    device = SimulatedP1Device(context())
    device.sf_mixer_running = False
    runner = OwnedTransferRunner(c.paths[1], c.identities[1], owner, device)
    try:
        with pytest.raises((SimulationBlocked, OwnershipBlocked)):
            OwnedPhaseSession(
                PlanLifecycleCoordinator(store, runner),
                "run-1",
                c.calibrations,
                column_readiness=READINESS,
            )
        assert not device.calls and not device.sf_calls
    finally:
        runner.close()
        store.close()
        owner.close()
    assert before == [p.read_bytes() for p in c.paths]


def test_five_contiguous_phases_use_command_confirmed_state(session_case):
    c, session = session_case()
    original_fixture = c.runner.device.current
    initial_sessions = (c.runner.device.arduino_session_id, c.runner.device.sf_session_id)
    snapshots = []
    for index, phase in enumerate(LATE_PHASES):
        assert c.coordinator.store.load_demo_run("run-1").phase is phase
        snapshots.append(session._state)
        result = session.execute_next()
        assert c.retained() is None and result.machine.active_execution is None
        assert session.generation == index + 1
        assert c.runner.device.current is original_fixture and c.runner.device.used
        assert initial_sessions == (
            c.runner.device.arduino_session_id,
            c.runner.device.sf_session_id,
        )
    assert result.run.status is RunStatus.COMPLETED
    assert c.runner.device.sf_mixer_running is False
    assert c.runner.device.carousel_position == 1
    assert c.runner.device.waits == [Decimal("2.5"), Decimal("10"), Decimal("5"), Decimal("5")]
    rows = c.rows("prepared_command_plans")
    assert len(rows) == 5
    plans = [c.runner.load_plan(row["phase_execution_id"]) for row in rows]
    for plan, snapshot in zip(plans, snapshots, strict=True):
        assert plan.prepared.assumptions == snapshot.model_copy(
            update={"phase_execution_id": plan.phase_execution_id}
        )
    assert snapshots[1].valve_positions != snapshots[0].valve_positions
    assert all(row["state"] == "COMPLETED" for row in c.rows("arduino_command_journal"))
    assert all(row["state"] == "COMPLETED" for row in c.rows("sf_action_journal"))
    assert all(row["operation_completed"] == 1 for row in c.rows("execution_waits"))
    blocked_again(c, session)
    restart_rejected(c)


def test_p1_chain_requires_explicit_timer_before_delay(session_case):
    c, session = session_case(RunPhase.P1_TRANSFER_S_TO_REACTOR)
    session.execute_next()
    assert session.execute_next().run.phase is RunPhase.DELAY_BETWEEN_ADDITIONS
    before = [p.read_bytes() for p in c.paths]
    with pytest.raises(SimulationBlocked, match="explicit monotonic timer"):
        session.execute_next()
    assert before == [p.read_bytes() for p in c.paths]
    assert session.generation == 2


@pytest.mark.parametrize("change", ["boot", "arduino", "sf", "fixture", "carousel", "mixer", "run"])
def test_change_between_phases_prevents_new_plan_or_send(session_case, change):
    c, session = session_case()
    session.execute_next()
    if change == "boot":
        c.runner.device.controller_boot_id += 1
    elif change == "arduino":
        c.runner.device.arduino_session_id = str(uuid4())
    elif change == "sf":
        c.runner.device.sf_session_id = str(uuid4())
    elif change == "fixture":
        c.runner.device.current = context(phase_execution_id="replacement")
    elif change == "carousel":
        c.runner.device.carousel_position = 3
    elif change == "mixer":
        c.runner.device.sf_mixer_running = True
    else:
        c.stop()
    before = [p.read_bytes() for p in c.paths]
    blocked_again(c, session)
    assert before == [p.read_bytes() for p in c.paths]
    assert c.retained() is None
    restart_rejected(c)


@pytest.mark.parametrize("target", ["sf", "arduino", "other_connection"])
def test_service_work_between_phases_invalidates_continuity(session_case, target):
    c, session = session_case()
    session.execute_next()
    if target == "sf":
        c.runner.hardware.sf_service.set_state(BottomValveState.CLOSED)
    elif target == "arduino":
        c.runner.hardware.arduino_service.execute(
            phase_execution_id="service",
            operation_command_id=str(uuid4()),
            command="VALVE_SET_POSITION",
            arguments={"valve": "V1", "position_degrees": 90},
        )
    else:
        other = HardwareOwnership(c.paths[0], c.identities[0])
        try:
            other.complete(other.claim("external-service"))
        finally:
            other.close()
    before = [p.read_bytes() for p in c.paths]
    blocked_again(c, session)
    assert before == [p.read_bytes() for p in c.paths]
    assert c.retained() is None


def test_claim_atomically_checks_intervening_service_generation(session_case, monkeypatch):
    c, session = session_case()
    session.execute_next()
    original = c.owner.claim
    other = HardwareOwnership(c.paths[0], c.identities[0])

    def race(*a, **kw):
        other.complete(other.claim("race-service"))
        return original(*a, **kw)

    monkeypatch.setattr(c.owner, "claim", race)
    before = counts(c)
    try:
        with pytest.raises(OwnershipBlocked, match="history changed"):
            session.execute_next()
    finally:
        other.close()
    assert before == counts(c) and c.retained() is None
    assert c.coordinator.store.load_machine_snapshot().active_execution is None
    blocked_again(c, session)


@pytest.mark.parametrize("phase", [RunPhase.SF_MIXING, RunPhase.P2_TRANSFER_SF_TO_COLUMN])
def test_unknown_action_never_allows_next_phase_even_after_cleanup(session_case, phase):
    c, session = session_case(phase)
    error = ArduinoUnavailableError("lost result")

    def fail(values):
        if values["command"] == "SF_MIXER_SET_STATE" and values["arguments"]["running"]:
            raise error
        if values["command"] == "PUMP_MOVE_ABSOLUTE_STEPS":
            raise error

    c.runner.device.before_send = fail
    with pytest.raises(ArduinoUnavailableError) as caught:
        session.execute_next()
    assert caught.value is error and c.retained() is not None
    if phase is RunPhase.SF_MIXING:
        assert c.runner.device.calls[-1]["arguments"] == {"running": False}
    else:
        assert c.runner.device.sf_calls[-1]["state"] == "CLOSED"
    blocked_again(c, session)
    restart_rejected(c)


def test_sf_connection_loss_still_runs_required_arduino_stop(session_case):
    c, session = session_case(RunPhase.SF_MIXING)
    c.runner.device.during_wait = lambda _: setattr(c.runner.device, "sf_session_id", "lost")
    with pytest.raises(SimulationBlocked, match="SF session"):
        session.execute_next()
    assert c.runner.device.calls[-1]["arguments"] == {"running": False}
    assert c.retained() is not None
    blocked_again(c, session)


def test_arduino_connection_loss_still_runs_required_sf_close(session_case):
    c, session = session_case(RunPhase.P2_TRANSFER_SF_TO_COLUMN)

    def lose(values):
        if values["command"] == "PUMP_MOVE_ABSOLUTE_STEPS":
            c.runner.device.arduino_session_id = "lost"

    c.runner.device.before_send = lose
    with pytest.raises(SimulationBlocked, match="Arduino session"):
        session.execute_next()
    assert c.runner.device.sf_calls[-1]["state"] == "CLOSED"
    assert c.retained() is not None
    blocked_again(c, session)


@pytest.mark.parametrize("phase", LATE_PHASES[1:])
def test_stop_during_phase_prevents_handoff(session_case, phase):
    c, session = session_case(phase)
    if phase is RunPhase.P2_TRANSFER_SF_TO_COLUMN:
        c.runner.device.before_sf_send = lambda values: (
            c.stop() if values["state"] == "OPEN" else None
        )
    else:
        c.runner.device.during_wait = lambda _: c.stop()
    assert session.execute_next().run.status is RunStatus.ABORTED
    assert c.retained() is not None
    blocked_again(c, session)
    restart_rejected(c)


@pytest.mark.parametrize("stage", ["resolve", "release"])
def test_resolution_failure_cannot_publish_continuity(session_case, monkeypatch, stage):
    c, session = session_case()

    def fail(*a, **kw):
        raise OSError("persistence failed")

    target, method = (
        (c.owner, "complete")
        if stage == "release"
        else (c.coordinator.store, "resolve_phase_execution")
    )
    monkeypatch.setattr(target, method, fail)
    with pytest.raises(OSError, match="persistence failed"):
        session.execute_next()
    assert session.generation == 0 and c.retained() is not None
    blocked_again(c, session)
    restart_rejected(c)


@pytest.mark.parametrize("change", ["arduino", "sf", "fixture"])
def test_state_is_revalidated_after_claim_before_lifecycle_start(session_case, monkeypatch, change):
    c, session = session_case()
    claim = c.owner.claim

    def race(*a, **kw):
        lease = claim(*a, **kw)
        if change == "arduino":
            c.runner.device.arduino_session_id = "replacement"
        elif change == "sf":
            c.runner.device.sf_session_id = "replacement"
        else:
            c.runner.device.carousel_position = 3
        return lease

    monkeypatch.setattr(c.owner, "claim", race)
    with pytest.raises(SimulationBlocked):
        session.execute_next()
    assert counts(c) == (0, 0) and c.retained() is not None
    assert c.coordinator.store.load_machine_snapshot().active_execution is None
    blocked_again(c, session)
    restart_rejected(c)


def test_concurrent_session_entry_is_rejected_without_poisoning_active_execution(session_case):
    from concurrent.futures import ThreadPoolExecutor

    c, session = session_case()
    calls = []

    def compete(_):
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(session.execute_next)
            with pytest.raises(SimulationBlocked, match="already executing"):
                future.result(timeout=3)
        calls.append(True)

    c.runner.device.before_send = compete
    session.execute_next()
    assert calls and c.retained() is None
    c.runner.device.before_send = lambda _: None
    session.execute_next()
    assert session.generation == 2


@pytest.mark.parametrize("target", ["arduino", "sf", "timer"])
def test_result_persistence_failure_in_later_phase_blocks_handoff(session_case, target):
    c, session = session_case()
    session.execute_next()
    if target == "sf":
        session.execute_next()
        session.execute_next()
    before_generation = session.generation
    runner = c.runner
    component = runner._journal if target == "arduino" else runner._sf if target == "sf" else runner
    attribute = "_connection" if target == "arduino" else "_db"
    original = getattr(component, attribute)
    hits = []

    class Fault:
        def __getattr__(self, name):
            return getattr(original, name)

        def execute(self, sql, args=()):
            if (
                (target == "timer" and sql.startswith("UPDATE execution_waits SET state="))
                or (target == "sf" and "SET state='COMPLETED'" in sql)
                or (target == "arduino" and "UPDATE arduino_command_journal" in sql)
            ):
                hits.append(sql)
                raise sqlite3.OperationalError("result persistence failed")
            return original.execute(sql, args)

    setattr(component, attribute, Fault())
    try:
        with pytest.raises((sqlite3.OperationalError, ProtectedOperationError)) as caught:
            session.execute_next()
        if isinstance(caught.value, ProtectedOperationError):
            assert isinstance(caught.value.primary_error, sqlite3.OperationalError)
            assert isinstance(caught.value.followup_error, sqlite3.OperationalError)
            assert "result persistence failed" in str(caught.value.primary_error)
        else:
            assert "result persistence failed" in str(caught.value)
        assert hits and session.generation == before_generation
        assert c.retained() is not None
        assert c.coordinator.store.load_machine_snapshot().active_execution is not None
        blocked_again(c, session)
    finally:
        setattr(component, attribute, original)
    restart_rejected(c)


@pytest.mark.parametrize(
    "bad", ["mixer", "boot", "carousel", "run", "history", "plan", "calibration"]
)
def test_initial_session_requires_independent_fresh_fixture(session_case, bad):
    from app.hardware.command_plan_store import PlanSource

    c, _ = session_case(bind=False)
    if bad == "mixer":
        c.runner.device.sf_mixer_running = None
    elif bad == "boot":
        c.runner.device.controller_boot_id += 1
    elif bad == "carousel":
        c.runner.device.carousel_position = None
    elif bad == "run":
        c.stop()
    elif bad == "history":
        c.owner.complete(c.owner.claim("old-service"))
    elif bad == "plan":
        run = c.coordinator.store.load_demo_run("run-1")
        c.runner._plans.persist(
            PlanSource(
                run_id=run.run_id,
                run_event_sequence=run.event_sequence,
                plan=source_for_run(run, c.calibrations, READINESS),
            ),
            context(),
        )
    else:
        c.calibrations = c.calibrations.model_copy(
            update={
                "p1": c.calibrations.p1.model_copy(
                    update={"working_empty_chamber_position_steps": 4200}
                )
            }
        )
    before = [p.read_bytes() for p in c.paths]
    with pytest.raises((SimulationBlocked, OwnershipBlocked)):
        OwnedPhaseSession(c.coordinator, "run-1", c.calibrations, column_readiness=READINESS)
    assert counts(c) == (0, 0)
    assert before == [p.read_bytes() for p in c.paths]


@pytest.mark.parametrize("stage", ["gap", "arduino", "sf"])
def test_real_process_exit_cannot_reconstruct_or_resume_session(session_case, stage):
    c, _ = session_case(bind=False)
    code = """
import os, sys
from pathlib import Path
from app.hardware.owned_transfer_runner import OwnedTransferRunner
from app.hardware.owned_phase_session import OwnedPhaseSession
from app.hardware.sequence_ownership import HardwareOwnership
from app.hardware.simulated_lifecycle import PlanLifecycleCoordinator, SimulationLifecycleStore
from app.hardware.simulated_p1_runner import SimulatedP1Device
from app.demo.calibration_models import PumpCalibrationSet
from app.demo.guided_demo_phase_executor import ColumnFractionCollectionReadiness
from tests.test_command_planning import context
ctx = context()
owner = HardwareOwnership(Path(sys.argv[1]), sys.argv[4])
store = SimulationLifecycleStore(Path(sys.argv[3]), sys.argv[6], sys.argv[5])
device = SimulatedP1Device(ctx)
device.sf_mixer_running = False
runner = OwnedTransferRunner(Path(sys.argv[2]), sys.argv[5], owner, device)
cals = PumpCalibrationSet(p1=ctx.pumps[0].calibration, p2=ctx.pumps[1].calibration)
session = OwnedPhaseSession(PlanLifecycleCoordinator(store, runner), 'run-1', cals,
    column_readiness=ColumnFractionCollectionReadiness(True, True))
session.execute_next()
if sys.argv[7] == 'gap':
    os._exit(73)
if sys.argv[7] == 'arduino':
    device.before_send = lambda _: os._exit(73)
else:
    session.execute_next()
    session.execute_next()
    device.before_sf_send = lambda values: os._exit(73) if values['state'] == 'OPEN' else None
session.execute_next()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, *map(str, c.paths), *c.identities, stage], timeout=20
    )
    assert result.returncode == 73
    if stage == "gap":
        assert c.retained() is None
        assert c.coordinator.store.load_demo_run("run-1").phase is RunPhase.SF_MIXING
    else:
        assert c.retained() is not None
        table = "arduino_command_journal" if stage == "arduino" else "sf_action_journal"
        assert c.rows(table)[-1]["state"] == "INTENT_PERSISTED"
    restart_rejected(c)


def test_other_process_completed_service_invalidates_next_phase(session_case):
    c, session = session_case()
    session.execute_next()
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from pathlib import Path
from app.hardware.sequence_ownership import HardwareOwnership
owner = HardwareOwnership(Path(sys.argv[1]), sys.argv[2])
owner.complete(owner.claim('other-process-service'))
owner.close()
""",
            str(c.paths[0]),
            c.identities[0],
        ],
        timeout=20,
    )
    assert result.returncode == 0
    before = [p.read_bytes() for p in c.paths]
    blocked_again(c, session)
    assert before == [p.read_bytes() for p in c.paths]


@pytest.mark.parametrize("connection", ["arduino_session_id", "sf_session_id"])
def test_session_change_during_result_commit_retains_owner(session_case, monkeypatch, connection):
    c, session = session_case()
    resolve = c.coordinator.store.resolve_phase_execution

    def change(*a, **kw):
        result = resolve(*a, **kw)
        setattr(c.runner.device, connection, "replacement")
        return result

    monkeypatch.setattr(c.coordinator.store, "resolve_phase_execution", change)
    with pytest.raises(SimulationBlocked, match="session changed"):
        session.execute_next()
    assert session.generation == 0
    assert c.retained() is not None
    assert c.coordinator.store.load_machine_snapshot().active_execution is None
    blocked_again(c, session)
    restart_rejected(c)


def test_sf_session_loss_during_route_blocks_later_normal_commands(session_case):
    c, session = session_case(RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR)

    def disconnect(_):
        c.runner.device.sf_session_id = "replacement"

    c.runner.device.before_send = disconnect
    with pytest.raises(SimulationBlocked, match="SF session changed"):
        session.execute_next()
    assert len(c.runner.device.calls) == 1
    assert len(c.rows("arduino_command_journal")) == 1
    assert c.retained() is not None
    blocked_again(c, session)


def test_bound_runner_cannot_bypass_session_with_external_plan(session_case):
    from app.hardware.command_plan_store import PlanSource

    c, session = session_case()
    run = c.coordinator.store.load_demo_run("run-1")
    c.runner._plans.persist(
        PlanSource(
            run_id=run.run_id,
            run_event_sequence=run.event_sequence,
            plan=source_for_run(run, c.calibrations, READINESS),
        ),
        context(),
    )
    with pytest.raises(SimulationBlocked, match="not authorized"):
        c.coordinator.execute("test-phase-1", c.calibrations)
    assert counts(c) == (0, 0) and c.retained() is None
