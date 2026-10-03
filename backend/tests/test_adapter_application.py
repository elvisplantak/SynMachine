"""Explicit adapter startup/teardown using fake Serial and DYNAMIXEL only."""

from dataclasses import replace
import json
from threading import Event, Thread, get_ident
from time import monotonic, sleep

import pytest

from app.hardware.adapter_application import build_adapter_application_execution
from app.hardware.arduino_serial import ArduinoSerialConfiguration, ArduinoProtocolError
from app.hardware.owned_startup_inspection import StartupInspectionError, inspect_owned_startup
from app.hardware.simulated_p1_runner import SimulationBlocked
from app.demo.maintenance_plan import MaintenanceKind
from app.demo.run_models import RunStatus
from tests.test_execution_coordinator import CONFIGURATION
from tests.test_owned_timed_execution import TIMED_SETTINGS
from app.main import create_app
from tests.test_api import ApiClient
from tests.test_arduino_serial import Clock, FakePort, hello_ok
from tests.test_command_planning import context
from tests.test_owned_application_api import NOW, PREFIX, start, maintenance, wait_idle
from tests.test_owned_maintenance import plan, interrupt
from tests.test_owned_offline_runtime import bundle as bundle, open_runtime
from tests.test_owned_pausable_demo import Clock as WaitClock
from tests.test_owned_phase_session import READINESS
from tests.test_prepared_adapter_execution import CommandPort, FollowingSession, CAPABILITIES
from tests.test_sf_bottom_valve import configuration


class ConnectingPort(CommandPort):
    def __init__(self, *, trusted=True):
        super().__init__()
        self.incoming.clear()
        self.trusted = trusted
        self.threads = [get_ident()]

    def write(self, value):
        self.threads.append(get_ident())
        message = json.loads(value)
        if message["type"] == "HELLO":
            count = FakePort.write(self, value)
            self.incoming.extend(hello_ok(
                backend_session_nonce=message["backend_session_nonce"],
                controller_boot_id=58 if self.trusted else None,
                software_state_trust="TRUSTED" if self.trusted else "UNTRUSTED",
                controller_state="IDLE" if self.trusted else "IDENTITY_UNTRUSTED",
                capabilities=CAPABILITIES,
            ))
            return count
        return super().write(value)

    def close(self):
        self.threads.append(get_ident())
        super().close()


@pytest.fixture
def assembly(bundle):
    ports, sessions, provider_threads = [], [], []

    def port_factory(_):
        # This is the first transport access. All bundle locks must already hold.
        with pytest.raises(SimulationBlocked, match="active runtime"):
            open_runtime(bundle)
        port = ConnectingPort()
        ports.append(port)
        return port

    def sf_factory(_):
        session = FollowingSession()
        from app.hardware.sf_bottom_valve import REGISTERS
        session.values[REGISTERS["torque_enable"]] = 0
        sessions.append(session)
        return session

    def context_factory(boot):
        assert boot == 58
        provider_threads.append(get_ident())
        return context()

    def build(**changes):
        values = dict(
            context_factory=context_factory, sf_mixer_running=False,
            column_readiness=READINESS, recovery_plan=plan(MaintenanceKind.RECOVERY),
            flush_plan=plan(MaintenanceKind.FLUSH), timer_factory=WaitClock().timer,
            arduino_port_factory=port_factory, arduino_monotonic=Clock(), arduino_sleep=lambda _: None,
            sf_session_factory=sf_factory, sf_sleep=lambda _: None,
        )
        values.update(changes)
        return build_adapter_application_execution(
            bundle, ArduinoSerialConfiguration(port="/dev/fake-arduino", command_timeout_seconds=0.1),
            configuration(), plan(MaintenanceKind.RECOVERY).calibrations, **values,
        )
    return build, ports, sessions, provider_threads


def test_build_opens_nothing_and_startup_sends_only_handshake(assembly, bundle):
    build, ports, sessions, providers = assembly
    before = [path.read_bytes() for path in (bundle.ownership_path, bundle.execution_path, bundle.lifecycle_path)]
    execution = build()
    assert ports == sessions == providers == []
    assert before == [path.read_bytes() for path in (bundle.ownership_path, bundle.execution_path, bundle.lifecycle_path)]
    execution.start(NOW)
    worker = execution._runtime._thread
    try:
        assert worker != get_ident() and providers == [worker]
        assert [json.loads(data)["type"] for data in ports[0].writes] == ["HELLO"]
        assert sessions == []
        assert inspect_owned_startup(bundle).owner_id is None
    finally:
        execution.close(NOW)
    assert ports[0].closed and set(ports[0].threads) == {worker}
    assert [json.loads(data)["type"] for data in ports[0].writes] == ["HELLO"]


