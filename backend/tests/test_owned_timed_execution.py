from decimal import Decimal
import sqlite3

import pytest

from app.demo.hardware_contract import BottomValveState
from app.demo.operation_executor import CollectionTimerOutcome, ProtectedOperationError
from app.demo.phases import RunPhase
from app.demo.run_models import RunStatus
from app.hardware.arduino_serial import ArduinoCommandFailedError, ArduinoUnavailableError
from app.hardware.execution_timer import MonotonicExecutionTimer
from app.hardware.sequence_ownership import OwnershipBlocked
from app.hardware.simulated_p1_runner import SimulationBlocked
from tests.test_execution_coordinator import SETTINGS
from tests.test_owned_transfer_slice import case as case, assert_restart_blocked

COLUMN = RunPhase.COLUMN_FRACTION_COLLECTION
MIXING = RunPhase.SF_MIXING
SETTLING = RunPhase.SF_SETTLING
TIMED_SETTINGS = SETTINGS.model_copy(update={"sf_mixing_duration_seconds": Decimal("2.5")})


def make(case, phase, **kw):
    return case(phase, settings=TIMED_SETTINGS, mixer_running=False, **kw)


def block_service(c):
    assert c.retained() == "test-phase-1"
    with pytest.raises(OwnershipBlocked):
        c.runner.hardware.sf_service.set_state(BottomValveState.CLOSED)
    with pytest.raises(OwnershipBlocked):
        c.runner.hardware.arduino_service.execute(
            phase_execution_id="service",
            operation_command_id="competing",
            command="SF_MIXER_SET_STATE",
            arguments={"running": False},
        )


@pytest.mark.parametrize("phase", [COLUMN, MIXING, SETTLING])
def test_complete_timed_phase_through_shared_lifecycle(case, phase):
    c = make(case, phase)

    def wait(_):
        block_service(c)
        row = c.rows("execution_waits")[-1]
        assert row["state"] == "INTENT_PERSISTED" and row["operation_completed"] == 0
        assert c.coordinator.store.load_machine_snapshot().active_execution.start_committed_at
        if phase is MIXING:
            assert c.runner.device.sf_mixer_running is True

    c.runner.device.during_wait = wait
    result = c.execute()
    assert c.retained() is None
    assert result.machine.active_execution is None
    assert all(
        r["state"] == "COMPLETED" and r["operation_completed"] == 1
        for r in c.rows("execution_waits")
    )
    if phase is COLUMN:
        assert result.run.status is RunStatus.COMPLETED
        assert len(c.rows("execution_waits")) == TIMED_SETTINGS.fraction_count
        assert (
            c.rows("execution_carousel_projection")[0]["position"] == 1
        )  # fixture starts at tube 40
        assert c.runner.device.calls[-1]["arguments"] == {"position_degrees": 4}
    elif phase is MIXING:
        assert [v["arguments"] for v in c.runner.device.calls] == [
            {"running": True},
            {"running": False},
        ]
        assert c.runner.device.sf_mixer_running is False
        assert result.run.phase is SETTLING
    else:
        assert not c.runner.device.calls and not c.runner.device.sf_calls
        assert result.run.phase is RunPhase.P2_TRANSFER_SF_TO_COLUMN


@pytest.mark.parametrize("phase", [COLUMN, MIXING, SETTLING])
@pytest.mark.parametrize("point", ["before_start", "during_wait", "resolution"])
def test_stop_retains_owner_and_required_followup(case, phase, point, monkeypatch):
    c = make(case, phase)
    if point == "during_wait":
        c.runner.device.during_wait = lambda _: c.stop()
    else:
        method = "claim_phase_execution" if point == "before_start" else "resolve_phase_execution"
        original = getattr(c.coordinator.store, method)

        def stop(*a, **kw):
            if point == "resolution":
                c.stop()
            result = original(*a, **kw)
            if point == "before_start":
                c.stop()
            return result

        monkeypatch.setattr(c.coordinator.store, method, stop)
    result = c.execute()
    assert result.run.status is RunStatus.ABORTED
    assert c.retained() == "test-phase-1"
    if point == "before_start":
        assert not c.runner.device.calls and not c.rows("execution_waits")
    elif point == "during_wait":
        row = c.rows("execution_waits")[-1]
        assert row["state"] == "STOP_REQUESTED" and row["operation_completed"] == 0
        if phase is COLUMN:
            assert not any(
                v["command"] == "CAROUSEL_MOVE_TO_POSITION" for v in c.runner.device.calls
            )
            assert c.runner.device.calls[-1]["arguments"] == {"position_degrees": 4}
        elif phase is MIXING:
            assert c.runner.device.calls[-1]["arguments"] == {"running": False}
    assert_restart_blocked(c)


