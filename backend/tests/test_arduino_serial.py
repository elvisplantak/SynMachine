from __future__ import annotations

import json
import uuid

import pytest

from app.hardware.arduino_serial import (
    ArduinoCommandFailedError,
    ArduinoCommandRejectedError,
    ArduinoProtocolError,
    ArduinoSerialClient,
    ArduinoSerialConfiguration,
    ArduinoUnavailableError,
)

NONCE = uuid.UUID("123e4567-e89b-12d3-a456-426614174000")
REQUEST_ID = uuid.UUID("223e4567-e89b-12d3-a456-426614174001")
OPERATION_ID = "323e4567-e89b-12d3-a456-426614174002"


def frame(**fields: object) -> bytes:
    return json.dumps(
        {"protocol": "LABFORGE/1", **fields}, separators=(",", ":")
    ).encode() + b"\n"


class FakePort:
    def __init__(self, incoming: bytes) -> None:
        self.incoming = bytearray(incoming)
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def read(self, size: int = 1) -> bytes:
        if not self.incoming:
            return b""
        result = bytes(self.incoming[:size])
        del self.incoming[:size]
        return result

    def close(self) -> None:
        self.closed = True


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        self.value += 0.001
        return self.value


def hello_ok(**changes: object) -> bytes:
    fields = {
        "type": "HELLO_OK",
        "backend_session_nonce": str(NONCE),
        "controller_boot_id": 7,
        "controller_state": "IDLE",
        "software_state_trust": "TRUSTED",
        "capabilities": ["PUMP_HOME"],
    }
    fields.update(changes)
    return frame(**fields)


def lifecycle(message_type: str, **extra: object) -> bytes:
    fields = {
        "type": message_type,
        "backend_session_nonce": str(NONCE),
        "controller_boot_id": 7,
        "phase_execution_id": "phase-1",
        "operation_command_id": OPERATION_ID,
    }
    fields.update(extra)
    return frame(**fields)


def client_for(incoming: bytes) -> tuple[ArduinoSerialClient, FakePort]:
    port = FakePort(incoming)
    client = ArduinoSerialClient(
        ArduinoSerialConfiguration(port="/dev/test", command_timeout_seconds=0.1),
        port_factory=lambda _: port,
        monotonic=Clock(),
        sleep=lambda _: None,
        nonce_factory=lambda: NONCE,
        request_id_factory=lambda: REQUEST_ID,
    )
    return client, port


def test_handshake_waits_for_mega_reset_before_sending_hello() -> None:
    port = FakePort(hello_ok())
    sleeps: list[float] = []
    client = ArduinoSerialClient(
        ArduinoSerialConfiguration(port="/dev/test", reset_settle_seconds=2.5),
        port_factory=lambda _: port,
        monotonic=Clock(),
        sleep=sleeps.append,
        nonce_factory=lambda: NONCE,
        request_id_factory=lambda: REQUEST_ID,
    )

    client.connect()

    assert sleeps == [2.5]
    assert len(port.writes) == 1


def test_handshake_establishes_trusted_session_and_capabilities() -> None:
    client, port = client_for(hello_ok())
    response = client.connect()
    assert response.controller_boot_id == 7
    assert client.connected
    assert client.capabilities == {"PUMP_HOME"}
    assert json.loads(port.writes[0]) == {
        "protocol": "LABFORGE/1",
        "type": "HELLO",
        "backend_session_nonce": str(NONCE),
    }


@pytest.mark.parametrize(
    "response",
    [
        hello_ok(backend_session_nonce="223e4567-e89b-12d3-a456-426614174000"),
        hello_ok(
            controller_boot_id=None,
            controller_state="IDENTITY_UNTRUSTED",
            software_state_trust="UNTRUSTED",
        ),
    ],
)
def test_handshake_rejects_wrong_session_or_untrusted_identity(response: bytes) -> None:
    client, port = client_for(response)
    with pytest.raises(ArduinoProtocolError):
        client.connect()
    assert port.closed


def test_execute_requires_caller_owned_ids_and_observes_truthful_lifecycle() -> None:
    incoming = (
        hello_ok()
        + lifecycle("ACCEPTED")
        + lifecycle("STARTED")
        + lifecycle("COMPLETED", result={"position_steps": 0})
    )
    client, port = client_for(incoming)
    client.connect()
    result = client.execute(
        phase_execution_id="phase-1",
        operation_command_id=OPERATION_ID,
        command="PUMP_HOME",
        arguments={"pump": "P1"},
    )
    assert result.result == {"position_steps": 0}
    command = json.loads(port.writes[1])
    assert command["phase_execution_id"] == "phase-1"
    assert command["operation_command_id"] == OPERATION_ID


def test_rejected_command_stays_distinct_from_execution_failure() -> None:
    client, _ = client_for(
        hello_ok() + lifecycle("REJECTED", error_code="CONTROLLER_BUSY")
    )
    client.connect()
    with pytest.raises(ArduinoCommandRejectedError) as error:
        client.execute(
            phase_execution_id="phase-1",
            operation_command_id=OPERATION_ID,
            command="PUMP_HOME",
            arguments={"pump": "P1"},
        )
    assert error.value.error_code == "CONTROLLER_BUSY"


