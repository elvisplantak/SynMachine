"""Explicit settings and per-request current input for the existing adapter path.

No environment loader, transport activation, diagnostic API or physical trust is
added. Current positions never belong in persistent configuration. The provider
receives correlation only; it must independently obtain current operator/state
evidence and cannot turn STATUS, old journals or a new boot into position proof.
"""

from collections.abc import Callable
from dataclasses import dataclass
from math import isfinite
from time import monotonic, sleep
from typing import Annotated, Literal, Self
from uuid import uuid4

from pydantic import Field, StrictBool, StrictFloat, StrictInt, model_validator

from app.demo.calibration_models import PumpCalibrationSet, PumpId
from app.demo.hardware_contract import BottomValveState
from app.demo.maintenance_plan import MaintenanceKind, MaintenancePlan
from app.demo.operation_models import SymbolicRouteId
from app.hardware.arduino_serial import ArduinoSerialConfiguration
from app.hardware.command_planning import (
    CommandPlanningContext, CurrentInputAttribution, PlanningModel, PumpPlanningState, RouteSequence, ValveTarget,
)
from app.hardware.execution_timer import MonotonicExecutionTimer
from app.hardware.sf_bottom_valve import SfBottomValveConfiguration
from app.hardware.simulated_p1_runner import SimulationBlocked

Nonempty = Annotated[str, Field(strict=True, min_length=1)]
Finite = Annotated[StrictFloat, Field(allow_inf_nan=False)]
REQUIRED_COMMANDS = frozenset({
    "PUMP_HOME", "PUMP_MOVE_ABSOLUTE_STEPS", "VALVE_HOME", "VALVE_SET_POSITION",
    "COLUMN_BOTTOM_VALVE_HOME", "COLUMN_BOTTOM_VALVE_SET_POSITION",
    "CAROUSEL_SET_REFERENCE", "CAROUSEL_MOVE_TO_POSITION", "SF_MIXER_SET_STATE",
})


class ArduinoAdapterSettings(PlanningModel):
    port: Nonempty
    baud_rate: Annotated[StrictInt, Field(gt=0)]
    reset_settle_seconds: Annotated[Finite, Field(ge=0)]
    handshake_timeout_seconds: Annotated[Finite, Field(gt=0)]
    command_timeout_seconds: Annotated[Finite, Field(gt=0)]
    read_chunk_size: Annotated[StrictInt, Field(ge=1, le=512)]

    def adapter_configuration(self):
        return ArduinoSerialConfiguration(**self.model_dump())

    @model_validator(mode="after")
    def validate_adapter(self) -> Self:
        self.adapter_configuration()
        return self


class SfAdapterSettings(PlanningModel):
    port: Nonempty
    baud_rate: Annotated[StrictInt, Field(gt=0)]
    device_id: Annotated[StrictInt, Field(ge=0, le=252)]
    closed_position: StrictInt
    open_position: StrictInt
    profile_velocity: Annotated[StrictInt, Field(ge=0)]
    profile_acceleration: Annotated[StrictInt, Field(ge=0)]
    position_tolerance: Annotated[StrictInt, Field(ge=0)]
    motion_timeout_seconds: Annotated[Finite, Field(gt=0)]
    poll_interval_seconds: Annotated[Finite, Field(ge=0)]

    def adapter_configuration(self):
        return SfBottomValveConfiguration(**self.model_dump())

    @model_validator(mode="after")
    def validate_adapter(self) -> Self:
        if not self.port.strip():
            raise ValueError("SF port must not be blank")
        self.adapter_configuration()
        return self


class AdapterExecutionConfiguration(PlanningModel):
    """Serializable planning inputs, never current state or a live-work permit."""

    profile_id: Nonempty
    evidence_note: Nonempty
    calibration_scope: Literal["DEMO_NOMINAL", "WORKING_VERIFIED"]
    current_context_timeout_seconds: Annotated[Finite, Field(gt=0)]
    arduino: ArduinoAdapterSettings
    sf: SfAdapterSettings
    calibrations: PumpCalibrationSet
    route_sequences: tuple[RouteSequence, ...]
    recovery_plan: MaintenancePlan
    flush_plan: MaintenancePlan

    @model_validator(mode="after")
    def validate_coherence(self) -> Self:
        if not self.profile_id.strip() or not self.evidence_note.strip():
            raise ValueError("profile identity and evidence must not be blank")
        if self.arduino.port.strip() == self.sf.port.strip():
            raise ValueError("Arduino and SF ports must be distinct")
        routes = [route.route_id for route in self.route_sequences]
        if len(routes) != len(set(routes)) or set(routes) != set(SymbolicRouteId):
            raise ValueError("full execution configuration needs each explicit route sequence once")
        for plan, kind in ((self.recovery_plan, MaintenanceKind.RECOVERY),
                           (self.flush_plan, MaintenanceKind.FLUSH)):
            if plan.kind is not kind or plan.calibrations != self.calibrations:
                raise ValueError("maintenance kind/calibration differs from configuration")
        for calibration in (self.calibrations.p1, self.calibrations.p2):
            if calibration.working_empty_chamber_position_steps > 20500:
                raise ValueError("working calibration exceeds the existing firmware travel boundary")
        return self


