import sqlite3
import subprocess
import sys

import pytest

from app.demo.operation_executor import ProtectedOperationError
from app.hardware.arduino_serial import ArduinoCommandFailedError, ArduinoUnavailableError
from app.hardware.command_planning import ArduinoAction, SfBottomValveAction
from app.hardware.simulated_p1_runner import (
    SimulatedTransferDevice,
    SimulatedTransferRunner,
    SimulationBlocked,
)
from tests.test_simulated_p1_runner import setup, run
from tests.test_command_planning import context


def sf_rows(path):
    with sqlite3.connect(path) as db:
        return db.execute(
            "SELECT action_id, target, state FROM simulation_sf_actions ORDER BY rowid"
        ).fetchall()


@pytest.mark.parametrize("kind", ["reactor", "sf"])
def test_p2_complete_order_and_committed_sf_intent(tmp_path, kind):
    path, identity, plan, device = setup(tmp_path, kind)
    events = []
    device.before_send = lambda v: events.append(v["operation_command_id"])

    def sf(v):
        with sqlite3.connect(path) as db:
            row = db.execute(
                "SELECT state, target FROM simulation_sf_actions WHERE action_id=?",
                (v["operation_command_id"],),
            ).fetchone()
        assert row == ("INTENT_PERSISTED", v["state"])
        events.append(v["operation_command_id"])

    device.before_sf_send = sf
    runner = SimulatedTransferRunner(path, identity, device)
    try:
        assert run(runner) == ("COMPLETED", len(plan.prepared.operations))
        expected = [
            a.operation_command_id
            for op in plan.prepared.operations
            for a in (*op.actions, *op.required_followup)
        ]
        assert events == expected
        assert all(row[2] == "COMPLETED" for row in sf_rows(path))
        assert all(v["arguments"].get("pump", "P2") == "P2" for v in device.calls)
    finally:
        runner.close()


def protected(plan):
    return next(
        (index, op)
        for index, op in enumerate(plan.prepared.operations)
        if any(isinstance(a, SfBottomValveAction) and a.state.value == "OPEN" for a in op.actions)
    )


@pytest.mark.parametrize("primary", ["ok", "failed", "unknown"])
@pytest.mark.parametrize("closing", ["ok", "failed", "unknown"])
def test_primary_and_required_close_outcomes(tmp_path, primary, closing):
    path, identity, plan, device = setup(tmp_path, "sf")
    index, operation = protected(plan)
    pump = next(a for a in operation.actions if isinstance(a, ArduinoAction))
    close_id = operation.required_followup[0].operation_command_id
    errors = []

    def error(outcome):
        if outcome == "failed":
            raise ArduinoCommandFailedError("SIMULATED_FAILURE", True)
        if outcome == "unknown":
            raise ArduinoUnavailableError("lost response")

    def send(v):
        if v["operation_command_id"] == pump.operation_command_id:
            error(primary)

    def sf(v):
        if v["operation_command_id"] == close_id:
            errors.append(v)
            error(closing)

    device.before_send, device.before_sf_send = send, sf
    runner = SimulatedTransferRunner(path, identity, device)
    try:
        if primary == closing == "ok":
            assert run(runner)[0] == "COMPLETED"
        else:
            with pytest.raises(Exception) as caught:
                run(runner)
            if primary != "ok" and closing != "ok":
                assert isinstance(caught.value, ProtectedOperationError)
                assert caught.value.primary_error is not None
                assert caught.value.followup_error is not None
            expected = "OUTCOME_UNKNOWN" if "unknown" in (primary, closing) else "FAILED"
            assert runner.status(plan.phase_execution_id) == (expected, index)
            later_ids = {
                a.operation_command_id
                for op in plan.prepared.operations[index + 1 :]
                for a in (*op.actions, *op.required_followup)
            }
            assert not later_ids.intersection(
                v["operation_command_id"] for v in device.calls + device.sf_calls
            )
        assert len(errors) == 1
        row = next(r for r in sf_rows(path) if r[0] == close_id)
        assert (
            row[2] == {"ok": "COMPLETED", "failed": "FAILED", "unknown": "OUTCOME_UNKNOWN"}[closing]
        )
    finally:
        runner.close()
    fresh = SimulatedTransferRunner(path, identity, SimulatedTransferDevice(context()))
    try:
        with pytest.raises(SimulationBlocked):
            run(fresh)
        assert not fresh.device.calls and not fresh.device.sf_calls
    finally:
        fresh.close()


@pytest.mark.parametrize("unknown", [False, True])
def test_open_failure_still_attempts_close_without_pump(tmp_path, unknown):
    path, identity, plan, device = setup(tmp_path, "sf")
    _, operation = protected(plan)
    opener = operation.actions[0].operation_command_id

    def sf(v):
        if v["operation_command_id"] == opener:
            if unknown:
                raise ArduinoUnavailableError("open unknown")
            raise ArduinoCommandFailedError("OPEN_FAILED", True)

    device.before_sf_send = sf
    runner = SimulatedTransferRunner(path, identity, device)
    try:
        with pytest.raises((ArduinoUnavailableError, ArduinoCommandFailedError)):
            run(runner)
        assert not any(v["command"] == "PUMP_MOVE_ABSOLUTE_STEPS" for v in device.calls)
        assert sf_rows(path)[-1][1:] == ("CLOSED", "COMPLETED")
    finally:
        runner.close()


def test_stop_during_open_waits_for_aspiration_and_close(tmp_path):
    path, identity, plan, device = setup(tmp_path, "sf")
    index, operation = protected(plan)
    stopped = False

    def sf(v):
        nonlocal stopped
        if v["state"] == "OPEN":
            stopped = True

    device.before_sf_send = sf
    runner = SimulatedTransferRunner(path, identity, device)
    try:
        assert run(runner, stop_requested=lambda: stopped) == ("STOPPED", index + 1)
        assert sf_rows(path)[-1][1:] == ("CLOSED", "COMPLETED")
        assert device.calls[-1]["command"] == "PUMP_MOVE_ABSOLUTE_STEPS"
    finally:
        runner.close()