@pytest.mark.parametrize("phase", [COLUMN, MIXING])
@pytest.mark.parametrize("fault", ["intent", "result", "operation_completed"])
def test_wait_persistence_fault_requires_cleanup_without_false_completion(case, phase, fault):
    c = make(case, phase)
    original = c.runner._db

    class Fault:
        def execute(self, sql, args=()):
            if (
                fault == "intent"
                and sql.startswith("INSERT INTO execution_waits")
                or fault == "result"
                and "UPDATE execution_waits SET state=?" in sql
                or fault == "operation_completed"
                and "SET operation_completed=1" in sql
                and c.runner.device.waits
            ):
                raise sqlite3.OperationalError("timer write failed")
            return original.execute(sql, args)

    c.runner._db = Fault()
    try:
        with pytest.raises(sqlite3.OperationalError):
            c.execute()
    finally:
        c.runner._db = original
    assert c.runner.device.calls[-1]["arguments"] == (
        {"running": False} if phase is MIXING else {"position_degrees": 4}
    )
    assert not any(r["operation_completed"] for r in c.rows("execution_waits"))
    assert c.coordinator.store.load_machine_snapshot().active_execution is not None
    if fault == "intent":
        assert not c.runner.device.waits
    assert_restart_blocked(c)


@pytest.mark.parametrize("phase", [COLUMN, MIXING])
@pytest.mark.parametrize("primary", ["failed", "unknown", "wait_error"])
@pytest.mark.parametrize("cleanup", ["ok", "unknown"])
def test_primary_and_followup_errors_keep_owner(case, phase, primary, cleanup):
    c = make(case, phase)
    plan = c.runner.load_plan("test-phase-1")
    operation = next(op for op in plan.prepared.operations if op.required_followup)
    primary_id = operation.actions[0].operation_command_id
    cleanup_id = operation.required_followup[0].operation_command_id
    primary_error = (
        ArduinoCommandFailedError("ACTUATOR_FAILURE", True)
        if primary == "failed"
        else ArduinoUnavailableError("primary unknown")
    )
    close_error = ArduinoUnavailableError("cleanup unknown")

    def send(values):
        if values["operation_command_id"] == primary_id and primary != "wait_error":
            raise primary_error
        if values["operation_command_id"] == cleanup_id and cleanup == "unknown":
            raise close_error

    def wait(_):
        raise primary_error

    c.runner.device.before_send = send
    if primary == "wait_error":
        c.runner.device.during_wait = wait
    with pytest.raises(
        ProtectedOperationError if cleanup == "unknown" else type(primary_error)
    ) as caught:
        c.execute()
    if cleanup == "unknown":
        assert caught.value.primary_error is primary_error
        assert caught.value.followup_error is close_error
    else:
        assert caught.value is primary_error
    assert not any(r["operation_completed"] for r in c.rows("execution_waits"))
    assert c.coordinator.store.load_machine_snapshot().active_execution is not None
    assert_restart_blocked(c)


def test_carousel_projection_invalid_before_send_and_unknown_stays_invalid(case):
    c = make(case, COLUMN)

    def send(values):
        if values["command"] == "CAROUSEL_MOVE_TO_POSITION":
            assert c.runner.device.carousel_position is None
            assert c.rows("execution_carousel_projection")[0]["position"] is None
            raise ArduinoUnavailableError("carousel unknown")

    c.runner.device.before_send = send
    with pytest.raises(ArduinoUnavailableError):
        c.execute()
    assert len(c.rows("execution_waits")) == 1
    assert c.rows("execution_carousel_projection")[0]["position"] is None
    assert_restart_blocked(c)


