"""Offline lowering of scheduler operations; never opens or commands hardware.

All positions are caller-supplied planning assumptions, not observations. A
future runtime must establish them in the expected boot, persist command intent,
exclude competing Service commands, and resolve each outcome before advancing.
"""

from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Annotated, Literal, Self
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, model_validator

from app.demo.calibration_models import PumpCalibration, PumpId
from app.demo.hardware_contract import BottomValveState
from app.demo.operation_models import (
    AspirateFromSfOperation,
    AspirateOperation,
    CollectColumnFractionOperation,
    DispenseOperation,
    MoveCarouselToNextFractionOperation,
    OperationKind,
    PlannedOperation,
    PrepareColumnFractionCollectionOperation,
    PrepareSfToColumnTransferOperation,
    SelectRouteOperation,
    TimedSfOperation,
    PausableWaitOperation,
    SymbolicRouteId,
)
from app.hardware.provenance import reject_lost_keys
from app.protocol.models import PhaseExecutionId, UINT32_MAX


class CommandPlanningError(ValueError):
    """No complete command plan can be produced from the supplied assumptions."""


ValveId = Literal["V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8"]


class PlanningModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="wrap")
    @classmethod
    def preserve_input_keys(cls, value, handler):
        validated = handler(value)
        reject_lost_keys(value, validated)
        return validated


class ValveTarget(PlanningModel):
    valve: ValveId
    position_degrees: Annotated[StrictInt, Field(ge=0, le=180)]

    @model_validator(mode="after")
    def validate_position(self) -> Self:
        if self.position_degrees not in (0, 90, 180):
            raise ValueError("valve position must be 0, 90, or 180")
        return self


# Derived from the approved tubing graph and nominal k1-k2/k1-k3 mapping.
# These are final target sets ONLY, not verified fluid routes or safe switching
# sequences. There is deliberately no default switching order.
_ROUTE_TARGETS = {
    SymbolicRouteId.S_TO_P1: {"V6": 180, "V1": 90},
    SymbolicRouteId.B1_TO_P1: {"V4": 180, "V6": 90, "V1": 90},
    SymbolicRouteId.B2_TO_P1: {"V4": 90, "V6": 90, "V1": 90},
    SymbolicRouteId.P1_TO_REACTOR: {"V1": 180, "V2": 90},
    SymbolicRouteId.REACTOR_TO_P2: {"V3": 90},
    SymbolicRouteId.P2_TO_SF_TOP: {"V3": 180, "V7": 180},
    SymbolicRouteId.SF_BOTTOM_TO_P2: {"V3": 180, "V7": 90, "V8": 180},
    SymbolicRouteId.P2_TO_COLUMN: {"V3": 180, "V7": 90, "V8": 90, "V5": 90},
}

_ASPIRATION_ROUTES = {
    SymbolicRouteId.S_TO_P1: PumpId.P1,
    SymbolicRouteId.B1_TO_P1: PumpId.P1,
    SymbolicRouteId.B2_TO_P1: PumpId.P1,
    SymbolicRouteId.REACTOR_TO_P2: PumpId.P2,
    SymbolicRouteId.SF_BOTTOM_TO_P2: PumpId.P2,
}
_DISPENSE_ROUTES = {
    SymbolicRouteId.P1_TO_REACTOR: PumpId.P1,
    SymbolicRouteId.P2_TO_SF_TOP: PumpId.P2,
    SymbolicRouteId.P2_TO_COLUMN: PumpId.P2,
}


class RouteSequence(PlanningModel):
    """Explicit proposed order for offline review, not physical authorization."""

    route_id: SymbolicRouteId
    targets: tuple[ValveTarget, ...]

    @model_validator(mode="after")
    def validate_targets(self) -> Self:
        targets = {target.valve: target.position_degrees for target in self.targets}
        if len(targets) != len(self.targets) or targets != _ROUTE_TARGETS[self.route_id]:
            raise ValueError("route targets must exactly match the nominal topology")
        return self


