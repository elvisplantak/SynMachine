from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.demo.column_fraction_collection_operation_plan import (
    ColumnFractionCollectionConfiguration,
    ColumnFractionCollectionOperationPlan,
    ColumnPowerLossRecoveryRequirements,
    ColumnRecoveryAction,
    FractionCollectionStopPoint,
    FractionCompletion,
    LogicalColumnValveState,
    build_column_fraction_collection_operations,
    column_power_loss_recovery_requirements,
    plan_column_fraction_collection_operations,
)
from app.demo.machine_lifecycle import complete_recovery
from app.demo.machine_models import MachineSnapshot, MachineState
from app.demo.models import DemoExecutionSettings
from app.demo.operation_models import (
    CollectColumnFractionAction,
    CollectColumnFractionOperation,
    MoveCarouselToNextFractionOperation,
    OperationKind,
    PrepareColumnFractionCollectionAction,
    PrepareColumnFractionCollectionOperation,
    TopologyId,
)
from app.demo.phases import RunPhase
from app.demo.run_models import RunStatus


NOW = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)


def configuration(
    *, fraction_count: int = 3, duration: str = "45.25"
) -> ColumnFractionCollectionConfiguration:
    return ColumnFractionCollectionConfiguration(
        fraction_count=fraction_count,
        fraction_duration_seconds=duration,
        carousel_ready_confirmed=True,
        column_bottom_valve_referenced_confirmed=True,
    )


def operation_plan(
    *, fraction_count: int = 3, duration: str = "45.25"
) -> ColumnFractionCollectionOperationPlan:
    return plan_column_fraction_collection_operations(
        configuration(fraction_count=fraction_count, duration=duration)
    )


