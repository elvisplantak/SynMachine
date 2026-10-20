from decimal import Decimal
from typing import Any, cast

import pytest

from app.demo.calibration_models import PumpId
from app.demo.fake_hardware_adapter import FakeHardwareAdapter
from app.demo.hardware_contract import (
    AspirateCommand,
    BottomValveState,
    DispenseCommand,
    HardwareContract,
    MoveCarouselCommand,
    SelectRouteCommand,
)
from app.demo.operation_executor import (
    CollectionTimer,
    CollectionTimerOutcome,
    OperationExecutionOutcome,
    OperationExecutor,
    ProtectedOperationError,
)
from app.demo.operation_models import (
    AspirateFromSfOperation,
    AspirateOperation,
    CollectColumnFractionOperation,
    DispenseOperation,
    MoveCarouselToNextFractionOperation,
    OperationKind,
    PrepareColumnFractionCollectionOperation,
    PrepareSfToColumnTransferOperation,
    SelectRouteOperation,
    SymbolicRouteId,
)

Event = tuple[object, ...]


class FakeCollectionTimer(CollectionTimer):
    def __init__(
        self,
        events: list[Event] | None = None,
        *,
        outcome: CollectionTimerOutcome = CollectionTimerOutcome.COMPLETED,
        error: Exception | None = None,
    ) -> None:
        self.events = events if events is not None else []
        self.outcome = outcome
        self.error = error

    def wait(self, duration_seconds: Decimal) -> CollectionTimerOutcome:
        self.events.append(("timer", duration_seconds))
        if self.error is not None:
            raise self.error
        return self.outcome


class ScriptedHardware(HardwareContract):
    def __init__(
        self,
        events: list[Event],
        failures: dict[Event, Exception] | None = None,
    ) -> None:
        self.events = events
        self.failures = failures or {}

    def _record(self, event: Event) -> None:
        self.events.append(event)
        error = self.failures.get(event)
        if error is not None:
            raise error

    def select_route(self, route_id: SymbolicRouteId) -> None:
        self._record(("select_route", route_id))

    def aspirate(self, pump_id: PumpId, nominal_volume_ml: Decimal) -> None:
        self._record(("aspirate", pump_id, nominal_volume_ml))

    def dispense(self, pump_id: PumpId, nominal_volume_ml: Decimal) -> None:
        self._record(("dispense", pump_id, nominal_volume_ml))

    def set_sf_bottom_valve(self, state: BottomValveState) -> None:
        self._record(("sf", state))

    def set_column_bottom_valve(self, state: BottomValveState) -> None:
        self._record(("column", state))

    def move_carousel_to_next_fraction(
        self,
        source_fraction_number: int,
        destination_fraction_number: int,
    ) -> None:
        self._record(
            ("carousel", source_fraction_number, destination_fraction_number)
        )


def executor(
    hardware: HardwareContract,
    timer: CollectionTimer | None = None,
) -> OperationExecutor:
    return OperationExecutor(hardware, timer or FakeCollectionTimer())


def select_route_operation() -> SelectRouteOperation:
    return SelectRouteOperation(
        operation_kind=OperationKind.SELECT_ROUTE,
        operation_number=1,
        cycle_number=1,
        cycle_count=1,
        route_id=SymbolicRouteId.REACTOR_TO_P2,
    )


def aspirate_operation() -> AspirateOperation:
    return AspirateOperation(
        operation_kind=OperationKind.ASPIRATE,
        operation_number=1,
        cycle_number=1,
        cycle_count=1,
        pump_id=PumpId.P2,
        volume_ml=Decimal("1.250"),
    )


def dispense_operation() -> DispenseOperation:
    return DispenseOperation(
        operation_kind=OperationKind.DISPENSE,
        operation_number=1,
        cycle_number=1,
        cycle_count=1,
        pump_id=PumpId.P1,
        volume_ml=Decimal("2.500"),
    )


def prepare_sf_operation() -> PrepareSfToColumnTransferOperation:
    return PrepareSfToColumnTransferOperation(
        operation_kind=OperationKind.PREPARE_SF_TO_COLUMN_TRANSFER,
        operation_number=1,
    )


def aspirate_from_sf_operation() -> AspirateFromSfOperation:
    return AspirateFromSfOperation(
        operation_kind=OperationKind.ASPIRATE_FROM_SF,
        operation_number=2,
        cycle_number=1,
        cycle_count=1,
        pump_id=PumpId.P2,
        volume_ml=Decimal("3.125"),
    )


def prepare_collection_operation() -> PrepareColumnFractionCollectionOperation:
    return PrepareColumnFractionCollectionOperation(
        operation_kind=OperationKind.PREPARE_COLUMN_FRACTION_COLLECTION,
        operation_number=1,
        column_bottom_valve_referenced=True,
    )


