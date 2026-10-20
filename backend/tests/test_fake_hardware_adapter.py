from decimal import Decimal

import pytest

from app.demo.calibration_models import PumpId
from app.demo.fake_hardware_adapter import (
    FailureSelection,
    FakeHardwareAdapter,
    SimulatedHardwareCommandError,
)
from app.demo.hardware_contract import (
    AspirateCommand,
    BottomValveState,
    DispenseCommand,
    HardwareCommandKind,
    HardwareContract,
    MoveCarouselCommand,
    SelectRouteCommand,
    SetColumnBottomValveCommand,
    SetSfBottomValveCommand,
)
from app.demo.operation_models import SymbolicRouteId


def test_commands_succeed_and_are_recorded_in_exact_order_with_typed_arguments() -> None:
    adapter = FakeHardwareAdapter()

    adapter.select_route(SymbolicRouteId.B1_TO_P1)
    adapter.aspirate(PumpId.P1, Decimal("1.250"))
    adapter.set_sf_bottom_valve(BottomValveState.OPEN)
    adapter.set_sf_bottom_valve(BottomValveState.CLOSED)
    adapter.select_route(SymbolicRouteId.P2_TO_COLUMN)
    adapter.dispense(PumpId.P2, Decimal("2.500"))
    adapter.set_column_bottom_valve(BottomValveState.OPEN)
    adapter.set_column_bottom_valve(BottomValveState.CLOSED)
    adapter.move_carousel_to_next_fraction(3, 4)

    assert adapter.command_history == [
        SelectRouteCommand(route_id=SymbolicRouteId.B1_TO_P1),
        AspirateCommand(pump_id=PumpId.P1, nominal_volume_ml=Decimal("1.250")),
        SetSfBottomValveCommand(state=BottomValveState.OPEN),
        SetSfBottomValveCommand(state=BottomValveState.CLOSED),
        SelectRouteCommand(route_id=SymbolicRouteId.P2_TO_COLUMN),
        DispenseCommand(pump_id=PumpId.P2, nominal_volume_ml=Decimal("2.500")),
        SetColumnBottomValveCommand(state=BottomValveState.OPEN),
        SetColumnBottomValveCommand(state=BottomValveState.CLOSED),
        MoveCarouselCommand(source_fraction_number=3, destination_fraction_number=4),
    ]


def test_selected_command_invocation_fails_after_being_recorded() -> None:
    adapter = FakeHardwareAdapter(
        fail_on=FailureSelection(HardwareCommandKind.ASPIRATE, invocation=2)
    )

    adapter.aspirate(PumpId.P1, Decimal("1"))
    with pytest.raises(SimulatedHardwareCommandError) as error:
        adapter.aspirate(PumpId.P2, Decimal("2"))

    assert error.value.invocation == 2
    assert error.value.command == AspirateCommand(
        pump_id=PumpId.P2,
        nominal_volume_ml=Decimal("2"),
    )
    assert adapter.command_history[-1] == error.value.command


def test_command_kinds_are_fixed_and_not_constructor_arguments() -> None:
    commands = [
        (
            SelectRouteCommand(route_id=SymbolicRouteId.B1_TO_P1),
            HardwareCommandKind.SELECT_ROUTE,
        ),
        (
            AspirateCommand(PumpId.P1, Decimal("1")),
            HardwareCommandKind.ASPIRATE,
        ),
        (
            DispenseCommand(PumpId.P2, Decimal("2")),
            HardwareCommandKind.DISPENSE,
        ),
        (
            SetSfBottomValveCommand(BottomValveState.OPEN),
            HardwareCommandKind.SET_SF_BOTTOM_VALVE,
        ),
        (
            SetColumnBottomValveCommand(BottomValveState.CLOSED),
            HardwareCommandKind.SET_COLUMN_BOTTOM_VALVE,
        ),
        (
            MoveCarouselCommand(1, 2),
            HardwareCommandKind.MOVE_CAROUSEL_TO_NEXT_FRACTION,
        ),
    ]

    assert [command.kind for command, _ in commands] == [
        expected_kind for _, expected_kind in commands
    ]
    with pytest.raises(TypeError, match="unexpected keyword argument 'kind'"):
        SelectRouteCommand(
            route_id=SymbolicRouteId.B1_TO_P1,
            kind=HardwareCommandKind.DISPENSE,  # type: ignore[call-arg]
        )


@pytest.mark.parametrize("invocation", [0, -1])
def test_failure_selection_rejects_invocations_below_one(invocation: int) -> None:
    with pytest.raises(ValueError, match="failure invocation must be at least 1"):
        FailureSelection(HardwareCommandKind.ASPIRATE, invocation=invocation)


def test_fake_is_explicitly_created_and_implements_only_the_contract() -> None:
    adapter: HardwareContract = FakeHardwareAdapter()

    assert isinstance(adapter, FakeHardwareAdapter)
    assert adapter.command_history == []
    assert not hasattr(adapter, "serial")
    assert not hasattr(adapter, "hardware_mode")
