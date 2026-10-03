from datetime import UTC, datetime
from concurrent.futures import ThreadPoolExecutor
import sqlite3
from threading import Event, get_ident
from time import monotonic, sleep
from uuid import uuid4

import pytest

from app.demo.calibration_models import PumpCalibrationSet
from app.demo.maintenance_plan import MaintenanceKind
from app.demo.machine_models import MachineState
from app.hardware.owned_application_execution import OwnedApplicationExecution
from app.hardware.arduino_serial import ArduinoUnavailableError
from app.hardware.owned_startup_inspection import inspect_owned_startup
from app.hardware.simulated_p1_runner import SimulatedP1Device, SimulationBlocked
from app.main import create_app
from app.startup_bootstrap import ProcessStartupDisposition
from tests.test_api import ApiClient
from tests.test_command_planning import context
from tests.test_execution_coordinator import CONFIGURATION
from tests.test_owned_maintenance import plan, readiness, interrupt
from tests.test_owned_offline_runtime import bundle as bundle
from tests.test_owned_pausable_demo import Clock
from tests.test_owned_phase_session import READINESS
from tests.test_owned_timed_execution import TIMED_SETTINGS
from tests.test_prepared_adapter_execution import adapters as adapters

NOW = datetime.now(UTC)
COMMAND = {"occurred_at": NOW.isoformat()}
PREFIX = "/api/v1"


def payload(run_id="run-api"):
    return dict(
        run_id=run_id, configuration=CONFIGURATION.model_dump(mode="json"),
        execution_settings=TIMED_SETTINGS.model_dump(mode="json"), **COMMAND,
    )


@pytest.fixture
def assembly(bundle):
    devices = []
    clock = Clock()

    def factory():
        device = SimulatedP1Device(context())
        device.sf_mixer_running = False
        devices.append(device)
        return device

    ctx = context()
    execution = OwnedApplicationExecution(
        bundle, factory, PumpCalibrationSet(p1=ctx.pumps[0].calibration, p2=ctx.pumps[1].calibration),
        timer_factory=clock.timer, column_readiness=READINESS,
        recovery_plan=plan(MaintenanceKind.RECOVERY), flush_plan=plan(MaintenanceKind.FLUSH),
    )
    app = create_app(application_execution=execution)
    return app, execution, devices, clock


def wait_idle(client):
    deadline = monotonic() + 10
    while monotonic() < deadline:
        response = client.get(PREFIX + "/execution")
        assert response.status_code == 200, response.text
        if not response.json()["busy"]:
            return response.json()
        sleep(0.01)
    pytest.fail("owned application execution did not reach an idle boundary")


def start(client, run_id="run-api"):
    created = client.post(PREFIX + "/runs", json=payload(run_id))
    assert created.status_code == 200, created.text
    response = client.post(PREFIX + f"/runs/{run_id}/start", json=COMMAND)
    assert response.status_code == 202, response.text
    return response.json()


def pump_request():
    return dict(phase_execution_id="service", operation_command_id=str(uuid4()),
                pump="P1", command="HOME", safe_route_confirmed=True)


def test_http_complete_run_then_new_run_reuses_existing_executor(assembly, bundle):
    app, _, devices, _ = assembly
    with ApiClient(app, lifespan="on") as client:
        assert client.get(PREFIX + "/execution").json()["automatic_resume_allowed"] is False
        assert devices[0].calls == devices[0].sf_calls == []
        accepted = start(client)
        assert accepted["action"] == "RUN"
        status = wait_idle(client)
        assert status["error"] is None and status["retained_owner_id"] is None
        assert client.get(PREFIX + "/runs/run-api").json()["status"] == "COMPLETED"
        assert client.get(PREFIX + "/machine").json()["state"] == "READY"
        start(client, "run-next")
        assert wait_idle(client)["error"] is None
        assert client.get(PREFIX + "/runs/run-next").json()["status"] == "COMPLETED"
    report = inspect_owned_startup(bundle)
    assert len(report.prepared_phase_ids) == 20 and report.ownership_generation == 20
    assert report.owner_id is None


def maintenance(client, kind, run_id=None):
    response = client.post(PREFIX + f"/machine/{kind.lower()}/start", json=dict(
        run_id=run_id, readiness=readiness().model_dump(), **COMMAND,
    ))
    assert response.status_code == 202, response.text
    assert response.json()["run_id"] == run_id
    return response.json()


