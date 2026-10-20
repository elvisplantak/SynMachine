"""Configuration/current input on real adapters with fake transports only."""

from dataclasses import asdict, replace
import json
from threading import get_ident

import pytest
from pydantic import ValidationError

from app.demo.maintenance_plan import MaintenanceKind
from app.demo.operation_models import PumpId
from app.hardware.adapter_configuration import (
    AdapterExecutionConfiguration, CurrentContextResponse, CurrentDeviceState,
    build_configured_adapter_application_execution,
)
from app.hardware.arduino_serial import ArduinoSerialConfiguration
from app.hardware.command_planning import CommandPlanningContext, prepare_command_plan
from app.hardware.owned_startup_inspection import inspect_owned_startup
from app.hardware.simulated_p1_runner import SimulationBlocked
from app.main import create_app
from tests.test_adapter_application import ConnectingPort
from tests.test_api import ApiClient
from tests.test_arduino_serial import Clock
from tests.test_command_planning import context
from tests.test_owned_application_api import COMMAND, NOW, PREFIX, maintenance, start, wait_idle
from tests.test_owned_maintenance import interrupt, plan
from tests.test_owned_offline_runtime import bundle as bundle
from tests.test_owned_pausable_demo import Clock as WaitClock
from tests.test_prepared_adapter_execution import FollowingSession
from tests.test_sf_bottom_valve import configuration as sf_configuration


def profile():
    return AdapterExecutionConfiguration(
        profile_id="hypothetical-unit-test", evidence_note="fake-only fixture, no physical approval",
        calibration_scope="DEMO_NOMINAL",
        current_context_timeout_seconds=5.0,
        arduino=asdict(ArduinoSerialConfiguration(port="/dev/fake-arduino", command_timeout_seconds=0.1)),
        sf=asdict(sf_configuration()), calibrations=plan(MaintenanceKind.RECOVERY).calibrations,
        route_sequences=context().route_sequences,
        recovery_plan=plan(MaintenanceKind.RECOVERY), flush_plan=plan(MaintenanceKind.FLUSH),
    )


def state(request, *, unknown=False, **changes):
    ctx = context()
    values = dict(
        operator="test operator", evidence_note="new independent fake input for this request",
        observed_at_monotonic=request.requested_at_monotonic,
        pumps=tuple(dict(pump_id=pump.calibration.pump_id,
                         position_steps=None if unknown else pump.position_steps) for pump in ctx.pumps),
        valve_positions=() if unknown else ctx.valve_positions,
        reactor_mixer_running=False, sf_mixer_running=None if unknown else False,
        sf_bottom_valve=None if unknown else ctx.sf_bottom_valve,
        column_position_degrees=None if unknown else ctx.column_position_degrees,
        carousel_position=40,
    )
    values.update(changes)
    return CurrentDeviceState(**values)


@pytest.fixture
def configured(bundle):
    ports, sessions, requests = [], [], []
    current = [None]
    clock = [10.0]

    def port_factory(_):
        port = ConnectingPort()
        ports.append(port)
        return port

    def sf_factory(_):
        from app.hardware.sf_bottom_valve import REGISTERS
        session = FollowingSession()
        session.values[REGISTERS["torque_enable"]] = 0
        sessions.append(session)
        return session

    def provider(request):
        requests.append((request, get_ident()))
        if current[0] is not None:
            return current[0](request)
        return CurrentContextResponse(request, state(request, unknown=request.purpose == "RECOVERY"))

    def build(**changes):
        values = dict(
            current_state_provider=provider, arduino_port_factory=port_factory,
            sf_session_factory=sf_factory, context_clock=lambda: clock[0],
            timer_factory=WaitClock().timer, arduino_monotonic=Clock(), arduino_sleep=lambda _: None,
            sf_sleep=lambda _: None,
        )
        values.update(changes)
        return build_configured_adapter_application_execution(bundle, profile(), **values)

    return build, ports, sessions, requests, current, clock


