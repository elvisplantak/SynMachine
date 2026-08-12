from app.hardware.runtime_configuration import (
    SF_BOTTOM_VALVE_PORT_ENVIRONMENT_VARIABLE,
    build_sf_bottom_valve_from_environment,
)


def test_missing_or_blank_port_disables_sf_bottom_valve_runtime() -> None:
    assert build_sf_bottom_valve_from_environment({}) is None
    assert (
        build_sf_bottom_valve_from_environment({SF_BOTTOM_VALVE_PORT_ENVIRONMENT_VARIABLE: "   "})
        is None
    )


def test_explicit_stable_port_builds_actuator_without_opening_hardware() -> None:
    actuator = build_sf_bottom_valve_from_environment(
        {
            SF_BOTTOM_VALVE_PORT_ENVIRONMENT_VARIABLE: (
                "/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_FTA2U3CN-if00-port0"
            )
        }
    )

    assert actuator is not None
