"""Fresh, non-actuating observations; never a hardware recovery/release permit.

The caller must serialize this probe with all hardware work under the shared
sequence owner. Production startup does not call it. It does not open/reconnect
Arduino, provision databases, infer physical references or persist trust.
"""

from dataclasses import dataclass

from app.hardware.arduino_serial import ArduinoProtocolError, ArduinoSerialClient
from app.hardware.sf_bottom_valve import SfBottomValveActuator, SfValveObservation
from app.protocol.models import Status


@dataclass(frozen=True)
class CurrentHardwareObservations:
    arduino_status: Status
    arduino_status_request_ids: tuple[str, str]
    arduino_connection_epoch: int
    capabilities: frozenset[str]
    sf_valve: SfValveObservation

    @property
    def may_release_owner(self) -> bool:
        # Status is software evidence only; register proximity is not fluidic
        # readiness. Neither can resolve an unknown historical command outcome.
        return False


def observe_current_hardware(
    arduino: ArduinoSerialClient,
    sf_valve: SfBottomValveActuator,
    *,
    required_commands: frozenset[str],
) -> CurrentHardwareObservations:
    """Bracket a read-only SF sample with fresh correlated Arduino STATUS queries.

    Both status replies must be trusted/idle with no active command. Required
    capabilities must be present in this connection's HELLO. Connection changes,
    exceptions, stale/corrupt protocol replies and incomplete samples return no
    report. Callers must not reuse a report as a permission or a cached preflight.
    """
    if type(arduino) is not ArduinoSerialClient or type(sf_valve) is not SfBottomValveActuator:
        raise TypeError("explicit existing Arduino and SF adapters are required")
    if (
        type(required_commands) is not frozenset or not required_commands
        or any(type(command) is not str or not command for command in required_commands)
    ):
        raise ValueError("required commands must be an explicit non-empty frozenset")
    epoch = arduino.connection_epoch
    capabilities = arduino.capabilities
    if not required_commands <= capabilities:
        raise ArduinoProtocolError("required controller capabilities are absent")

    def sample():
        status = arduino.query_status()
        if (
            arduino.connection_epoch != epoch
            or not arduino.connected
            or arduino.capabilities != capabilities
            or status.controller_state != "IDLE"
            or status.software_state_trust != "TRUSTED"
            or status.active_operation_command_id is not None
        ):
            raise ArduinoProtocolError("fresh controller software observation is not trusted idle")
        return status

    before = sample()
    sf = sf_valve.inspect_state()
    after = sample()
    if before.request_id == after.request_id:
        raise ArduinoProtocolError("bracketing observations require distinct status request IDs")
    if (before.backend_session_nonce, before.controller_boot_id) != (
        after.backend_session_nonce, after.controller_boot_id
    ):
        raise ArduinoProtocolError("controller session changed during observation")
    return CurrentHardwareObservations(
        after, (before.request_id, after.request_id), epoch, capabilities, sf
    )
