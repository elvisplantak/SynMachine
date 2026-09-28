import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from app.hardware.arduino_command_journal import (
    ArduinoCommandJournalState,
    SQLiteArduinoCommandJournal,
)
from app.hardware.arduino_serial import (
    ArduinoCommandFailedError,
    ArduinoCommandRejectedError,
    ArduinoUnavailableError,
)
from app.hardware.command_plan_store import SQLiteCommandPlanStore
from app.hardware.simulated_p1_runner import (
    SimulatedP1Device,
    SimulatedP1Runner,
    SimulationBlocked,
    provision_simulation,
)
from tests.test_command_plan_store import source
from tests.test_command_planning import context


def setup(tmp_path, kind="solvent"):
    path = tmp_path / "simulation.db"
    identity = provision_simulation(path)
    with SQLiteCommandPlanStore(path) as plans:
        saved = plans.persist(source(kind), context()).plan
    device = SimulatedP1Device(context())
    return path, identity, saved, device


def run(runner, **changes):
    values = dict(run_id="run-1", run_event_sequence=12)
    values.update(changes)
    return runner.run("test-phase-1", **values)


@pytest.mark.parametrize("kind", ["solvent", "first", "second"])
def test_whole_phase_order_and_intents_before_send(tmp_path, monkeypatch, kind):
    import serial

    monkeypatch.setattr(serial, "Serial", lambda *a, **k: pytest.fail("Serial opened"))
    path, identity, plan, device = setup(tmp_path, kind)
    runner = SimulatedP1Runner(path, identity, device)

    def verify(values):
        with SQLiteArduinoCommandJournal(path) as journal:
            entry = journal.load(values["operation_command_id"])
            assert entry.state is ArduinoCommandJournalState.INTENT_PERSISTED
            assert entry.arguments == values["arguments"]
        assert runner.status(plan.phase_execution_id)[0] == "RUNNING"

    device.before_send = verify
    try:
        assert run(runner) == ("COMPLETED", len(plan.prepared.operations))
        expected = [a for op in plan.prepared.operations for a in op.actions]
        assert [c["operation_command_id"] for c in device.calls] == [
            a.operation_command_id for a in expected
        ]
        assert [c["arguments"] for c in device.calls] == [dict(a.arguments) for a in expected]
        if kind in ("first", "second"):
            v4_targets = [
                call["arguments"]["position_degrees"]
                for call in device.calls
                if call["arguments"].get("valve") == "V4"
            ]
            assert v4_targets == ([180] if kind == "first" else [90])
        with SQLiteArduinoCommandJournal(path) as journal:
            assert all(
                journal.load(a.operation_command_id).state is ArduinoCommandJournalState.COMPLETED
                for a in expected
            )
    finally:
        runner.close()
    fresh = SimulatedP1Runner(path, identity, SimulatedP1Device(context()))
    try:
        with pytest.raises(SimulationBlocked):
            run(fresh)
        assert not fresh.device.calls
    finally:
        fresh.close()


@pytest.mark.parametrize(
    "error,phase_state,journal_state",
    [
        (ArduinoCommandRejectedError("INVALID_FIELD"), "FAILED", "REJECTED"),
        (ArduinoCommandFailedError("PUMP_MOTION_TIMEOUT", True), "FAILED", "FAILED"),
        (ArduinoUnavailableError("timeout"), "OUTCOME_UNKNOWN", "OUTCOME_UNKNOWN"),
        (RuntimeError("unexpected transport failure"), "OUTCOME_UNKNOWN", "INTENT_PERSISTED"),
    ],
)
def test_failure_stops_sequence_and_never_resends_after_reopen(
    tmp_path, error, phase_state, journal_state
):
    path, identity, plan, device = setup(tmp_path)
    runner = SimulatedP1Runner(path, identity, device)
    attempts = []

    def fail(values):
        attempts.append(values)
        raise error

    device.before_send = fail
    try:
        with pytest.raises(type(error)):
            run(runner)
        assert runner.status(plan.phase_execution_id) == (phase_state, 0)
        assert len(attempts) == 1
        with SQLiteArduinoCommandJournal(path) as journal:
            assert journal.load(attempts[0]["operation_command_id"]).state == journal_state
    finally:
        runner.close()
    fresh = SimulatedP1Runner(path, identity, SimulatedP1Device(context()))
    try:
        with pytest.raises(SimulationBlocked):
            run(fresh)
        assert fresh.device.calls == []
    finally:
        fresh.close()


def test_stop_waits_for_operation_boundary(tmp_path):
    path, identity, plan, device = setup(tmp_path)
    runner = SimulatedP1Runner(path, identity, device)
    try:
        assert run(runner, stop_requested=lambda: bool(device.calls)) == ("STOPPED", 1)
        assert len(device.calls) == len(plan.prepared.operations[0].actions)
        assert len(device.calls) > 1
    finally:
        runner.close()


def test_stop_before_first_operation_sends_nothing(tmp_path):
    path, identity, _, device = setup(tmp_path)
    runner = SimulatedP1Runner(path, identity, device)
    try:
        assert run(runner, stop_requested=lambda: True) == ("STOPPED", 0)
        assert device.calls == []
    finally:
        runner.close()