def replacement(bundle, devices):
    def factory():
        device = SimulatedP1Device(context())
        device.sf_mixer_running = False
        devices.append(device)
        return device
    execution = OwnedApplicationExecution(
        bundle, factory, plan(MaintenanceKind.RECOVERY).calibrations,
        timer_factory=Clock().timer, column_readiness=READINESS,
        recovery_plan=plan(MaintenanceKind.RECOVERY), flush_plan=plan(MaintenanceKind.FLUSH),
    )
    return create_app(application_execution=execution)


def test_initial_flush_needs_no_invented_run_and_allows_first_real_run(assembly, bundle):
    app, _, devices, _ = assembly
    with ApiClient(app, lifespan="on") as client:
        response = client.post(PREFIX + "/machine/initialize", json=COMMAND)
        assert response.status_code == 200 and response.json()["state"] == "READY"
        assert devices[0].calls == devices[0].sf_calls == []
        assert client.post(PREFIX + "/machine/initialize", json=COMMAND).status_code == 409
        maintenance(client, "FLUSH")
        assert wait_idle(client)["error"] is None
        report = inspect_owned_startup(bundle)
        assert report.runs == () and report.owner_id is None
        assert report.machine.state is MachineState.READY
        assert report.machine.interrupted_maintenance_id is None
        assert not any(call["command"].endswith("HOME") for call in devices[0].calls)
        start(client)
        assert wait_idle(client)["error"] is None


@pytest.mark.parametrize("initialized", [False, True])
def test_service_failure_without_run_reconciles_then_recovers_flushes(assembly, bundle, initialized):
    app, _, devices, _ = assembly
    with ApiClient(app, lifespan="on") as client:
        if initialized:
            assert client.post(PREFIX + "/machine/initialize", json=COMMAND).status_code == 200

        def fail(_):
            raise ArduinoUnavailableError("fake Service transport ambiguity")
        devices[0].before_send = fail
        response = client.post(PREFIX + "/service/pumps/command", json=pump_request())
        assert response.status_code == 503
        assert client.get(PREFIX + "/execution").json()["retained_owner_id"]
        assert client.post(PREFIX + "/runs", json=payload()).status_code == 409
    evidence = bundle.execution_path.read_bytes()
    app = replacement(bundle, devices)
    with ApiClient(app, lifespan="on") as client:
        assert app.state.process_startup.disposition is ProcessStartupDisposition.OWNERSHIP_RECONCILED
        assert devices[-1].calls == devices[-1].sf_calls == []
        assert bundle.execution_path.read_bytes() == evidence
        machine = client.get(PREFIX + "/machine").json()
        assert machine["state"] == "RECOVERING" and machine["interrupted_maintenance_id"]
        assert client.get(PREFIX + "/execution").json()["run_id"] is None
        maintenance(client, "RECOVERY")
        status = wait_idle(client)
        assert status["error"] is None and status["retained_owner_id"]
        assert inspect_owned_startup(bundle).runs == ()
        assert client.post(PREFIX + "/runs", json=payload()).status_code == 409
        maintenance(client, "FLUSH")
        status = wait_idle(client)
        assert status["error"] is None and status["retained_owner_id"] is None
        assert inspect_owned_startup(bundle).runs == ()
        start(client)
        assert wait_idle(client)["error"] is None


def test_machine_only_maintenance_stop_and_restart_never_replays_commands(assembly, bundle):
    app, _, devices, _ = assembly
    entered, release = Event(), Event()
    with ApiClient(app, lifespan="on") as client:
        assert client.post(PREFIX + "/machine/initialize", json=COMMAND).status_code == 200

        def block(_):
            if not entered.is_set():
                entered.set()
                assert release.wait(10)
        devices[0].before_send = block
        try:
            accepted = maintenance(client, "FLUSH")
            assert entered.wait(5)
            assert client.post(PREFIX + "/execution/foreign/stop", json=COMMAND).status_code == 409
            stopped = client.post(PREFIX + f"/execution/{accepted['operation_id']}/stop", json=COMMAND)
            assert stopped.status_code == 200 and stopped.json() == accepted
        finally:
            release.set()
        status = wait_idle(client)
        assert status["error"] and status["retained_owner_id"]
        machine = inspect_owned_startup(bundle).machine
        assert machine.active_maintenance.run_id is None
        assert machine.interrupted_maintenance_id == machine.active_maintenance.execution_id
    evidence = bundle.execution_path.read_bytes()
    app = replacement(bundle, devices)
    with ApiClient(app, lifespan="on") as client:
        assert app.state.process_startup.disposition is ProcessStartupDisposition.MAINTENANCE_RECONCILED
        assert bundle.execution_path.read_bytes() == evidence
        assert devices[-1].calls == devices[-1].sf_calls == []
        maintenance(client, "FLUSH")
        assert wait_idle(client)["error"]
        assert bundle.execution_path.read_bytes() == evidence
        maintenance(client, "RECOVERY")
        assert wait_idle(client)["error"] is None
        maintenance(client, "FLUSH")
        assert wait_idle(client)["error"] is None
        assert inspect_owned_startup(bundle).runs == ()