def test_failed_command_preserves_execution_started_truth() -> None:
    client, _ = client_for(
        hello_ok()
        + lifecycle("ACCEPTED")
        + lifecycle("STARTED")
        + lifecycle("FAILED", error_code="PUMP_MOTION_TIMEOUT", execution_started=True)
    )
    client.connect()
    with pytest.raises(ArduinoCommandFailedError) as error:
        client.execute(
            phase_execution_id="phase-1",
            operation_command_id=OPERATION_ID,
            command="PUMP_HOME",
            arguments={"pump": "P1"},
        )
    assert error.value.execution_started is True


@pytest.mark.parametrize(
    "incoming",
    [
        lifecycle("STARTED"),
        lifecycle("ACCEPTED") + lifecycle("COMPLETED", result={}),
        lifecycle(
            "ACCEPTED",
            operation_command_id="423e4567-e89b-12d3-a456-426614174003",
        ),
    ],
)
def test_out_of_order_or_mismatched_lifecycle_fails_closed(incoming: bytes) -> None:
    client, _ = client_for(hello_ok() + incoming)
    client.connect()
    with pytest.raises(ArduinoProtocolError):
        client.execute(
            phase_execution_id="phase-1",
            operation_command_id=OPERATION_ID,
            command="PUMP_HOME",
            arguments={"pump": "P1"},
        )


def test_timeout_reports_unknown_outcome_and_never_retries_command() -> None:
    client, port = client_for(hello_ok() + lifecycle("ACCEPTED"))
    client.connect()
    with pytest.raises(ArduinoUnavailableError, match="outcome is unknown"):
        client.execute(
            phase_execution_id="phase-1",
            operation_command_id=OPERATION_ID,
            command="PUMP_HOME",
            arguments={"pump": "P1"},
        )
    assert len(port.writes) == 2


def test_unadvertised_capability_is_rejected_without_command_bytes() -> None:
    client, port = client_for(hello_ok())
    client.connect()
    with pytest.raises(ArduinoProtocolError, match="does not advertise"):
        client.execute(
            phase_execution_id="phase-1",
            operation_command_id=OPERATION_ID,
            command="VALVE_HOME",
            arguments={"valve": "V1"},
        )
    assert len(port.writes) == 1


def test_multiple_lifecycle_frames_in_one_read_are_not_discarded() -> None:
    incoming = (
        hello_ok()
        + lifecycle("ACCEPTED")
        + lifecycle("STARTED")
        + lifecycle("COMPLETED", result={"position_steps": 0})
    )
    port = FakePort(incoming)
    client = ArduinoSerialClient(
        ArduinoSerialConfiguration(
            port="/dev/test", command_timeout_seconds=0.1, read_chunk_size=512
        ),
        port_factory=lambda _: port,
        monotonic=Clock(),
        sleep=lambda _: None,
        nonce_factory=lambda: NONCE,
        request_id_factory=lambda: REQUEST_ID,
    )
    client.connect()
    result = client.execute(
        phase_execution_id="phase-1",
        operation_command_id=OPERATION_ID,
        command="PUMP_HOME",
        arguments={"pump": "P1"},
    )
    assert result.result == {"position_steps": 0}


def test_query_status_is_correlated_and_does_not_send_physical_command() -> None:
    status = frame(
        type="STATUS",
        backend_session_nonce=str(NONCE),
        controller_boot_id=7,
        request_id=str(REQUEST_ID),
        controller_state="IDLE",
        software_state_trust="TRUSTED",
        active_operation_command_id=None,
    )
    client, port = client_for(hello_ok() + status)
    client.connect()
    response = client.query_status()
    assert response.controller_state == "IDLE"
    assert json.loads(port.writes[1])["type"] == "QUERY_STATUS"


def test_query_command_recovers_completed_outcome_without_resending_command() -> None:
    command_status = frame(
        type="COMMAND_STATUS",
        backend_session_nonce=str(NONCE),
        controller_boot_id=7,
        request_id=str(REQUEST_ID),
        phase_execution_id="phase-1",
        operation_command_id=OPERATION_ID,
        command_state="COMPLETED",
        result={"position_steps": 0},
    )
    client, port = client_for(hello_ok() + command_status)
    client.connect()
    response = client.query_command(OPERATION_ID)
    assert response.command_state == "COMPLETED"
    outbound = json.loads(port.writes[1])
    assert outbound["type"] == "QUERY_COMMAND"
    assert outbound["operation_command_id"] == OPERATION_ID
    assert all(json.loads(item)["type"] != "COMMAND" for item in port.writes)


@pytest.mark.parametrize(
    "change",
    [
        {"request_id": "423e4567-e89b-12d3-a456-426614174003"},
        {"controller_boot_id": 8},
        {"operation_command_id": "423e4567-e89b-12d3-a456-426614174003"},
    ],
)
def test_query_command_rejects_mismatched_correlation(change: dict[str, object]) -> None:
    fields: dict[str, object] = {
        "type": "COMMAND_STATUS",
        "backend_session_nonce": str(NONCE),
        "controller_boot_id": 7,
        "request_id": str(REQUEST_ID),
        "phase_execution_id": "phase-1",
        "operation_command_id": OPERATION_ID,
        "command_state": "STARTED",
    }
    fields.update(change)
    client, _ = client_for(hello_ok() + frame(**fields))
    client.connect()
    with pytest.raises(ArduinoProtocolError, match="correlation mismatch"):
        client.query_command(OPERATION_ID)
