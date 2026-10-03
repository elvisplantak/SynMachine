from dataclasses import replace
from datetime import UTC, datetime
import json
import uuid

import pytest

from app.hardware.arduino_serial import ArduinoProtocolError
from app.hardware.recovery_reference_checks import ReferenceItem
from app.hardware.simulated_p1_runner import SimulationBlocked
from tests.test_owned_offline_runtime import bundle as bundle, open_runtime, start
from tests.test_fresh_hardware_observations import devices as devices, REQUIRED
from tests.test_arduino_serial import frame, hello_ok


@pytest.fixture
def recovery(bundle):
    with open_runtime(bundle) as original:
        start(original)
    with open_runtime(bundle) as runtime:
        runtime.reconcile_interruption(datetime.now(UTC))
        yield runtime


def begin(runtime, devices):
    return runtime.begin_reference_checks(devices[0], devices[1], required_commands=REQUIRED)


def confirm(checks, item=ReferenceItem.P1, challenge=None):
    return checks.confirm(
        checks.challenge if challenge is None else challenge, item,
        operator="Test operator", evidence_note="Explicit independent test-fixture attestation",
    )


def test_complete_attestations_never_release_owner_or_rewrite_evidence(recovery, devices, bundle):
    paths = (bundle.ownership_path, bundle.execution_path, bundle.lifecycle_path)
    before = tuple(path.read_bytes() for path in paths)
    checks = begin(recovery, devices)
    assert checks.report(checks.challenge).missing == tuple(ReferenceItem)
    for item in ReferenceItem:
        report = confirm(checks, item)
    assert report.missing == ()
    assert len(report.confirmations) == len(ReferenceItem)
    assert report.may_release_owner is False
    assert report.challenge.interrupted_run_id == "run-1"
    assert report.challenge.retained_owner_id.startswith("reconciliation-")
    assert all(entry.operator == "Test operator" for entry in report.confirmations)
    assert tuple(path.read_bytes() for path in paths) == before
    assert devices[3].writes == []
    assert all(json.loads(frame)["type"] in {"HELLO", "QUERY_STATUS"} for frame in devices[2].writes)
    assert recovery._runner.device.calls == recovery._runner.device.sf_calls == []
    with pytest.raises(SimulationBlocked):
        recovery.execute_next()


def test_each_confirmation_and_report_queries_again(recovery, devices):
    checks = begin(recovery, devices)
    assert devices[2].query_count == 2
    report = confirm(checks)
    assert devices[2].query_count == 4
    assert ReferenceItem.P1 not in report.missing
    checks.report(checks.challenge)
    assert devices[2].query_count == 6


def test_new_check_round_invalidates_old_confirmations(recovery, devices):
    old = begin(recovery, devices)
    confirm(old)
    fresh = begin(recovery, devices)
    assert fresh.report(fresh.challenge).missing == tuple(ReferenceItem)
    assert fresh.challenge.check_id != old.challenge.check_id
    with pytest.raises(SimulationBlocked, match="stale"):
        old.report(old.challenge)


def test_copied_challenge_is_not_current_process_capability(recovery, devices):
    checks = begin(recovery, devices)
    with pytest.raises(SimulationBlocked, match="foreign"):
        confirm(checks, challenge=replace(checks.challenge))
    with pytest.raises(SimulationBlocked, match="stale"):
        checks.report(checks.challenge)


def test_restart_cannot_reuse_reference_checks(bundle, devices):
    with open_runtime(bundle) as original:
        start(original)
    with open_runtime(bundle) as previous:
        previous.reconcile_interruption(datetime.now(UTC))
        old = begin(previous, devices)
        confirm(old)
    with open_runtime(bundle) as restarted:
        fresh = begin(restarted, devices)
        assert fresh.report(fresh.challenge).missing == tuple(ReferenceItem)
        with pytest.raises(SimulationBlocked, match="closed"):
            old.report(old.challenge)
        with pytest.raises(SimulationBlocked, match="foreign"):
            confirm(fresh, challenge=old.challenge)


def test_reconnect_invalidates_even_with_same_nonce_and_boot(recovery, devices):
    client, _, port, _ = devices
    checks = begin(recovery, devices)
    confirm(checks)
    port.incoming.extend(hello_ok(capabilities=list(REQUIRED)))
    client.connect()
    with pytest.raises(SimulationBlocked, match="session changed"):
        checks.report(checks.challenge)
    assert checks._confirmations == {}
    with pytest.raises(SimulationBlocked, match="stale"):
        confirm(checks)