def test_successful_service_before_first_run_requires_new_independent_fixture(assembly, bundle):
    app, _, devices, _ = assembly
    with ApiClient(app, lifespan="on") as client:
        response = client.post(PREFIX + "/service/pumps/command", json=pump_request())
        assert response.status_code == 200
        assert client.post(PREFIX + "/machine/initialize", json=COMMAND).status_code == 409
    app = replacement(bundle, devices)
    with ApiClient(app, lifespan="on") as client:
        assert devices[-1].calls == []
        assert client.post(PREFIX + "/machine/initialize", json=COMMAND).status_code == 200
        start(client)
        assert wait_idle(client)["error"] is None


@pytest.mark.parametrize("startup_pending", [False, True])
def test_explicit_start_after_configuration_or_initialization_interruption(assembly, bundle, startup_pending, monkeypatch):
    from app.demo.application_service import GuidedDemoApplicationService

    app, _, devices, _ = assembly
    with ApiClient(app, lifespan="on") as client:
        if startup_pending:
            def fail(*args):
                raise sqlite3.OperationalError("initial completion write failed")
            with monkeypatch.context() as patch:
                patch.setattr(GuidedDemoApplicationService, "complete_startup", fail)
                assert client.post(PREFIX + "/machine/initialize", json=COMMAND).status_code == 500
            assert client.get(PREFIX + "/machine").json()["state"] == "STARTING"
        assert client.post(PREFIX + "/runs", json=payload()).status_code == (409 if startup_pending else 200)
        assert devices[0].calls == []
    app = replacement(bundle, devices)
    with ApiClient(app, lifespan="on") as client:
        assert devices[-1].calls == []
        if startup_pending:
            assert client.post(PREFIX + "/machine/initialize", json=COMMAND).status_code == 200
            assert client.post(PREFIX + "/runs", json=payload()).status_code == 200
        assert client.post(PREFIX + "/runs/run-api/start", json=COMMAND).status_code == 202
        assert wait_idle(client)["error"] is None


def test_worker_is_thread_confined_and_service_uses_same_durable_journal(assembly, bundle):
    app, execution, devices, _ = assembly
    with ApiClient(app, lifespan="on") as client:
        assert execution._runtime._thread != get_ident()
        with pytest.raises(SimulationBlocked, match="thread"):
            execution._runtime.execute_next()
        request = pump_request()
        response = client.post(PREFIX + "/service/pumps/command", json=request)
        assert response.status_code == 200, response.text
        assert response.json()["state"] == "COMPLETED"
        with sqlite3.connect(bundle.execution_path) as db:
            assert db.execute("SELECT operation_command_id FROM arduino_command_journal").fetchall() == [
                (request["operation_command_id"],)
            ]
        assert len(devices[0].calls) == 1
        assert client.post(PREFIX + "/service/sf-bottom-valve", json={"state": "CLOSED"}).status_code == 200
        with sqlite3.connect(bundle.execution_path) as db:
            assert db.execute("SELECT state FROM sf_action_journal").fetchall() == [("COMPLETED",)]


@pytest.mark.parametrize("route", [
    "/machine/startup/complete", "/machine/flush/complete",
    "/runs/run-api/phases/current/complete", "/runs/run-api/stop/confirm",
])
def test_manual_lifecycle_confirmations_cannot_bypass_executor(assembly, route):
    app, _, devices, _ = assembly
    with ApiClient(app, lifespan="on") as client:
        assert client.post(PREFIX + route, json=COMMAND).status_code == 409
        assert devices[0].calls == devices[0].sf_calls == []