class CurrentPumpPosition(PlanningModel):
    pump_id: PumpId
    position_steps: Annotated[StrictInt, Field(ge=0, le=20500)] | None


class CurrentDeviceState(PlanningModel):
    """Explicit present evidence; null/missing reference stays unknown.

    Evidence text records a caller statement, not authenticated hardware proof.
    No calibration, route order, phase identity or boot is accepted from here.
    """

    operator: Nonempty
    evidence_note: Nonempty
    observed_at_monotonic: Finite
    pumps: tuple[CurrentPumpPosition, ...]
    valve_positions: tuple[ValveTarget, ...]
    reactor_mixer_running: StrictBool | None
    sf_mixer_running: StrictBool | None
    sf_bottom_valve: BottomValveState | None
    column_position_degrees: StrictInt | None
    carousel_position: Annotated[StrictInt, Field(ge=1, le=40)] | None

    @model_validator(mode="after")
    def validate_state(self) -> Self:
        if not self.operator.strip() or not self.evidence_note.strip():
            raise ValueError("current state needs explicit operator and evidence")
        for entries in ([pump.pump_id for pump in self.pumps],
                        [valve.valve for valve in self.valve_positions]):
            if len(entries) != len(set(entries)):
                raise ValueError("duplicate current reference")
        if self.column_position_degrees not in (None, 0, 4, 94):
            raise ValueError("Column reference must be unknown, HOME, CLOSED or OPEN")
        return self


@dataclass(frozen=True)
class CurrentContextRequest:
    request_id: str
    controller_boot_id: int
    backend_session_nonce: str
    connection_epoch: int
    purpose: Literal["RUN", "RECOVERY"]
    requested_at_monotonic: float
    deadline_monotonic: float


@dataclass(frozen=True)
class CurrentContextResponse:
    request: CurrentContextRequest
    state: CurrentDeviceState


