from dataclasses import dataclass
from decimal import Decimal

from app.demo.calibration_models import PumpId
from app.demo.hardware_contract import (
    AspirateCommand,
    BottomValveState,
    DispenseCommand,
    HardwareCommand,
    HardwareCommandKind,
    HardwareContract,
    MoveCarouselCommand,
    SelectRouteCommand,
    SetColumnBottomValveCommand,
    SetSfBottomValveCommand,
)
from app.demo.operation_models import SymbolicRouteId


@dataclass(frozen=True)
class FailureSelection:
    command_kind: HardwareCommandKind
    invocation: int = 1

    def __post_init__(self) -> None:
        if self.invocation < 1:
            raise ValueError("failure invocation must be at least 1")


class SimulatedHardwareCommandError(RuntimeError):
    """Deterministic fake failure; it makes no claim about physical hardware."""

    def __init__(self, command: HardwareCommand, invocation: int) -> None:
        self.command = command
        self.invocation = invocation
        super().__init__(
            f"simulated {command.kind} failure on invocation {invocation}"
        )


class FakeHardwareAdapter(HardwareContract):
    """Explicit fake whose successful returns mean simulated command success only."""

    def __init__(self, fail_on: FailureSelection | None = None) -> None:
        self.command_history: list[HardwareCommand] = []
        self._fail_on = fail_on
        self._invocations: dict[HardwareCommandKind, int] = {}

    def _record(self, command: HardwareCommand) -> None:
        self.command_history.append(command)
        invocation = self._invocations.get(command.kind, 0) + 1
        self._invocations[command.kind] = invocation
        if (
            self._fail_on is not None
            and command.kind == self._fail_on.command_kind
            and invocation == self._fail_on.invocation
        ):
            raise SimulatedHardwareCommandError(command, invocation)

    def select_route(self, route_id: SymbolicRouteId) -> None:
        self._record(SelectRouteCommand(route_id=route_id))

    def aspirate(self, pump_id: PumpId, nominal_volume_ml: Decimal) -> None:
        self._record(
            AspirateCommand(
                pump_id=pump_id,
                nominal_volume_ml=nominal_volume_ml,
            )
        )

    def dispense(self, pump_id: PumpId, nominal_volume_ml: Decimal) -> None:
        self._record(
            DispenseCommand(
                pump_id=pump_id,
                nominal_volume_ml=nominal_volume_ml,
            )
        )

    def set_sf_bottom_valve(self, state: BottomValveState) -> None:
        self._record(SetSfBottomValveCommand(state=state))

    def set_column_bottom_valve(self, state: BottomValveState) -> None:
        self._record(SetColumnBottomValveCommand(state=state))

    def move_carousel_to_next_fraction(
        self,
        source_fraction_number: int,
        destination_fraction_number: int,
    ) -> None:
        self._record(
            MoveCarouselCommand(
                source_fraction_number=source_fraction_number,
                destination_fraction_number=destination_fraction_number,
            )
        )