def test_stop_during_command_excludes_services_and_requires_flush(assembly):
    app, _, devices, _ = assembly
    entered, release = Event(), Event()
    with ApiClient(app, lifespan="on") as client:
        def block(_):
            if not entered.is_set():
                entered.set()
                assert release.wait(10)
        devices[0].before_send = block
        try:
            start(client)
            assert entered.wait(5)
            for route, body in (
                ("/service/pumps/command", pump_request()),
                ("/service/sf-bottom-valve", {"state": "CLOSED"}),
                ("/runs", payload("other")),
                ("/machine/recovery/start", dict(run_id="run-api", readiness=readiness().model_dump(), **COMMAND)),
            ):
                response = client.post(PREFIX + route, json=body)
                assert response.status_code == 409, response.text
            assert client.post(PREFIX + "/runs/run-api/stop/request", json=COMMAND).status_code == 200
            assert client.post(PREFIX + "/runs/foreign/stop/request", json=COMMAND).status_code == 409
        finally:
            release.set()
        status = wait_idle(client)
        assert status["error"] is None and status["retained_owner_id"]
        assert client.get(PREFIX + "/runs/run-api").json()["status"] == "ABORTED"
        assert client.get(PREFIX + "/machine").json()["state"] == "FLUSH_REQUIRED"
        assert client.post(PREFIX + "/runs", json=payload("forbidden")).status_code == 409
        response = client.post(PREFIX + "/machine/flush/start", json=dict(readiness=readiness().model_dump(), **COMMAND))
        assert response.status_code == 202, response.text
        assert wait_idle(client)["error"] is None
        assert client.get(PREFIX + "/machine").json()["state"] == "READY"
        start(client, "after-flush")
        assert wait_idle(client)["error"] is None


def test_pause_resume_http_retains_owner_and_stop_while_paused_is_orderly(assembly):
    app, _, _, clock = assembly
    entered, release = Event(), Event()

    def hook():
        if not entered.is_set():
            entered.set()
            assert release.wait(10)

    clock.hook = hook
    with ApiClient(app, lifespan="on") as client:
        try:
            start(client)
            assert entered.wait(5)
            response = client.post(PREFIX + "/runs/run-api/pause", json=COMMAND)
            assert response.status_code == 200, response.text
            assert response.json()["run"]["status"] == "PAUSED"
            intent = response.json()["machine"]["active_execution"]
            assert client.post(PREFIX + "/service/pumps/command", json=pump_request()).status_code == 409
            response = client.post(PREFIX + "/runs/run-api/resume", json=COMMAND)
            assert response.status_code == 200 and response.json()["machine"]["active_execution"] == intent
            assert client.post(PREFIX + "/runs/run-api/pause", json=COMMAND).status_code == 200
            assert client.post(PREFIX + "/runs/run-api/stop/request", json=COMMAND).status_code == 200
        finally:
            release.set()
        assert wait_idle(client)["error"] is None
        assert client.get(PREFIX + "/runs/run-api").json()["status"] == "ABORTED"


def test_restart_reconciles_before_any_transport_and_explicit_recovery_flush(assembly, bundle):
    interrupt(bundle)
    before = bundle.execution_path.read_bytes()
    app, _, devices, _ = assembly
    with ApiClient(app, lifespan="on") as client:
        assert app.state.process_startup.disposition is ProcessStartupDisposition.ACTIVE_RUN_RECONCILED
        assert client.get(PREFIX + "/runs/run-1").json()["status"] == "FAULTED"
        assert client.get(PREFIX + "/machine").json()["state"] == "RECOVERING"
        assert devices[0].calls == devices[0].sf_calls == []
        assert bundle.execution_path.read_bytes() == before
        assert client.post(PREFIX + "/service/pumps/command", json=pump_request()).status_code == 409
        for action in ("recovery", "flush"):
            response = client.post(PREFIX + f"/machine/{action}/start", json=dict(
                run_id="run-1", readiness=readiness().model_dump(), **COMMAND,
            ))
            assert response.status_code == 202, response.text
            assert wait_idle(client)["error"] is None
        assert client.get(PREFIX + "/machine").json()["state"] == "READY"
        assert client.get(PREFIX + "/runs/run-1").json()["status"] == "FAULTED"
        start(client)
        assert wait_idle(client)["error"] is None


