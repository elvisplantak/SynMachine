import sqlite3
import subprocess
import sys
from decimal import Decimal

import pytest

from app.demo.operation_executor import ProtectedOperationError
from app.hardware.arduino_serial import ArduinoCommandFailedError, ArduinoUnavailableError
from app.hardware.command_planning import CollectionWait
from app.hardware.simulated_p1_runner import (
    SimulatedTransferDevice,
    SimulatedTransferRunner,
    SimulationBlocked,
)
from tests.test_command_planning import context
from tests.test_simulated_p1_runner import setup, run


def collecting(plan):
    return next(
        (i, op)
        for i, op in enumerate(plan.prepared.operations)
        if any(isinstance(a, CollectionWait) for a in op.actions)
    )


def test_collection_order_waits_and_wrap(tmp_path):
    path, identity, plan, device = setup(tmp_path, "column")
    events = []
    device.before_send = lambda v: events.append(v["operation_command_id"])

    def wait(duration):
        events.append(duration)
        with sqlite3.connect(path) as db:
            assert db.execute(
                "SELECT state FROM simulation_waits ORDER BY operation_number DESC LIMIT 1"
            ).fetchone() == ("INTENT_PERSISTED",)

    device.during_wait = wait
    runner = SimulatedTransferRunner(path, identity, device)
    try:
        assert run(runner) == ("COMPLETED", len(plan.prepared.operations))
        expected = [
            a.duration_seconds if isinstance(a, CollectionWait) else a.operation_command_id
            for op in plan.prepared.operations
            for a in (*op.actions, *op.required_followup)
        ]
        assert events == expected
        assert device.waits == [Decimal("2.5")] * 3
        moves = [
            v["arguments"]["position"]
            for v in device.calls
            if v["command"] == "CAROUSEL_MOVE_TO_POSITION"
        ]
        assert moves == [1, 2]
        assert device.carousel_position == 2
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT position FROM simulation_carousel_projection").fetchone() == (
                2,
            )
            assert (
                db.execute("SELECT state FROM simulation_waits").fetchall() == [("COMPLETED",)] * 3
            )
    finally:
        runner.close()


@pytest.mark.parametrize("point", ["during_open", "during_wait", "during_close"])
def test_collection_stop_requires_close_and_blocks_carousel(tmp_path, point):
    path, identity, plan, device = setup(tmp_path, "column")
    index, op = collecting(plan)
    stopped = False

    def request():
        nonlocal stopped
        stopped = True

    def send(v):
        if (
            point == "during_open"
            and v["operation_command_id"] == op.actions[0].operation_command_id
        ):
            request()
        if (
            point == "during_close"
            and v["operation_command_id"] == op.required_followup[0].operation_command_id
        ):
            request()

    device.before_send = send
    if point == "during_wait":
        device.during_wait = lambda _: request()
    runner = SimulatedTransferRunner(path, identity, device)
    try:
        expected = (
            ("STOPPED", index + 1)
            if point == "during_close"
            else ("COLLECTION_STOP_REQUESTED", index)
        )
        assert run(runner, stop_requested=lambda: stopped) == expected
        assert (
            device.calls[-1]["operation_command_id"] == op.required_followup[0].operation_command_id
        )
        assert not any(v["command"] == "CAROUSEL_MOVE_TO_POSITION" for v in device.calls)
    finally:
        runner.close()
    reopened = SimulatedTransferRunner(path, identity, SimulatedTransferDevice(context()))
    try:
        with pytest.raises(SimulationBlocked):
            run(reopened)
        assert not reopened.device.calls
    finally:
        reopened.close()


