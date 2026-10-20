"""Explicit adapter resource composition, without environment activation.

Construction opens nothing. Application startup locks/validates the existing
bundle before connecting Serial. Tests inject fake transports; independent
current context, calibrations and readiness are never inferred here.
"""

from contextlib import contextmanager
from time import monotonic, sleep

from app.demo.calibration_models import PumpCalibrationSet
from app.hardware.arduino_serial import ArduinoSerialClient, ArduinoSerialConfiguration
from app.hardware.command_planning import CommandPlanningContext
from app.hardware.execution_timer import MonotonicExecutionTimer
from app.hardware.owned_application_execution import OwnedApplicationExecution
from app.hardware.prepared_adapter_device import PreparedAdapterDevice
from app.hardware.sf_bottom_valve import SfBottomValveActuator, SfBottomValveConfiguration
from app.hardware.simulated_p1_runner import SimulationBlocked


def build_adapter_application_execution(
    bundle, arduino_configuration, sf_configuration, calibrations, *,
    context_factory=None, sf_mixer_running=None, column_readiness=None,
    current_context_provider=None,
    recovery_plan=None, flush_plan=None,
    timer_factory=MonotonicExecutionTimer,
    arduino_port_factory=None, arduino_monotonic=monotonic, arduino_sleep=sleep,
    sf_session_factory=None, sf_monotonic=monotonic, sf_sleep=sleep,
    transport_mode="UNSPECIFIED", profile_id=None,
):
    """Prepare a caller-injected application, never connect or activate it here.

    context_factory(connected_boot_id) supplies independently established current
    state on the execution worker. The boot argument only binds that state to this
    connection; it must not be used to relabel historical position/reference data.
    Transport/clock injection uses the existing adapters' supported interfaces.
    """
    if (type(arduino_configuration) is not ArduinoSerialConfiguration
        or type(sf_configuration) is not SfBottomValveConfiguration
        or type(calibrations) is not PumpCalibrationSet):
        raise TypeError("explicit adapter configurations and calibrations are required")
    if current_context_provider is None:
        if not callable(context_factory):
            raise TypeError("independent current-context factory is required")
    else:
        from app.hardware.adapter_configuration import AdapterCurrentContextProvider
        if type(current_context_provider) is not AdapterCurrentContextProvider:
            raise TypeError("explicit current-context provider is required")
        if context_factory is not None or sf_mixer_running is not None:
            raise TypeError("configured current provider cannot mix with legacy state inputs")
    if sf_mixer_running is not None and type(sf_mixer_running) is not bool:
        raise TypeError("SF mixer state must be an explicit boolean or unknown")
    calibrations = PumpCalibrationSet.model_validate(calibrations.model_dump())

    @contextmanager
    def device_resources():
        arduino = ArduinoSerialClient(
            arduino_configuration,
            **({"port_factory": arduino_port_factory} if arduino_port_factory is not None else {}),
            monotonic=arduino_monotonic, sleep=arduino_sleep,
        )
        device = None
        try:
            arduino.connect()
            context = (context_factory(arduino.controller_boot_id)
                if current_context_provider is None else current_context_provider.bootstrap(arduino))
            if type(context) is not CommandPlanningContext:
                raise TypeError("independent current context must be a CommandPlanningContext")
            context = CommandPlanningContext.model_validate(context.model_dump())
            if current_context_provider is None and any(p.position_steps is None for p in context.pumps):
                raise SimulationBlocked("legacy current context requires explicit pump positions")
            expected = {p.pump_id: p for p in (calibrations.p1, calibrations.p2)}
            if {p.calibration.pump_id: p.calibration for p in context.pumps} != expected:
                raise SimulationBlocked("current-context calibrations differ from application inputs")
            sf = SfBottomValveActuator(
                sf_configuration,
                **({"session_factory": sf_session_factory} if sf_session_factory is not None else {}),
                clock=sf_monotonic, sleep=sf_sleep,
            )
            device = PreparedAdapterDevice(
                context, arduino, sf, current_context_provider=current_context_provider
            )
            device.sf_mixer_running = sf_mixer_running
            yield device
        finally:
            if device is not None:
                device.close()
            # No torque write or actuator command is an implicit teardown action.
            # SF sessions already close in the existing actuator's own scope.
            arduino.close()

    return OwnedApplicationExecution(
        bundle, device_resources, calibrations, timer_factory=timer_factory,
        column_readiness=column_readiness, recovery_plan=recovery_plan,
        flush_plan=flush_plan,
        current_context_provider=current_context_provider,
        transport_mode=transport_mode, profile_id=profile_id,
        operator_input_source=(None if current_context_provider is None
                               else current_context_provider.operator_input_source),
    )
