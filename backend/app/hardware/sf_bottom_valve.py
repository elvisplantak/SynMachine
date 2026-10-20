from __future__ import annotations

import time
from threading import Lock
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.demo.hardware_contract import BottomValveState, HardwareCommandError


PROTOCOL_VERSION = 2.0
EXPECTED_MODEL_NUMBER = 1060


@dataclass(frozen=True)
class Register:
    address: int
    size: int


REGISTERS = {
    "operating_mode": Register(11, 1),
    "min_position_limit": Register(52, 4),
    "max_position_limit": Register(48, 4),
    "torque_enable": Register(64, 1),
    "hardware_error_status": Register(70, 1),
    "profile_acceleration": Register(108, 4),
    "profile_velocity": Register(112, 4),
    "goal_position": Register(116, 4),
    "present_position": Register(132, 4),
}


@dataclass(frozen=True)
class SfBottomValveConfiguration:
    port: str
    baud_rate: int = 57_600
    device_id: int = 2
    closed_position: int = 2559
    open_position: int = 3697
    profile_velocity: int = 20
    profile_acceleration: int = 1
    position_tolerance: int = 20
    motion_timeout_seconds: float = 15.0
    poll_interval_seconds: float = 0.05

    def __post_init__(self) -> None:
        if not self.port:
            raise ValueError("DYNAMIXEL port must not be empty")
        if not 0 <= self.device_id <= 252:
            raise ValueError("DYNAMIXEL device_id must be in 0..252")
        if self.closed_position == self.open_position:
            raise ValueError("OPEN and CLOSED positions must differ")
        if self.position_tolerance < 0:
            raise ValueError("position_tolerance must not be negative")
        if self.motion_timeout_seconds <= 0:
            raise ValueError("motion_timeout_seconds must be positive")
        if self.poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds must not be negative")


class DynamixelSession(Protocol):
    def ping(self, device_id: int) -> int: ...

    def read(self, device_id: int, register: Register) -> int: ...

    def write(self, device_id: int, register: Register, value: int) -> None: ...

    def close(self) -> None: ...


class SfBottomValveControl(Protocol):
    def set_state(self, state: BottomValveState) -> None: ...


SessionFactory = Callable[[SfBottomValveConfiguration], DynamixelSession]
Clock = Callable[[], float]
Sleeper = Callable[[float], None]


class DynamixelSdkSession:
    def __init__(self, configuration: SfBottomValveConfiguration) -> None:
        try:
            from dynamixel_sdk import COMM_SUCCESS, PacketHandler, PortHandler
        except ImportError as error:
            raise HardwareCommandError(
                "dynamixel-sdk is not installed in the backend environment"
            ) from error

        self._comm_success = COMM_SUCCESS
        self._port = PortHandler(configuration.port)
        self._packet = PacketHandler(PROTOCOL_VERSION)
        try:
            if not self._port.openPort():
                raise HardwareCommandError(f"failed to open DYNAMIXEL port {configuration.port}")
            if not self._port.setBaudRate(configuration.baud_rate):
                raise HardwareCommandError(
                    f"failed to set DYNAMIXEL baud {configuration.baud_rate}"
                )
        except Exception:
            self._port.closePort()
            raise

    def ping(self, device_id: int) -> int:
        value, communication, device_error = self._packet.ping(self._port, device_id)
        self._check_result(communication, device_error)
        return int(value)

    def read(self, device_id: int, register: Register) -> int:
        readers = {
            1: self._packet.read1ByteTxRx,
            2: self._packet.read2ByteTxRx,
            4: self._packet.read4ByteTxRx,
        }
        value, communication, device_error = readers[register.size](
            self._port, device_id, register.address
        )
        self._check_result(communication, device_error)
        return int(value)

    def write(self, device_id: int, register: Register, value: int) -> None:
        writers = {
            1: self._packet.write1ByteTxRx,
            2: self._packet.write2ByteTxRx,
            4: self._packet.write4ByteTxRx,
        }
        communication, device_error = writers[register.size](
            self._port, device_id, register.address, value
        )
        self._check_result(communication, device_error)

    def close(self) -> None:
        self._port.closePort()

    def _check_result(self, communication: int, device_error: int) -> None:
        if communication != self._comm_success:
            raise HardwareCommandError(self._packet.getTxRxResult(communication))
        if device_error != 0:
            raise HardwareCommandError(self._packet.getRxPacketError(device_error))


@dataclass(frozen=True)
class SfValveObservation:
    """One read-only register sample, not durable position or fluidic trust."""

    present_position: int
    torque_enabled: bool
    observed_state: BottomValveState | None


