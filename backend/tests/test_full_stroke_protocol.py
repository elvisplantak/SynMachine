"""Firmware/host boundary for the explicit, capability-gated full stroke."""

import json

import pytest

from app.hardware.arduino_serial import ArduinoProtocolError
from tests.test_arduino_serial import OPERATION_ID, client_for, hello_ok, lifecycle

CAPABILITIES = [
    "PUMP_HOME", "PUMP_MOVE_ABSOLUTE_STEPS", "VALVE_HOME", "VALVE_SET_POSITION",
    "COLUMN_BOTTOM_VALVE_HOME", "COLUMN_BOTTOM_VALVE_SET_POSITION",
    "CAROUSEL_SET_REFERENCE", "CAROUSEL_MOVE_TO_POSITION", "SF_MIXER_SET_STATE",
    "PUMP_ASPIRATE_FULL_STROKE",
]


def test_ten_capability_firmware_handshake_and_explicit_full_stroke_wire():
    client, port = client_for(
        hello_ok(capabilities=CAPABILITIES)
        + lifecycle("ACCEPTED") + lifecycle("STARTED")
        + lifecycle("COMPLETED", result={})
    )
    try:
        assert len(client.connect().capabilities) == 10
        result = client.execute(phase_execution_id="phase-1", operation_command_id=OPERATION_ID,
                                command="PUMP_ASPIRATE_FULL_STROKE", arguments={"pump": "P1"})
        assert result.accepted and result.started
        assert len(port.writes) == 2
        command = json.loads(port.writes[1])
        assert command["command"] == "PUMP_ASPIRATE_FULL_STROKE"
        assert command["arguments"] == {"pump": "P1"}
    finally:
        client.close()


def test_older_firmware_cannot_receive_full_stroke_or_implicit_home_fallback():
    client, port = client_for(hello_ok(capabilities=CAPABILITIES[:-1]))
    try:
        client.connect()
        with pytest.raises(ArduinoProtocolError, match="does not advertise"):
            client.execute(phase_execution_id="phase-1", operation_command_id=OPERATION_ID,
                           command="PUMP_ASPIRATE_FULL_STROKE", arguments={"pump": "P2"})
        assert len(port.writes) == 1
        assert json.loads(port.writes[0])["type"] == "HELLO"
    finally:
        client.close()