@pytest.mark.parametrize("phase", [COLUMN, MIXING])
def test_boot_change_during_wait_prevents_stale_cleanup(case, phase):
    c = make(case, phase)

    def change(_):
        c.runner.device.controller_boot_id += 1

    c.runner.device.during_wait = change
    with pytest.raises(ProtectedOperationError):
        c.execute()
    assert c.rows("execution_waits")[-1]["state"] == "OUTCOME_UNKNOWN"
    assert c.runner.device.carousel_position is None
    if phase is MIXING:
        assert c.runner.device.sf_mixer_running is None
        assert c.runner.device.calls[-1]["arguments"] == {"running": True}
    assert_restart_blocked(c)


class Clock:
    def __init__(self):
        self.now = 0
        self.sleeps = []
        self.hook = lambda: None

    def read(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += round(seconds * 1_000_000_000)
        self.hook()


def test_monotonic_timer_measures_elapsed_not_poll_count():
    clock = Clock()

    def oversleep():
        clock.now += 70_000_000

    clock.hook = oversleep
    timer = MonotonicExecutionTimer(clock=clock.read, sleeper=clock.sleep)
    assert timer.wait(Decimal("0.1"), lambda: False) is CollectionTimerOutcome.COMPLETED
    assert clock.sleeps == [0.05]
    assert clock.now == 120_000_000


def test_timer_stop_at_deadline_wins_and_never_sleeps_again():
    clock = Clock()
    timer = MonotonicExecutionTimer(clock=clock.read, sleeper=clock.sleep)
    assert (
        timer.wait(Decimal("0.05"), lambda: clock.now == 50_000_000)
        is CollectionTimerOutcome.STOP_REQUESTED
    )
    assert clock.sleeps == [0.05]


@pytest.mark.parametrize("duration", [Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), 1.0])
def test_timer_rejects_invalid_duration(duration):
    with pytest.raises(ValueError):
        MonotonicExecutionTimer().wait(duration, lambda: False)


def test_timer_clock_regression_fails():
    clock = iter([100, 99])
    with pytest.raises(ValueError, match="regressed"):
        MonotonicExecutionTimer(clock=lambda: next(clock)).wait(Decimal("1"), lambda: False)


@pytest.mark.parametrize("phase", [COLUMN, MIXING, SETTLING])
def test_monotonic_timer_integrated_with_owner_and_lifecycle(case, phase):
    clock = Clock()
    timer = MonotonicExecutionTimer(clock=clock.read, sleeper=clock.sleep)
    c = make(case, phase, timer=timer)
    clock.hook = lambda: block_service(c)
    c.execute()
    assert clock.now > 0 and max(clock.sleeps) <= 0.05
    assert c.retained() is None
    assert all(r["operation_completed"] for r in c.rows("execution_waits"))


def test_real_short_monotonic_wait_with_fake_hardware(case):
    from time import monotonic

    settings = TIMED_SETTINGS.model_copy(update={"sf_mixing_duration_seconds": Decimal("0.01")})
    c = case(MIXING, settings=settings, mixer_running=False, timer=MonotonicExecutionTimer())
    start = monotonic()
    c.execute()
    assert monotonic() - start >= 0.01
    assert c.retained() is None


@pytest.mark.parametrize("phase", [MIXING, SETTLING])
@pytest.mark.parametrize("state", [True, None])
def test_timed_sf_needs_independent_stopped_mixer(case, phase, state):
    c = case(phase, settings=TIMED_SETTINGS, mixer_running=state)
    with pytest.raises(SimulationBlocked, match="stopped mixer"):
        c.execute()
    assert c.retained() is None
    assert not c.runner.device.calls and not c.rows("execution_waits")