class AdapterCurrentContextProvider:
    """One worker/callback boundary; no cached readiness or physical commands.

    Each request must receive newly obtained evidence within that request's time
    interval. This detects cached/foreign replies, not a dishonest caller that
    relabels history. Completed owned commands remain the continuity source once
    execution begins. Restart or Service work never reconstructs that continuity.
    """

    def __init__(self, configuration, callback, *, clock=monotonic):
        if type(configuration) is not AdapterExecutionConfiguration or not callable(callback):
            raise TypeError("explicit execution configuration and current-state callback required")
        if not callable(clock):
            raise TypeError("monotonic clock required")
        self.configuration = AdapterExecutionConfiguration.model_validate(configuration.model_dump())
        self._callback = callback
        self._clock = clock
        self._identity = None
        self._capabilities = None

    @property
    def operator_input_source(self):
        from app.hardware.operator_current_input import OperatorCurrentInput
        return self._callback if type(self._callback) is OperatorCurrentInput else None

    @staticmethod
    def _connection(arduino):
        if not arduino.connected or arduino.controller_boot_id is None:
            raise SimulationBlocked("current input requires a connected trusted controller")
        return (arduino.controller_boot_id, arduino.backend_session_nonce, arduino.connection_epoch)

    def bootstrap(self, arduino):
        if self._identity is not None:
            raise SimulationBlocked("current-context provider cannot be reused across connections")
        if not REQUIRED_COMMANDS <= arduino.capabilities:
            raise SimulationBlocked("configured execution requires all controller command capabilities")
        self._identity = self._connection(arduino)
        self._capabilities = arduino.capabilities
        return self._context(())

    def _context(self, positions, state=None):
        positions = {pump.pump_id: pump.position_steps for pump in positions}
        return CommandPlanningContext(
            phase_execution_id=str(uuid4()), controller_boot_id=self._identity[0],
            pumps=tuple(PumpPlanningState(calibration=calibration,
                        position_steps=positions.get(calibration.pump_id))
                        for calibration in (self.configuration.calibrations.p1,
                                            self.configuration.calibrations.p2)),
            route_sequences=self.configuration.route_sequences,
            valve_positions=() if state is None else state.valve_positions,
            reactor_mixer_running=None if state is None else state.reactor_mixer_running,
            sf_bottom_valve=None if state is None else state.sf_bottom_valve,
            column_position_degrees=None if state is None else state.column_position_degrees,
            carousel_position=None if state is None else state.carousel_position,
        )

    def acquire(self, arduino, purpose):
        if purpose not in ("RUN", "RECOVERY"):
            raise ValueError("explicit current-context purpose required")
        if (self._identity is None or self._connection(arduino) != self._identity
            or arduino.capabilities != self._capabilities):
            raise SimulationBlocked("current-context controller session changed")
        before = self._clock()
        if type(before) not in (int, float) or not isfinite(before):
            raise SimulationBlocked("invalid current-context monotonic clock")
        deadline = before + self.configuration.current_context_timeout_seconds
        if not isfinite(deadline):
            raise SimulationBlocked("invalid current-context deadline")
        request = CurrentContextRequest(str(uuid4()), *self._identity, purpose, before, deadline)
        response = self._callback(request)
        after = self._clock()
        if (self._connection(arduino) != self._identity
            or arduino.capabilities != self._capabilities):
            raise SimulationBlocked("controller session changed while acquiring current input")
        if type(response) is not CurrentContextResponse or response.request is not request:
            raise SimulationBlocked("current input response is stale or foreign")
        if type(response.state) is not CurrentDeviceState:
            raise TypeError("explicit current device state required")
        state = CurrentDeviceState.model_validate(response.state.model_dump())
        if (type(after) not in (int, float) or not isfinite(after)
            or not before <= state.observed_at_monotonic <= after):
            raise SimulationBlocked("current input must be observed within this fresh request")
        if after > deadline:
            raise SimulationBlocked("current input response exceeded its configured deadline")
        context = self._context(state.pumps, state)
        if state.reactor_mixer_running is not False:
            raise SimulationBlocked("current Reactor mixer state must be explicitly stopped")
        if purpose == "RUN":
            if (any(pump.position_steps != pump.calibration.working_empty_chamber_position_steps
                    for pump in context.pumps)
                or {valve.valve for valve in state.valve_positions} != {f"V{i}" for i in range(1, 9)}
                or state.sf_mixer_running is not False
                or state.sf_bottom_valve is not BottomValveState.CLOSED
                or state.column_position_degrees is None or state.carousel_position is None):
                raise SimulationBlocked("new run requires complete independently established current references")
        elif state.carousel_position != self.configuration.recovery_plan.recovery.carousel_position:
            raise SimulationBlocked("current manual alignment differs from recovery plan")
        if self.operator_input_source is not None:
            # Stored with existing plan assumptions as history only. Restart or
            # later execution must never treat this receipt as fresh readiness.
            context = context.model_copy(update={"current_input_attribution": CurrentInputAttribution(
                request_id=request.request_id, purpose=purpose, operator=state.operator,
                evidence_note=state.evidence_note, observed_at_monotonic=state.observed_at_monotonic,
                attribution_method="OPERATOR_CREDENTIAL",
            )})
        return context, state.sf_mixer_running


def build_configured_adapter_application_execution(
    bundle, configuration, *, current_state_provider: Callable,
    arduino_port_factory, sf_session_factory,
    context_clock=monotonic, timer_factory=MonotonicExecutionTimer,
    arduino_monotonic=monotonic, arduino_sleep=sleep,
    sf_monotonic=monotonic, sf_sleep=sleep,
):
    """Delegate to the existing composition; explicit test transports required.

    This preparation milestone supplies no default real transport factory or
    production/environment entry point. Callers must not treat a profile as
    permission to activate real ports or execute physical work.
    """
    from app.hardware.adapter_application import build_adapter_application_execution

    if not callable(arduino_port_factory) or not callable(sf_session_factory):
        raise TypeError("explicit transport factories are required for preparation")
    provider = AdapterCurrentContextProvider(configuration, current_state_provider, clock=context_clock)
    configuration = provider.configuration
    source = provider.operator_input_source
    if source is not None and source.clock is not context_clock:
        raise ValueError("operator source and configured provider must share the monotonic clock")
    return build_adapter_application_execution(
        bundle, configuration.arduino.adapter_configuration(), configuration.sf.adapter_configuration(),
        configuration.calibrations, current_context_provider=provider,
        recovery_plan=configuration.recovery_plan, flush_plan=configuration.flush_plan,
        timer_factory=timer_factory, arduino_port_factory=arduino_port_factory,
        arduino_monotonic=arduino_monotonic, arduino_sleep=arduino_sleep,
        sf_session_factory=sf_session_factory, sf_monotonic=sf_monotonic, sf_sleep=sf_sleep,
    )
