"""Complete fake demo and durable Pause/Resume under the existing phase owner."""

from datetime import UTC, datetime
from decimal import Decimal
import sqlite3

import pytest

from app.demo.events import DomainEventType
from app.demo.hardware_contract import BottomValveState
from app.demo.operation_executor import CollectionTimerOutcome
from app.demo.phases import RunPhase
from app.demo.run_models import RunStatus
from app.hardware.execution_timer import MonotonicExecutionTimer
from app.hardware.sequence_ownership import OwnershipBlocked
from app.hardware.simulated_lifecycle import SimulationLifecycleStore
from app.hardware.simulated_p1_runner import SimulationBlocked
from tests.test_owned_phase_session import (
    session_case as session_case,
    blocked_again,
    restart_rejected,
)

WAIT_PHASES = (RunPhase.DELAY_BETWEEN_ADDITIONS, RunPhase.REACTION_HOLD)


class Clock:
    def __init__(self):
        self.now = 0
        self.hook = lambda: None
        self.sleeps = []

    def read(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += round(seconds * 1_000_000_000)
        assert self.now < 500_000_000_000, "timer failed to finish"
        self.hook()

    def timer(self):
        return MonotonicExecutionTimer(clock=self.read, sleeper=self.sleep, poll_seconds=1)


def pause(c, paused, *, store=None):
    store = c.coordinator.store if store is None else store
    intent = store.load_machine_snapshot().active_execution
    return store.set_wait_paused(intent.execution_id, paused=paused, occurred_at=datetime.now(UTC))


@pytest.mark.parametrize("order", ["B1_THEN_B2", "B2_THEN_B1"])
def test_complete_demo_uses_one_session_from_solvent_to_last_fraction(
    session_case, monkeypatch, order
):
    from app.demo.models import AdditionOrder
    from tests import test_execution_coordinator as fixtures

    monkeypatch.setattr(
        fixtures,
        "CONFIGURATION",
        fixtures.CONFIGURATION.model_copy(update={"addition_order": AdditionOrder(order)}),
    )
    clock = Clock()
    c, session = session_case(RunPhase.P1_TRANSFER_S_TO_REACTOR, timer=clock.timer())
    observed = []
    for _ in range(10):
        observed.append(c.coordinator.store.load_demo_run("run-1").phase)
        result = session.execute_next()
        assert c.retained() is None and result.machine.active_execution is None
    assert observed == [
        phase for phase in RunPhase if phase not in (RunPhase.READY, RunPhase.COMPLETED)
    ]
    assert result.run.status is RunStatus.COMPLETED
    assert session.generation == 10
    assert len(c.rows("prepared_command_plans")) == 10
    waits = c.rows("execution_waits")
    assert [Decimal(row["duration_seconds"]) for row in waits] == [5, 60, Decimal("2.5"), 10, 5, 5]
    assert all(row["state"] == "COMPLETED" and row["operation_completed"] == 1 for row in waits)
    assert clock.now == 87_500_000_000
    restart_rejected(c)


@pytest.mark.parametrize("phase", WAIT_PHASES)
def test_pause_resume_keeps_same_intent_owner_and_excludes_paused_time(session_case, phase):
    clock = Clock()
    c, session = session_case(phase, timer=clock.timer())
    other = SimulationLifecycleStore(c.paths[2], c.identities[2], c.identities[1])
    observed_ids = []

    def hook():
        intent = other.load_machine_snapshot().active_execution
        observed_ids.append(intent.execution_id)
        assert c.retained() == intent.execution_id
        assert c.rows("execution_waits")[0]["state"] == "INTENT_PERSISTED"
        with pytest.raises(OwnershipBlocked):
            c.runner.hardware.sf_service.set_state(BottomValveState.CLOSED)
        if clock.now == 1_000_000_000:
            pause(c, True, store=other)
        if clock.now == 4_000_000_000:
            pause(c, False, store=other)

    clock.hook = hook
    try:
        result = session.execute_next()
    finally:
        other.close()
    assert result.run.status is RunStatus.RUNNING
    assert len(set(observed_ids)) == 1 and session.generation == 1
    duration = 5 if phase is WAIT_PHASES[0] else 60
    # The entire transition-containing poll interval is conservatively excluded.
    assert clock.now == (duration + 4) * 1_000_000_000
    events = c.coordinator.store.load_events("RUN", "run-1")
    assert [
        e.event_type
        for e in events
        if e.event_type in (DomainEventType.RUN_PAUSED, DomainEventType.RUN_RESUMED)
    ] == [DomainEventType.RUN_PAUSED, DomainEventType.RUN_RESUMED]
    assert not c.runner.device.calls and not c.runner.device.sf_calls
    assert c.retained() is None


@pytest.mark.parametrize("phase", WAIT_PHASES)
def test_stop_while_paused_is_not_completed_and_retains_owner(session_case, phase):
    clock = Clock()
    c, session = session_case(phase, timer=clock.timer())

    def hook():
        if clock.now == 1_000_000_000:
            pause(c, True)
        else:
            c.stop()

    clock.hook = hook
    assert session.execute_next().run.status is RunStatus.ABORTED
    row = c.rows("execution_waits")[0]
    assert row["state"] == "STOP_REQUESTED" and row["operation_completed"] == 0
    assert c.retained() is not None
    blocked_again(c, session)
    restart_rejected(c)


@pytest.mark.parametrize("resume", [True, False])
def test_pause_wins_result_commit_race_and_waits_for_resume_or_stop(
    session_case, monkeypatch, resume
):
    clock = Clock()
    c, session = session_case(WAIT_PHASES[0], timer=clock.timer())
    store = c.coordinator.store
    resolve = store.resolve_phase_execution
    injected = False

    def race(*a, **kw):
        nonlocal injected
        if not injected:
            injected = True
            pause(c, True)
        return resolve(*a, **kw)

    monkeypatch.setattr(store, "resolve_phase_execution", race)

    def hook():
        if injected:
            assert c.retained() is not None
            if resume:
                pause(c, False)
            else:
                c.stop()

    clock.hook = hook
    result = session.execute_next()
    assert result.run.status is (RunStatus.RUNNING if resume else RunStatus.ABORTED)
    assert (c.retained() is None) is resume
    assert len(c.rows("execution_waits")) == 1
    assert not c.runner.device.calls


def test_short_pause_resume_between_polls_cannot_be_lost():
    clock = Clock()
    state = [RunStatus.RUNNING, 10]

    def hook():
        if clock.now == 1_000_000_000:
            state[1] += 2  # Both durable transitions occurred between polls.

    clock.hook = hook
    assert (
        clock.timer().wait_pausable(Decimal(2), lambda: tuple(state))
        is CollectionTimerOutcome.COMPLETED
    )
    assert clock.now == 3_000_000_000


@pytest.mark.parametrize("bad", [Decimal(-1), Decimal("NaN"), Decimal("Infinity"), 1])
def test_pausable_timer_rejects_invalid_duration(bad):
    with pytest.raises(ValueError):
        Clock().timer().wait_pausable(bad, lambda: (RunStatus.RUNNING, 1))


@pytest.mark.parametrize("status", [RunStatus.RUNNING, RunStatus.PAUSED, RunStatus.ABORTING])
def test_zero_budget_checks_controls_before_completion(status):
    clock = Clock()
    state = [status, 1]
    clock.hook = lambda: state.__setitem__(slice(None), [RunStatus.ABORTING, 2])
    result = clock.timer().wait_pausable(Decimal(0), lambda: tuple(state))
    assert result is (
        CollectionTimerOutcome.COMPLETED
        if status is RunStatus.RUNNING
        else CollectionTimerOutcome.STOP_REQUESTED
    )
    assert len(clock.sleeps) == (1 if status is RunStatus.PAUSED else 0)


@pytest.mark.parametrize(
    "bad",
    [("RUNNING", 1), (RunStatus.RUNNING, True), (RunStatus.FAULTED, 1), (RunStatus.PAUSED, -1)],
)
def test_invalid_timer_control_fails_closed(bad):
    with pytest.raises(ValueError):
        Clock().timer().wait_pausable(Decimal(1), lambda: bad)


@pytest.mark.parametrize(
    "fault", ["wait_intent", "wait_result", "pause_write", "resolution", "release"]
)
def test_wait_persistence_fault_blocks_continuity(session_case, monkeypatch, fault):
    clock = Clock()
    c, session = session_case(WAIT_PHASES[0], timer=clock.timer())
    original = c.runner._db
    hits = []

    class Fault:
        def __getattr__(self, name):
            return getattr(original, name)

        def execute(self, sql, args=()):
            if (fault == "wait_intent" and sql.startswith("INSERT INTO execution_waits")) or (
                fault == "wait_result" and sql.startswith("UPDATE execution_waits SET state=")
            ):
                hits.append(sql)
                raise sqlite3.OperationalError("injected failure")
            return original.execute(sql, args)

    c.runner._db = Fault()

    def fail(*a, **kw):
        hits.append(fault)
        raise sqlite3.OperationalError("injected failure")

    if fault == "pause_write":
        # Inject only after start, so lifecycle claim/start can commit normally.
        def during():
            monkeypatch.setattr(c.coordinator.store, "_write_transition", fail)
            pause(c, True)

        clock.hook = during
    elif fault == "resolution":
        monkeypatch.setattr(c.coordinator.store, "resolve_phase_execution", fail)
    elif fault == "release":
        monkeypatch.setattr(c.owner, "complete", fail)
    try:
        with pytest.raises(sqlite3.OperationalError, match="injected failure"):
            session.execute_next()
        assert hits and c.retained() is not None
        assert session.generation == 0
        blocked_again(c, session)
    finally:
        c.runner._db = original
    if fault == "wait_intent":
        assert not clock.sleeps
    restart_rejected(c)


@pytest.mark.parametrize("connection", ["arduino_session_id", "sf_session_id"])
def test_connection_loss_while_paused_blocks_resume(session_case, connection):
    clock = Clock()
    c, session = session_case(WAIT_PHASES[0], timer=clock.timer())

    def hook():
        if clock.now == 1_000_000_000:
            pause(c, True)
        else:
            setattr(c.runner.device, connection, "replacement")

    clock.hook = hook
    with pytest.raises(SimulationBlocked):
        session.execute_next()
    assert c.retained() is not None
    assert c.rows("execution_waits")[0]["state"] == "OUTCOME_UNKNOWN"
    blocked_again(c, session)


@pytest.mark.parametrize("phase", WAIT_PHASES)
def test_zero_configured_waits_still_persist_and_resolve_intent(session_case, monkeypatch, phase):
    from tests import test_execution_coordinator as fixtures

    monkeypatch.setattr(
        fixtures,
        "CONFIGURATION",
        fixtures.CONFIGURATION.model_copy(
            update={
                "delay_between_additions_seconds": Decimal(0),
                "reaction_duration_seconds": Decimal(0),
            }
        ),
    )
    clock = Clock()
    c, session = session_case(phase, timer=clock.timer())
    assert session.execute_next().run.status is RunStatus.RUNNING
    assert not clock.sleeps and c.retained() is None
    assert c.rows("execution_waits")[0]["operation_completed"] == 1


def test_complete_demo_with_pauses_in_both_waits(session_case):
    clock = Clock()
    c, session = session_case(RunPhase.P1_TRANSFER_S_TO_REACTOR, timer=clock.timer())
    paused_phases = set()

    def hook():
        run = c.coordinator.store.load_demo_run("run-1")
        if run.phase in WAIT_PHASES:
            if run.phase not in paused_phases:
                pause(c, True)
                paused_phases.add(run.phase)
            elif run.status is RunStatus.PAUSED:
                pause(c, False)

    clock.hook = hook
    for _ in range(10):
        result = session.execute_next()
    assert paused_phases == set(WAIT_PHASES)
    assert result.run.status is RunStatus.COMPLETED and session.generation == 10
    assert clock.now == 91_500_000_000


@pytest.mark.parametrize(
    "stage", ["before_start", "wrong_token", "wrong_phase", "after_resolution"]
)
def test_pause_rejected_outside_matching_started_wait(session_case, stage):
    clock = Clock()
    phase = RunPhase.P1_TRANSFER_S_TO_REACTOR if stage == "wrong_phase" else WAIT_PHASES[0]
    c, session = session_case(phase, timer=clock.timer())
    store = c.coordinator.store

    def reject(_=None):
        machine = store.load_machine_snapshot()
        token = machine.active_execution.execution_id if machine.active_execution else "absent"
        before = c.paths[2].read_bytes()
        with pytest.raises(SimulationBlocked):
            store.set_wait_paused(
                "foreign" if stage == "wrong_token" else token,
                paused=True,
                occurred_at=datetime.now(UTC),
            )
        assert c.paths[2].read_bytes() == before

    if stage == "before_start":
        reject()
    elif stage == "after_resolution":
        session.execute_next()
        reject()
    elif stage == "wrong_phase":
        c.runner.device.before_send = reject
        session.execute_next()
    else:
        clock.hook = reject
        session.execute_next()


def test_wait_rejects_configuration_change_hidden_in_pause_transition(session_case):
    from app.demo.lifecycle import pause_run

    clock = Clock()
    c, session = session_case(WAIT_PHASES[0], timer=clock.timer())
    store = c.coordinator.store

    def change():
        run = store.load_demo_run("run-1")
        result = pause_run(run, datetime.now(UTC))
        modified = result.run.model_copy(
            update={
                "configuration": run.configuration.model_copy(
                    update={"reaction_duration_seconds": Decimal(1)}
                )
            }
        )
        store.persist_run_transition(modified, result.events)

    clock.hook = change
    with pytest.raises(SimulationBlocked, match="snapshot differs"):
        session.execute_next()
    assert c.retained() is not None
    assert c.rows("execution_waits")[0]["state"] == "OUTCOME_UNKNOWN"
    blocked_again(c, session)


@pytest.mark.parametrize("fault", ["clock", "sleeper", "state_read"])
def test_wait_runtime_error_retains_durable_intent(session_case, monkeypatch, fault):
    clock = Clock()
    c, session = session_case(WAIT_PHASES[0], timer=clock.timer())

    def fail(*a, **kw):
        raise OSError("injected wait failure")

    if fault == "clock":
        clock.hook = lambda: setattr(clock, "now", -1)
    elif fault == "sleeper":
        clock.hook = fail
    else:
        monkeypatch.setattr(c.coordinator.store, "read_wait_control", fail)
    with pytest.raises((ValueError, OSError)):
        session.execute_next()
    assert c.retained() is not None
    assert c.coordinator.store.load_machine_snapshot().active_execution is not None
    blocked_again(c, session)
    restart_rejected(c)


@pytest.mark.parametrize("stage", ["waiting", "paused"])
def test_process_death_during_wait_never_resumes(session_case, stage):
    import subprocess
    import sys

    c, _ = session_case(WAIT_PHASES[0], bind=False)
    code = """
import os, sys
from pathlib import Path
from datetime import UTC, datetime
from app.hardware.owned_transfer_runner import OwnedTransferRunner
from app.hardware.owned_phase_session import OwnedPhaseSession
from app.hardware.execution_timer import MonotonicExecutionTimer
from app.hardware.sequence_ownership import HardwareOwnership
from app.hardware.simulated_lifecycle import PlanLifecycleCoordinator, SimulationLifecycleStore
from app.hardware.simulated_p1_runner import SimulatedP1Device
from app.demo.calibration_models import PumpCalibrationSet
from tests.test_command_planning import context
ctx = context()
owner = HardwareOwnership(Path(sys.argv[1]), sys.argv[4])
store = SimulationLifecycleStore(Path(sys.argv[3]), sys.argv[6], sys.argv[5])
device = SimulatedP1Device(ctx)
device.sf_mixer_running = False
def die(_):
    if sys.argv[7] == 'paused':
        intent = store.load_machine_snapshot().active_execution
        store.set_wait_paused(intent.execution_id, paused=True, occurred_at=datetime.now(UTC))
    os._exit(73)
runner = OwnedTransferRunner(Path(sys.argv[2]), sys.argv[5], owner, device,
    timer=MonotonicExecutionTimer(clock=lambda: 0, sleeper=die))
cals = PumpCalibrationSet(p1=ctx.pumps[0].calibration, p2=ctx.pumps[1].calibration)
OwnedPhaseSession(PlanLifecycleCoordinator(store, runner), 'run-1', cals).execute_next()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, *map(str, c.paths), *c.identities, stage], timeout=20
    )
    assert result.returncode == 73
    assert c.retained() is not None
    assert c.rows("execution_waits")[0]["state"] == "INTENT_PERSISTED"
    assert c.coordinator.store.load_demo_run("run-1").status is (
        RunStatus.PAUSED if stage == "paused" else RunStatus.RUNNING
    )
    restart_rejected(c)


def test_timer_does_not_charge_control_read_overhead():
    clock = Clock()

    def read():
        clock.now += 300_000_000
        return RunStatus.RUNNING, 1

    assert clock.timer().wait_pausable(Decimal(2), read) is CollectionTimerOutcome.COMPLETED
    assert clock.now == 2_900_000_000


def test_stop_wins_timer_deadline():
    clock = Clock()

    def read():
        return (RunStatus.ABORTING, 2) if clock.now >= 2_000_000_000 else (RunStatus.RUNNING, 1)

    assert clock.timer().wait_pausable(Decimal(2), read) is CollectionTimerOutcome.STOP_REQUESTED
    assert clock.now == 2_000_000_000


@pytest.mark.parametrize("bad", ["wrong_id", "old_time", "default_resolution"])
def test_paused_result_deferral_still_validates_token_and_time(session_case, bad):
    from datetime import timedelta
    from app.demo.machine_models import PhaseExecutionResult, PhaseExecutionOutcome
    from app.demo.phase_result_resolution import (
        ExecutionIdMismatchError,
        InvalidExecutionResultError,
    )

    clock = Clock()
    c, session = session_case(WAIT_PHASES[0], timer=clock.timer())
    store = c.coordinator.store
    checked = False

    def hook():
        nonlocal checked
        if checked:
            return
        checked = True
        pause(c, True)
        intent = store.load_machine_snapshot().active_execution
        before = c.paths[2].read_bytes()
        result = PhaseExecutionResult(
            execution_id="foreign" if bad == "wrong_id" else intent.execution_id,
            outcome=PhaseExecutionOutcome.COMPLETED,
            reported_at=intent.claimed_at - timedelta(seconds=1)
            if bad == "old_time"
            else datetime.now(UTC),
        )
        with pytest.raises((ExecutionIdMismatchError, InvalidExecutionResultError)):
            store.resolve_phase_execution(result, defer_paused_wait=bad != "default_resolution")
        assert c.paths[2].read_bytes() == before
        assert c.retained() == intent.execution_id
        pause(c, False)

    clock.hook = hook
    session.execute_next()
    assert checked and c.retained() is None