@pytest.mark.parametrize("phase", [COLUMN, MIXING, SETTLING])
@pytest.mark.parametrize("point", ["wait", "resolution"])
def test_process_death_during_timed_phase_never_resumes_or_cleans_up(case, phase, point):
    import subprocess
    import sys

    c = make(case, phase)
    code = """
import os, sys
from pathlib import Path
from app.demo.calibration_models import PumpCalibrationSet
from app.demo.guided_demo_phase_executor import ColumnFractionCollectionReadiness
from app.hardware.sequence_ownership import HardwareOwnership
from app.hardware.owned_transfer_runner import OwnedTransferRunner
from app.hardware.simulated_lifecycle import PlanLifecycleCoordinator, SimulationLifecycleStore
from app.hardware.simulated_p1_runner import SimulatedP1Device
from tests.test_command_planning import context
ctx = context()
owner = HardwareOwnership(Path(sys.argv[1]), sys.argv[4])
store = SimulationLifecycleStore(Path(sys.argv[3]), sys.argv[6], sys.argv[5])
device = SimulatedP1Device(ctx)
device.sf_mixer_running = False
if sys.argv[7] == 'wait':
    device.during_wait = lambda _: os._exit(73)
else:
    store.resolve_phase_execution = lambda _: os._exit(73)
runner = OwnedTransferRunner(Path(sys.argv[2]), sys.argv[5], owner, device)
cals = PumpCalibrationSet(p1=ctx.pumps[0].calibration, p2=ctx.pumps[1].calibration)
PlanLifecycleCoordinator(store, runner).execute('test-phase-1', cals,
    column_readiness=ColumnFractionCollectionReadiness(True, True))
"""
    result = subprocess.run(
        [sys.executable, "-c", code, *map(str, c.paths), *c.identities, point], timeout=20
    )
    assert result.returncode == 73
    assert c.retained() == "test-phase-1"
    rows = c.rows("execution_waits")
    if point == "wait":
        assert rows[-1]["state"] == "INTENT_PERSISTED"
        assert rows[-1]["operation_completed"] == 0
        if phase is MIXING:
            assert len(c.rows("arduino_command_journal")) == 1  # START only
    else:
        assert all(r["operation_completed"] == 1 for r in rows)
    assert c.coordinator.store.load_machine_snapshot().active_execution is not None
    assert_restart_blocked(c)
    # The accepted recovery mechanism also understands new timed SF intents.
    from datetime import UTC, datetime
    from app.demo.machine_models import MachineState

    resolved = c.coordinator.store.reconcile_interrupted_phase_execution_at_startup(
        datetime.now(UTC)
    )
    assert resolved.machine.state is MachineState.RECOVERY_REQUIRED
    assert c.retained() == "test-phase-1"  # reconciliation alone never unlocks hardware


@pytest.mark.parametrize("phase", [COLUMN, MIXING])
@pytest.mark.parametrize("primary", ["ok", "failed", "unknown"])
@pytest.mark.parametrize("fault", ["intent", "result"])
def test_required_cleanup_journal_failure_preserves_primary(
    case, monkeypatch, phase, primary, fault
):
    c = make(case, phase)
    journal = c.runner._journal
    plan = c.runner.load_plan("test-phase-1")
    operation = next(op for op in plan.prepared.operations if op.required_followup)
    stop_id = operation.required_followup[0].operation_command_id
    primary_id = operation.actions[0].operation_command_id
    primary_error = (
        ArduinoCommandFailedError("ACTUATOR_FAILURE", True)
        if primary == "failed"
        else ArduinoUnavailableError("START unknown")
    )

    def send(values):
        if values["operation_command_id"] == primary_id and primary != "ok":
            raise primary_error

    c.runner.device.before_send = send
    if fault == "intent":
        original = journal.persist_intent

        def fail(**kw):
            if kw["operation_command_id"] == stop_id:
                raise sqlite3.OperationalError("STOP intent failed")
            return original(**kw)

        monkeypatch.setattr(journal, "persist_intent", fail)
    else:
        original = journal.record_outcome

        def fail(operation_id, *a, **kw):
            if operation_id == stop_id:
                raise sqlite3.OperationalError("STOP outcome failed")
            return original(operation_id, *a, **kw)

        monkeypatch.setattr(journal, "record_outcome", fail)
    with pytest.raises(
        sqlite3.OperationalError if primary == "ok" else ProtectedOperationError
    ) as caught:
        c.execute()
    if primary != "ok":
        assert caught.value.primary_error is primary_error
        assert isinstance(caught.value.followup_error, sqlite3.OperationalError)
    stopped = [v for v in c.runner.device.calls if v["operation_command_id"] == stop_id]
    assert bool(stopped) is (fault == "result")
    assert not any(r["operation_completed"] for r in c.rows("execution_waits"))
    assert_restart_blocked(c)