@pytest.mark.parametrize("changed", ["owner", "journal"])
def test_database_context_change_invalidates_checks(recovery, devices, changed):
    checks = begin(recovery, devices)
    confirm(checks)
    if changed == "owner":
        recovery._owner._db.execute("UPDATE hardware_sequences SET state='ACTIVE'")
    else:
        recovery._runner._db.execute(
            "INSERT INTO sf_action_journal VALUES ('new','phase','session','OPEN','INTENT_PERSISTED',NULL)"
        )
    before_queries = devices[2].query_count
    with pytest.raises(SimulationBlocked, match="database context changed"):
        checks.report(checks.challenge)
    assert checks._confirmations == {}
    assert devices[2].query_count == before_queries


def test_database_change_during_sample_is_rejected(recovery, devices, monkeypatch):
    checks = begin(recovery, devices)
    original = devices[3].close

    def close():
        original()
        recovery._owner._db.execute("UPDATE hardware_sequences SET state='ACTIVE'")

    monkeypatch.setattr(devices[3], "close", close)
    with pytest.raises(SimulationBlocked, match="during observation"):
        confirm(checks)


@pytest.mark.parametrize("position", [3697, 3000])
def test_open_or_unknown_sf_is_not_accepted(recovery, devices, position):
    checks = begin(recovery, devices)
    confirm(checks)
    devices[3].positions = iter([position])
    with pytest.raises(SimulationBlocked, match="closed SF"):
        checks.report(checks.challenge)
    assert not checks._confirmations
    assert devices[3].writes == []


def test_incomplete_observation_invalidates_prior_attestations(recovery, devices):
    checks = begin(recovery, devices)
    confirm(checks)
    devices[2].status_changes["controller_state"] = "BUSY"
    with pytest.raises(ArduinoProtocolError):
        checks.report(checks.challenge)
    devices[2].status_changes.clear()
    with pytest.raises(SimulationBlocked, match="stale"):
        checks.report(checks.challenge)


@pytest.mark.parametrize("operator,note", [("", "proof"), ("op", " "), (True, "proof")])
def test_confirmation_requires_operator_and_explanation(recovery, devices, operator, note):
    checks = begin(recovery, devices)
    with pytest.raises(ValueError):
        checks.confirm(checks.challenge, ReferenceItem.P1, operator=operator, evidence_note=note)
    assert checks.report(checks.challenge).missing == tuple(ReferenceItem)


def test_duplicate_confirmation_cannot_replace_prior_evidence(recovery, devices):
    checks = begin(recovery, devices)
    confirm(checks)
    with pytest.raises(SimulationBlocked, match="already confirmed"):
        confirm(checks)
    assert not checks._confirmations


def test_unreconciled_runtime_cannot_start_reference_checks(bundle, devices):
    with open_runtime(bundle) as original:
        start(original)
    with open_runtime(bundle) as runtime:
        with pytest.raises(SimulationBlocked, match="reconciled interruption"):
            begin(runtime, devices)
        assert devices[2].query_count == 0


def test_live_runtime_cannot_collect_recovery_confirmations(bundle, devices):
    with open_runtime(bundle) as runtime:
        start(runtime)
        with pytest.raises(SimulationBlocked):
            begin(runtime, devices)
        assert devices[2].query_count == 0


def test_busy_runtime_gate_prevents_observation(recovery, devices):
    with recovery._gate:
        with pytest.raises(SimulationBlocked, match="already active"):
            begin(recovery, devices)
    assert devices[2].query_count == 0


@pytest.mark.parametrize("observation", ["initial", "confirmation"])
@pytest.mark.parametrize("bracket", [0, 1])
def test_repeated_request_id_invalidates_reference_checks(recovery, devices, observation, bracket):
    checks = begin(recovery, devices)
    confirm(checks)
    queries = [json.loads(value) for value in devices[2].writes[1:]]
    assert checks._requests == {query["request_id"] for query in queries}
    index = bracket + (2 if observation == "confirmation" else 0)
    requests = iter([uuid.UUID(queries[index]["request_id"]), uuid.uuid4()])
    devices[0]._request_id_factory = lambda: next(requests)
    with pytest.raises(SimulationBlocked, match="new status request"):
        checks.report(checks.challenge)
    assert checks._confirmations == {}
    with pytest.raises(SimulationBlocked, match="stale"):
        confirm(checks)
    assert devices[3].writes == []
    assert all(json.loads(value)["type"] in {"HELLO", "QUERY_STATUS"} for value in devices[2].writes)
    assert recovery._runner.device.calls == recovery._runner.device.sf_calls == []