class PumpPlanningState(PlanningModel):
    calibration: PumpCalibration
    position_steps: Annotated[StrictInt, Field(ge=0, le=20500)]

    @model_validator(mode="after")
    def validate_position(self) -> Self:
        full = self.calibration.working_full_chamber_position_steps
        empty = self.calibration.working_empty_chamber_position_steps
        if empty > 20500 or not full <= self.position_steps <= empty:
            raise ValueError("pump position and working range must fit 0..20500")
        return self


class CommandPlanningContext(PlanningModel):
    phase_execution_id: PhaseExecutionId
    # Conservative planning boundary: exclude the boot-counter exhaustion value.
    controller_boot_id: Annotated[StrictInt, Field(ge=1, le=UINT32_MAX - 1)]
    pumps: tuple[PumpPlanningState, ...] = ()
    valve_positions: tuple[ValveTarget, ...] = ()
    route_sequences: tuple[RouteSequence, ...] = ()
    reactor_mixer_running: StrictBool | None = None
    sf_bottom_valve: BottomValveState | None = None
    column_position_degrees: StrictInt | None = None
    # Physical tube aligned for fraction 1; never assumed to be tube 1.
    carousel_position: Annotated[StrictInt, Field(ge=1, le=40)] | None = None

    @model_validator(mode="after")
    def validate_unique_entries(self) -> Self:
        for values in (
            [pump.calibration.pump_id for pump in self.pumps],
            [target.valve for target in self.valve_positions],
            [route.route_id for route in self.route_sequences],
        ):
            if len(values) != len(set(values)):
                raise ValueError("duplicate planning state or route")
        if self.column_position_degrees not in (None, 0, 4, 94):
            raise ValueError("column position must be unknown, HOME, CLOSED, or OPEN")
        return self


@dataclass(frozen=True)
class ArduinoAction:
    operation_command_id: str
    command: str
    arguments: tuple[tuple[str, str | int | bool], ...]


@dataclass(frozen=True)
class SfBottomValveAction:
    operation_command_id: str
    state: BottomValveState


@dataclass(frozen=True)
class CollectionWait:
    duration_seconds: Decimal
    stop_interruptible: Literal[True] = True


@dataclass(frozen=True)
class PausableWait:
    duration_seconds: Decimal
    pause_supported: Literal[True] = True


Action = ArduinoAction | SfBottomValveAction | CollectionWait | PausableWait


@dataclass(frozen=True)
class PreparedOperation:
    operation_number: int
    operation_kind: OperationKind
    actions: tuple[Action, ...]
    # Must be attempted even if a primary action fails. No normal Stop boundary
    # inside an operation. CollectionWait alone may end early on Stop.
    required_followup: tuple[Action, ...] = ()


@dataclass(frozen=True)
class PreparedCommandPlan:
    assumptions: CommandPlanningContext
    operations: tuple[PreparedOperation, ...]
    projected_pump_positions: tuple[tuple[PumpId, int], ...]
    # Projection is valid ONLY if every operation completes successfully.
    projected_carousel_position: int | None


def prepare_command_plan(
    operations: tuple[PlannedOperation, ...], context: CommandPlanningContext
) -> PreparedCommandPlan:
    """Preflight the whole plan without I/O, rounding, homing, or state updates.

    Command IDs depend on phase identity and action slot, not mutable arguments.
    Changed arguments in a reused slot conflict in the durable command journal.
    A future runtime must also persist and compare the entire immutable plan:
    per-command IDs alone cannot detect changes to order or omitted actions.
    This function neither persists nor grants permission to execute the result.
    """
    return _Planner(context).prepare(operations)