def test_unknown_wait_error_write_keeps_primary_and_runs_mixer_stop(case):
    c = make(case, MIXING)
    error = OSError("timer failed")
    db = c.runner._db

    class Fault:
        def execute(self, sql, args=()):
            if "execution_waits SET state='OUTCOME_UNKNOWN'" in sql:
                raise sqlite3.OperationalError("cannot persist timer error")
            return db.execute(sql, args)

    c.runner._db = Fault()

    def fail(_):
        raise error

    c.runner.device.during_wait = fail
    try:
        with pytest.raises(OSError) as caught:
            c.execute()
        assert caught.value is error
        assert any("Timer outcome persistence failed" in note for note in error.__notes__)
    finally:
        c.runner._db = db
    assert c.runner.device.calls[-1]["arguments"] == {"running": False}
    assert c.rows("execution_waits")[-1]["state"] == "INTENT_PERSISTED"
    assert_restart_blocked(c)


@pytest.mark.parametrize("phase", [COLUMN, MIXING])
def test_stop_immediately_after_open_or_start_skips_elapsed_wait_but_cleans_up(case, phase):
    c = make(case, phase)

    def send(values):
        if values["arguments"] in ({"running": True}, {"position_degrees": 94}):
            c.stop()

    c.runner.device.before_send = send
    c.runner.device.during_wait = lambda _: pytest.fail("elapsed wait after Stop")
    assert c.execute().run.status is RunStatus.ABORTED
    assert c.runner.device.calls[-1]["arguments"] == (
        {"running": False} if phase is MIXING else {"position_degrees": 4}
    )
    assert c.rows("execution_waits")[-1]["operation_completed"] == 0
    assert_restart_blocked(c)


def test_changed_carousel_fixture_rejected_before_claim(case):
    c = make(case, COLUMN)
    c.runner.device.carousel_position = None
    with pytest.raises(SimulationBlocked, match="alignment"):
        c.execute()
    assert c.retained() is None
    assert not c.runner.device.calls


def test_stale_mixing_duration_rejected_before_claim(case, monkeypatch):
    c = make(case, MIXING)
    original = c.coordinator.store.load_demo_run

    def changed(run_id):
        run = original(run_id)
        return run.model_copy(
            update={
                "execution_settings": run.execution_settings.model_copy(
                    update={"sf_mixing_duration_seconds": Decimal("3")}
                )
            }
        )

    monkeypatch.setattr(c.coordinator.store, "load_demo_run", changed)
    with pytest.raises(SimulationBlocked, match="differs from current run"):
        c.execute()
    assert c.retained() is None
    assert not c.runner.device.calls


def test_missing_mixing_duration_is_not_invented(case):
    with pytest.raises(ValueError, match="configure SF mixing duration"):
        case(MIXING, mixer_running=False)


@pytest.mark.parametrize("value", ["0", "-1", "NaN", "Infinity"])
def test_invalid_mixing_duration_rejected(value):
    from app.demo.models import DemoExecutionSettings
    from pydantic import ValidationError

    values = SETTINGS.model_dump()
    values["sf_mixing_duration_seconds"] = value
    with pytest.raises(ValidationError):
        DemoExecutionSettings.model_validate(values)


def test_timer_zero_duration_and_huge_duration_stop():
    clock = Clock()
    timer = MonotonicExecutionTimer(clock=clock.read, sleeper=clock.sleep)
    assert timer.wait(Decimal("0"), lambda: False) is CollectionTimerOutcome.COMPLETED
    assert not clock.sleeps
    assert (
        timer.wait(Decimal("1e1000"), lambda: bool(clock.sleeps))
        is CollectionTimerOutcome.STOP_REQUESTED
    )
    assert clock.sleeps == [0.05]


def test_sf_session_loss_while_mixing_requires_stop_and_keeps_owner(case):
    c = make(case, MIXING)
    c.runner.device.during_wait = lambda _: setattr(c.runner.device, "sf_session_id", "changed")
    with pytest.raises(SimulationBlocked, match="SF session"):
        c.execute()
    assert c.runner.device.calls[-1]["arguments"] == {"running": False}
    assert c.rows("execution_waits")[-1]["state"] == "OUTCOME_UNKNOWN"
    assert_restart_blocked(c)


@pytest.mark.parametrize("phase", [MIXING, SETTLING])
def test_manual_phase_completion_cannot_bypass_active_timed_intent(case, phase):
    from datetime import UTC, datetime
    from app.demo.application_service import GuidedDemoApplicationError

    c = make(case, phase)

    def wait(_):
        with pytest.raises(GuidedDemoApplicationError, match="execution"):
            c.service.complete_current_phase("run-1", datetime.now(UTC))
        assert c.coordinator.store.load_demo_run("run-1").phase is phase

    c.runner.device.during_wait = wait
    c.execute()