def test_constructed_adapters_execute_full_http_run_and_close_on_worker(assembly):
    build, ports, sessions, _ = assembly
    execution = build()
    with ApiClient(create_app(application_execution=execution), lifespan="on") as client:
        checked = []

        def check(message):
            entry = execution._runtime._runner._journal.load(message["operation_command_id"])
            assert entry.state.value == "INTENT_PERSISTED"
            checked.append(message["operation_command_id"])
        ports[0].before_command = check
        start(client)
        assert wait_idle(client)["error"] is None
        assert client.get(PREFIX + "/runs/run-api").json()["status"] == "COMPLETED"
        assert checked
        worker = execution._runtime._thread
    assert ports[0].closed and set(ports[0].threads) == {worker}
    assert sessions and all(session.closed for session in sessions)


def test_constructed_adapters_reconcile_without_replay_then_recover_flush_run(assembly, bundle):
    interrupt(bundle)
    evidence = bundle.execution_path.read_bytes()
    build, ports, sessions, _ = assembly
    execution = build()
    with ApiClient(create_app(application_execution=execution), lifespan="on") as client:
        assert bundle.execution_path.read_bytes() == evidence
        assert sessions == [] and len(ports[0].writes) == 1
        assert client.get(PREFIX + "/machine").json()["state"] == "RECOVERING"
        maintenance(client, "RECOVERY", "run-1")
        status = wait_idle(client)
        assert status["error"] is None and status["retained_owner_id"]
        maintenance(client, "FLUSH", "run-1")
        status = wait_idle(client)
        assert status["error"] is None and status["retained_owner_id"] is None
        start(client, "after-adapter-recovery")
        assert wait_idle(client)["error"] is None
    assert ports[0].closed and all(session.closed for session in sessions)


def test_duplicate_application_never_opens_second_transport(assembly):
    build, ports, _, _ = assembly
    first, second = build(), build()
    first.start(NOW)
    try:
        with pytest.raises(SimulationBlocked, match="active runtime"):
            second.start(NOW)
        assert len(ports) == 1
    finally:
        first.close(NOW)


@pytest.mark.parametrize("identity", ["ownership_id", "execution_id", "lifecycle_id"])
def test_invalid_bundle_identity_is_rejected_before_transport_factory(assembly, identity):
    build, ports, sessions, _ = assembly
    execution = build()
    execution.bundle = replace(execution.bundle, **{identity: "foreign"})
    with pytest.raises(StartupInspectionError):
        execution.start(NOW)
    assert ports == sessions == []


@pytest.mark.parametrize("failure", ["boot", "calibration", "provider", "type", "timer"])
def test_setup_failure_closes_connection_and_releases_runtime_locks(assembly, bundle, failure):
    build, ports, sessions, _ = assembly

    def provider(boot):
        if failure == "provider":
            raise RuntimeError("independent context unavailable")
        if failure == "type":
            return {}
        data = context().model_dump()
        if failure == "boot":
            data["controller_boot_id"] = boot + 1
        if failure == "calibration":
            data["pumps"][0]["calibration"]["working_volume_ml"] = "99"
        return type(context()).model_validate(data)
    changes = {"context_factory": provider}
    if failure == "timer":
        changes["timer_factory"] = lambda: object()
    execution = build(**changes)
    with pytest.raises((RuntimeError, TypeError)):
        execution.start(NOW)
    assert len(ports) == 1 and ports[0].closed and sessions == []
    assert [json.loads(data)["type"] for data in ports[0].writes] == ["HELLO"]
    assert inspect_owned_startup(bundle).owner_id is None
    with open_runtime(bundle):
        pass


def test_untrusted_handshake_never_requests_context_or_opens_sf(assembly):
    build, ports, sessions, providers = assembly

    def port_factory(_):
        port = ConnectingPort(trusted=False)
        ports.append(port)
        return port
    execution = build(arduino_port_factory=port_factory)
    with pytest.raises(ArduinoProtocolError, match="untrusted"):
        execution.start(NOW)
    assert ports[0].closed and providers == sessions == []


def test_shutdown_waits_for_orderly_stop_before_closing_adapter_resource(assembly, bundle):
    build, ports, _, _ = assembly
    execution = build()
    execution.start(NOW)
    execution.create_run("run-api", CONFIGURATION, TIMED_SETTINGS, NOW)
    entered, release, finished = Event(), Event(), Event()
    failures = []

    def block(_):
        if not entered.is_set():
            entered.set()
            assert release.wait(10)

    def close():
        try:
            execution.close(NOW)
        except Exception as error:
            failures.append(error)
        finally:
            finished.set()

    ports[0].before_command = block
    execution.start_run("run-api", NOW)
    assert entered.wait(5)
    closer = Thread(target=close)
    closer.start()
    try:
        deadline = monotonic() + 5
        while monotonic() < deadline:
            if inspect_owned_startup(bundle).runs[0].status is RunStatus.ABORTING:
                break
            sleep(0.01)
        else:
            pytest.fail("shutdown did not persist Stop before waiting")
        assert not ports[0].closed and not finished.is_set()
    finally:
        release.set()
        closer.join(10)
    assert finished.is_set() and not failures and ports[0].closed
    report = inspect_owned_startup(bundle)
    assert report.owner_id and report.runs[0].status is RunStatus.ABORTED
