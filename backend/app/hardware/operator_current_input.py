"""Fresh attributed operator input, consumed by the existing configured provider.

No transport, reference reconstruction, production activation or physical proof.
The credential binds a declaration to the explicitly configured local operator.
It is not device evidence, a general API login or permission for physical work.
"""

from hashlib import sha256
from hmac import compare_digest
from math import isfinite
from threading import Event, RLock
from time import monotonic
from typing import Annotated, Literal

from pydantic import Field, StrictBool, StrictInt, model_validator

from app.hardware.adapter_configuration import (
    CurrentContextRequest, CurrentContextResponse, CurrentDeviceState, CurrentPumpPosition,
)
from app.hardware.command_planning import PlanningModel, ValveTarget
from app.demo.hardware_contract import BottomValveState
from app.hardware.simulated_p1_runner import SimulationBlocked


class OperatorCredentialRejected(Exception):
    """No credential, identity or state is included in errors."""


class OperatorReferenceInput(PlanningModel):
    evidence_note: Annotated[str, Field(strict=True, min_length=1, max_length=2000)]
    observed_now_confirmed: StrictBool
    pumps: Annotated[tuple[CurrentPumpPosition, ...], Field(max_length=2)]
    valve_positions: Annotated[tuple[ValveTarget, ...], Field(max_length=8)]
    reactor_mixer_running: StrictBool | None
    sf_mixer_running: StrictBool | None
    sf_bottom_valve: BottomValveState | None
    column_position_degrees: StrictInt | None
    carousel_position: Annotated[StrictInt, Field(ge=1, le=40)] | None

    @model_validator(mode="after")
    def validate_confirmation(self):
        if not self.observed_now_confirmed or not self.evidence_note.strip():
            raise ValueError("new operator observation and explicit evidence are required")
        for entries in ([pump.pump_id for pump in self.pumps],
                        [valve.valve for valve in self.valve_positions]):
            if len(entries) != len(set(entries)):
                raise ValueError("duplicate operator reference")
        if self.column_position_degrees not in (None, 0, 4, 94):
            raise ValueError("Column reference must be unknown, HOME, CLOSED or OPEN")
        return self


class OperatorInputChallenge(PlanningModel):
    request_id: str
    purpose: Literal["RUN", "RECOVERY"]
    operator: str
    controller_boot_id: int
    connection_epoch: int
    remaining_seconds: float


class OperatorCurrentInput:
    """One pending request, explicit credential, bounded wait, no persisted state.

    HTTP/UI readers see only a pending challenge. They cannot create one, fill
    defaults, set observation time or supply an arbitrary operator name. A fresh
    declaration consumes the challenge once. Another attempt needs a new request.
    """

    def __init__(self, *, operator, credential, clock=monotonic):
        if type(operator) is not str or not operator.strip():
            raise ValueError("explicit operator identity required")
        if (type(credential) is not str or not credential.isascii()
            or len(credential) < 32 or any(char.isspace() for char in credential)):
            raise ValueError("explicit ASCII operator credential of at least 32 characters required")
        if not callable(clock):
            raise TypeError("monotonic clock required")
        self._operator = operator
        self.clock = clock
        self._credential_hash = sha256(credential.encode()).digest()
        self._lock = RLock()
        self._request = None
        self._event = None
        self._response = None
        self._failure = None
        self._closed = False

    @property
    def operator(self):
        return self._operator

    def _now(self):
        now = self.clock()
        if type(now) not in (float, int) or not isfinite(now):
            raise SimulationBlocked("invalid operator input clock")
        return now

    def _authenticate(self, credential):
        digest = sha256(credential.encode()).digest() if type(credential) is str else b""
        if not compare_digest(self._credential_hash, digest):
            raise OperatorCredentialRejected("operator credential rejected")

    def _cancel(self, reason):
        if self._request is not None:
            self._failure = reason
            self._response = None
            self._event.set()

    def pending(self):
        with self._lock:
            if self._request is None or self._response is not None or self._failure is not None:
                return None
            now = self._now()
            if not self._request.requested_at_monotonic <= now <= self._request.deadline_monotonic:
                self._cancel("operator input expired or monotonic clock changed")
                return None
            return OperatorInputChallenge(
                request_id=self._request.request_id, purpose=self._request.purpose,
                operator=self.operator, controller_boot_id=self._request.controller_boot_id,
                connection_epoch=self._request.connection_epoch,
                remaining_seconds=self._request.deadline_monotonic - now,
            )

    def __call__(self, request):
        if type(request) is not CurrentContextRequest:
            raise TypeError("explicit configured current request required")
        with self._lock:
            if self._closed or self._request is not None:
                raise SimulationBlocked("operator current input unavailable or already pending")
            now = self._now()
            if not request.requested_at_monotonic <= now < request.deadline_monotonic:
                raise SimulationBlocked("operator current input request expired")
            self._request, self._event = request, Event()
            self._response = self._failure = None
            event = self._event
            remaining = request.deadline_monotonic - now
        try:
            if not event.wait(remaining):
                raise SimulationBlocked("fresh operator current input timed out")
            with self._lock:
                if self._failure is not None:
                    raise SimulationBlocked(self._failure)
                if self._response is None:
                    raise SimulationBlocked("operator current input unavailable")
                return self._response
        finally:
            with self._lock:
                self._request = self._event = self._response = self._failure = None

    def submit(self, request_id, references, *, credential):
        with self._lock:
            self._authenticate(credential)
            if (self._closed or self._request is None or self._response is not None
                or self._failure is not None or request_id != self._request.request_id):
                raise SimulationBlocked("operator current input request is no longer pending")
            if type(references) is not OperatorReferenceInput:
                raise TypeError("explicit operator reference input required")
            references = OperatorReferenceInput.model_validate(references.model_dump())
            now = self._now()
            if not self._request.requested_at_monotonic <= now <= self._request.deadline_monotonic:
                self._cancel("operator current input expired or monotonic clock changed")
                raise SimulationBlocked("operator current input expired")
            state = CurrentDeviceState(
                operator=self.operator, observed_at_monotonic=now,
                **references.model_dump(exclude={"observed_now_confirmed"}),
            )
            self._response = CurrentContextResponse(self._request, state)
            self._event.set()
            return {"request_id": request_id, "declaration_received": True}

    def cancel(self, request_id, *, credential):
        with self._lock:
            self._authenticate(credential)
            if (self._request is None or self._response is not None or self._failure is not None
                or request_id != self._request.request_id):
                raise SimulationBlocked("operator current input request is no longer pending")
            self._cancel("operator current input cancelled")
            return {"request_id": request_id, "cancelled": True}

    def cancel_pending(self):
        with self._lock:
            self._cancel("operator current input cancelled by Stop")

    def close(self):
        with self._lock:
            self._closed = True
            self._cancel("operator current input source closed")