@pytest.mark.parametrize("fault", ["invalidate", "restore"])
def test_carousel_projection_write_fault_blocks_next_fraction(case, fault):
    c = make(case, COLUMN)
    db = c.runner._db

    class Fault:
        def execute(self, sql, args=()):
            if (
                fault == "invalidate"
                and "execution_carousel_projection SET position=NULL" in sql
                or fault == "restore"
                and "execution_carousel_projection SET position=?" in sql
            ):
                raise sqlite3.OperationalError("projection persistence failed")
            return db.execute(sql, args)

    c.runner._db = Fault()
    try:
        with pytest.raises(sqlite3.OperationalError):
            c.execute()
    finally:
        c.runner._db = db
    assert len(c.rows("execution_waits")) == 1
    moved = any(v["command"] == "CAROUSEL_MOVE_TO_POSITION" for v in c.runner.device.calls)
    assert moved is (fault == "restore")
    assert c.runner.device.carousel_position is None
    if moved:
        assert c.rows("execution_carousel_projection")[0]["position"] is None
    assert_restart_blocked(c)


def test_previous_execution_schema_is_rejected_without_migration(case):
    from app.hardware.owned_transfer_runner import OwnedTransferRunner
    from app.hardware.simulated_p1_runner import SimulatedP1Device
    from tests.test_command_planning import context

    c = make(case, COLUMN)
    with sqlite3.connect(c.paths[1]) as db:
        db.execute("DROP TABLE execution_waits")
        db.execute("DROP TABLE execution_carousel_projection")
    before = c.paths[1].read_bytes()
    with pytest.raises(SimulationBlocked, match="schema"):
        OwnedTransferRunner(c.paths[1], c.identities[1], c.owner, SimulatedP1Device(context()))
    assert c.paths[1].read_bytes() == before


def test_zero_settling_duration_completes_without_hardware_or_sleep(case):
    settings = TIMED_SETTINGS.model_copy(update={"sf_settling_duration_seconds": Decimal("0")})
    clock = Clock()
    c = case(
        SETTLING,
        settings=settings,
        mixer_running=False,
        timer=MonotonicExecutionTimer(clock=clock.read, sleeper=clock.sleep),
    )
    c.execute()
    assert not clock.sleeps and not c.runner.device.calls
    assert c.rows("execution_waits")[0]["operation_completed"] == 1


@pytest.mark.parametrize("where", ["plan", "operation"])
def test_unknown_timed_plan_fields_rejected_before_persistence(case, where):
    from pydantic import ValidationError
    from app.hardware.command_plan_store import SQLiteCommandPlanStore

    c = make(case, MIXING)
    payload = c.runner.load_plan("test-phase-1").source.model_dump(mode="json")
    target = payload["plan"] if where == "plan" else payload["plan"]["operations"][0]
    target["unknown_policy"] = True
    before = c.paths[1].read_bytes()
    with SQLiteCommandPlanStore(c.paths[1]) as plans:
        with pytest.raises(ValidationError):
            plans.persist(payload, c.runner.device.current)
    assert c.paths[1].read_bytes() == before


def test_stop_from_separate_lifecycle_connection_interrupts_real_wait(case):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import UTC, datetime
    from threading import Event
    from time import sleep
    from app.demo.application_service import GuidedDemoApplicationService
    from app.hardware.simulated_lifecycle import SimulationLifecycleStore

    waiting = Event()

    def sleeper(seconds):
        waiting.set()
        sleep(seconds)

    c = make(case, MIXING, timer=MonotonicExecutionTimer(sleeper=sleeper))

    def request_stop():
        assert waiting.wait(5)
        with SimulationLifecycleStore(c.paths[2], c.identities[2], c.identities[1]) as store:
            GuidedDemoApplicationService(store).request_stop_demo("run-1", datetime.now(UTC))

    with ThreadPoolExecutor(max_workers=1) as pool:
        request = pool.submit(request_stop)
        result = c.execute()
        request.result(timeout=5)
    assert result.run.status is RunStatus.ABORTED
    assert c.rows("execution_waits")[0]["state"] == "STOP_REQUESTED"
    assert c.runner.device.calls[-1]["arguments"] == {"running": False}
    assert_restart_blocked(c)