def collect_operation() -> CollectColumnFractionOperation:
    return CollectColumnFractionOperation(
        operation_kind=OperationKind.COLLECT_COLUMN_FRACTION,
        operation_number=2,
        fraction_number=1,
        fraction_count=2,
        configured_duration_seconds=Decimal("12.500"),
        stop_interrupts_collection_timer=True,
        required_close_follows_stop=True,
        required_close_failure_blocks_further_operations=True,
    )


def carousel_operation() -> MoveCarouselToNextFractionOperation:
    return MoveCarouselToNextFractionOperation(
        operation_kind=OperationKind.MOVE_CAROUSEL_TO_NEXT_FRACTION,
        operation_number=3,
        fraction_count=2,
        source_fraction_number=1,
        destination_fraction_number=2,
        requires_successful_collection=True,
        requires_column_bottom_valve_closed=True,
        movement_failure_leaves_column_bottom_valve_closed=True,
        movement_failure_marks_carousel_position_untrusted=True,
        movement_failure_blocks_next_fraction=True,
        movement_failure_uses_existing_fault_mechanism=True,
    )


def test_simple_operations_map_exact_semantic_arguments() -> None:
    hardware = FakeHardwareAdapter()
    operation_executor = executor(hardware)

    assert (
        operation_executor.execute(select_route_operation())
        is OperationExecutionOutcome.COMPLETED
    )
    assert (
        operation_executor.execute(aspirate_operation())
        is OperationExecutionOutcome.COMPLETED
    )
    assert (
        operation_executor.execute(dispense_operation())
        is OperationExecutionOutcome.COMPLETED
    )
    assert (
        operation_executor.execute(carousel_operation())
        is OperationExecutionOutcome.COMPLETED
    )
    assert hardware.command_history == [
        SelectRouteCommand(SymbolicRouteId.REACTOR_TO_P2),
        AspirateCommand(PumpId.P2, Decimal("1.250")),
        DispenseCommand(PumpId.P1, Decimal("2.500")),
        MoveCarouselCommand(1, 2),
    ]


def test_sf_to_column_preparation_closes_both_valves_in_order() -> None:
    events: list[Event] = []

    result = executor(ScriptedHardware(events)).execute(prepare_sf_operation())

    assert result is OperationExecutionOutcome.COMPLETED
    assert events == [
        ("sf", BottomValveState.CLOSED),
        ("column", BottomValveState.CLOSED),
    ]


def test_second_preparation_close_is_attempted_and_first_error_propagates() -> None:
    events: list[Event] = []
    first_error = RuntimeError("first close failed")
    hardware = ScriptedHardware(
        events, {("sf", BottomValveState.CLOSED): first_error}
    )

    with pytest.raises(RuntimeError) as caught:
        executor(hardware).execute(prepare_sf_operation())

    assert caught.value is first_error
    assert events == [
        ("sf", BottomValveState.CLOSED),
        ("column", BottomValveState.CLOSED),
    ]


def test_both_preparation_failures_are_preserved() -> None:
    events: list[Event] = []
    first_error = RuntimeError("SF close failed")
    second_error = RuntimeError("Column close failed")
    hardware = ScriptedHardware(
        events,
        {
            ("sf", BottomValveState.CLOSED): first_error,
            ("column", BottomValveState.CLOSED): second_error,
        },
    )

    with pytest.raises(ProtectedOperationError) as caught:
        executor(hardware).execute(prepare_sf_operation())

    assert caught.value.primary_error is first_error
    assert caught.value.followup_error is second_error


def test_column_preparation_closes_column() -> None:
    events: list[Event] = []

    result = executor(ScriptedHardware(events)).execute(
        prepare_collection_operation()
    )

    assert result is OperationExecutionOutcome.COMPLETED
    assert events == [("column", BottomValveState.CLOSED)]


def test_sf_aspiration_is_indivisible_open_aspirate_close_sequence() -> None:
    events: list[Event] = []

    result = executor(ScriptedHardware(events)).execute(
        aspirate_from_sf_operation()
    )

    assert result is OperationExecutionOutcome.COMPLETED
    assert events == [
        ("sf", BottomValveState.OPEN),
        ("aspirate", PumpId.P2, Decimal("3.125")),
        ("sf", BottomValveState.CLOSED),
    ]


