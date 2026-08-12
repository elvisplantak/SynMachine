from __future__ import annotations

import json
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import serial

from app.protocol import (
    Accepted,
    Command,
    CommandStatus,
    Completed,
    Failed,
    Hello,
    HelloOk,
    NdjsonStreamParser,
    ParseError,
    ParseSuccess,
    ProtocolError,
    QueryCommand,
    QueryStatus,
    Rejected,
    Started,
    Status,
)
from app.protocol.models import ProtocolMessage


class ArduinoSerialError(RuntimeError):
    """Base error for the LABFORGE/1 Arduino transport."""


class ArduinoUnavailableError(ArduinoSerialError):
    """The configured Arduino transport cannot be opened or completed."""


class ArduinoProtocolError(ArduinoSerialError):
    """The controller response violates the LABFORGE/1 contract."""


class ArduinoCommandRejectedError(ArduinoSerialError):
    def __init__(self, error_code: str, message: str | None = None) -> None:
        super().__init__(error_code if message is None else f"{error_code}: {message}")
        self.error_code = error_code


class ArduinoCommandFailedError(ArduinoSerialError):
    def __init__(
        self,
        error_code: str,
        execution_started: bool,
        message: str | None = None,
    ) -> None:
        super().__init__(error_code if message is None else f"{error_code}: {message}")
        self.error_code = error_code
        self.execution_started = execution_started


class SerialPort(Protocol):
    def write(self, data: bytes) -> int: ...

    def read(self, size: int = 1) -> bytes: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class ArduinoSerialConfiguration:
    port: str
    baud_rate: int = 115200
    handshake_timeout_seconds: float = 2.0
    command_timeout_seconds: float = 60.0
    read_chunk_size: int = 64

    def __post_init__(self) -> None:
        if not self.port.strip():
            raise ValueError("Arduino serial port must not be empty")
        if self.baud_rate <= 0:
            raise ValueError("Arduino baud rate must be positive")
        if self.handshake_timeout_seconds <= 0 or self.command_timeout_seconds <= 0:
            raise ValueError("Arduino timeouts must be positive")
        if not 1 <= self.read_chunk_size <= 512:
            raise ValueError("Arduino read chunk size must be in 1..512")


@dataclass(frozen=True)
class ArduinoCommandResult:
    result: dict[str, str | int | bool]
    accepted: bool
    started: bool


