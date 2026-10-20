"""Explicit shared composition for Arduino, SF and Service. Not wired by startup."""

from collections.abc import Callable
from threading import get_ident
from typing import TypeVar
from uuid import uuid4

from app.demo.hardware_contract import BottomValveState
from app.demo.operation_executor import _execute_with_required_followup
from app.hardware.arduino_command_journal import ArduinoCommandJournalState
from app.hardware.sequence_ownership import HardwareOwnership, OwnershipBlocked, SequenceLease

T = TypeVar("T")


class _OperationCommands:
    """Ephemeral access, confined to one executing callback and thread."""

    def __init__(self, arduino, sf, lease, journaled_sf=False):
        self._arduino = arduino
        self._sf = sf
        self._lease = lease
        self._journaled_sf = journaled_sf
        self._thread = get_ident()
        self._active = True
        self._error = None

    def _call(self, callback):
        if not self._active or self._thread != get_ident():
            raise OwnershipBlocked("operation scope is inactive or belongs to another thread")
        if self._error is not None:
            raise self._error
        try:
            return callback()
        except BaseException as error:
            self._error = error
            raise

    def execute(self, **values):
        def send():
            if values["phase_execution_id"] != self._lease.phase_execution_id:
                raise OwnershipBlocked("Arduino phase identity does not match sequence owner")
            entry = self._arduino.execute(**values)
            if entry.state is not ArduinoCommandJournalState.COMPLETED:
                raise OwnershipBlocked(f"Arduino outcome is unresolved: {entry.state.value}")
            return entry

        return self._call(send)

    def set_state(self, state: BottomValveState):
        if self._journaled_sf:
            return self.execute_sf(
                phase_execution_id=self._lease.phase_execution_id,
                operation_command_id=str(uuid4()),
                state=state,
            )
        return self._call(lambda: self._sf.set_state(state))

    def execute_sf(self, *, phase_execution_id, operation_command_id, state):
        def send():
            if phase_execution_id != self._lease.phase_execution_id:
                raise OwnershipBlocked("SF phase identity does not match sequence owner")
            return self._sf.execute(
                phase_execution_id=phase_execution_id,
                operation_command_id=operation_command_id,
                state=state,
            )

        return self._call(send)


class OwnedHardware:
    """All callers of this composition share one durable owner.

    The underlying adapters must remain private to this composition. Existing
    unwrapped application construction is intentionally unchanged in this stage.
    """

    def __init__(self, ownership: HardwareOwnership, arduino, sf, *, journaled_sf=False):
        self.ownership = ownership
        self._journaled_sf = journaled_sf
        self._arduino = arduino
        self._sf = sf
        self.arduino_service = _ArduinoService(self)
        self.sf_service = _SfService(self)

    def run_operation(
        self,
        lease: SequenceLease,
        primary: Callable[[_OperationCommands], T],
        *,
        required_followup: Callable[[_OperationCommands], None] | None = None,
    ) -> T:
        def call(callback):
            scope = _OperationCommands(self._arduino, self._sf, lease, self._journaled_sf)
            try:
                result = callback(scope)
                if scope._error is not None:
                    raise scope._error  # Swallowing an adapter error cannot authorize success.
                return result
            finally:
                scope._active = False

        def protected():
            if required_followup is None:
                return call(primary)
            return _execute_with_required_followup(
                lambda: call(primary), lambda: call(required_followup)
            )

        return self.ownership.invoke(lease, protected)


class _ArduinoService:
    def __init__(self, runtime: OwnedHardware):
        self._runtime = runtime

    def execute(self, **values):
        if values["command"] == "SF_MIXER_SET_STATE" and values["arguments"].get("running") is True:
            raise OwnershipBlocked(
                "continuous mixer start needs a retained sequence and explicit Stop"
            )
        owner = self._runtime.ownership
        lease = owner.claim(
            "service.arduino." + values["operation_command_id"],
            phase_execution_id=values["phase_execution_id"],
        )
        result = self._runtime.run_operation(lease, lambda commands: commands.execute(**values))
        owner.complete(lease)
        return result


class _SfService:
    def __init__(self, runtime: OwnedHardware):
        self._runtime = runtime

    def set_state(self, state: BottomValveState):
        owner = self._runtime.ownership
        lease = owner.claim("service.sf." + str(uuid4()))
        self._runtime.run_operation(lease, lambda commands: commands.set_state(state))
        owner.complete(lease)