def test_configuration_roundtrip_contains_settings_not_current_references():
    value = profile()
    assert AdapterExecutionConfiguration.model_validate_json(value.model_dump_json()) == value
    for forbidden in ("controller_boot_id", "position_steps", "sf_mixer_running", "backend_session_nonce"):
        assert f'"{forbidden}":' not in value.model_dump_json()


@pytest.mark.parametrize("problem", [
    "missing-port", "missing-timing", "same-port", "blank-port", "boolean-baud", "nan-timeout",
    "missing-route", "duplicate-route", "calibration-mismatch", "wrong-kind", "travel-boundary",
    "current-reference", "nested-extra", "missing-calibration-scope", "missing-current-timeout",
])
def test_invalid_or_incomplete_configuration_rejected_before_resources(problem):
    data = profile().model_dump()
    if problem == "missing-port":
        del data["arduino"]["port"]
    elif problem == "missing-timing":
        del data["sf"]["motion_timeout_seconds"]
    elif problem == "same-port":
        data["sf"]["port"] = data["arduino"]["port"]
    elif problem == "blank-port":
        data["sf"]["port"] = " "
    elif problem == "boolean-baud":
        data["arduino"]["baud_rate"] = True
    elif problem == "nan-timeout":
        data["arduino"]["command_timeout_seconds"] = float("nan")
    elif problem == "missing-route":
        data["route_sequences"] = data["route_sequences"][:-1]
    elif problem == "duplicate-route":
        data["route_sequences"] += (data["route_sequences"][0],)
    elif problem == "calibration-mismatch":
        data["flush_plan"]["calibrations"]["p1"]["working_volume_ml"] = "99"
    elif problem == "wrong-kind":
        data["recovery_plan"] = data["flush_plan"]
    elif problem == "travel-boundary":
        for field in (data["calibrations"], data["recovery_plan"]["calibrations"],
                      data["flush_plan"]["calibrations"]):
            field["p1"]["working_empty_chamber_position_steps"] = 20501
    elif problem == "current-reference":
        data["current_positions"] = {"P1": 4100}
    elif problem == "nested-extra":
        data["calibrations"]["p1"]["current_boot_id"] = 58
    elif problem == "missing-current-timeout":
        del data["current_context_timeout_seconds"]
    else:
        del data["calibration_scope"]
    with pytest.raises(ValidationError):
        AdapterExecutionConfiguration.model_validate(data)


def test_construction_and_restart_startup_do_not_request_state_or_send_commands(configured, bundle):
    build, ports, sessions, requests, _, _ = configured
    execution = build()
    assert ports == sessions == requests == []
    execution.start(NOW)
    try:
        assert len(ports) == 1 and sessions == requests == []
        assert [json.loads(value)["type"] for value in ports[0].writes] == ["HELLO"]
        current = execution._runtime._runner.device.current
        assert all(pump.position_steps is None for pump in current.pumps)
        assert current.valve_positions == () and current.carousel_position is None
        assert inspect_owned_startup(bundle).machine is None
    finally:
        execution.close(NOW)


def test_full_http_run_then_second_run_keeps_owned_continuity_without_provider_replay(configured):
    build, ports, _, requests, current, _ = configured
    execution = build()
    with ApiClient(create_app(application_execution=execution), lifespan="on") as client:
        assert client.post(PREFIX + "/machine/initialize", json=COMMAND).status_code == 200
        assert len(requests) == 1
        start(client)
        assert wait_idle(client)["error"] is None
        assert client.get(PREFIX + "/runs/run-api").json()["status"] == "COMPLETED"
        assert len(requests) == 2  # initialization and first start, not each phase
        assert requests[0][0].request_id != requests[1][0].request_id
        assert all(thread == execution._runtime._thread for _, thread in requests)
        current[0] = lambda _: pytest.fail("completed same-session state must not be replaced")
        start(client, "second-run")
        assert wait_idle(client)["error"] is None
        assert client.get(PREFIX + "/runs/second-run").json()["status"] == "COMPLETED"
    assert ports[0].closed


