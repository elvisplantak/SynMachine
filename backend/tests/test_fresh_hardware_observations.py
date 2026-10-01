import json
import uuid

import pytest

from app.demo.hardware_contract import BottomValveState, HardwareCommandError
from app.hardware.arduino_serial import (
    ArduinoProtocolError, ArduinoSerialClient, ArduinoSerialConfiguration,
)
from app.hardware.fresh_hardware_observations import observe_current_hardware
from app.hardware.sf_bottom_valve import SfBottomValveActuator, REGISTERS
from tests.test_arduino_serial import FakePort, NONCE, hello_ok, frame, Clock
from tests.test_sf_bottom_valve import FakeSession, configuration

REQUIRED = frozenset({"PUMP_HOME"})


class ReplyPort(FakePort):
    def __init__(self):
        super().__init__(hello_ok(capabilities=list(REQUIRED)))
        self.status_changes = {}
        self.query_count = 0
        self.on_query = lambda: None

    def write(self, data):
        count = super().write(data)
        request = json.loads(data)
        if request["type"] == "QUERY_STATUS":
            self.query_count += 1
            self.on_query()
            response = dict(
                type="STATUS", backend_session_nonce=request["backend_session_nonce"],
                controller_boot_id=request["controller_boot_id"], request_id=request["request_id"],
                controller_state="IDLE", software_state_trust="TRUSTED",
                active_operation_command_id=None,
            )
            response.update(self.status_changes)
            self.incoming.extend(frame(**response))
        return count


@pytest.fixture
def devices():
    port = ReplyPort()
    client = ArduinoSerialClient(
        ArduinoSerialConfiguration(port="/dev/test"), port_factory=lambda _: port,
        sleep=lambda _: None, monotonic=Clock(), nonce_factory=lambda: NONCE,
    )
    client.connect()
    session = FakeSession()
    session.values[REGISTERS["torque_enable"]] = 0
    actuator = SfBottomValveActuator(configuration(), session_factory=lambda _: session)
    yield client, actuator, port, session
    client.close()


def observe(devices):
    client, actuator, _, _ = devices
    return observe_current_hardware(client, actuator, required_commands=REQUIRED)


def test_existing_protocol_and_sf_reads_do_not_authorize_release(devices):
    report = observe(devices)
    _, _, port, session = devices
    assert port.query_count == 2
    assert [json.loads(value)["type"] for value in port.writes] == [
        "HELLO", "QUERY_STATUS", "QUERY_STATUS",
    ]
    assert report.sf_valve.observed_state is BottomValveState.CLOSED
    assert report.sf_valve.torque_enabled is False
    assert report.may_release_owner is False
    assert session.writes == [] and session.closed


@pytest.mark.parametrize("changes", [
    {"controller_state": "BUSY"},
    {"controller_state": "ERROR"},
    {"controller_state": "PROTOCOL_ONLY"},
    {"software_state_trust": "UNTRUSTED"},
    {"active_operation_command_id": str(uuid.uuid4())},
    {"backend_session_nonce": str(uuid.uuid4())},
    {"controller_boot_id": 999},
    {"request_id": str(uuid.uuid4())},
])
def test_bad_initial_status_prevents_sf_probe(devices, changes):
    _, _, port, session = devices
    port.status_changes = changes
    with pytest.raises(ArduinoProtocolError):
        observe(devices)
    assert not session.closed and not session.writes
    assert port.query_count == 1


def test_missing_capability_fails_before_any_query(devices):
    client, actuator, port, session = devices
    with pytest.raises(ArduinoProtocolError, match="capabilities"):
        observe_current_hardware(client, actuator, required_commands=frozenset({"MISSING"}))
    assert port.query_count == 0 and not session.closed


@pytest.mark.parametrize("required", [frozenset(), {"PUMP_HOME"}, frozenset({1})])
def test_required_capabilities_are_explicit(devices, required):
    client, actuator, port, _ = devices
    with pytest.raises(ValueError):
        observe_current_hardware(client, actuator, required_commands=required)
    assert port.query_count == 0


def test_second_status_must_also_be_idle(devices, monkeypatch):
    _, _, port, session = devices
    original = session.close

    def close():
        original()
        port.status_changes["controller_state"] = "BUSY"

    monkeypatch.setattr(session, "close", close)
    with pytest.raises(ArduinoProtocolError):
        observe(devices)
    assert port.query_count == 2 and not session.writes


