"""Operator declarations on the existing owned path; fake transports only."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import sqlite3
from time import monotonic, sleep
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.hardware.adapter_configuration import CurrentContextRequest
from app.hardware.operator_current_input import (
    OperatorCredentialRejected, OperatorCurrentInput, OperatorReferenceInput,
)
from app.hardware.simulated_p1_runner import SimulationBlocked
from app.main import create_app
from tests.test_adapter_configuration import configured as configured, state
from tests.test_owned_offline_runtime import bundle as bundle
from tests.test_owned_maintenance import interrupt
from tests.test_owned_application_api import COMMAND, PREFIX, maintenance, start, wait_idle
from tests.test_api import ApiClient

CREDENTIAL = "fake-only-operator-credential-12345"
AUTH = {"Authorization": "Bearer " + CREDENTIAL}


def request(timeout=1.0):
    now = monotonic()
    return CurrentContextRequest(str(uuid4()), 58, "unit-test-nonce", 1, "RECOVERY", now, now + timeout)


def references(req, unknown=False):
    data = state(req, unknown=unknown).model_dump(exclude={"operator", "observed_at_monotonic"})
    return OperatorReferenceInput(**data, observed_now_confirmed=True)


def pending(source):
    deadline = monotonic() + 2
    while monotonic() < deadline:
        value = source.pending()
        if value is not None:
            return value
        sleep(0.002)
    pytest.fail("operator challenge did not become pending")


def challenge(client):
    deadline = monotonic() + 3
    while monotonic() < deadline:
        value = client.get(PREFIX + "/execution").json().get("current_input")
        if value is not None:
            return value
        sleep(0.002)
    pytest.fail("HTTP operator challenge did not become pending")


def declare(client, value, *, unknown=False, headers=AUTH):
    req = request()
    return client.post(PREFIX + "/execution/current-input/" + value["request_id"],
                       json=references(req, unknown).model_dump(mode="json"), headers=headers)


def source():
    return OperatorCurrentInput(operator="configured operator", credential=CREDENTIAL)


@pytest.mark.parametrize("problem", ["no-operator", "short-credential", "unicode-credential", "whitespace-credential", "no-clock"])
def test_source_requires_explicit_identity_and_credential(problem):
    values = dict(operator="configured operator", credential=CREDENTIAL)
    values.update({"operator": " "} if problem == "no-operator" else
                  {"credential": "short"} if problem == "short-credential" else
                  {"credential": "č" * 40} if problem == "unicode-credential" else
                  {"credential": CREDENTIAL + "\n"} if problem == "whitespace-credential" else {"clock": None})
    with pytest.raises((ValueError, TypeError)):
        OperatorCurrentInput(**values)


def test_source_attributes_identity_time_and_exact_request_without_cached_input():
    current = source()
    req = request()
    with ThreadPoolExecutor() as pool:
        future = pool.submit(current, req)
        visible = pending(current)
        assert CREDENTIAL not in visible.model_dump_json()
        assert visible.operator == "configured operator" and visible.request_id == req.request_id
        submitted_at = monotonic()
        current.submit(req.request_id, references(req, True), credential=CREDENTIAL)
        response = future.result(1)
    assert response.request is req
    assert response.state.operator == "configured operator"
    assert response.state.observed_at_monotonic >= submitted_at
    assert current.pending() is None
    with pytest.raises(SimulationBlocked):
        current.submit(req.request_id, references(req), credential=CREDENTIAL)


@pytest.mark.parametrize("problem", ["wrong-credential", "foreign-request", "second-consumer"])
def test_rejected_request_does_not_consume_valid_pending_challenge(problem):
    current = source()
    req = request()
    with ThreadPoolExecutor() as pool:
        future = pool.submit(current, req)
        pending(current)
        if problem == "second-consumer":
            with pytest.raises(SimulationBlocked):
                current(replace(req, request_id=str(uuid4())))
        else:
            with pytest.raises((OperatorCredentialRejected, SimulationBlocked)):
                current.submit(str(uuid4()) if problem == "foreign-request" else req.request_id,
                               references(req), credential="wrong" if problem == "wrong-credential" else CREDENTIAL)
        assert not future.done() and current.pending().request_id == req.request_id
        current.cancel(req.request_id, credential=CREDENTIAL)
        with pytest.raises(SimulationBlocked, match="cancelled"):
            future.result(1)


@pytest.mark.parametrize("problem", ["operator", "observed_at_monotonic", "false-observation", "duplicate-pump", "bad-column"])
def test_client_cannot_supply_identity_time_or_invalid_observation(problem):
    data = references(request()).model_dump()
    if problem == "false-observation":
        data["observed_now_confirmed"] = False
    elif problem == "duplicate-pump":
        data["pumps"] = (data["pumps"][0], data["pumps"][0])
    elif problem == "bad-column":
        data["column_position_degrees"] = 8
    else:
        data[problem] = "forged" if problem == "operator" else 10.0
    with pytest.raises(ValidationError):
        OperatorReferenceInput.model_validate(data)


def test_absent_confirmation_times_out_and_cannot_be_submitted_later():
    current = source()
    req = request(0.02)
    with pytest.raises(SimulationBlocked, match="timed out"):
        current(req)
    assert current.pending() is None
    with pytest.raises(SimulationBlocked):
        current.submit(req.request_id, references(req), credential=CREDENTIAL)


@pytest.mark.parametrize("closing", [False, True])
def test_stop_or_close_unblocks_wait_without_confirmation(closing):
    current = source()
    req = request(30)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(current, req)
        pending(current)
        current.close() if closing else current.cancel_pending()
        with pytest.raises(SimulationBlocked):
            future.result(1)
    assert current.pending() is None
    if closing:
        with pytest.raises(SimulationBlocked):
            current(request())


def test_late_submission_expires_challenge_without_relabelling_time():
    clock = [10.0]
    current = OperatorCurrentInput(operator="test operator", credential=CREDENTIAL, clock=lambda: clock[0])
    req = replace(request(), requested_at_monotonic=10.0, deadline_monotonic=15.0)
    with ThreadPoolExecutor() as pool:
        future = pool.submit(current, req)
        pending(current)
        clock[0] = 16.0
        with pytest.raises(SimulationBlocked, match="expired"):
            current.submit(req.request_id, references(req), credential=CREDENTIAL)
        with pytest.raises(SimulationBlocked):
            future.result(1)


@pytest.mark.parametrize("closing", [False, True])
def test_stop_or_close_invalidates_submitted_input_before_consumer_uses_it(closing):
    current = source()
    req = request()
    with ThreadPoolExecutor() as pool:
        future = pool.submit(current, req)
        pending(current)
        with current._lock:
            current.submit(req.request_id, references(req), credential=CREDENTIAL)
            current.close() if closing else current.cancel_pending()
        with pytest.raises(SimulationBlocked):
            future.result(1)


def test_http_initialization_start_credentials_and_one_use_confirmation(configured):
    build, ports, sessions, _, _, _ = configured
    current = source()
    execution = build(current_state_provider=current, context_clock=current.clock)
    with ApiClient(create_app(application_execution=execution), lifespan="on") as client, ThreadPoolExecutor() as pool:
        assert client.get(PREFIX + "/execution").json()["current_input"] is None
        initializing = pool.submit(client.post, PREFIX + "/machine/initialize", json=COMMAND)
        initial = challenge(client)
        assert sessions == [] and len(ports[0].writes) == 1
        assert declare(client, initial, headers={}).status_code == 401
        assert declare(client, initial, headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert not initializing.done()
        assert declare(client, initial).status_code == 200
        assert initializing.result(2).json()["state"] == "READY"
        assert declare(client, initial).status_code == 409
        start(client)
        running = challenge(client)
        assert running["request_id"] != initial["request_id"]
        assert len(ports[0].writes) == 1
        assert declare(client, initial).status_code == 409
        assert declare(client, running).status_code == 200
        assert wait_idle(client)["error"] is None
        assert client.get(PREFIX + "/runs/run-api").json()["status"] == "COMPLETED"
        with sqlite3.connect(execution.bundle.execution_path) as db:
            rows = db.execute("SELECT payload_json FROM prepared_command_plans").fetchall()
        assert rows
        for (payload,) in rows:
            receipt = json.loads(payload)["prepared"]["assumptions"]["current_input_attribution"]
            assert receipt["request_id"] == running["request_id"]
            assert receipt["operator"] == "configured operator"
            assert receipt["attribution_method"] == "OPERATOR_CREDENTIAL"
            assert CREDENTIAL not in payload
        start(client, "retained-command-continuity")
        assert wait_idle(client)["error"] is None
        assert current.pending() is None


def test_http_recovery_unknown_input_retains_owner_through_flush(configured, bundle):
    interrupt(bundle)
    build, ports, _, _, _, _ = configured
    current = source()
    execution = build(current_state_provider=current, context_clock=current.clock)
    evidence = bundle.execution_path.read_bytes()
    with ApiClient(create_app(application_execution=execution), lifespan="on") as client:
        assert bundle.execution_path.read_bytes() == evidence
        retained = client.get(PREFIX + "/execution").json()["retained_owner_id"]
        maintenance(client, "RECOVERY", "run-1")
        recovering = challenge(client)
        assert recovering["purpose"] == "RECOVERY" and len(ports[0].writes) == 1
        assert declare(client, recovering, unknown=True).status_code == 200
        assert wait_idle(client)["retained_owner_id"] == retained
        assert client.get(PREFIX + "/machine").json()["state"] == "FLUSH_REQUIRED"
        maintenance(client, "FLUSH", "run-1")
        assert wait_idle(client)["retained_owner_id"] is None
        start(client, "after-operator-recovery")
        assert wait_idle(client)["error"] is None


def test_stop_during_operator_wait_sends_no_commands_and_preserves_created_run(configured):
    build, ports, sessions, _, _, _ = configured
    current = source()
    execution = build(current_state_provider=current, context_clock=current.clock)
    with ApiClient(create_app(application_execution=execution), lifespan="on") as client:
        start(client)
        value = challenge(client)
        operation = client.get(PREFIX + "/execution").json()["operation"]
        assert client.post(PREFIX + "/execution/" + operation["operation_id"] + "/stop", json=COMMAND).status_code == 200
        assert "cancelled" in wait_idle(client)["error"]
        assert declare(client, value).status_code == 409
        assert client.get(PREFIX + "/runs/run-api").json()["status"] == "CREATED"
        assert sessions == [] and [json.loads(line)["type"] for line in ports[0].writes] == ["HELLO"]


def test_cancel_pending_initialization_returns_without_commands(configured):
    build, ports, _, _, _, _ = configured
    current = source()
    execution = build(current_state_provider=current, context_clock=current.clock)
    with ApiClient(create_app(application_execution=execution), lifespan="on") as client, ThreadPoolExecutor() as pool:
        initializing = pool.submit(client.post, PREFIX + "/machine/initialize", json=COMMAND)
        value = challenge(client)
        assert client.post(PREFIX + "/execution/current-input/" + value["request_id"] + "/cancel", headers=AUTH).status_code == 200
        assert initializing.result(2).status_code == 409
        assert len(ports[0].writes) == 1


def test_configured_source_refuses_a_different_clock_before_transport_access(configured):
    build, ports, sessions, _, _, _ = configured
    with pytest.raises(ValueError, match="share the monotonic clock"):
        build(current_state_provider=source())
    assert ports == sessions == []


def test_partial_run_input_blocks_motion_and_explicit_retry_uses_same_created_run(configured):
    build, ports, sessions, _, _, _ = configured
    current = source()
    execution = build(current_state_provider=current, context_clock=current.clock)
    with ApiClient(create_app(application_execution=execution), lifespan="on") as client:
        start(client)
        first = challenge(client)
        assert declare(client, first, unknown=True).status_code == 200
        assert "complete independently established" in wait_idle(client)["error"]
        assert client.get(PREFIX + "/runs/run-api").json()["status"] == "CREATED"
        assert sessions == [] and len(ports[0].writes) == 1
        assert client.post(PREFIX + "/runs/run-api/start", json=COMMAND).status_code == 202
        second = challenge(client)
        assert second["request_id"] != first["request_id"]
        assert declare(client, first).status_code == 409
        assert declare(client, second).status_code == 200
        # With no machine yet, READY and first Start are separate requests.
        starting = challenge(client)
        assert starting["request_id"] != second["request_id"]
        assert declare(client, starting).status_code == 200
        assert wait_idle(client)["error"] is None
        assert client.get(PREFIX + "/runs/run-api").json()["status"] == "COMPLETED"


def test_shutdown_unblocks_initialization_wait_without_actuation(configured):
    build, ports, sessions, _, _, _ = configured
    current = source()
    execution = build(current_state_provider=current, context_clock=current.clock)
    with ApiClient(create_app(application_execution=execution), lifespan="on") as client, ThreadPoolExecutor() as pool:
        initializing = pool.submit(client.post, PREFIX + "/machine/initialize", json=COMMAND)
        value = challenge(client)
        closing = pool.submit(execution.close, COMMAND["occurred_at"])
        assert initializing.result(2).status_code == 409
        closing.result(2)
    assert current.pending() is None and ports[0].closed and sessions == []
    with pytest.raises(SimulationBlocked):
        current.submit(value["request_id"], references(request()), credential=CREDENTIAL)


def test_restart_rejects_old_request_and_credential_preserves_owner_then_requires_flush(configured, bundle):
    interrupt(bundle)
    build, ports, _, _, _, _ = configured
    first_source = source()
    first_execution = build(current_state_provider=first_source, context_clock=first_source.clock)
    before = bundle.execution_path.read_bytes()
    with ApiClient(create_app(application_execution=first_execution), lifespan="on") as client:
        maintenance(client, "RECOVERY", "run-1")
        old = challenge(client)
        retained = client.get(PREFIX + "/execution").json()["retained_owner_id"]
    assert bundle.execution_path.read_bytes() == before
    second_source = OperatorCurrentInput(operator="configured operator", credential=CREDENTIAL + "-rotated")
    second_execution = build(current_state_provider=second_source, context_clock=second_source.clock)
    new_auth = {"Authorization": "Bearer " + CREDENTIAL + "-rotated"}
    with ApiClient(create_app(application_execution=second_execution), lifespan="on") as client:
        assert client.get(PREFIX + "/execution").json()["current_input"] is None
        assert client.get(PREFIX + "/execution").json()["retained_owner_id"] == retained
        maintenance(client, "RECOVERY", "run-1")
        fresh = challenge(client)
        assert fresh["request_id"] != old["request_id"]
        assert declare(client, old, unknown=True, headers=new_auth).status_code == 409
        assert declare(client, fresh, unknown=True).status_code == 401
        assert bundle.execution_path.read_bytes() == before
        assert len(ports[1].writes) == 1
        assert declare(client, fresh, unknown=True, headers=new_auth).status_code == 200
        assert wait_idle(client)["retained_owner_id"] == retained
        assert client.get(PREFIX + "/machine").json()["state"] == "FLUSH_REQUIRED"
        maintenance(client, "FLUSH", "run-1")
        assert wait_idle(client)["retained_owner_id"] is None
        start(client, "new-run-after-restart-confirmations")
        assert wait_idle(client)["error"] is None