def test_failure_is_visible_and_restart_does_not_replay(assembly, bundle):
    app, _, devices, _ = assembly
    with ApiClient(app, lifespan="on") as client:
        def fail(_):
            raise SimulationBlocked("injected transport loss")
        devices[0].before_send = fail
        start(client)
        status = wait_idle(client)
        assert "transport loss" in status["error"]
        assert status["retained_owner_id"]
        assert client.post(PREFIX + "/machine/flush/complete", json=COMMAND).status_code == 409
    evidence = bundle.execution_path.read_bytes()
    replacement = OwnedApplicationExecution(
        bundle, lambda: SimulatedP1Device(context()),
        plan(MaintenanceKind.RECOVERY).calibrations, timer_factory=Clock().timer,
    )
    with ApiClient(create_app(application_execution=replacement), lifespan="on") as client:
        assert client.get(PREFIX + "/runs/run-api").json()["status"] == "FAULTED"
        assert client.get(PREFIX + "/execution").json()["retained_owner_id"]
        assert bundle.execution_path.read_bytes() == evidence


def test_composition_rejects_mixed_hardware_or_wrong_database(assembly, tmp_path):
    _, execution, _, _ = assembly
    with pytest.raises(ValueError, match="mixed"):
        create_app(application_execution=execution, arduino_commands=object())
    with pytest.raises(ValueError, match="differs"):
        create_app(tmp_path / "other.db", application_execution=execution)


def test_default_application_does_not_enable_owned_executor(tmp_path):
    with ApiClient(create_app(tmp_path / "default.db"), lifespan="on") as client:
        assert client.get(PREFIX + "/execution").status_code == 503
        assert client.post(PREFIX + "/machine/recovery/start", json=COMMAND).status_code == 503


def test_busy_close_requests_orderly_stop_and_releases_only_process_locks(assembly, bundle):
    app, _, devices, _ = assembly
    entered, release = Event(), Event()
    with ApiClient(app, lifespan="on") as client:
        def block(_):
            if not entered.is_set():
                entered.set()
                assert release.wait(10)
        devices[0].before_send = block
        start(client)
        assert entered.wait(5)
        # Explicit Stop and teardown both obey the same atomic boundary.
        assert client.post(PREFIX + "/runs/run-api/stop/request", json=COMMAND).status_code == 200
        release.set()
    report = inspect_owned_startup(bundle)
    assert report.owner_id and report.machine.state is MachineState.FLUSH_REQUIRED


def test_early_stop_before_worker_binds_run_is_not_lost(assembly, monkeypatch):
    app, execution, devices, _ = assembly
    entered, release = Event(), Event()
    with ApiClient(app, lifespan="on") as client:
        original = execution._runtime.start_created_run

        def hold(*args, **kwargs):
            entered.set()
            assert release.wait(10)
            return original(*args, **kwargs)

        monkeypatch.setattr(execution._runtime, "start_created_run", hold)
        try:
            start(client)
            assert entered.wait(5)
            response = client.post(PREFIX + "/runs/run-api/stop/request", json=COMMAND)
            assert response.status_code == 200, response.text
        finally:
            release.set()
        assert wait_idle(client)["error"] is None
        assert client.get(PREFIX + "/runs/run-api").json()["status"] == "ABORTED"
        assert devices[0].calls == devices[0].sf_calls == []


def test_http_stop_between_phases_sends_no_next_command(assembly, monkeypatch):
    app, execution, devices, _ = assembly
    entered, release = Event(), Event()
    with ApiClient(app, lifespan="on") as client:
        original = execution._runtime.execute_next

        def hold():
            result = original()
            if not entered.is_set():
                entered.set()
                assert release.wait(10)
            return result

        monkeypatch.setattr(execution._runtime, "execute_next", hold)
        try:
            start(client)
            assert entered.wait(5)
            before = len(devices[0].calls), len(devices[0].sf_calls)
            assert client.post(PREFIX + "/runs/run-api/stop/request", json=COMMAND).status_code == 200
        finally:
            release.set()
        assert wait_idle(client)["error"] is None
        assert (len(devices[0].calls), len(devices[0].sf_calls)) == before
        assert client.get(PREFIX + "/machine").json()["state"] == "FLUSH_REQUIRED"


