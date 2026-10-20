from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.demo.calibration_models import PumpCalibration, PumpCalibrationSet, PumpId
from app.demo.fluid_plan import build_fluid_plan
from app.demo.models import AdditionOrder, DemoConfiguration
from app.demo.operation_models import (
    AspirateFromSfAction,
    AspirateFromSfOperation,
    DispenseOperation,
    OperationKind,
    PrepareSfToColumnAction,
    PrepareSfToColumnTransferOperation,
    SelectRouteOperation,
    SymbolicRouteId,
    TopologyId,
)
from app.demo.p2_sf_to_column_operation_plan import (
    LogicalValveState,
    P2NominalContents,
    P2SfToColumnOperationPlan,
    P2SfToColumnOperationPlanningError,
    build_p2_sf_to_column_operations,
    plan_p2_sf_to_column_operations,
)
from app.demo.phases import RunPhase
from app.demo.transfer_cycle_planner import TransferCyclePlan


def configuration(total_volume_ml: str = "10") -> DemoConfiguration:
    return DemoConfiguration(
        b1_ratio_percent="35",
        total_mixture_volume_ml=total_volume_ml,
        combined_b1_b2_volume_ml="1",
        addition_order=AdditionOrder.B1_THEN_B2,
        addition_speed_command_percent="45",
        reactor_mixing_command_percent="55",
        sf_mixing_command_percent="30",
        simulated_target_temperature_c="24",
        reaction_duration_seconds="420",
        delay_between_additions_seconds="7",
    )


def calibration(pump_id: PumpId, volume: str) -> PumpCalibration:
    return PumpCalibration(
        pump_id=pump_id,
        working_full_chamber_position_steps=1111,
        working_empty_chamber_position_steps=8888,
        working_volume_ml=volume,
    )


def operation_plan(
    total_volume_ml: str = "10", p2_working_volume_ml: str = "3"
) -> P2SfToColumnOperationPlan:
    calibrations = PumpCalibrationSet(
        p1=calibration(PumpId.P1, "7"),
        p2=calibration(PumpId.P2, p2_working_volume_ml),
    )
    return plan_p2_sf_to_column_operations(
        build_fluid_plan(configuration(total_volume_ml)), calibrations
    )


