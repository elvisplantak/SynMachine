from decimal import Decimal

from app.demo.calibration_models import PumpId
from app.demo.fake_hardware_adapter import FakeHardwareAdapter
from app.demo.hardware_contract import (
    AspirateCommand,
    BottomValveState,
    MoveCarouselCommand,
    SelectRouteCommand,
    SetColumnBottomValveCommand,
)
from app.demo.operation_models import SymbolicRouteId
from app.hardware.composite_adapter import DynamixelSfBottomValveAdapter


class RecordingSfActuator:
    def __init__(self) -> None:
        self.states: list[BottomValveState] = []

    def set_state(self, state: BottomValveState) -> None:
        self.states.append(state)


def test_only_sf_bottom_valve_is_routed_to_dynamixel() -> None:
    arduino = FakeHardwareAdapter()
    sf = RecordingSfActuator()
    adapter = DynamixelSfBottomValveAdapter(arduino, sf)  # type: ignore[arg-type]

    adapter.select_route(SymbolicRouteId.REACTOR_TO_P2)
    adapter.aspirate(PumpId.P2, Decimal("1.5"))
    adapter.set_sf_bottom_valve(BottomValveState.OPEN)
    adapter.set_sf_bottom_valve(BottomValveState.CLOSED)
    adapter.set_column_bottom_valve(BottomValveState.CLOSED)
    adapter.move_carousel_to_next_fraction(4, 5)

    assert sf.states == [BottomValveState.OPEN, BottomValveState.CLOSED]
    assert arduino.command_history == [
        SelectRouteCommand(SymbolicRouteId.REACTOR_TO_P2),
        AspirateCommand(PumpId.P2, Decimal("1.5")),
        SetColumnBottomValveCommand(BottomValveState.CLOSED),
        MoveCarouselCommand(4, 5),
    ]