def test_ready_flush_keeps_completed_run_terminal_and_uses_same_owner(assembly):
    app, _, devices, _ = assembly
    with ApiClient(app, lifespan="on") as client:
        start(client)
        assert wait_idle(client)["error"] is None
        before = len(devices[0].calls)
        response = client.post(PREFIX + "/machine/flush/start", json=dict(
            readiness=readiness().model_dump(), **COMMAND,
        ))
        assert response.status_code == 202, response.text
        status = wait_idle(client)
        assert status["error"] is None and status["retained_owner_id"] is None
        assert client.get(PREFIX + "/machine").json()["state"] == "READY"
        assert client.get(PREFIX + "/runs/run-api").json()["status"] == "COMPLETED"
        assert not any(call["command"] == "PUMP_HOME" for call in devices[0].calls[before:])
        start(client, "after-manual-flush")
        assert wait_idle(client)["error"] is None


def test_service_between_runs_cannot_turn_stale_context_into_permission(assembly):
    app, _, devices, _ = assembly
    with ApiClient(app, lifespan="on") as client:
        start(client)
        assert wait_idle(client)["error"] is None
        assert client.post(PREFIX + "/service/sf-bottom-valve", json={"state": "CLOSED"}).status_code == 200
        before = len(devices[0].calls), len(devices[0].sf_calls)
        start(client, "stale-input")
        assert wait_idle(client)["error"]
        assert (len(devices[0].calls), len(devices[0].sf_calls)) == before


def test_parallel_http_reads_and_controls_use_separate_snapshot_handles(assembly):
    app, _, _, clock = assembly
    entered, release = Event(), Event()

    def hold():
        if not entered.is_set():
            entered.set()
            assert release.wait(10)
    clock.hook = hold
    with ApiClient(app, lifespan="on") as client:
        try:
            start(client)
            assert entered.wait(5)
            paths = [PREFIX + "/machine", PREFIX + "/runs/run-api", PREFIX + "/execution"] * 8
            with ThreadPoolExecutor(max_workers=8) as pool:
                responses = list(pool.map(client.get, paths))
            assert all(response.status_code == 200 for response in responses)
            assert client.post(PREFIX + "/runs/run-api/stop/request", json=COMMAND).status_code == 200
        finally:
            release.set()
        assert wait_idle(client)["error"] is None


def test_stopped_maintenance_restart_is_reconciled_without_resend(assembly, bundle):
    interrupt(bundle)
    app, _, devices, _ = assembly
    entered, release = Event(), Event()
    with ApiClient(app, lifespan="on") as client:
        def hold(_):
            if not entered.is_set():
                entered.set()
                assert release.wait(10)
        devices[0].before_send = hold
        try:
            response = client.post(PREFIX + "/machine/recovery/start", json=dict(
                run_id="run-1", readiness=readiness().model_dump(), **COMMAND,
            ))
            assert response.status_code == 202
            assert entered.wait(5)
            assert client.post(PREFIX + "/runs/run-1/stop/request", json=COMMAND).status_code == 200
        finally:
            release.set()
        assert wait_idle(client)["error"]
        assert client.get(PREFIX + "/machine").json()["active_maintenance"]
    evidence = bundle.execution_path.read_bytes()
    replacement = OwnedApplicationExecution(
        bundle, lambda: SimulatedP1Device(context()),
        plan(MaintenanceKind.RECOVERY).calibrations, timer_factory=Clock().timer,
    )
    app = create_app(application_execution=replacement)
    with ApiClient(app, lifespan="on") as client:
        assert app.state.process_startup.disposition is ProcessStartupDisposition.MAINTENANCE_RECONCILED
        machine = client.get(PREFIX + "/machine").json()
        assert machine["state"] == "RECOVERING" and machine["active_maintenance"] is None
        assert client.get(PREFIX + "/execution").json()["run_id"] == "run-1"
        assert bundle.execution_path.read_bytes() == evidence


def test_http_adapters_keep_intent_before_bytes_through_complete_run(bundle, adapters):
    from app.hardware.prepared_adapter_device import PreparedAdapterDevice

    client_adapter, sf, port, sessions = adapters
    devices = []

    def factory():
        device = PreparedAdapterDevice(context(), client_adapter, sf)
        device.sf_mixer_running = False
        devices.append(device)
        return device

    execution = OwnedApplicationExecution(
        bundle, factory, plan(MaintenanceKind.RECOVERY).calibrations,
        timer_factory=Clock().timer, column_readiness=READINESS,
    )
    checked = []

    def before(message):
        entry = execution._runtime._runner._journal.load(message["operation_command_id"])
        assert entry.state.value == "INTENT_PERSISTED"
        with execution.store() as store:
            assert store.load_machine_snapshot().active_execution is not None
        checked.append(message["operation_command_id"])

    port.before_command = before
    with ApiClient(create_app(application_execution=execution), lifespan="on") as client:
        start(client)
        assert wait_idle(client)["error"] is None
        assert client.get(PREFIX + "/runs/run-api").json()["status"] == "COMPLETED"
        events = client.get(PREFIX + "/runs/run-api/events").json()
        assert events[0]["event_type"] == "RUN_CREATED"
        assert events[-1]["run_status"] == "COMPLETED"
        machine_events = client.get(PREFIX + "/machine/events").json()
        assert machine_events[-1]["machine_state"] == "READY"
    assert len(checked) == len(devices[0].calls)
    assert sessions and all(session.closed for session in sessions)