def test_equal_bracketing_ids_clear_confirmations_permanently(recovery, devices):
    checks = begin(recovery, devices)
    confirm(checks)
    request_id = uuid.uuid4()
    devices[0]._request_id_factory = lambda: request_id
    with pytest.raises(ArduinoProtocolError, match="distinct status request IDs"):
        checks.report(checks.challenge)
    assert checks._confirmations == {}
    with pytest.raises(SimulationBlocked, match="stale"):
        confirm(checks)
    assert devices[3].writes == []
    assert all(json.loads(value)["type"] in {"HELLO", "QUERY_STATUS"} for value in devices[2].writes)
    assert recovery._runner.device.calls == recovery._runner.device.sf_calls == []


@pytest.mark.parametrize("stream", ["receive", "pending"])
def test_stale_status_with_reused_before_id_cannot_pass_round(recovery, devices, monkeypatch, stream):
    from app.protocol.models import Status

    client, _, port, session = devices
    checks = begin(recovery, devices)
    confirm(checks)
    previous = json.loads(port.writes[1])
    stale = dict(
        type="STATUS", backend_session_nonce=previous["backend_session_nonce"],
        controller_boot_id=previous["controller_boot_id"], request_id=previous["request_id"],
        controller_state="IDLE", software_state_trust="TRUSTED",
        active_operation_command_id=None,
    )
    if stream == "receive":
        port.incoming.extend(frame(**stale))
    else:
        client._pending_messages.append(Status(protocol="LABFORGE/1", **stale))
    requests = iter([uuid.UUID(previous["request_id"]), uuid.uuid4()])
    client._request_id_factory = lambda: next(requests)
    original_write = port.write

    def write(data):
        # No fresh reply to the reused before query: only the queued stale
        # reply can satisfy normal correlation. The after query replies normally.
        if json.loads(data)["request_id"] == previous["request_id"]:
            port.writes.append(data)
            return len(data)
        return original_write(data)

    monkeypatch.setattr(port, "write", write)
    with pytest.raises(SimulationBlocked, match="new status request"):
        checks.report(checks.challenge)
    assert checks._confirmations == {}
    assert not port.incoming and not client._pending_messages
    with pytest.raises(SimulationBlocked, match="stale"):
        confirm(checks)
    assert session.writes == []
    assert all(json.loads(value)["type"] in {"HELLO", "QUERY_STATUS"} for value in port.writes)
    assert recovery._runner.device.calls == recovery._runner.device.sf_calls == []


def test_torque_on_invalidates_confirmations_without_changing_torque(recovery, devices):
    from app.hardware.sf_bottom_valve import REGISTERS
    checks = begin(recovery, devices)
    confirm(checks)
    devices[3].values[REGISTERS["torque_enable"]] = 1
    with pytest.raises(SimulationBlocked, match="torque off"):
        checks.report(checks.challenge)
    assert devices[3].writes == []
    assert not checks._confirmations


def test_runtime_close_is_blocked_during_reference_sampling(recovery, devices, monkeypatch):
    original = devices[3].close
    attempted = []

    def close():
        with pytest.raises(SimulationBlocked, match="during runtime operation"):
            recovery.close()
        attempted.append(True)
        original()

    monkeypatch.setattr(devices[3], "close", close)
    checks = begin(recovery, devices)
    confirm(checks)
    assert len(attempted) == 2


def test_challenge_cannot_be_reassigned(recovery, devices):
    checks = begin(recovery, devices)
    with pytest.raises(AttributeError):
        checks.challenge = replace(checks.challenge, retained_owner_id="another")
    assert checks.report(checks.challenge).challenge.retained_owner_id != "another"


def test_missing_single_valve_reference_remains_explicit(recovery, devices):
    checks = begin(recovery, devices)
    for item in ReferenceItem:
        if item is not ReferenceItem.V8:
            confirm(checks, item)
    report = checks.report(checks.challenge)
    assert report.missing == (ReferenceItem.V8,)
    assert report.may_release_owner is False


@pytest.mark.parametrize("external", [False, True])
def test_write_preserving_summary_still_invalidates_confirmations(recovery, devices, external):
    import sqlite3
    recovery._runner._db.execute(
        "INSERT INTO sf_action_journal VALUES ('old','phase','session','OPEN',"
        "'OUTCOME_UNKNOWN','initial error')"
    )
    checks = begin(recovery, devices)
    confirm(checks)
    sql = "UPDATE sf_action_journal SET error='changed error'"
    if external:
        with sqlite3.connect(recovery.bundle.execution_path) as connection:
            connection.execute(sql)
    else:
        recovery._runner._db.execute(sql)
    with pytest.raises(SimulationBlocked, match="database context changed"):
        checks.report(checks.challenge)
    assert checks._confirmations == {}