@pytest.mark.parametrize("kind", ["column"])
def test_other_phases_rejected_before_claim(tmp_path, kind):
    path, identity, _, device = setup(tmp_path, kind)
    runner = SimulatedP1Runner(path, identity, device)
    try:
        with pytest.raises(SimulationBlocked):
            run(runner)
        assert runner.status("test-phase-1") is None
        assert not device.calls
    finally:
        runner.close()


@pytest.mark.parametrize("change", ["run", "event", "assumptions", "boot"])
def test_preflight_requires_independent_matching_state(tmp_path, change):
    path, identity, _, device = setup(tmp_path)
    args = {}
    if change == "run":
        args["run_id"] = "other"
    if change == "event":
        args["run_event_sequence"] = 13
    if change == "assumptions":
        device.current = context(reactor_mixer_running=True)
    if change == "boot":
        device.controller_boot_id += 1
    runner = SimulatedP1Runner(path, identity, device)
    try:
        with pytest.raises(SimulationBlocked):
            run(runner, **args)
        assert runner.status("test-phase-1") is None
        assert not device.calls
    finally:
        runner.close()


@pytest.mark.parametrize("last_command", [False, True])
def test_reboot_between_commands_blocks_continuation(tmp_path, last_command):
    path, identity, plan, device = setup(tmp_path)
    count = sum(len(op.actions) for op in plan.prepared.operations) if last_command else 1

    def reboot(_):
        if len(device.calls) + 1 == count:
            device.controller_boot_id = 59

    device.before_send = reboot
    runner = SimulatedP1Runner(path, identity, device)
    try:
        with pytest.raises(ArduinoUnavailableError):
            run(runner)
        assert len(device.calls) == count
        assert runner.status("test-phase-1")[0] == "OUTCOME_UNKNOWN"
    finally:
        runner.close()


def test_independent_runners_cannot_interleave_sequences(tmp_path):
    path, identity, _, device = setup(tmp_path)
    entered, release = Event(), Event()

    def block(_):
        entered.set()
        assert release.wait(5)

    device.before_send = block
    first = SimulatedP1Runner(path, identity, device)
    second = SimulatedP1Runner(path, identity, SimulatedP1Device(context()))
    try:
        with ThreadPoolExecutor(1) as pool:
            future = pool.submit(run, first)
            assert entered.wait(5)
            try:
                with pytest.raises(SimulationBlocked):
                    run(second)
                assert second.device.calls == []
            finally:
                release.set()
            assert future.result()[0] == "COMPLETED"
    finally:
        first.close()
        second.close()


def test_process_exit_after_intent_leaves_phase_blocked(tmp_path):
    path, identity, _, _ = setup(tmp_path)
    code = """
import os, sys
from app.hardware.simulated_p1_runner import SimulatedP1Runner, SimulatedP1Device
from tests.test_command_planning import context
from pathlib import Path
client = SimulatedP1Device(context())
client.before_send = lambda _: os._exit(19)
runner = SimulatedP1Runner(Path(sys.argv[1]), sys.argv[2], client)
runner.run("test-phase-1", run_id="run-1", run_event_sequence=12)
"""
    result = subprocess.run([sys.executable, "-c", code, str(path), identity])
    assert result.returncode == 19
    runner = SimulatedP1Runner(path, identity, SimulatedP1Device(context()))
    try:
        assert runner.status("test-phase-1") == ("RUNNING", 0)
        with pytest.raises(SimulationBlocked):
            run(runner)
        assert not runner.device.calls
    finally:
        runner.close()


@pytest.mark.parametrize("case", ["missing", "empty", "wrong_identity"])
def test_open_never_creates_or_repairs_wrong_database(tmp_path, case):
    path = tmp_path / "missing.db"
    if case == "empty":
        path.touch()
    if case == "wrong_identity":
        provision_simulation(path)
    before = path.read_bytes() if path.exists() else None
    with pytest.raises((sqlite3.Error, SimulationBlocked)):
        SimulatedP1Runner(path, "wrong", SimulatedP1Device(context()))
    assert (path.read_bytes() if path.exists() else None) == before


def test_no_live_transport_accepted(tmp_path):
    with pytest.raises(TypeError):
        SimulatedP1Runner(tmp_path / "absent", "id", object())


def test_result_write_failure_after_send_never_allows_restart(tmp_path, monkeypatch):
    path, identity, _, device = setup(tmp_path)
    runner = SimulatedP1Runner(path, identity, device)

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("injected outcome write failure")

    monkeypatch.setattr(runner._journal, "record_outcome", fail)
    try:
        with pytest.raises(sqlite3.OperationalError):
            run(runner)
        assert len(device.calls) == 1
        assert runner.status("test-phase-1") == ("OUTCOME_UNKNOWN", 0)
    finally:
        runner.close()
    fresh = SimulatedP1Runner(path, identity, SimulatedP1Device(context()))
    try:
        with pytest.raises(SimulationBlocked):
            run(fresh)
        assert not fresh.device.calls
    finally:
        fresh.close()


