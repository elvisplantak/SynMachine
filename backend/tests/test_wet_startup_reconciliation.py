"""Only the exact failed pre-liquid bootstrap can enter explicit reconciliation."""

import hashlib
import json
import sqlite3

import pytest

from app import wet_reactor_sf as wet
from app.hardware.arduino_serial import ArduinoCommandFailedError
from app.hardware.owned_offline_runtime import OwnedOfflineRuntime
from app.hardware.owned_startup_inspection import inspect_owned_startup
from tests.test_wet_reactor_sf import case as case, wire
from tests.test_owned_offline_runtime import bundle as bundle


@pytest.fixture
def reconciliation(case, tmp_path, monkeypatch):
    count = 0
    def failure(message):
        nonlocal count
        count += 1
        if count == 13:
            raise ArduinoCommandFailedError("PUMP_MOTION_TIMEOUT", True)
    case.port.before_command = failure
    with pytest.raises(ArduinoCommandFailedError):
        case.run()
    case.port.before_command = lambda _: None
    report = inspect_owned_startup(case.bundle)
    with sqlite3.connect(case.bundle.execution_path) as db:
        db.row_factory = sqlite3.Row
        proof = {"failure_command": "PUMP_HOME", "failure_pump": "P1",
                 "failure": "PUMP_MOTION_TIMEOUT", "ownership": {"owner_id": report.owner_id},
                 "arduino_command_journal": [dict(r) for r in db.execute(
                     "SELECT * FROM arduino_command_journal ORDER BY rowid")],
                 "sf_action_journal": [dict(r) for r in db.execute(
                     "SELECT * FROM sf_action_journal ORDER BY rowid")]}
    source = tmp_path / "failure.json"
    source.write_text(json.dumps(proof))
    monkeypatch.setattr(wet, "STARTUP_FAILURE_RECORD", source)
    path = tmp_path / "startup-reconciliation.json"
    path.write_text(json.dumps({"purpose": "RECONCILE_RECORDED_STARTUP_TIMEOUT",
        "retained_owner": report.owner_id, "plan_sha256": wet.plan_digest(),
        "failure_record_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "operator_approved": True, "retain_owner_until_separate_flush": True}))
    query = case.client.query_status
    monkeypatch.setattr(case.client, "query_status", lambda: query().model_copy(
        update={"p1_home_active": True}))
    return path


def resume(case, path):
    with OwnedOfflineRuntime(case.bundle, case.device, timer=case.clock.timer()) as runtime:
        wet.run(runtime, case.client, case.sf, case.events.append, case.stopping.is_set,
                startup_reconciliation=path)


def test_explicit_reconciliation_keeps_prior_failure_and_owner_until_separate_flush(case, reconciliation):
    report = inspect_owned_startup(case.bundle)
    resume(case, reconciliation)
    after = inspect_owned_startup(case.bundle)
    assert after.owner_id == report.owner_id and after.owner_state == "BLOCKED"
    assert after.ownership_generation == 1
    assert len(wire(case)) == 65
    assert case.events[-1]["event"] == "SEQUENCE_COMMANDS_COMPLETED"
    assert case.events[-1]["owner_retained_for_separate_flush"] is True
    with sqlite3.connect(case.bundle.execution_path) as db:
        assert db.execute("SELECT state,error_code FROM arduino_command_journal "
            "ORDER BY rowid LIMIT 1 OFFSET 12").fetchone() == ("FAILED", "PUMP_MOTION_TIMEOUT")
    count = len(wire(case))
    with pytest.raises(RuntimeError, match="changed"):
        resume(case, reconciliation)
    assert len(wire(case)) == count


@pytest.mark.parametrize("value", [False, None])
def test_inactive_or_unsupported_input_blocks_before_any_new_motion(case, reconciliation, value, monkeypatch):
    query = case.client.query_status
    monkeypatch.setattr(case.client, "query_status", lambda: query().model_copy(
        update={"p1_home_active": value}))
    with pytest.raises(RuntimeError, match="HOME input inactive"):
        resume(case, reconciliation)
    assert len(wire(case)) == 13
    assert inspect_owned_startup(case.bundle).owner_state == "BLOCKED"


def test_p1_home_rechecks_signal_immediately_before_command(case, reconciliation, monkeypatch):
    query = case.client.query_status
    def changed(event):
        case.events.append(event)
        if event["event"] == "ACTION_START" and event["command"] == "PUMP_HOME":
            monkeypatch.setattr(case.client, "query_status", lambda: query().model_copy(
                update={"p1_home_active": False}))
    with OwnedOfflineRuntime(case.bundle, case.device, timer=case.clock.timer()) as runtime:
        with pytest.raises(RuntimeError, match="no repeated search"):
            wet.run(runtime, case.client, case.sf, changed, case.stopping.is_set,
                    startup_reconciliation=reconciliation)
    assert not any(m["command"] == "PUMP_HOME" for m in wire(case)[13:])
    assert inspect_owned_startup(case.bundle).owner_state == "BLOCKED"


@pytest.mark.parametrize("field,value", [("operator_approved", False), ("operator_approved", 1), ("plan_sha256", "wrong"),
    ("failure_record_sha256", "wrong"), ("retained_owner", "other"),
    ("retain_owner_until_separate_flush", False)])
def test_changed_or_unapproved_plan_cannot_adopt_owner(case, reconciliation, field, value):
    data = json.loads(reconciliation.read_text())
    data[field] = value
    reconciliation.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match="persisted"):
        resume(case, reconciliation)
    assert len(wire(case)) == 13
    assert inspect_owned_startup(case.bundle).owner_state == "BLOCKED"


def test_changed_journal_blocks_before_device_factory(case, reconciliation):
    with sqlite3.connect(case.bundle.execution_path) as db:
        db.execute("UPDATE arduino_command_journal SET error_code='OTHER' WHERE state='FAILED'")
    configuration = wet.load_profile(wet.PROFILE)
    with pytest.raises(RuntimeError, match="changed"):
        with OwnedOfflineRuntime(case.bundle, timer=case.clock.timer(), device_factory=lambda:
             wet.connected_device(configuration, case.bundle, lambda _: None,
                                  startup_reconciliation=True)):
            pass
    assert len(wire(case)) == 13


def test_new_pump_failure_retains_original_owner_and_stops_again(case, reconciliation):
    case.port.before_command = lambda m: (_ for _ in ()).throw(
        ArduinoCommandFailedError("PUMP_HOME_SWITCH_STUCK", True)) if m["command"] == "PUMP_HOME" else None
    with pytest.raises(ArduinoCommandFailedError):
        resume(case, reconciliation)
    assert inspect_owned_startup(case.bundle).owner_state == "BLOCKED"
    assert not any(m["command"] == "PUMP_ASPIRATE_FULL_STROKE" for m in wire(case))