@pytest.mark.parametrize("problem", [
    "unavailable", "foreign-response", "cached-time", "future-time", "unknown-pump", "nonempty-pump",
    "missing-valve", "unknown-carousel", "unknown-column", "unknown-reactor", "unknown-sf-mixer",
    "open-sf", "changed-session", "regressing-clock", "late-provider",
])
def test_new_run_blocks_without_complete_fresh_current_input(configured, problem):
    build, ports, sessions, requests, current, clock = configured
    execution = build()

    def fail(request):
        changes = {}
        if problem == "unavailable":
            raise SimulationBlocked("independent current input unavailable")
        if problem == "foreign-response":
            return CurrentContextResponse(replace(request), state(request))
        if problem == "cached-time":
            changes["observed_at_monotonic"] = 9.0
        elif problem == "future-time":
            changes["observed_at_monotonic"] = 11.0
        elif problem in ("unknown-pump", "nonempty-pump"):
            changes["pumps"] = (dict(pump_id="P1", position_steps=None if problem == "unknown-pump" else 4000),
                                dict(pump_id="P2", position_steps=4100))
        elif problem == "missing-valve":
            changes["valve_positions"] = context().valve_positions[:-1]
        elif problem == "unknown-carousel":
            changes["carousel_position"] = None
        elif problem == "unknown-column":
            changes["column_position_degrees"] = None
        elif problem == "unknown-reactor":
            changes["reactor_mixer_running"] = None
        elif problem == "unknown-sf-mixer":
            changes["sf_mixer_running"] = None
        elif problem == "open-sf":
            changes["sf_bottom_valve"] = "OPEN"
        elif problem == "changed-session":
            ports[0].close()
            execution._runtime._runner.device._arduino.close()
        elif problem == "regressing-clock":
            clock[0] = 9.0
        elif problem == "late-provider":
            clock[0] = request.deadline_monotonic + 1.0
        return CurrentContextResponse(request, state(request, **changes))

    current[0] = fail
    with ApiClient(create_app(application_execution=execution), lifespan="on") as client:
        start(client)
        assert wait_idle(client)["error"]
        assert client.get(PREFIX + "/runs/run-api").json()["status"] == "CREATED"
        assert sessions == []
        assert [json.loads(value)["type"] for value in ports[0].writes] == ["HELLO"]
        device = execution._runtime._runner.device
        assert all(pump.position_steps is None for pump in device.current.pumps)
        assert device.sf_mixer_running is None


def test_old_response_cannot_be_reused_after_successful_initialization(configured):
    build, ports, _, _, current, _ = configured
    cached = []

    def callback(request):
        if cached:
            return cached[0]
        cached.append(CurrentContextResponse(request, state(request)))
        return cached[0]

    current[0] = callback
    with ApiClient(create_app(application_execution=build()), lifespan="on") as client:
        assert client.post(PREFIX + "/machine/initialize", json=COMMAND).status_code == 200
        start(client)
        assert "stale or foreign" in wait_idle(client)["error"]
        assert [json.loads(value)["type"] for value in ports[0].writes] == ["HELLO"]