class SfBottomValveActuator:
    """Synchronous XL430 OPEN/CLOSED adapter for the supervised demo runtime."""

    def __init__(
        self,
        configuration: SfBottomValveConfiguration,
        *,
        session_factory: SessionFactory = DynamixelSdkSession,
        clock: Clock = time.monotonic,
        sleep: Sleeper = time.sleep,
    ) -> None:
        self._configuration = configuration
        self._session_factory = session_factory
        self._clock = clock
        self._sleep = sleep
        self._command_lock = Lock()

    def inspect_state(self) -> SfValveObservation:
        """Read the configured actuator without enabling torque or setting targets.

        Shares the actuator command lock. The short-lived connection is closed
        before returning, so this does not establish ongoing SF session trust.
        """
        if not self._command_lock.acquire(blocking=False):
            raise HardwareCommandError("SF bottom valve command already active")
        session = None
        primary_error = None
        try:
            session = self._session_factory(self._configuration)
            # Validate both configured endpoints; no new calibration is inferred.
            self._validate_device(session, self._configuration.closed_position)
            self._validate_device(session, self._configuration.open_position)
            device_id = self._configuration.device_id
            torque = session.read(device_id, REGISTERS["torque_enable"])
            position = session.read(device_id, REGISTERS["present_position"])
            if type(torque) is not int or torque not in (0, 1) or type(position) is not int:
                raise HardwareCommandError("invalid SF observation register value")
            minimum = session.read(device_id, REGISTERS["min_position_limit"])
            maximum = session.read(device_id, REGISTERS["max_position_limit"])
            if not minimum <= position <= maximum:
                raise HardwareCommandError("SF observed position outside configured limits")
            if session.read(device_id, REGISTERS["hardware_error_status"]) != 0:
                raise HardwareCommandError("SF hardware error during observation")
            candidates = [
                state for state, target in (
                    (BottomValveState.CLOSED, self._configuration.closed_position),
                    (BottomValveState.OPEN, self._configuration.open_position),
                )
                if abs(position - target) <= self._configuration.position_tolerance
            ]
            return SfValveObservation(
                position, bool(torque), candidates[0] if len(candidates) == 1 else None
            )
        except BaseException as error:
            primary_error = error
            raise
        finally:
            try:
                if session is not None:
                    try:
                        session.close()
                    except Exception as error:
                        if primary_error is None:
                            raise HardwareCommandError("SF observation close failed") from error
                        primary_error.add_note(f"SF observation close also failed: {error}")
            finally:
                self._command_lock.release()

    def set_state(self, state: BottomValveState) -> None:
        if not isinstance(state, BottomValveState):
            raise ValueError(f"unsupported SF bottom valve state: {state!r}")
        if not self._command_lock.acquire(blocking=False):
            raise HardwareCommandError("SF bottom valve command already active")
        try:
            self._set_state_locked(state)
        finally:
            self._command_lock.release()

    def _set_state_locked(self, state: BottomValveState) -> None:
        target = (
            self._configuration.open_position
            if state is BottomValveState.OPEN
            else self._configuration.closed_position
        )
        session: DynamixelSession | None = None
        torque_enabled = False
        primary_error: BaseException | None = None
        try:
            session = self._session_factory(self._configuration)
            self._validate_device(session, target)
            current = session.read(self._configuration.device_id, REGISTERS["present_position"])
            session.write(
                self._configuration.device_id,
                REGISTERS["profile_acceleration"],
                self._configuration.profile_acceleration,
            )
            session.write(
                self._configuration.device_id,
                REGISTERS["profile_velocity"],
                self._configuration.profile_velocity,
            )
            # Prevent movement toward a stale persisted Goal Position on torque enable.
            session.write(self._configuration.device_id, REGISTERS["goal_position"], current)
            # From this point the command may have reached the actuator even if the
            # acknowledgement is lost, so cleanup must attempt torque disable.
            torque_enabled = True
            session.write(self._configuration.device_id, REGISTERS["torque_enable"], 1)
            session.write(self._configuration.device_id, REGISTERS["goal_position"], target)
            self._wait_for_target(session, target)
        except HardwareCommandError as error:
            primary_error = error
            raise
        except Exception as error:
            command_error = HardwareCommandError(
                f"SF bottom valve {state.value} command failed: {error}"
            )
            primary_error = command_error
            raise command_error from error
        finally:
            if session is not None:
                cleanup_error: Exception | None = None
                if torque_enabled:
                    try:
                        session.write(
                            self._configuration.device_id,
                            REGISTERS["torque_enable"],
                            0,
                        )
                    except Exception as error:
                        cleanup_error = error
                try:
                    session.close()
                except Exception as error:
                    if cleanup_error is None:
                        cleanup_error = error
                if cleanup_error is not None and primary_error is None:
                    raise HardwareCommandError(
                        f"SF bottom valve reached its target but cleanup failed: {cleanup_error}"
                    ) from cleanup_error

    def _validate_device(self, session: DynamixelSession, target: int) -> None:
        device_id = self._configuration.device_id
        model = session.ping(device_id)
        if model != EXPECTED_MODEL_NUMBER:
            raise HardwareCommandError(
                f"expected XL430 model {EXPECTED_MODEL_NUMBER}, received {model}"
            )
        mode = session.read(device_id, REGISTERS["operating_mode"])
        if mode != 3:
            raise HardwareCommandError(f"SF bottom valve operating mode must be 3, received {mode}")
        hardware_error = session.read(device_id, REGISTERS["hardware_error_status"])
        if hardware_error != 0:
            raise HardwareCommandError(f"SF bottom valve hardware_error_status={hardware_error}")
        minimum = session.read(device_id, REGISTERS["min_position_limit"])
        maximum = session.read(device_id, REGISTERS["max_position_limit"])
        if not minimum <= target <= maximum:
            raise HardwareCommandError(
                f"SF bottom valve target {target} is outside {minimum}..{maximum}"
            )

    def _wait_for_target(self, session: DynamixelSession, target: int) -> None:
        device_id = self._configuration.device_id
        deadline = self._clock() + self._configuration.motion_timeout_seconds
        last_position: int | None = None
        while self._clock() < deadline:
            hardware_error = session.read(device_id, REGISTERS["hardware_error_status"])
            if hardware_error != 0:
                raise HardwareCommandError(
                    f"SF bottom valve hardware_error_status={hardware_error}"
                )
            last_position = session.read(device_id, REGISTERS["present_position"])
            if abs(last_position - target) <= self._configuration.position_tolerance:
                return
            self._sleep(self._configuration.poll_interval_seconds)
        raise HardwareCommandError(
            f"SF bottom valve motion timeout: target={target}, "
            f"last_present_position={last_position}"
        )
