from __future__ import annotations

import json
import logging
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


# A full 80,000-pulse Column Bottom Valve HOME search takes at least 80 seconds
# at the confirmed minimum 1 ms rising-edge interval. Cooperative loop overhead
# makes wall-clock execution longer, so retain a conservative supervised-demo
# host lifecycle window instead of treating 80 seconds as an upper bound.
COLUMN_BOTTOM_VALVE_HOME_MINIMUM_FULL_SEARCH_SECONDS = 80.0
DEFAULT_COMMAND_TIMEOUT_SECONDS = 180.0
COLUMN_DIAGNOSTIC_INTERVAL_SECONDS = 2.0

logger = logging.getLogger("uvicorn.error")


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
    reset_settle_seconds: float = 2.5
    handshake_timeout_seconds: float = 2.0
    command_timeout_seconds: float = DEFAULT_COMMAND_TIMEOUT_SECONDS
    read_chunk_size: int = 64

    def __post_init__(self) -> None:
        if not self.port.strip():
            raise ValueError("Arduino serial port must not be empty")
        if self.baud_rate <= 0:
            raise ValueError("Arduino baud rate must be positive")
        if self.reset_settle_seconds < 0:
            raise ValueError("Arduino reset settle time must not be negative")
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
        sleep: Callable[[float], None] = time.sleep,
        nonce_factory: Callable[[], uuid.UUID] = uuid.uuid4,
        request_id_factory: Callable[[], uuid.UUID] = uuid.uuid4,
    ) -> None:
        self._configuration = configuration
        self._port_factory = port_factory or self._open_port
        self._monotonic = monotonic
        self._sleep = sleep
        self._nonce_factory = nonce_factory
        self._request_id_factory = request_id_factory
        self._port: SerialPort | None = None
        self._parser = NdjsonStreamParser()
        self._pending_messages: deque[ProtocolMessage] = deque()
        self._session_nonce: str | None = None
        self._controller_boot_id: int | None = None
        self._capabilities: frozenset[str] = frozenset()
        self._connection_epoch = 0

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
    def connection_epoch(self) -> int:
        """Process-local connection generation, not a controller or physical identity.

        Every close/reconnect invalidates observations, even if a test transport
        reuses the nonce and boot ID. This value is never persisted as trust.
        """
        return self._connection_epoch

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
            # Opening the Mega 2560 USB serial port asserts DTR and resets the
            # board. Wait for the bootloader and firmware setup before sending
            # HELLO; otherwise the first frame can be consumed during reset.
            self._sleep(self._configuration.reset_settle_seconds)
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
        self._connection_epoch += 1
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
        diagnostics_enabled = command == "COLUMN_BOTTOM_VALVE_HOME"
        next_diagnostic_at = (
            self._monotonic() + COLUMN_DIAGNOSTIC_INTERVAL_SECONDS
            if diagnostics_enabled
            else deadline
        )
        diagnostic_request_id: str | None = None
        last_column_diagnostic: Status | None = None
        completed_command: ArduinoCommandResult | None = None
        while True:
            now = self._monotonic()
            remaining = deadline - now
            if remaining <= 0:
                raise ArduinoUnavailableError(
                    "Arduino command outcome is unknown after transport timeout"
                )
            read_timeout = remaining
            if diagnostics_enabled and diagnostic_request_id is None:
                read_timeout = min(remaining, max(0.001, next_diagnostic_at - now))
            try:
                response = self._read_message(read_timeout)
            except ArduinoUnavailableError as exc:
                now = self._monotonic()
                if (
                    diagnostics_enabled
                    and diagnostic_request_id is None
                    and now < deadline
                    and now >= next_diagnostic_at
                ):
                    diagnostic_request_id = str(self._request_id_factory())
                    self._write_message(
                        QueryStatus(
                            protocol="LABFORGE/1",
                            type="QUERY_STATUS",
                            backend_session_nonce=self._session_nonce,
                            controller_boot_id=self._controller_boot_id,
                            request_id=diagnostic_request_id,
                        )
                    )
                    continue
                if last_column_diagnostic is not None:
                    logger.warning(
                        "Column HOME transport ended after diagnostic: "
                        "state=%s stage_steps=%s home_active=%s",
                        last_column_diagnostic.column_motion_state,
                        last_column_diagnostic.column_stage_steps,
                        last_column_diagnostic.column_home_active,
                    )
                raise ArduinoUnavailableError(
                    "Arduino command outcome is unknown after transport failure"
                ) from exc
            if isinstance(response, Status):
                if diagnostic_request_id is None:
                    raise ArduinoProtocolError("Unexpected STATUS without diagnostic query")
                self._validate_query_correlation(response, diagnostic_request_id)
                logger.disabled = False
                logger.warning(
                    "Column HOME diagnostic: state=%s stage_steps=%s home_active=%s",
                    response.column_motion_state,
                    response.column_stage_steps,
                    response.column_home_active,
                )
                last_column_diagnostic = response
                diagnostic_request_id = None
                next_diagnostic_at = self._monotonic() + COLUMN_DIAGNOSTIC_INTERVAL_SECONDS
                if completed_command is not None:
                    return completed_command
                continue
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
                completed_command = ArduinoCommandResult(
                    result=dict(response.result), accepted=True, started=True
                )
                if diagnostic_request_id is None:
                    return completed_command
                continue
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
