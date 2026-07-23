from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from app.demo.calibration_models import PumpId
from app.demo.operation_models import SymbolicRouteId


class HardwareCommandKind(StrEnum):
    SELECT_ROUTE = "SELECT_ROUTE"
    ASPIRATE = "ASPIRATE"
    DISPENSE = "DISPENSE"
    SET_SF_BOTTOM_VALVE = "SET_SF_BOTTOM_VALVE"
    SET_COLUMN_BOTTOM_VALVE = "SET_COLUMN_BOTTOM_VALVE"
    MOVE_CAROUSEL_TO_NEXT_FRACTION = "MOVE_CAROUSEL_TO_NEXT_FRACTION"


class BottomValveState(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


@dataclass(frozen=True)
class SelectRouteCommand:
    route_id: SymbolicRouteId
    kind: HardwareCommandKind = field(
        init=False, default=HardwareCommandKind.SELECT_ROUTE
    )


@dataclass(frozen=True)
class AspirateCommand:
    pump_id: PumpId
    nominal_volume_ml: Decimal
    kind: HardwareCommandKind = field(init=False, default=HardwareCommandKind.ASPIRATE)


@dataclass(frozen=True)
class DispenseCommand:
    pump_id: PumpId
    nominal_volume_ml: Decimal
    kind: HardwareCommandKind = field(init=False, default=HardwareCommandKind.DISPENSE)


@dataclass(frozen=True)
class SetSfBottomValveCommand:
    state: BottomValveState
    kind: HardwareCommandKind = field(
        init=False, default=HardwareCommandKind.SET_SF_BOTTOM_VALVE
    )


@dataclass(frozen=True)
class SetColumnBottomValveCommand:
    state: BottomValveState
    kind: HardwareCommandKind = field(
        init=False, default=HardwareCommandKind.SET_COLUMN_BOTTOM_VALVE
    )


@dataclass(frozen=True)
class MoveCarouselCommand:
    source_fraction_number: int
    destination_fraction_number: int
    kind: HardwareCommandKind = field(
        init=False,
        default=HardwareCommandKind.MOVE_CAROUSEL_TO_NEXT_FRACTION,
    )


HardwareCommand = (
    SelectRouteCommand
    | AspirateCommand
    | DispenseCommand
    | SetSfBottomValveCommand
    | SetColumnBottomValveCommand
    | MoveCarouselCommand
)


class HardwareContract(ABC):
    """Semantic command boundary; success is not sensor confirmation."""

    @abstractmethod
    def select_route(self, route_id: SymbolicRouteId) -> None: ...

    @abstractmethod
    def aspirate(self, pump_id: PumpId, nominal_volume_ml: Decimal) -> None: ...

    @abstractmethod
    def dispense(self, pump_id: PumpId, nominal_volume_ml: Decimal) -> None: ...

    @abstractmethod
    def set_sf_bottom_valve(self, state: BottomValveState) -> None: ...

    @abstractmethod
    def set_column_bottom_valve(self, state: BottomValveState) -> None: ...

    @abstractmethod
    def move_carousel_to_next_fraction(
        self,
        source_fraction_number: int,
        destination_fraction_number: int,
    ) -> None: ...