def invalid_plan(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ColumnFractionCollectionOperationPlan.model_validate(values)


def test_one_fraction_has_exact_sequence_and_no_carousel_move() -> None:
    result = operation_plan(fraction_count=1, duration="12.5")

    assert result.phase is RunPhase.COLUMN_FRACTION_COLLECTION
    assert result.required_topology_id is TopologyId.LABFORGE_V1_APPROVED_TARGET
    assert tuple(operation.operation_kind for operation in result.operations) == (
        OperationKind.PREPARE_COLUMN_FRACTION_COLLECTION,
        OperationKind.COLLECT_COLUMN_FRACTION,
    )
    collection = result.operations[1]
    assert isinstance(collection, CollectColumnFractionOperation)
    assert collection.fraction_number == collection.fraction_count == 1
    assert collection.configured_duration_seconds == Decimal("12.5")


def test_multi_fraction_exact_sequence_numbering_and_positions() -> None:
    result = operation_plan(fraction_count=3)

    assert tuple(operation.operation_kind for operation in result.operations) == (
        OperationKind.PREPARE_COLUMN_FRACTION_COLLECTION,
        OperationKind.COLLECT_COLUMN_FRACTION,
        OperationKind.MOVE_CAROUSEL_TO_NEXT_FRACTION,
        OperationKind.COLLECT_COLUMN_FRACTION,
        OperationKind.MOVE_CAROUSEL_TO_NEXT_FRACTION,
        OperationKind.COLLECT_COLUMN_FRACTION,
    )
    assert tuple(operation.operation_number for operation in result.operations) == tuple(
        range(1, 7)
    )
    collections = [
        operation
        for operation in result.operations
        if isinstance(operation, CollectColumnFractionOperation)
    ]
    movements = [
        operation
        for operation in result.operations
        if isinstance(operation, MoveCarouselToNextFractionOperation)
    ]
    assert [operation.fraction_number for operation in collections] == [1, 2, 3]
    assert all(operation.fraction_count == 3 for operation in collections)
    assert [
        (operation.source_fraction_number, operation.destination_fraction_number)
        for operation in movements
    ] == [(1, 2), (2, 3)]
    assert all(operation.destination_fraction_number != 4 for operation in movements)


def test_protected_preparation_and_collection_semantics_are_exact() -> None:
    result = operation_plan(fraction_count=1)
    preparation, collection = result.operations

    assert isinstance(preparation, PrepareColumnFractionCollectionOperation)
    assert preparation.column_bottom_valve_referenced is True
    assert preparation.required_action_sequence == (
        PrepareColumnFractionCollectionAction.CLOSE_COLUMN_BOTTOM_VALVE,
    )
    assert isinstance(collection, CollectColumnFractionOperation)
    assert collection.required_action_sequence == (
        CollectColumnFractionAction.OPEN_COLUMN_BOTTOM_VALVE,
        CollectColumnFractionAction.COLLECT_UNTIL_DURATION_OR_STOP,
        CollectColumnFractionAction.CLOSE_COLUMN_BOTTOM_VALVE,
    )
    assert collection.stop_interrupts_collection_timer is True
    assert collection.required_close_follows_stop is True
    assert collection.required_close_failure_blocks_further_operations is True


def test_configuration_reuses_execution_settings_and_preserves_decimal() -> None:
    settings = DemoExecutionSettings(
        sf_settling_duration_seconds="10",
        fraction_count=4,
        fraction_duration_seconds="20.0000001",
    )
    result = ColumnFractionCollectionConfiguration.from_execution_settings(
        settings,
        carousel_ready_confirmed=True,
        column_bottom_valve_referenced_confirmed=True,
    )

    assert result.fraction_count == 4
    assert result.fraction_duration_seconds == Decimal("20.0000001")


@pytest.mark.parametrize(
    "values",
    [
        {"fraction_count": 0},
        {"fraction_count": -1},
        {"fraction_count": 1.5},
        {"fraction_count": True},
        {"fraction_duration_seconds": "0"},
        {"fraction_duration_seconds": "-0.1"},
        {"fraction_duration_seconds": "NaN"},
        {"carousel_ready_confirmed": False},
        {"column_bottom_valve_referenced_confirmed": False},
    ],
)
def test_invalid_configuration_is_rejected(values: dict[str, object]) -> None:
    valid: dict[str, object] = {
        "fraction_count": 1,
        "fraction_duration_seconds": "1",
        "carousel_ready_confirmed": True,
        "column_bottom_valve_referenced_confirmed": True,
    }
    with pytest.raises(ValidationError):
        ColumnFractionCollectionConfiguration(**(valid | values))


@pytest.mark.parametrize(
    "change",
    [
        "missing_preparation",
        "duplicate_preparation",
        "preparation_not_first",
        "missing_collection",
        "swapped_order",
        "extra_operation",
        "move_before_collection",
        "two_moves",
        "missing_move",
        "move_after_final",
    ],
)
def test_invalid_exact_sequences_are_rejected(change: str) -> None:
    values = operation_plan(fraction_count=3).model_dump()
    operations = list(values["operations"])
    if change == "missing_preparation":
        operations.pop(0)
    elif change == "duplicate_preparation":
        operations.insert(1, dict(operations[0]))
    elif change == "preparation_not_first":
        operations[0], operations[1] = operations[1], operations[0]
    elif change == "missing_collection":
        operations.pop(3)
    elif change == "swapped_order":
        operations[1], operations[2] = operations[2], operations[1]
    elif change == "extra_operation":
        operations.append(dict(operations[-1]))
    elif change == "move_before_collection":
        operations[1] = dict(operations[2])
    elif change == "two_moves":
        operations[3] = dict(operations[2])
    elif change == "missing_move":
        operations.pop(2)
    else:
        operations.append(dict(operations[4]))
    values["operations"] = operations
    invalid_plan(values)


@pytest.mark.parametrize(
    ("operation_index", "field", "value"),
    [
        (1, "fraction_number", 2),
        (1, "fraction_count", 2),
        (1, "configured_duration_seconds", Decimal("1")),
        (2, "source_fraction_number", 2),
        (2, "destination_fraction_number", 3),
    ],
)
def test_wrong_operation_details_are_rejected(
    operation_index: int, field: str, value: object
) -> None:
    values = operation_plan().model_dump()
    operations = list(values["operations"])
    operations[operation_index][field] = value
    values["operations"] = operations
    invalid_plan(values)


@pytest.mark.parametrize("operation_index", [0, 1])
def test_modified_protected_internal_actions_are_rejected(operation_index: int) -> None:
    values = operation_plan(fraction_count=1).model_dump()
    operations = list(values["operations"])
    operations[operation_index]["required_action_sequence"] = ()
    values["operations"] = operations
    invalid_plan(values)


def test_wrong_phase_and_unconfirmed_readiness_are_rejected() -> None:
    values = operation_plan().model_dump()
    values["phase"] = RunPhase.P2_TRANSFER_SF_TO_COLUMN
    invalid_plan(values)

    with pytest.raises(ValidationError, match="carousel readiness must be confirmed"):
        ColumnFractionCollectionConfiguration(
            fraction_count=1,
            fraction_duration_seconds="1",
            carousel_ready_confirmed=False,
            column_bottom_valve_referenced_confirmed=True,
        )


def test_logical_state_tracks_close_collection_and_only_successful_movement() -> None:
    result = operation_plan(fraction_count=3)

    after_preparation = result.logical_state_after(1)
    after_first_collection = result.logical_state_after(2)
    after_first_move = result.logical_state_after(3)
    after_final_collection = result.logical_state_after(result.operation_count)

    assert after_preparation.column_bottom_valve is LogicalColumnValveState.CLOSED
    assert after_preparation.carousel_fraction_number == 1
    assert after_first_collection.column_bottom_valve is LogicalColumnValveState.CLOSED
    assert after_first_collection.carousel_fraction_number == 1
    assert after_first_collection.pending_carousel_movement is True
    assert after_first_move.carousel_fraction_number == 2
    assert after_first_move.pending_carousel_movement is False
    assert after_final_collection.column_bottom_valve is LogicalColumnValveState.CLOSED
    assert after_final_collection.carousel_fraction_number == 3
    assert after_final_collection.last_fraction_completion is FractionCompletion.COMPLETE
    assert after_final_collection.pending_carousel_movement is False
    assert all(
        result.logical_state_after(operation.operation_number).column_bottom_valve
        is LogicalColumnValveState.CLOSED
        for operation in result.operations
    )


@pytest.mark.parametrize(
    ("stop_point", "completion", "timer_interrupted", "carousel_position"),
    [
        (
            FractionCollectionStopPoint.BEFORE_COLLECTION,
            FractionCompletion.NOT_STARTED,
            False,
            1,
        ),
        (
            FractionCollectionStopPoint.DURING_COLLECTION,
            FractionCompletion.PARTIAL,
            True,
            1,
        ),
        (
            FractionCollectionStopPoint.AFTER_COLLECTION_CLOSE_BEFORE_MOVE,
            FractionCompletion.COMPLETE,
            False,
            1,
        ),
        (
            FractionCollectionStopPoint.DURING_CAROUSEL_MOVE,
            FractionCompletion.COMPLETE,
            False,
            2,
        ),
    ],
)
def test_stop_semantics_block_next_operation_and_keep_valve_closed(
    stop_point: FractionCollectionStopPoint,
    completion: FractionCompletion,
    timer_interrupted: bool,
    carousel_position: int,
) -> None:
    state = operation_plan().logical_state_after_stop(1, stop_point)

    assert state.column_bottom_valve is LogicalColumnValveState.CLOSED
    assert state.last_fraction_completion is completion
    assert state.collection_timer_interrupted is timer_interrupted
    assert state.carousel_fraction_number == carousel_position
    assert state.pending_carousel_movement is False
    assert state.further_operations_blocked is True
    assert state.normal_abort_resulting_run_status is RunStatus.ABORTED
    assert state.normal_abort_resulting_machine_state is MachineState.FLUSH_REQUIRED


def test_stop_before_later_collection_preserves_previous_completed_fraction() -> None:
    state = operation_plan().logical_state_after_stop(
        2, FractionCollectionStopPoint.BEFORE_COLLECTION
    )

    assert state.column_bottom_valve is LogicalColumnValveState.CLOSED
    assert state.carousel_fraction_number == 2
    assert state.last_fraction_number == 1
    assert state.last_fraction_completion is FractionCompletion.COMPLETE
    assert state.pending_carousel_movement is False
    assert state.further_operations_blocked is True
    assert state.normal_abort_resulting_run_status is RunStatus.ABORTED
    assert state.normal_abort_resulting_machine_state is MachineState.FLUSH_REQUIRED


def test_after_close_before_move_stop_requires_non_final_fraction() -> None:
    result = operation_plan(fraction_count=3)

    accepted = result.logical_state_after_stop(
        2, FractionCollectionStopPoint.AFTER_COLLECTION_CLOSE_BEFORE_MOVE
    )
    assert accepted.last_fraction_completion is FractionCompletion.COMPLETE
    with pytest.raises(
        ValueError, match="there is no carousel movement after the final fraction"
    ):
        result.logical_state_after_stop(
            3, FractionCollectionStopPoint.AFTER_COLLECTION_CLOSE_BEFORE_MOVE
        )


def test_carousel_move_requires_successful_collection_and_required_close() -> None:
    movements = [
        operation
        for operation in operation_plan().operations
        if isinstance(operation, MoveCarouselToNextFractionOperation)
    ]
    assert movements
    assert all(operation.requires_successful_collection for operation in movements)
    assert all(
        operation.requires_column_bottom_valve_closed for operation in movements
    )
    assert all(
        operation.movement_failure_leaves_column_bottom_valve_closed
        for operation in movements
    )
    assert all(
        operation.movement_failure_marks_carousel_position_untrusted
        for operation in movements
    )
    assert all(operation.movement_failure_blocks_next_fraction for operation in movements)
    assert all(
        operation.movement_failure_uses_existing_fault_mechanism
        for operation in movements
    )


def test_failed_carousel_move_invalidates_position_and_blocks_next_fraction() -> None:
    state = operation_plan().logical_state_after_carousel_move_failure(1)

    assert state.column_bottom_valve is LogicalColumnValveState.CLOSED
    assert state.carousel_fraction_number is None
    assert state.carousel_position_trusted is False
    assert state.last_fraction_number == 1
    assert state.last_fraction_completion is FractionCompletion.COMPLETE
    assert state.further_operations_blocked is True
    assert state.failure_requires_existing_fault_mechanism is True
    assert state.normal_abort_resulting_run_status is None
    assert state.normal_abort_resulting_machine_state is None


def test_power_loss_requirements_extend_existing_recovery_lifecycle() -> None:
    requirements = column_power_loss_recovery_requirements()
    recovering = MachineSnapshot(
        state=MachineState.RECOVERING,
        event_sequence=3,
        interrupted_run_id="run-interrupted",
    )
    recovered = complete_recovery(recovering, NOW)

    assert requirements.ordered_actions == (
        ColumnRecoveryAction.RESTORE_COLUMN_BOTTOM_VALVE_CLOSED,
        ColumnRecoveryAction.CONTINUE_EXISTING_MACHINE_RECOVERY,
    )
    assert requirements.old_fraction_run_must_not_resume is True
    assert requirements.active_fraction_untrusted is True
    assert requirements.previous_column_bottom_valve_position_trusted is False
    assert (
        requirements.recovery_target_column_bottom_valve_state
        is LogicalColumnValveState.CLOSED
    )
    assert (
        requirements.successful_recovery_result_column_bottom_valve_state
        is LogicalColumnValveState.CLOSED
    )
    assert requirements.carousel_position_trusted is False
    assert requirements.automatic_carousel_movement_allowed is False
    assert requirements.manual_carousel_alignment_required is True
    assert requirements.service_confirmation_required_before_future_run_or_flush is True
    assert requirements.resulting_machine_state is MachineState.FLUSH_REQUIRED
    assert recovered.machine.state is requirements.resulting_machine_state


def test_recovery_order_cannot_be_modified() -> None:
    values = column_power_loss_recovery_requirements().model_dump()
    values["ordered_actions"] = tuple(reversed(values["ordered_actions"]))
    with pytest.raises(ValidationError, match="Column valve close must be the first"):
        ColumnPowerLossRecoveryRequirements.model_validate(values)


def test_json_round_trip_preserves_types_and_exact_decimal() -> None:
    original = operation_plan(fraction_count=2, duration="1.0000000001")
    restored = ColumnFractionCollectionOperationPlan.model_validate_json(
        original.model_dump_json()
    )

    assert restored == original
    assert isinstance(restored.operations[0], PrepareColumnFractionCollectionOperation)
    assert isinstance(restored.operations[1], CollectColumnFractionOperation)
    assert isinstance(restored.operations[2], MoveCarouselToNextFractionOperation)
    assert restored.operations[1].configured_duration_seconds == Decimal("1.0000000001")


def test_symbolic_boundary_has_no_waste_or_physical_position_claims() -> None:
    serialized = {
        "plan": operation_plan().model_dump(),
        "recovery": column_power_loss_recovery_requirements().model_dump(),
    }
    text = str(serialized).lower()
    assert all(not hasattr(operation, "route_id") for operation in operation_plan().operations)
    for forbidden in (
        "waste_route",
        "sensor_confirmed",
        "angle",
        "pin",
        "motor_step",
        "speed",
        "carousel_step",
    ):
        assert forbidden not in text


def test_plan_and_configuration_are_immutable() -> None:
    result = operation_plan()
    with pytest.raises(ValidationError):
        result.operations = ()
    with pytest.raises(ValidationError):
        result.configuration.fraction_count = 4


def test_public_builder_returns_exact_plan_operations() -> None:
    config = configuration(fraction_count=2)
    assert build_column_fraction_collection_operations(config) == (
        plan_column_fraction_collection_operations(config).operations
    )