@pytest.mark.parametrize(
    ("failed_event", "expected_events"),
    [
        (
            ("sf", BottomValveState.OPEN),
            [
                ("sf", BottomValveState.OPEN),
                ("sf", BottomValveState.CLOSED),
            ],
        ),
        (
            ("aspirate", PumpId.P2, Decimal("3.125")),
            [
                ("sf", BottomValveState.OPEN),
                ("aspirate", PumpId.P2, Decimal("3.125")),
                ("sf", BottomValveState.CLOSED),
            ],
        ),
    ],
)
def test_sf_close_is_attempted_and_primary_error_propagates(
    failed_event: Event,
    expected_events: list[Event],
) -> None:
    events: list[Event] = []
    primary_error = RuntimeError("primary SF action failed")
    hardware = ScriptedHardware(events, {failed_event: primary_error})

    with pytest.raises(RuntimeError) as caught:
        executor(hardware).execute(aspirate_from_sf_operation())

    assert caught.value is primary_error
    assert events == expected_events


def test_dual_sf_failure_preserves_primary_and_close_errors() -> None:
    events: list[Event] = []
    primary_error = RuntimeError("aspiration failed")
    close_error = RuntimeError("SF close failed")
    hardware = ScriptedHardware(
        events,
        {
            ("aspirate", PumpId.P2, Decimal("3.125")): primary_error,
            ("sf", BottomValveState.CLOSED): close_error,
        },
    )

    with pytest.raises(ProtectedOperationError) as caught:
        executor(hardware).execute(aspirate_from_sf_operation())

    assert caught.value.primary_error is primary_error
    assert caught.value.followup_error is close_error


@pytest.mark.parametrize(
    ("timer_outcome", "expected_outcome"),
    [
        (
            CollectionTimerOutcome.COMPLETED,
            OperationExecutionOutcome.COMPLETED,
        ),
        (
            CollectionTimerOutcome.STOP_REQUESTED,
            OperationExecutionOutcome.COLLECTION_STOP_REQUESTED,
        ),
    ],
)
def test_collection_opens_waits_exact_duration_and_closes_before_outcome(
    timer_outcome: CollectionTimerOutcome,
    expected_outcome: OperationExecutionOutcome,
) -> None:
    events: list[Event] = []
    hardware = ScriptedHardware(events)
    timer = FakeCollectionTimer(events, outcome=timer_outcome)

    result = executor(hardware, timer).execute(collect_operation())

    assert result is expected_outcome
    assert events == [
        ("column", BottomValveState.OPEN),
        ("timer", Decimal("12.500")),
        ("column", BottomValveState.CLOSED),
    ]
    assert not any(event[0] == "carousel" for event in events)


def test_column_close_is_attempted_after_timer_failure_and_error_propagates() -> None:
    events: list[Event] = []
    timer_error = RuntimeError("timer failed")
    timer = FakeCollectionTimer(events, error=timer_error)

    with pytest.raises(RuntimeError) as caught:
        executor(ScriptedHardware(events), timer).execute(collect_operation())

    assert caught.value is timer_error
    assert events == [
        ("column", BottomValveState.OPEN),
        ("timer", Decimal("12.500")),
        ("column", BottomValveState.CLOSED),
    ]


def test_column_close_is_attempted_after_uncertain_open_failure() -> None:
    events: list[Event] = []
    open_error = RuntimeError("Column open failed")
    hardware = ScriptedHardware(
        events, {("column", BottomValveState.OPEN): open_error}
    )

    with pytest.raises(RuntimeError) as caught:
        executor(hardware).execute(collect_operation())

    assert caught.value is open_error
    assert events == [
        ("column", BottomValveState.OPEN),
        ("column", BottomValveState.CLOSED),
    ]


@pytest.mark.parametrize(
    "timer_outcome",
    [
        CollectionTimerOutcome.COMPLETED,
        CollectionTimerOutcome.STOP_REQUESTED,
    ],
)
def test_failed_column_close_prevents_success_or_stop_outcome(
    timer_outcome: CollectionTimerOutcome,
) -> None:
    events: list[Event] = []
    close_error = RuntimeError("Column close failed")
    hardware = ScriptedHardware(
        events, {("column", BottomValveState.CLOSED): close_error}
    )
    timer = FakeCollectionTimer(events, outcome=timer_outcome)

    with pytest.raises(RuntimeError) as caught:
        executor(hardware, timer).execute(collect_operation())

    assert caught.value is close_error


def test_dual_column_failure_preserves_primary_and_close_errors() -> None:
    events: list[Event] = []
    timer_error = RuntimeError("timer failed")
    close_error = RuntimeError("Column close failed")
    hardware = ScriptedHardware(
        events, {("column", BottomValveState.CLOSED): close_error}
    )
    timer = FakeCollectionTimer(events, error=timer_error)

    with pytest.raises(ProtectedOperationError) as caught:
        executor(hardware, timer).execute(collect_operation())

    assert caught.value.primary_error is timer_error
    assert caught.value.followup_error is close_error


def test_unknown_operation_is_rejected() -> None:
    with pytest.raises(TypeError, match="unsupported planned operation type"):
        executor(FakeHardwareAdapter()).execute(cast(Any, object()))
