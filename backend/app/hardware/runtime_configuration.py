from __future__ import annotations

from collections.abc import Mapping

from app.hardware.sf_bottom_valve import (
    SfBottomValveActuator,
    SfBottomValveConfiguration,
)


SF_BOTTOM_VALVE_PORT_ENVIRONMENT_VARIABLE = "LABFORGE_SF_BOTTOM_VALVE_PORT"


def build_sf_bottom_valve_from_environment(
    environment: Mapping[str, str],
) -> SfBottomValveActuator | None:
    port = environment.get(SF_BOTTOM_VALVE_PORT_ENVIRONMENT_VARIABLE, "").strip()
    if not port:
        return None
    return SfBottomValveActuator(SfBottomValveConfiguration(port=port))