@pytest.mark.parametrize("bad", [None, {"operator": "test"}, {**readiness().model_dump(), "reactor_mixer_stopped": False}])
def test_maintenance_requires_complete_per_attempt_readiness(assembly, bad):
    app, _, devices, _ = assembly
    with ApiClient(app, lifespan="on") as client:
        response = client.post(PREFIX + "/machine/recovery/start", json=dict(
            run_id="run-api", readiness=bad, **COMMAND,
        ))
        assert response.status_code == 422
        assert devices[0].calls == devices[0].sf_calls == []


def test_second_application_cannot_open_owned_bundle(assembly, bundle):
    app, _, _, _ = assembly
    other = OwnedApplicationExecution(
        bundle, lambda: SimulatedP1Device(context()),
        plan(MaintenanceKind.RECOVERY).calibrations, timer_factory=Clock().timer,
    )
    with ApiClient(app, lifespan="on"):
        with pytest.raises(SimulationBlocked, match="active runtime"):
            other.start(NOW)
    replacement = OwnedApplicationExecution(
        bundle, lambda: SimulatedP1Device(context()),
        plan(MaintenanceKind.RECOVERY).calibrations, timer_factory=Clock().timer,
    )
    replacement.start(NOW)
    replacement.close(NOW)


def test_stop_write_failure_finishes_atomic_route_then_blocks_aspiration(assembly, monkeypatch):
    from app.demo.application_service import GuidedDemoApplicationService

    app, _, devices, _ = assembly
    entered, release = Event(), Event()
    with ApiClient(app, lifespan="on") as client:
        def hold(_):
            if not entered.is_set():
                entered.set()
                assert release.wait(10)
        devices[0].before_send = hold
        try:
            start(client)
            assert entered.wait(5)

            def fail(*args, **kwargs):
                raise sqlite3.OperationalError("Stop disk write failed")

            monkeypatch.setattr(GuidedDemoApplicationService, "request_stop_demo", fail)
            response = client.post(PREFIX + "/runs/run-api/stop/request", json=COMMAND)
            assert response.status_code == 500
        finally:
            release.set()
        status = wait_idle(client)
        assert "Stop persistence failed" in status["error"]
        assert status["retained_owner_id"]
        assert len(devices[0].calls) == 2
        assert all(call["command"] == "VALVE_SET_POSITION" for call in devices[0].calls)


def test_close_while_active_sets_stop_without_waiting_behind_execution(assembly):
    from threading import Thread

    _, execution, devices, _ = assembly
    execution.start(NOW)
    execution.create_run("run-api", CONFIGURATION, TIMED_SETTINGS, NOW)
    entered, release = Event(), Event()

    def hold(_):
        if not entered.is_set():
            entered.set()
            assert release.wait(10)
    devices[0].before_send = hold
    execution.start_run("run-api", NOW)
    assert entered.wait(5)
    failures = []

    def close():
        try:
            execution.close(NOW)
        except Exception as error:
            failures.append(error)
    closer = Thread(target=close)
    closer.start()
    try:
        deadline = monotonic() + 5
        while monotonic() < deadline:
            with sqlite3.connect(execution.bundle.lifecycle_path) as db:
                if db.execute("SELECT status FROM demo_runs WHERE run_id='run-api'").fetchone() == ("ABORTING",):
                    break
            sleep(0.01)
        else:
            pytest.fail("shutdown did not persist Stop before waiting for execution")
    finally:
        release.set()
        closer.join(10)
    assert not closer.is_alive() and failures == []
    report = inspect_owned_startup(execution.bundle)
    assert report.owner_id and report.machine.state is MachineState.FLUSH_REQUIRED