@pytest.mark.parametrize(
    "primary", ["open_failed", "open_unknown", "wait_failed", "wait_ok", "wait_stop"]
)
@pytest.mark.parametrize("closing", ["ok", "failed", "unknown"])
def test_collection_primary_and_close_faults(tmp_path, primary, closing):
    path, identity, plan, device = setup(tmp_path, "column")
    index, op = collecting(plan)
    stopped = False

    def send(v):
        if v["operation_command_id"] == op.actions[0].operation_command_id:
            if primary == "open_failed":
                raise ArduinoCommandFailedError("OPEN_FAILED", True)
            if primary == "open_unknown":
                raise ArduinoUnavailableError("open unknown")
        if v["operation_command_id"] == op.required_followup[0].operation_command_id:
            if closing == "failed":
                raise ArduinoCommandFailedError("CLOSE_FAILED", True)
            if closing == "unknown":
                raise ArduinoUnavailableError("close unknown")

    def wait(_):
        nonlocal stopped
        if primary == "wait_failed":
            raise RuntimeError("timer failure")
        if primary == "wait_stop":
            stopped = True

    device.before_send, device.during_wait = send, wait
    runner = SimulatedTransferRunner(path, identity, device)
    try:
        if primary in ("wait_ok", "wait_stop") and closing == "ok":
            outcome = run(runner, stop_requested=lambda: stopped)
            assert outcome[0] == (
                "COMPLETED" if primary == "wait_ok" else "COLLECTION_STOP_REQUESTED"
            )
        else:
            with pytest.raises(Exception) as error:
                run(runner, stop_requested=lambda: stopped)
            if primary in ("open_failed", "open_unknown", "wait_failed") and closing != "ok":
                assert isinstance(error.value, ProtectedOperationError)
            unknown = primary in ("open_unknown", "wait_failed") or closing == "unknown"
            assert runner.status(plan.phase_execution_id) == (
                "OUTCOME_UNKNOWN" if unknown else "FAILED",
                index,
            )
            assert not any(v["command"] == "CAROUSEL_MOVE_TO_POSITION" for v in device.calls)
        with sqlite3.connect(path) as db:
            row = db.execute(
                "SELECT state FROM arduino_command_journal WHERE operation_command_id=?",
                (op.required_followup[0].operation_command_id,),
            ).fetchone()
            assert row == (
                {"ok": "COMPLETED", "failed": "FAILED", "unknown": "OUTCOME_UNKNOWN"}[closing],
            )
    finally:
        runner.close()


@pytest.mark.parametrize("outcome", ["failed", "unknown", "reboot"])
def test_carousel_failure_discards_projection_and_blocks_later_open(tmp_path, outcome):
    path, identity, plan, device = setup(tmp_path, "column")

    def send(v):
        if v["command"] == "CAROUSEL_MOVE_TO_POSITION":
            assert device.carousel_position is None
            if outcome == "failed":
                raise ArduinoCommandFailedError("CAROUSEL_FAILED", True)
            if outcome == "unknown":
                raise ArduinoUnavailableError("carousel unknown")
            device.controller_boot_id += 1

    device.before_send = send
    runner = SimulatedTransferRunner(path, identity, device)
    try:
        with pytest.raises((ArduinoCommandFailedError, ArduinoUnavailableError)):
            run(runner)
        assert device.carousel_position is None
        assert len(device.waits) == 1
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT position FROM simulation_carousel_projection").fetchone() == (
                None,
            )
    finally:
        runner.close()
    reopened = SimulatedTransferRunner(path, identity, SimulatedTransferDevice(context()))
    try:
        with pytest.raises(SimulationBlocked):
            run(reopened)
        assert not reopened.device.calls
    finally:
        reopened.close()