class ArduinoSerialClient:
    """Synchronous, single-command LABFORGE/1 controller client.

    The caller owns durable creation of phase_execution_id and
    operation_command_id before calling execute(). This client never invents or
    retries a physical-command identity.
    """

    def __init__(
        self,
        configuration: ArduinoSerialConfiguration,
        *,
        port_factory: Callable[[ArduinoSerialConfiguration], SerialPort] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        nonce_factory: Callable[[], uuid.UUID] = uuid.uuid4,
        request_id_factory: Callable[[], uuid.UUID] = uuid.uuid4,
    ) -> None:
        self._configuration = configuration
        self._port_factory = port_factory or self._open_port
        self._monotonic = monotonic
        self._nonce_factory = nonce_factory
        self._request_id_factory = request_id_factory
        self._port: SerialPort | None = None
        self._parser = NdjsonStreamParser()
        self._pending_messages: deque[ProtocolMessage] = deque()
        self._session_nonce: str | None = None
        self._controller_boot_id: int | None = None
        self._capabilities: frozenset[str] = frozenset()

    @staticmethod
    def _open_port(configuration: ArduinoSerialConfiguration) -> SerialPort:
        try:
            return serial.Serial(
                port=configuration.port,
                baudrate=configuration.baud_rate,
                timeout=0.05,
                write_timeout=1.0,
            )
        except serial.SerialException as exc:
            raise ArduinoUnavailableError(
                f"Cannot open Arduino port {configuration.port}: {exc}"
            ) from exc

    @property
    def connected(self) -> bool:
        return self._port is not None and self._controller_boot_id is not None

    @property
    def capabilities(self) -> frozenset[str]:
        return self._capabilities

    @property
    def controller_boot_id(self) -> int | None:
        return self._controller_boot_id

    def connect(self) -> HelloOk:
        self.close()
        try:
            self._port = self._port_factory(self._configuration)
            self._parser = NdjsonStreamParser()
            self._pending_messages.clear()
            nonce = str(self._nonce_factory())
            self._write_message(
                Hello(
                    protocol="LABFORGE/1",
                    type="HELLO",
                    backend_session_nonce=nonce,
                )
            )
            response = self._read_message(self._configuration.handshake_timeout_seconds)
        except ArduinoSerialError:
            self.close()
            raise
        if not isinstance(response, HelloOk):
            self.close()
            raise ArduinoProtocolError("Expected HELLO_OK from Arduino")
        if response.backend_session_nonce != nonce:
            self.close()
            raise ArduinoProtocolError("HELLO_OK session nonce mismatch")
        if response.controller_boot_id is None or response.software_state_trust != "TRUSTED":
            self.close()
            raise ArduinoProtocolError("Arduino identity or software state is untrusted")
        self._session_nonce = nonce
        self._controller_boot_id = response.controller_boot_id
        self._capabilities = frozenset(response.capabilities)
        return response

    def close(self) -> None:
        port, self._port = self._port, None
        self._session_nonce = None
        self._controller_boot_id = None
        self._capabilities = frozenset()
        self._pending_messages.clear()
        if port is not None:
            port.close()

    def execute(
        self,
        *,
        phase_execution_id: str,
        operation_command_id: str,
        command: str,
        arguments: dict[str, str | int | bool],
    ) -> ArduinoCommandResult:
        if not self.connected:
            raise ArduinoUnavailableError("Arduino is not connected")
        if command not in self._capabilities:
            raise ArduinoProtocolError(f"Arduino does not advertise {command}")
        assert self._session_nonce is not None
        assert self._controller_boot_id is not None
        outbound = Command(
            protocol="LABFORGE/1",
            type="COMMAND",
            backend_session_nonce=self._session_nonce,
            controller_boot_id=self._controller_boot_id,
            phase_execution_id=phase_execution_id,
            operation_command_id=operation_command_id,
            command=command,
            arguments=arguments,
        )
        self._write_message(outbound)
        accepted = False
        started = False
        deadline = self._monotonic() + self._configuration.command_timeout_seconds
        while True:
            remaining = deadline - self._monotonic()
            if remaining <= 0:
                raise ArduinoUnavailableError(
                    "Arduino command outcome is unknown after transport timeout"
                )
            try:
                response = self._read_message(remaining)
            except ArduinoUnavailableError as exc:
                raise ArduinoUnavailableError(
                    "Arduino command outcome is unknown after transport failure"
                ) from exc
            if isinstance(response, ProtocolError):
                raise ArduinoProtocolError(response.error_code)
            if not isinstance(response, (Rejected, Accepted, Started, Completed, Failed)):
                raise ArduinoProtocolError(
                    f"Unexpected {response.type} while awaiting command lifecycle"
                )
            if (
                response.backend_session_nonce != self._session_nonce
                or response.controller_boot_id != self._controller_boot_id
                or response.phase_execution_id != phase_execution_id
                or response.operation_command_id != operation_command_id
            ):
                raise ArduinoProtocolError("Command lifecycle correlation mismatch")
            if isinstance(response, Rejected):
                if accepted or started:
                    raise ArduinoProtocolError("REJECTED arrived after command acceptance")
                raise ArduinoCommandRejectedError(response.error_code, response.message)
            if isinstance(response, Accepted):
                if accepted or started:
                    raise ArduinoProtocolError("Duplicate or out-of-order ACCEPTED")
                accepted = True
                continue
            if isinstance(response, Started):
                if not accepted or started:
                    raise ArduinoProtocolError("STARTED arrived out of order")
                started = True
                continue
            if isinstance(response, Completed):
                if not accepted or not started:
                    raise ArduinoProtocolError("COMPLETED arrived before STARTED")
                return ArduinoCommandResult(
                    result=dict(response.result), accepted=True, started=True
                )
            if not accepted:
                raise ArduinoProtocolError("FAILED arrived before ACCEPTED")
            if response.execution_started != started:
                raise ArduinoProtocolError("FAILED execution_started contradicts lifecycle")
            raise ArduinoCommandFailedError(
                response.error_code,
                response.execution_started,
                response.message,
            )

    def query_status(self) -> Status:
        """Read controller state without authorizing actuator movement."""

        self._require_connected()
        request_id = str(self._request_id_factory())
        assert self._session_nonce is not None
        assert self._controller_boot_id is not None
        self._write_message(
            QueryStatus(
                protocol="LABFORGE/1",
                type="QUERY_STATUS",
                backend_session_nonce=self._session_nonce,
                controller_boot_id=self._controller_boot_id,
                request_id=request_id,
            )
        )
        response = self._read_message(self._configuration.handshake_timeout_seconds)
        if isinstance(response, ProtocolError):
            raise ArduinoProtocolError(response.error_code)
        if not isinstance(response, Status):
            raise ArduinoProtocolError(f"Expected STATUS, received {response.type}")
        self._validate_query_correlation(response, request_id)
        return response

    def query_command(self, operation_command_id: str) -> CommandStatus:
        """Recover an existing command outcome without resending the command."""

        self._require_connected()
        request_id = str(self._request_id_factory())
        assert self._session_nonce is not None
        assert self._controller_boot_id is not None
        self._write_message(
            QueryCommand(
                protocol="LABFORGE/1",
                type="QUERY_COMMAND",
                backend_session_nonce=self._session_nonce,
                controller_boot_id=self._controller_boot_id,
                request_id=request_id,
                operation_command_id=operation_command_id,
            )
        )
        response = self._read_message(self._configuration.handshake_timeout_seconds)
        if isinstance(response, ProtocolError):
            raise ArduinoProtocolError(response.error_code)
        if not isinstance(response, CommandStatus):
            raise ArduinoProtocolError(
                f"Expected COMMAND_STATUS, received {response.type}"
            )
        self._validate_query_correlation(response, request_id)
        if response.operation_command_id != operation_command_id:
            raise ArduinoProtocolError("COMMAND_STATUS operation correlation mismatch")
        return response

    def _require_connected(self) -> None:
        if not self.connected:
            raise ArduinoUnavailableError("Arduino is not connected")

    def _validate_query_correlation(
        self, response: Status | CommandStatus, request_id: str
    ) -> None:
        if (
            response.backend_session_nonce != self._session_nonce
            or response.controller_boot_id != self._controller_boot_id
            or response.request_id != request_id
        ):
            raise ArduinoProtocolError("Query response correlation mismatch")

    def _write_message(self, message: ProtocolMessage) -> None:
        if self._port is None:
            raise ArduinoUnavailableError("Arduino port is closed")
        frame = (
            json.dumps(message.to_wire_dict(), separators=(",", ":"), ensure_ascii=False).encode()
            + b"\n"
        )
        try:
            written = self._port.write(frame)
        except (OSError, serial.SerialException) as exc:
            raise ArduinoUnavailableError(f"Arduino write failed: {exc}") from exc
        if written != len(frame):
            raise ArduinoUnavailableError("Arduino write was incomplete")

    def _read_message(self, timeout_seconds: float) -> ProtocolMessage:
        if self._port is None:
            raise ArduinoUnavailableError("Arduino port is closed")
        if self._pending_messages:
            return self._pending_messages.popleft()
        deadline = self._monotonic() + timeout_seconds
        while self._monotonic() < deadline:
            try:
                chunk = self._port.read(self._configuration.read_chunk_size)
            except (OSError, serial.SerialException) as exc:
                raise ArduinoUnavailableError(f"Arduino read failed: {exc}") from exc
            if not chunk:
                continue
            for outcome in self._parser.feed(chunk):
                if isinstance(outcome, ParseError):
                    raise ArduinoProtocolError(
                        f"Invalid Arduino frame: {outcome.error_code}"
                    )
                assert isinstance(outcome, ParseSuccess)
                self._pending_messages.append(outcome.message)
            if self._pending_messages:
                return self._pending_messages.popleft()
        raise ArduinoUnavailableError("Arduino response timeout")
