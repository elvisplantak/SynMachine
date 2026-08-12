from decimal import Decimal

from app.demo.calibration_models import PumpId
from app.demo.hardware_contract import BottomValveState, HardwareContract
from app.demo.operation_models import SymbolicRouteId
from app.hardware.sf_bottom_valve import SfBottomValveControl


class DynamixelSfBottomValveAdapter(HardwareContract):
    """Adds the host-connected SF valve to another HardwareContract."""

    def __init__(
        self,
        arduino_hardware: HardwareContract,
        sf_bottom_valve: SfBottomValveControl,
    ) -> None:
        self._arduino_hardware = arduino_hardware
        self._sf_bottom_valve = sf_bottom_valve

    def select_route(self, route_id: SymbolicRouteId) -> None:
        self._arduino_hardware.select_route(route_id)

    def aspirate(self, pump_id: PumpId, nominal_volume_ml: Decimal) -> None:
        self._arduino_hardware.aspirate(pump_id, nominal_volume_ml)

    def dispense(self, pump_id: PumpId, nominal_volume_ml: Decimal) -> None:
        self._arduino_hardware.dispense(pump_id, nominal_volume_ml)

    def set_sf_bottom_valve(self, state: BottomValveState) -> None:
        self._sf_bottom_valve.set_state(state)

    def set_column_bottom_valve(self, state: BottomValveState) -> None:
        self._arduino_hardware.set_column_bottom_valve(state)

    def move_carousel_to_next_fraction(
        self,
        source_fraction_number: int,
        destination_fraction_number: int,
    ) -> None:
        self._arduino_hardware.move_carousel_to_next_fraction(
            source_fraction_number,
            destination_fraction_number,
        )