def invalid_plan(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        P2SfToColumnOperationPlan.model_validate(values)


def test_one_cycle_has_exact_scheduler_visible_sequence() -> None:
    result = operation_plan("2.5", "3")

    assert result.phase is RunPhase.P2_TRANSFER_SF_TO_COLUMN
    assert result.required_topology_id is TopologyId.LABFORGE_V1_APPROVED_TARGET
    assert tuple(operation.operation_kind for operation in result.operations) == (
        OperationKind.PREPARE_SF_TO_COLUMN_TRANSFER,
        OperationKind.SELECT_ROUTE,
        OperationKind.ASPIRATE_FROM_SF,
        OperationKind.SELECT_ROUTE,
        OperationKind.DISPENSE,
    )
    assert result.operations[1].route_id is SymbolicRouteId.SF_BOTTOM_TO_P2
    assert result.operations[3].route_id is SymbolicRouteId.P2_TO_COLUMN


def test_multi_cycle_sequence_and_remainder_use_nominal_total() -> None:
    result = operation_plan("10", "3")

    assert result.transfer_cycle_plan.requested_volume_ml == Decimal("10")
    assert tuple(cycle.volume_ml for cycle in result.transfer_cycle_plan.cycles) == (
        Decimal("3"), Decimal("3"), Decimal("3"), Decimal("1")
    )
    assert result.operation_count == 17
    assert tuple(operation.operation_number for operation in result.operations) == tuple(
        range(1, 18)
    )
    for index, cycle in enumerate(result.transfer_cycle_plan.cycles):
        operations = result.operations[1 + index * 4 : 5 + index * 4]
        assert tuple(operation.operation_kind for operation in operations) == (
            OperationKind.SELECT_ROUTE,
            OperationKind.ASPIRATE_FROM_SF,
            OperationKind.SELECT_ROUTE,
            OperationKind.DISPENSE,
        )
        assert operations[0].route_id is SymbolicRouteId.SF_BOTTOM_TO_P2
        assert operations[2].route_id is SymbolicRouteId.P2_TO_COLUMN
        assert operations[1].volume_ml == operations[3].volume_ml == cycle.volume_ml


def test_protected_operations_have_exact_internal_semantics_and_one_stop_boundary() -> None:
    result = operation_plan("4", "3")
    preparation = result.operations[0]
    aspirations = [
        operation
        for operation in result.operations
        if isinstance(operation, AspirateFromSfOperation)
    ]

    assert isinstance(preparation, PrepareSfToColumnTransferOperation)
    assert preparation.required_action_sequence == (
        PrepareSfToColumnAction.CLOSE_SF_BOTTOM_VALVE,
        PrepareSfToColumnAction.CLOSE_COLUMN_BOTTOM_VALVE,
    )
    assert len(aspirations) == 2
    for aspiration in aspirations:
        assert aspiration.required_action_sequence == (
            AspirateFromSfAction.OPEN_SF_BOTTOM_VALVE,
            AspirateFromSfAction.ASPIRATE_P2,
            AspirateFromSfAction.CLOSE_SF_BOTTOM_VALVE,
        )
    assert not any(
        operation.operation_kind in {"OPEN_VALVE", "CLOSE_VALVE"}
        for operation in result.operations
    )


def test_preparation_occurs_exactly_once_and_first() -> None:
    result = operation_plan()
    preparations = [
        operation
        for operation in result.operations
        if isinstance(operation, PrepareSfToColumnTransferOperation)
    ]
    assert len(preparations) == 1
    assert result.operations[0] is preparations[0]


def test_success_and_stop_boundary_logical_states_are_explicit() -> None:
    result = operation_plan("4", "3")
    first_aspiration_number = 3

    stopped_after_aspiration = result.logical_state_after(first_aspiration_number)
    final = result.logical_state_after(result.operation_count)

    assert stopped_after_aspiration.sf_bottom_valve is LogicalValveState.CLOSED
    assert stopped_after_aspiration.column_bottom_valve is LogicalValveState.CLOSED
    assert stopped_after_aspiration.p2_contents is P2NominalContents.CYCLE_VOLUME
    assert final.sf_bottom_valve is LogicalValveState.CLOSED
    assert final.column_bottom_valve is LogicalValveState.CLOSED
    assert final.p2_contents is P2NominalContents.EMPTY


def test_plan_contains_no_waste_route_or_column_bottom_opening() -> None:
    serialized = operation_plan().model_dump()
    text = str(serialized)

    routes = {
        operation.route_id
        for operation in operation_plan().operations
        if isinstance(operation, SelectRouteOperation)
    }
    assert routes == {SymbolicRouteId.SF_BOTTOM_TO_P2, SymbolicRouteId.P2_TO_COLUMN}
    assert "WASTE" not in text.upper()
    assert "OPEN COLUMN_BOTTOM_VALVE" not in text


def test_zero_cycle_plan_is_rejected_by_phase_specific_builder_and_model() -> None:
    zero = TransferCyclePlan(
        pump_id=PumpId.P2,
        requested_volume_ml="0",
        working_volume_ml="3",
        cycles=(),
    )
    with pytest.raises(
        P2SfToColumnOperationPlanningError,
        match="P2_TRANSFER_SF_TO_COLUMN requires at least one",
    ):
        build_p2_sf_to_column_operations(zero)

    invalid_plan(
        {
            "phase": RunPhase.P2_TRANSFER_SF_TO_COLUMN,
            "required_topology_id": TopologyId.LABFORGE_V1_APPROVED_TARGET,
            "transfer_cycle_plan": zero,
            "operations": (),
        }
    )


def test_p1_transfer_cycle_plan_is_rejected_directly_by_builder() -> None:
    p1_plan = TransferCyclePlan(
        pump_id=PumpId.P1,
        requested_volume_ml="2",
        working_volume_ml="3",
        cycles=({"cycle_number": 1, "volume_ml": "2"},),
    )

    with pytest.raises(
        P2SfToColumnOperationPlanningError,
        match="P2_TRANSFER_SF_TO_COLUMN transfer cycle plan must use pump P2",
    ):
        build_p2_sf_to_column_operations(p1_plan)


@pytest.mark.parametrize("change", ["missing_prepare", "swap", "wrong_route", "extra"])
def test_invalid_exact_sequences_are_rejected(change: str) -> None:
    values = operation_plan("2", "3").model_dump()
    operations = list(values["operations"])
    if change == "missing_prepare":
        operations.pop(0)
    elif change == "swap":
        operations[2], operations[3] = operations[3], operations[2]
    elif change == "wrong_route":
        operations[3]["route_id"] = SymbolicRouteId.P2_TO_SF_TOP
    else:
        operations.append(dict(operations[-1]))
    values["operations"] = operations
    invalid_plan(values)


@pytest.mark.parametrize("operation_index", [0, 2])
def test_protected_internal_sequence_cannot_be_changed(operation_index: int) -> None:
    values = operation_plan("2", "3").model_dump()
    operations = list(values["operations"])
    operations[operation_index]["required_action_sequence"] = tuple(
        reversed(operations[operation_index]["required_action_sequence"])
    )
    values["operations"] = operations
    invalid_plan(values)


def test_serialized_plan_makes_no_measured_or_verified_claims() -> None:
    serialized = operation_plan().model_dump()
    text = str(serialized).lower()
    for forbidden in (
        "measured_volume",
        "delivered_volume",
        "sf_empty",
        "phase_detected",
        "phase_separated",
        "verified",
    ):
        assert forbidden not in text


def test_json_round_trip_preserves_protected_operation_types_and_decimals() -> None:
    original = operation_plan("4.00", "0.30")
    restored = P2SfToColumnOperationPlan.model_validate_json(original.model_dump_json())

    assert restored == original
    assert isinstance(restored.operations[0], PrepareSfToColumnTransferOperation)
    assert isinstance(restored.operations[1], SelectRouteOperation)
    assert isinstance(restored.operations[2], AspirateFromSfOperation)
    assert isinstance(restored.operations[3], SelectRouteOperation)
    assert isinstance(restored.operations[4], DispenseOperation)
    assert isinstance(restored.operations[2].volume_ml, Decimal)