def test_restart_during_collection_does_not_auto_close(tmp_path):
    path, identity, _, _ = setup(tmp_path, "column")
    code = """
import os, sys
from pathlib import Path
from app.hardware.simulated_p1_runner import SimulatedTransferDevice, SimulatedTransferRunner
from tests.test_command_planning import context
client = SimulatedTransferDevice(context())
client.during_wait = lambda _: os._exit(24)
runner = SimulatedTransferRunner(Path(sys.argv[1]), sys.argv[2], client)
runner.run("test-phase-1", run_id="run-1", run_event_sequence=12)
"""
    assert subprocess.run([sys.executable, "-c", code, str(path), identity]).returncode == 24
    before = path.read_bytes()
    runner = SimulatedTransferRunner(path, identity, SimulatedTransferDevice(context()))
    try:
        with pytest.raises(SimulationBlocked):
            run(runner)
        assert not runner.device.calls
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT state FROM simulation_waits").fetchall() == [
                ("INTENT_PERSISTED",)
            ]
    finally:
        runner.close()
    assert before == path.read_bytes()


@pytest.mark.parametrize("target", ["wait", "close"])
@pytest.mark.parametrize("stage", ["intent", "result"])
def test_collection_persistence_failures_never_complete_or_resume(tmp_path, target, stage):
    path, identity, plan, device = setup(tmp_path, "column")
    index, operation = collecting(plan)
    close_id = operation.required_followup[0].operation_command_id
    if target == "close":
        table = "arduino_command_journal"
        condition = f"NEW.operation_command_id=CAST(X'{close_id.encode().hex()}' AS TEXT)"
    else:
        table = "simulation_waits"
        condition = f"NEW.operation_number={operation.operation_number}"
    event = "INSERT" if stage == "intent" else "UPDATE"
    if stage == "result":
        condition += " AND NEW.state='COMPLETED'"
    with sqlite3.connect(path) as db:
        db.execute(
            f"CREATE TRIGGER injected_failure BEFORE {event} ON {table} WHEN {condition} BEGIN SELECT RAISE(ABORT, 'injected collection write failure'); END"
        )
    runner = SimulatedTransferRunner(path, identity, device)
    try:
        with pytest.raises(sqlite3.Error):
            run(runner)
        assert runner.status(plan.phase_execution_id) == ("OUTCOME_UNKNOWN", index)
        assert not any(v["command"] == "CAROUSEL_MOVE_TO_POSITION" for v in device.calls)
        close_sends = [v for v in device.calls if v["operation_command_id"] == close_id]
        assert len(close_sends) == (0 if target == "close" and stage == "intent" else 1)
    finally:
        runner.close()
    reopened = SimulatedTransferRunner(path, identity, SimulatedTransferDevice(context()))
    try:
        with pytest.raises(SimulationBlocked):
            run(reopened)
        assert not reopened.device.calls
    finally:
        reopened.close()


def test_reboot_during_wait_invalidates_carousel_projection(tmp_path):
    path, identity, _, device = setup(tmp_path, "column")
    device.during_wait = lambda _: setattr(device, "controller_boot_id", 999)
    runner = SimulatedTransferRunner(path, identity, device)
    try:
        with pytest.raises(ArduinoUnavailableError):
            run(runner)
        assert device.carousel_position is None
        with sqlite3.connect(path) as db:
            assert db.execute("SELECT position FROM simulation_carousel_projection").fetchone() == (
                None,
            )
        assert runner.status("test-phase-1")[0] == "OUTCOME_UNKNOWN"
    finally:
        runner.close()


@pytest.mark.parametrize("table", ["simulation_waits", "simulation_carousel_projection"])
def test_orphan_collection_evidence_blocks_first_send(tmp_path, table):
    path, identity, _, device = setup(tmp_path, "column")
    with sqlite3.connect(path) as db:
        if table == "simulation_waits":
            db.execute(
                "INSERT INTO simulation_waits VALUES ('test-phase-1', 2, '2.5', 'INTENT_PERSISTED')"
            )
        else:
            db.execute("INSERT INTO simulation_carousel_projection VALUES ('test-phase-1', NULL)")
    runner = SimulatedTransferRunner(path, identity, device)
    try:
        with pytest.raises(SimulationBlocked):
            run(runner)
        assert not device.calls
    finally:
        runner.close()