def test_disconnect_during_sf_sample_never_returns_report(devices, monkeypatch):
    client, _, port, session = devices
    original = session.close

    def close():
        original()
        client.close()

    monkeypatch.setattr(session, "close", close)
    from app.hardware.arduino_serial import ArduinoUnavailableError
    with pytest.raises(ArduinoUnavailableError):
        observe(devices)
    assert port.query_count == 1 and not session.writes


def test_reconnect_with_same_nonce_and_boot_invalidates_sample(devices, monkeypatch):
    client, _, port, session = devices
    original = session.close
    initial_epoch = client.connection_epoch

    def close():
        original()
        port.incoming.extend(hello_ok(capabilities=list(REQUIRED)))
        client.connect()

    monkeypatch.setattr(session, "close", close)
    with pytest.raises(ArduinoProtocolError, match="not trusted idle"):
        observe(devices)
    assert client.connection_epoch != initial_epoch
    assert session.writes == []


@pytest.mark.parametrize("position,state", [(2559, BottomValveState.CLOSED), (3697, BottomValveState.OPEN), (3000, None)])
def test_sf_reports_only_observed_position_without_moving(devices, position, state):
    _, _, _, session = devices
    session.positions = iter([position])
    report = observe(devices)
    assert report.sf_valve.observed_state is state
    assert report.may_release_owner is False
    assert session.writes == []


def test_sf_torque_on_is_reported_without_disabling_it(devices):
    _, _, _, session = devices
    session.values[REGISTERS["torque_enable"]] = 1
    report = observe(devices)
    assert report.sf_valve.torque_enabled is True
    assert report.may_release_owner is False and session.writes == []


def test_overlapping_sf_tolerance_does_not_invent_a_state():
    session = FakeSession(positions=[3100])
    session.values[REGISTERS["torque_enable"]] = 0
    actuator = SfBottomValveActuator(
        configuration(position_tolerance=1000), session_factory=lambda _: session
    )
    assert actuator.inspect_state().observed_state is None
    assert not session.writes


@pytest.mark.parametrize("failure", ["model", "mode", "error", "limits", "torque", "position", "close"])
def test_bad_sf_sample_never_returns_a_success_report(devices, failure):
    _, _, port, session = devices
    if failure == "model":
        session.model = 999
    if failure == "mode":
        session.values[REGISTERS["operating_mode"]] = 1
    if failure == "error":
        session.hardware_errors = iter([1])
    if failure == "limits":
        session.values[REGISTERS["max_position_limit"]] = 3000
    if failure == "torque":
        session.values[REGISTERS["torque_enable"]] = 2
    if failure == "position":
        session.positions = iter([-1])
    if failure == "close":
        session.fail_close = True
    with pytest.raises(HardwareCommandError):
        observe(devices)
    assert session.closed and session.writes == []
    assert port.query_count == 1


def test_sf_primary_error_preserved_if_close_also_fails(devices):
    _, _, _, session = devices
    session.model = 999
    session.fail_close = True
    with pytest.raises(HardwareCommandError, match="model") as caught:
        observe(devices)
    assert any("close also failed" in note for note in caught.value.__notes__)


def test_sf_inspection_and_actuation_share_exclusion(devices):
    _, actuator, port, session = devices
    with actuator._command_lock:
        with pytest.raises(HardwareCommandError, match="already active"):
            observe(devices)
    assert not session.closed and not session.writes
    assert port.query_count == 1
    assert actuator.inspect_state().observed_state is BottomValveState.CLOSED


def test_repeated_observation_requires_new_queries(devices):
    first = observe(devices)
    second = observe(devices)
    _, _, port, session = devices
    assert port.query_count == 4
    assert first.arduino_status.request_id != second.arduino_status.request_id
    assert first.may_release_owner is second.may_release_owner is False
    assert session.writes == []


def test_sf_error_appearing_after_position_read_rejects_observation(devices):
    _, _, _, session = devices
    session.hardware_errors = iter([0, 0, 1])
    with pytest.raises(HardwareCommandError, match="during observation"):
        observe(devices)
    assert session.closed and session.writes == []


def test_status_timeout_returns_no_partial_observation(devices, monkeypatch):
    from app.hardware.arduino_serial import ArduinoUnavailableError
    _, _, port, session = devices
    monkeypatch.setattr(port, "write", lambda data: len(data))
    with pytest.raises(ArduinoUnavailableError):
        observe(devices)
    assert not session.closed


def test_sf_close_failure_releases_adapter_lock_for_explicit_later_inspection(devices):
    _, actuator, _, session = devices
    session.fail_close = True
    with pytest.raises(HardwareCommandError, match="close failed"):
        actuator.inspect_state()
    session.fail_close = False
    assert actuator.inspect_state().observed_state is BottomValveState.CLOSED
    assert session.writes == []