def test_unknown_restart_state_recovers_then_flushes_and_permits_new_run(configured, bundle):
    interrupt(bundle)
    build, ports, _, requests, _, _ = configured
    old_evidence = bundle.execution_path.read_bytes()
    execution = build()
    with ApiClient(create_app(application_execution=execution), lifespan="on") as client:
        assert bundle.execution_path.read_bytes() == old_evidence
        assert requests == [] and len(ports[0].writes) == 1
        retained = client.get(PREFIX + "/execution").json()["retained_owner_id"]
        maintenance(client, "RECOVERY", "run-1")
        status = wait_idle(client)
        assert status["error"] is None and status["retained_owner_id"] == retained
        assert client.get(PREFIX + "/machine").json()["state"] == "FLUSH_REQUIRED"
        assert len(requests) == 1 and requests[0][0].purpose == "RECOVERY"
        current = execution._runtime._maintenance._state
        assert all(pump.position_steps == 4100 for pump in current.pumps)
        maintenance(client, "FLUSH", "run-1")
        status = wait_idle(client)
        assert status["error"] is None and status["retained_owner_id"] is None
        start(client, "after-current-recovery")
        assert wait_idle(client)["error"] is None
        assert len(requests) == 1  # recovery/flush established continuity; no reset/relabel
        assert client.get(PREFIX + "/runs/after-current-recovery").json()["status"] == "COMPLETED"


@pytest.mark.parametrize("problem", ["missing-alignment", "different-alignment", "reactor-running", "provider-failure"])
def test_recovery_missing_current_input_retains_owner_and_sends_nothing(configured, bundle, problem):
    interrupt(bundle)
    build, ports, sessions, _, current, _ = configured

    def fail(request):
        if problem == "provider-failure":
            raise SimulationBlocked("fresh recovery input unavailable")
        changes = ({"carousel_position": None} if problem == "missing-alignment" else
                   {"carousel_position": 1} if problem == "different-alignment" else
                   {"reactor_mixer_running": True})
        return CurrentContextResponse(request, state(request, unknown=True, **changes))

    current[0] = fail
    with ApiClient(create_app(application_execution=build()), lifespan="on") as client:
        retained = client.get(PREFIX + "/execution").json()["retained_owner_id"]
        maintenance(client, "RECOVERY", "run-1")
        status = wait_idle(client)
        assert status["error"] and status["retained_owner_id"] == retained
        assert sessions == [] and len(ports[0].writes) == 1


def test_unknown_pump_state_is_allowed_for_recovery_but_never_flush_or_transfer():
    from app.demo.p1_solvent_operation_plan import plan_p1_solvent_to_reactor_operations
    from app.demo.fluid_plan import build_fluid_plan
    from tests.test_execution_coordinator import CONFIGURATION

    ctx = context()
    data = ctx.model_dump()
    for pump in data["pumps"]:
        pump["position_steps"] = None
    unknown = CommandPlanningContext.model_validate(data)
    recovery = prepare_command_plan(plan(MaintenanceKind.RECOVERY).operations, unknown)
    assert recovery.projected_pump_positions == ((PumpId.P1, 4100), (PumpId.P2, 4100))
    with pytest.raises(ValueError, match="pump references"):
        prepare_command_plan(plan(MaintenanceKind.FLUSH).operations, unknown)
    transfer = plan_p1_solvent_to_reactor_operations(build_fluid_plan(CONFIGURATION), profile().calibrations)
    with pytest.raises(ValueError, match="unknown"):
        prepare_command_plan(transfer.operations, unknown)


def test_missing_controller_capability_blocks_startup_before_current_input(configured):
    from tests.test_arduino_serial import FakePort, hello_ok
    from tests.test_prepared_adapter_execution import CAPABILITIES

    build, ports, sessions, requests, _, _ = configured

    class MissingCapabilityPort(ConnectingPort):
        def write(self, value):
            message = json.loads(value)
            if message["type"] != "HELLO":
                return super().write(value)
            count = FakePort.write(self, value)
            self.incoming.extend(hello_ok(
                backend_session_nonce=message["backend_session_nonce"], controller_boot_id=58,
                capabilities=[command for command in CAPABILITIES if command != "PUMP_HOME"],
            ))
            return count

    def factory(_):
        port = MissingCapabilityPort()
        ports.append(port)
        return port

    with pytest.raises(SimulationBlocked, match="capabilities"):
        build(arduino_port_factory=factory).start(NOW)
    assert sessions == requests == [] and ports[0].closed
    assert len(ports[0].writes) == 1