def test_primary_arduino_reboot_does_not_skip_independent_sf_close(tmp_path):
    path, identity, _, device = setup(tmp_path, "sf")

    def send(v):
        if v["command"] == "PUMP_MOVE_ABSOLUTE_STEPS":
            device.controller_boot_id += 1

    device.before_send = send
    runner = SimulatedTransferRunner(path, identity, device)
    try:
        with pytest.raises(ArduinoUnavailableError):
            run(runner)
        assert sf_rows(path)[-1][1:] == ("CLOSED", "COMPLETED")
        assert runner.status("test-phase-1")[0] == "OUTCOME_UNKNOWN"
    finally:
        runner.close()


def test_sf_session_loss_blocks_further_sf_sends(tmp_path):
    path, identity, _, device = setup(tmp_path, "sf")

    def sf(v):
        if v["state"] == "OPEN":
            device.sf_session_id = "changed"

    device.before_sf_send = sf
    runner = SimulatedTransferRunner(path, identity, device)
    try:
        with pytest.raises(ProtectedOperationError):
            run(runner)
        assert sf_rows(path)[-1][1:] == ("OPEN", "OUTCOME_UNKNOWN")
        assert not any(v["command"] == "PUMP_MOVE_ABSOLUTE_STEPS" for v in device.calls)
        assert runner.status("test-phase-1")[0] == "OUTCOME_UNKNOWN"
    finally:
        runner.close()


def test_exit_between_open_and_close_never_auto_closes_or_resumes(tmp_path):
    path, identity, _, _ = setup(tmp_path, "sf")
    code = """
import os, sys
from pathlib import Path
from app.hardware.simulated_p1_runner import SimulatedTransferDevice, SimulatedTransferRunner
from tests.test_command_planning import context
client = SimulatedTransferDevice(context())
def die(values):
    if values["command"] == "PUMP_MOVE_ABSOLUTE_STEPS": os._exit(23)
client.before_send = die
runner = SimulatedTransferRunner(Path(sys.argv[1]), sys.argv[2], client)
runner.run("test-phase-1", run_id="run-1", run_event_sequence=12)
"""
    assert subprocess.run([sys.executable, "-c", code, str(path), identity]).returncode == 23
    assert sf_rows(path)[-1][1:] == ("OPEN", "COMPLETED")
    before = path.read_bytes()
    runner = SimulatedTransferRunner(path, identity, SimulatedTransferDevice(context()))
    try:
        with pytest.raises(SimulationBlocked):
            run(runner)
        assert runner.status("test-phase-1")[0] == "RUNNING"
        assert not runner.device.calls and not runner.device.sf_calls
    finally:
        runner.close()
    assert path.read_bytes() == before


def test_other_runner_blocked_while_sf_close_in_progress(tmp_path):
    path, identity, plan, device = setup(tmp_path, "sf")
    _, operation = protected(plan)
    second = SimulatedTransferRunner(path, identity, SimulatedTransferDevice(context()))
    attempted = []

    def sf(v):
        if v["operation_command_id"] == operation.required_followup[0].operation_command_id:
            with pytest.raises(SimulationBlocked):
                run(second)
            attempted.append(True)

    device.before_sf_send = sf
    first = SimulatedTransferRunner(path, identity, device)
    try:
        assert run(first)[0] == "COMPLETED"
        assert attempted == [True]
        assert not second.device.calls and not second.device.sf_calls
    finally:
        first.close()
        second.close()


@pytest.mark.parametrize("stage", ["intent", "result"])
def test_sf_database_write_failure_blocks_continuation(tmp_path, stage):
    path, identity, _, device = setup(tmp_path, "sf")
    trigger = (
        "BEFORE INSERT ON simulation_sf_actions WHEN NEW.target='OPEN'"
        if stage == "intent"
        else "BEFORE UPDATE ON simulation_sf_actions WHEN NEW.target='OPEN' AND NEW.state='COMPLETED'"
    )
    with sqlite3.connect(path) as db:
        db.execute(
            f"CREATE TRIGGER injected_fault {trigger} BEGIN SELECT RAISE(ABORT, 'injected disk failure'); END"
        )
    runner = SimulatedTransferRunner(path, identity, device)
    try:
        with pytest.raises(sqlite3.Error):
            run(runner)
        opens = [v for v in device.sf_calls if v["state"] == "OPEN"]
        assert len(opens) == (0 if stage == "intent" else 1)
        assert sf_rows(path)[-1][1:] == ("CLOSED", "COMPLETED")
        assert runner.status("test-phase-1")[0] == "OUTCOME_UNKNOWN"
        assert not any(v["command"] == "PUMP_MOVE_ABSOLUTE_STEPS" for v in device.calls)
    finally:
        runner.close()


def test_initial_sf_failure_still_closes_column(tmp_path):
    path, identity, plan, device = setup(tmp_path, "sf")
    first = plan.prepared.operations[0]
    assert first.required_followup

    def fail(v):
        raise ArduinoUnavailableError("initial SF close unknown")

    device.before_sf_send = fail
    runner = SimulatedTransferRunner(path, identity, device)
    try:
        with pytest.raises(ArduinoUnavailableError):
            run(runner)
        assert [v["operation_command_id"] for v in device.calls] == [
            a.operation_command_id for a in first.required_followup
        ]
        assert runner.status("test-phase-1") == ("OUTCOME_UNKNOWN", 0)
    finally:
        runner.close()