class _Planner:
    def __init__(self, context: CommandPlanningContext) -> None:
        self.context = context
        self.pumps = {pump.calibration.pump_id: pump for pump in context.pumps}
        self.positions = {pump_id: pump.position_steps for pump_id, pump in self.pumps.items()}
        self.valves = {target.valve: target.position_degrees for target in context.valve_positions}
        self.routes = {route.route_id: route for route in context.route_sequences}
        self.active_route: SymbolicRouteId | None = None
        self.sf = context.sf_bottom_valve
        self.column = context.column_position_degrees
        self.carousel = context.carousel_position
        self.next_fraction = 1
        self.last_collected = 0
        self.operation_number = 0

    def _id(self, slot: str) -> str:
        return str(
            uuid5(
                NAMESPACE_URL,
                (f"labforge:{self.context.phase_execution_id}:{self.operation_number}:{slot}"),
            )
        )

    def _arduino(self, slot: str, command: str, **arguments: str | int | bool) -> ArduinoAction:
        return ArduinoAction(self._id(slot), command, tuple(arguments.items()))

    def _column(self, state: BottomValveState, slot: str) -> tuple[Action, ...]:
        if self.column is None:
            raise CommandPlanningError("Column HOME reference is required")
        target = 4 if state is BottomValveState.CLOSED else 94
        if self.column == target:
            return ()
        self.column = target
        return (
            self._arduino(slot, "COLUMN_BOTTOM_VALVE_SET_POSITION", position_degrees=self.column),
        )

    def _sf(self, state: BottomValveState, slot: str) -> SfBottomValveAction:
        self.sf = state
        return SfBottomValveAction(self._id(slot), state)

    def _route(self, route_id: SymbolicRouteId) -> tuple[Action, ...]:
        route = self.routes.get(route_id)
        if route is None:
            raise CommandPlanningError(f"explicit switching sequence required for {route_id}")
        if (
            route_id
            in {
                SymbolicRouteId.REACTOR_TO_P2,
                SymbolicRouteId.P2_TO_SF_TOP,
                SymbolicRouteId.SF_BOTTOM_TO_P2,
                SymbolicRouteId.P2_TO_COLUMN,
            }
            and self.sf is not BottomValveState.CLOSED
        ):
            raise CommandPlanningError("P2 route switching requires SF bottom valve CLOSED")
        if route_id in {SymbolicRouteId.REACTOR_TO_P2, SymbolicRouteId.P2_TO_SF_TOP}:
            if self.context.reactor_mixer_running is not False:
                raise CommandPlanningError("Reactor-to-SF transfer requires Reactor mixer OFF")
        if route_id is SymbolicRouteId.P2_TO_COLUMN and self.column != 4:
            raise CommandPlanningError("Column filling requires Column CLOSED")
        actions: list[Action] = []
        for target in route.targets:
            if target.valve not in self.valves:
                raise CommandPlanningError(f"{target.valve} reference/position is unknown")
            if self.valves[target.valve] != target.position_degrees:
                # Valve-specific slots remain stable when a no-op is omitted.
                actions.append(
                    self._arduino(
                        f"valve:{target.valve}",
                        "VALVE_SET_POSITION",
                        valve=target.valve,
                        position_degrees=target.position_degrees,
                    )
                )
                self.valves[target.valve] = target.position_degrees
        self.active_route = route_id
        return tuple(actions)

    def _pump(self, pump_id: PumpId, volume: Decimal, aspirate: bool) -> ArduinoAction:
        allowed = _ASPIRATION_ROUTES if aspirate else _DISPENSE_ROUTES
        if allowed.get(self.active_route) is not pump_id:
            raise CommandPlanningError("pump operation does not match the selected route")
        pump = self.pumps.get(pump_id)
        if pump is None:
            raise CommandPlanningError(f"{pump_id} reference/position is unknown")
        if not volume.is_finite() or volume <= 0:
            raise CommandPlanningError("pump volume must be finite and positive")
        calibration = pump.calibration
        # Exact rational arithmetic avoids Decimal context rounding at boundaries.
        steps = (
            Fraction(volume)
            * calibration.working_stroke_steps
            / Fraction(calibration.working_volume_ml)
        )
        if steps.denominator != 1:
            raise CommandPlanningError(
                "volume is not representable as whole steps; no rounding policy"
            )
        target = self.positions[pump_id] + (-int(steps) if aspirate else int(steps))
        if not (
            calibration.working_full_chamber_position_steps
            <= target
            <= calibration.working_empty_chamber_position_steps
        ):
            raise CommandPlanningError("pump target exceeds the configured working range")
        if not 1 <= target <= 20500:
            raise CommandPlanningError("absolute target must be 1..20500; HOME is not a transfer")
        self.positions[pump_id] = target
        return self._arduino(
            "pump", "PUMP_MOVE_ABSOLUTE_STEPS", pump=pump_id.value, target_steps=target
        )

    def prepare(self, operations: tuple[PlannedOperation, ...]) -> PreparedCommandPlan:
        prepared: list[PreparedOperation] = []
        for number, operation in enumerate(operations, 1):
            if operation.operation_number != number:
                raise CommandPlanningError("operation numbers must be contiguous from 1")
            self.operation_number = number
            actions: tuple[Action, ...]
            followup: tuple[Action, ...] = ()
            if isinstance(operation, PausableWaitOperation):
                actions = (PausableWait(operation.duration_seconds),)
            elif isinstance(operation, TimedSfOperation):
                if self.sf is not BottomValveState.CLOSED:
                    raise CommandPlanningError("timed SF phases require SF bottom valve CLOSED")
                wait = CollectionWait(operation.duration_seconds)
                if operation.operation_kind is OperationKind.TIMED_SF_MIXING:
                    actions = (
                        self._arduino("mixer-start", "SF_MIXER_SET_STATE", running=True),
                        wait,
                    )
                    followup = (self._arduino("mixer-stop", "SF_MIXER_SET_STATE", running=False),)
                else:
                    actions = (wait,)
            elif isinstance(operation, SelectRouteOperation):
                actions = self._route(operation.route_id)
            elif isinstance(operation, (AspirateOperation, DispenseOperation)):
                if self.active_route is SymbolicRouteId.SF_BOTTOM_TO_P2:
                    raise CommandPlanningError("SF aspiration requires the protected operation")
                actions = (
                    self._pump(
                        operation.pump_id,
                        operation.volume_ml,
                        isinstance(operation, AspirateOperation),
                    ),
                )
            elif isinstance(operation, PrepareSfToColumnTransferOperation):
                actions = (self._sf(BottomValveState.CLOSED, "sf-close"),)
                followup = self._column(BottomValveState.CLOSED, "column-close")
            elif isinstance(operation, AspirateFromSfOperation):
                if (
                    self.active_route is not SymbolicRouteId.SF_BOTTOM_TO_P2
                    or self.sf is not BottomValveState.CLOSED
                    or self.column != 4
                ):
                    raise CommandPlanningError(
                        "protected SF aspiration requires route and closed valves"
                    )
                actions = (
                    self._sf(BottomValveState.OPEN, "sf-open"),
                    self._pump(operation.pump_id, operation.volume_ml, True),
                )
                followup = (self._sf(BottomValveState.CLOSED, "sf-close"),)
            elif isinstance(operation, PrepareColumnFractionCollectionOperation):
                actions = self._column(BottomValveState.CLOSED, "column-close")
            elif isinstance(operation, CollectColumnFractionOperation):
                if (
                    self.carousel is None
                    or self.column != 4
                    or operation.fraction_count > 40
                    or operation.fraction_number != self.next_fraction
                    or self.last_collected == operation.fraction_number
                ):
                    raise CommandPlanningError(
                        "collection requires aligned unused tube and Column CLOSED"
                    )
                actions = (
                    *self._column(BottomValveState.OPEN, "column-open"),
                    CollectionWait(operation.configured_duration_seconds),
                )
                followup = self._column(BottomValveState.CLOSED, "column-close")
                self.last_collected = operation.fraction_number
            elif isinstance(operation, MoveCarouselToNextFractionOperation):
                if (
                    self.carousel is None
                    or self.column != 4
                    or operation.fraction_count > 40
                    or operation.source_fraction_number != self.last_collected
                    or operation.source_fraction_number != self.next_fraction
                ):
                    raise CommandPlanningError(
                        "carousel move requires completed collection and closed Column"
                    )
                self.carousel = self.carousel % 40 + 1
                self.next_fraction = operation.destination_fraction_number
                actions = (
                    self._arduino("carousel", "CAROUSEL_MOVE_TO_POSITION", position=self.carousel),
                )
            else:
                raise CommandPlanningError(f"unsupported operation {type(operation).__name__}")
            prepared.append(PreparedOperation(number, operation.operation_kind, actions, followup))
        return PreparedCommandPlan(
            self.context, tuple(prepared), tuple(sorted(self.positions.items())), self.carousel
        )