def test_configured_transport_fault_restart_rejects_old_input_then_recovers(configured, bundle):
    from app.hardware.arduino_serial import ArduinoUnavailableError

    build, ports, _, requests, current, _ = configured
    responses = []

    def capture(request):
        response = CurrentContextResponse(request, state(request))
        responses.append(response)
        return response

    current[0] = capture
    with ApiClient(create_app(application_execution=build()), lifespan="on") as client:
        count = [0]

        def inject(_):
            count[0] += 1
            if count[0] == 3:
                raise ArduinoUnavailableError("fake transport fault")

        ports[0].before_command = inject
        start(client)
        status = wait_idle(client)
        retained = status["retained_owner_id"]
        assert status["error"] and retained
    evidence = bundle.execution_path.read_bytes()
    previous_requests = len(requests)
    current[0] = lambda _: responses[-1]
    execution = build()
    with ApiClient(create_app(application_execution=execution), lifespan="on") as client:
        assert bundle.execution_path.read_bytes() == evidence
        assert len(requests) == previous_requests
        assert len(ports[1].writes) == 1
        assert client.get(PREFIX + "/machine").json()["state"] == "RECOVERY_REQUIRED"
        maintenance(client, "RECOVERY", "run-api")
        status = wait_idle(client)
        assert "stale or foreign" in status["error"]
        assert status["retained_owner_id"] == retained and len(ports[1].writes) == 1
        current[0] = None
        maintenance(client, "RECOVERY", "run-api")
        status = wait_idle(client)
        assert status["error"] is None and status["retained_owner_id"] == retained
        assert client.get(PREFIX + "/machine").json()["state"] == "FLUSH_REQUIRED"
        maintenance(client, "FLUSH", "run-api")
        assert wait_idle(client)["retained_owner_id"] is None
        start(client, "new-after-fault")
        assert wait_idle(client)["error"] is None
        assert client.get(PREFIX + "/runs/new-after-fault").json()["status"] == "COMPLETED"


def test_direct_fresh_runtime_entry_cannot_skip_current_input(configured, bundle):
    from tests.test_execution_coordinator import CONFIGURATION
    from tests.test_owned_timed_execution import TIMED_SETTINGS

    build, ports, sessions, _, current, _ = configured
    execution = build()
    execution.start(NOW)

    def unavailable(_):
        raise SimulationBlocked("fresh input unavailable")

    current[0] = unavailable
    try:
        with pytest.raises(SimulationBlocked, match="fresh input unavailable"):
            execution._idle(lambda: execution._runtime.start_fresh_run(
                "direct-fresh", CONFIGURATION, TIMED_SETTINGS, profile().calibrations, occurred_at=NOW,
            ))
        assert inspect_owned_startup(bundle).machine is None
        assert inspect_owned_startup(bundle).runs == ()
        assert sessions == [] and len(ports[0].writes) == 1
    finally:
        execution.close(NOW)


def test_legacy_adapter_input_keeps_its_complete_position_requirement(configured, bundle):
    from app.hardware.adapter_application import build_adapter_application_execution
    from tests.test_owned_pausable_demo import Clock as TimerClock

    _, ports, _, _, _, _ = configured

    def port_factory(_):
        port = ConnectingPort()
        ports.append(port)
        return port

    data = context().model_dump()
    data["pumps"][0]["position_steps"] = None
    execution = build_adapter_application_execution(
        bundle, ArduinoSerialConfiguration(port="/dev/fake"), sf_configuration(), profile().calibrations,
        context_factory=lambda _: CommandPlanningContext.model_validate(data), sf_mixer_running=False,
        timer_factory=TimerClock().timer, arduino_port_factory=port_factory,
        arduino_monotonic=Clock(), arduino_sleep=lambda _: None,
    )
    with pytest.raises(SimulationBlocked, match="legacy current context"):
        execution.start(NOW)
    assert ports[0].closed and len(ports[0].writes) == 1