def test_intent_write_failure_sends_nothing(tmp_path, monkeypatch):
    path, identity, _, device = setup(tmp_path)
    runner = SimulatedP1Runner(path, identity, device)

    def fail(*args, **kwargs):
        raise sqlite3.OperationalError("injected intent write failure")

    monkeypatch.setattr(runner._journal, "persist_intent", fail)
    try:
        with pytest.raises(sqlite3.OperationalError):
            run(runner)
        assert not device.calls
        assert runner.status("test-phase-1") == ("OUTCOME_UNKNOWN", 0)
    finally:
        runner.close()


def test_unresolved_owner_blocks_different_phase(tmp_path):
    path, identity, _, device = setup(tmp_path)
    first = SimulatedP1Runner(path, identity, device)
    try:
        run(first, stop_requested=lambda: True)
    finally:
        first.close()
    ctx = context(phase_execution_id="second-phase")
    with SQLiteCommandPlanStore(path) as plans:
        plans.persist(source(ctx=ctx), ctx)
    second = SimulatedP1Runner(path, identity, SimulatedP1Device(ctx))
    try:
        with pytest.raises(SimulationBlocked):
            second.run("second-phase", run_id="run-1", run_event_sequence=12)
        assert second.status("second-phase") is None
        assert not second.device.calls
    finally:
        second.close()


def test_absent_plan_is_distinct_from_invalid_database(tmp_path):
    path = tmp_path / "valid.db"
    identity = provision_simulation(path)
    runner = SimulatedP1Runner(path, identity, SimulatedP1Device(context()))
    try:
        with pytest.raises(SimulationBlocked, match="plan is absent"):
            run(runner)
        assert runner.status("test-phase-1") is None
    finally:
        runner.close()


@pytest.mark.parametrize("kind", ["solvent", "first", "second"])
@pytest.mark.parametrize("ambiguous", [False, True])
def test_failure_at_every_action_stops_and_preserves_completed_prefix(tmp_path, kind, ambiguous):
    # Exercise valve switches and both pump directions, including later cycles.
    template = source(kind)
    from app.hardware.command_planning import prepare_command_plan

    operations = prepare_command_plan(template.plan.operations, context()).operations
    flattened = [(index, action) for index, op in enumerate(operations) for action in op.actions]
    for failure_index, (operation_index, _) in enumerate(flattened):
        folder = tmp_path / str(failure_index)
        folder.mkdir()
        path, identity, plan, device = setup(folder, kind)
        runner = SimulatedP1Runner(path, identity, device)

        def inject(_):
            if len(device.calls) == failure_index:
                if ambiguous:
                    raise ArduinoUnavailableError("simulated lost outcome")
                raise ArduinoCommandFailedError("SIMULATED_FAILURE", True)

        device.before_send = inject
        try:
            with pytest.raises((ArduinoUnavailableError, ArduinoCommandFailedError)):
                run(runner)
            expected_state = "OUTCOME_UNKNOWN" if ambiguous else "FAILED"
            assert runner.status(plan.phase_execution_id) == (expected_state, operation_index)
            assert len(device.calls) == failure_index
            with SQLiteArduinoCommandJournal(path) as journal:
                for index, (_, action) in enumerate(flattened):
                    entry = journal.load(action.operation_command_id)
                    if index < failure_index:
                        assert entry.state is ArduinoCommandJournalState.COMPLETED
                    elif index == failure_index:
                        assert entry.state == expected_state
                    else:
                        assert entry is None
        finally:
            runner.close()
        reopened = SimulatedP1Runner(path, identity, SimulatedP1Device(context()))
        try:
            with pytest.raises(SimulationBlocked):
                run(reopened)
            assert not reopened.device.calls
        finally:
            reopened.close()


@pytest.mark.parametrize("kind", ["solvent", "first", "second"])
@pytest.mark.parametrize("pump_action_index", [0, 1])
def test_stop_during_aspiration_or_dispense_finishes_current_operation(
    tmp_path, kind, pump_action_index
):
    path, identity, plan, device = setup(tmp_path, kind)
    pump_operations = [
        (index, op)
        for index, op in enumerate(plan.prepared.operations)
        if any(a.command == "PUMP_MOVE_ABSOLUTE_STEPS" for a in op.actions)
    ]
    op_index, operation = pump_operations[pump_action_index]
    target_id = operation.actions[0].operation_command_id
    stopped = False

    def request_stop(values):
        nonlocal stopped
        if values["operation_command_id"] == target_id:
            stopped = True

    device.before_send = request_stop
    runner = SimulatedP1Runner(path, identity, device)
    try:
        # Stop after the last operation is naturally a completed phase.
        expected_state = "COMPLETED" if op_index + 1 == len(plan.prepared.operations) else "STOPPED"
        assert run(runner, stop_requested=lambda: stopped) == (expected_state, op_index + 1)
        expected = [
            a.operation_command_id
            for op in plan.prepared.operations[: op_index + 1]
            for a in op.actions
        ]
        assert [c["operation_command_id"] for c in device.calls] == expected
    finally:
        runner.close()
