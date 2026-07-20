from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.demo.calibration_models import PumpCalibration, PumpCalibrationSet, PumpId
from app.demo.fluid_plan import build_fluid_plan
from app.demo.models import AdditionOrder, DemoConfiguration
from app.demo.operation_models import (
    AspirateOperation,
    DispenseOperation,
    OperationKind,
    SelectRouteOperation,
    SymbolicRouteId,
    TopologyId,
    build_syringe_transfer_operations,
)
from app.demo.p2_reactor_to_sf_operation_plan import (
    P2ReactorToSfOperationPlan,
    plan_p2_reactor_to_sf_operations,
)
from app.demo.phases import RunPhase
from app.demo.transfer_cycle_planner import TransferCyclePlan


def configuration(**overrides: object) -> DemoConfiguration:
    values: dict[str, object] = {
        "b1_ratio_percent": "35",
        "total_mixture_volume_ml": "10",
        "combined_b1_b2_volume_ml": "4",
        "addition_order": AdditionOrder.B1_THEN_B2,
        "addition_speed_command_percent": "45",
        "reactor_mixing_command_percent": "55",
        "sf_mixing_command_percent": "30",
        "simulated_target_temperature_c": "24",
        "reaction_duration_seconds": "420",
        "delay_between_additions_seconds": "7",
    }
    values.update(overrides)
    return DemoConfiguration(**values)


def calibration(pump_id: PumpId, working_volume_ml: str) -> PumpCalibration:
    return PumpCalibration(
        pump_id=pump_id,
        working_full_chamber_position_steps=1111,
        working_empty_chamber_position_steps=8888,
        working_volume_ml=working_volume_ml,
    )


def calibration_set(
    p1_working_volume_ml: str = "7",
    p2_working_volume_ml: str = "3",
) -> PumpCalibrationSet:
    return PumpCalibrationSet(
        p1=calibration(PumpId.P1, p1_working_volume_ml),
        p2=calibration(PumpId.P2, p2_working_volume_ml),
    )


def operation_plan(
    *,
    total_volume_ml: str = "10",
    p1_working_volume_ml: str = "7",
    p2_working_volume_ml: str = "3",
) -> P2ReactorToSfOperationPlan:
    return plan_p2_reactor_to_sf_operations(
        build_fluid_plan(configuration(total_mixture_volume_ml=total_volume_ml)),
        calibration_set(p1_working_volume_ml, p2_working_volume_ml),
    )


def invalid_plan(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        P2ReactorToSfOperationPlan.model_validate(values)


def test_basic_plan_uses_p2_nominal_total_and_symbolic_routes() -> None:
    result = operation_plan(total_volume_ml="8.75", p2_working_volume_ml="5")

    assert result.phase is RunPhase.P2_TRANSFER_REACTOR_TO_SF
    assert result.required_topology_id is TopologyId.LABFORGE_V1_APPROVED_TARGET
    assert result.transfer_cycle_plan.pump_id is PumpId.P2
    assert result.transfer_cycle_plan.requested_volume_ml == Decimal("8.75")
    for index in range(0, result.operation_count, 4):
        assert result.operations[index].route_id is SymbolicRouteId.REACTOR_TO_P2
        assert result.operations[index + 2].route_id is SymbolicRouteId.P2_TO_SF_TOP
        assert result.operations[index + 1].pump_id is PumpId.P2
        assert result.operations[index + 3].pump_id is PumpId.P2


def test_cycles_repeat_exact_pattern_and_preserve_remainder() -> None:
    result = operation_plan(total_volume_ml="10", p2_working_volume_ml="3")

    assert tuple(cycle.volume_ml for cycle in result.transfer_cycle_plan.cycles) == (
        Decimal("3"),
        Decimal("3"),
        Decimal("3"),
        Decimal("1"),
    )
    assert result.operation_count == 16
    assert tuple(operation.operation_number for operation in result.operations) == tuple(
        range(1, 17)
    )
    for index, cycle in enumerate(result.transfer_cycle_plan.cycles):
        operations = result.operations[index * 4 : index * 4 + 4]
        assert tuple(operation.operation_kind for operation in operations) == (
            OperationKind.SELECT_ROUTE,
            OperationKind.ASPIRATE,
            OperationKind.SELECT_ROUTE,
            OperationKind.DISPENSE,
        )
        assert operations[0].route_id is SymbolicRouteId.REACTOR_TO_P2
        assert operations[2].route_id is SymbolicRouteId.P2_TO_SF_TOP
        assert all(operation.cycle_number == cycle.cycle_number for operation in operations)
        assert all(operation.cycle_count == 4 for operation in operations)
        assert operations[1].volume_ml == operations[3].volume_ml == cycle.volume_ml


def test_p2_calibration_changes_cycle_splitting() -> None:
    first = operation_plan(p2_working_volume_ml="3")
    second = operation_plan(p2_working_volume_ml="4")

    assert tuple(cycle.volume_ml for cycle in first.transfer_cycle_plan.cycles) == (
        Decimal("3"),
        Decimal("3"),
        Decimal("3"),
        Decimal("1"),
    )
    assert tuple(cycle.volume_ml for cycle in second.transfer_cycle_plan.cycles) == (
        Decimal("4"),
        Decimal("4"),
        Decimal("2"),
    )


def test_changing_only_p1_calibration_does_not_change_plan() -> None:
    assert operation_plan(p1_working_volume_ml="0.5") == operation_plan(
        p1_working_volume_ml="9"
    )


def test_exact_multiple_has_only_full_positive_cycles_and_operations() -> None:
    result = operation_plan(total_volume_ml="9", p2_working_volume_ml="3")

    assert tuple(cycle.volume_ml for cycle in result.transfer_cycle_plan.cycles) == (
        Decimal("3"),
        Decimal("3"),
        Decimal("3"),
    )
    assert all(
        operation.volume_ml > 0
        for operation in result.operations
        if isinstance(operation, (AspirateOperation, DispenseOperation))
    )


def zero_cycle_plan() -> TransferCyclePlan:
    return TransferCyclePlan(
        pump_id=PumpId.P2,
        requested_volume_ml="0",
        working_volume_ml="3",
        cycles=(),
    )


def test_direct_zero_cycle_plan_has_no_operations() -> None:
    transfer_cycle_plan = zero_cycle_plan()
    operations = build_syringe_transfer_operations(
        transfer_cycle_plan,
        aspiration_route_id=SymbolicRouteId.REACTOR_TO_P2,
        dispense_route_id=SymbolicRouteId.P2_TO_SF_TOP,
    )
    result = P2ReactorToSfOperationPlan(
        phase=RunPhase.P2_TRANSFER_REACTOR_TO_SF,
        required_topology_id=TopologyId.LABFORGE_V1_APPROVED_TARGET,
        transfer_cycle_plan=transfer_cycle_plan,
        operations=operations,
    )

    assert operations == ()
    assert result.operations == ()
    assert result.operation_count == 0


def test_non_empty_operations_for_zero_cycle_plan_are_rejected() -> None:
    values = {
        "phase": RunPhase.P2_TRANSFER_REACTOR_TO_SF,
        "required_topology_id": TopologyId.LABFORGE_V1_APPROVED_TARGET,
        "transfer_cycle_plan": zero_cycle_plan(),
        "operations": operation_plan().operations,
    }
    invalid_plan(values)


def test_plan_fields_are_exact_and_operation_count_is_derived() -> None:
    assert set(P2ReactorToSfOperationPlan.model_fields) == {
        "phase",
        "required_topology_id",
        "transfer_cycle_plan",
        "operations",
    }
    assert "operation_count" not in P2ReactorToSfOperationPlan.model_fields


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("phase", RunPhase.P2_TRANSFER_SF_TO_COLUMN),
        ("required_topology_id", "CURRENT_MACHINE"),
    ],
)
def test_wrong_plan_identity_is_rejected(field: str, value: object) -> None:
    values = operation_plan().model_dump()
    values[field] = value
    invalid_plan(values)


def test_p1_transfer_cycle_plan_is_rejected() -> None:
    values = operation_plan().model_dump()
    values["transfer_cycle_plan"]["pump_id"] = PumpId.P1
    invalid_plan(values)


@pytest.mark.parametrize(
    ("operation_index", "field", "value"),
    [
        (0, "route_id", SymbolicRouteId.S_TO_P1),
        (2, "route_id", SymbolicRouteId.P1_TO_REACTOR),
        (1, "pump_id", PumpId.P1),
        (1, "volume_ml", Decimal("0.5")),
        (3, "volume_ml", Decimal("0.5")),
        (1, "operation_number", 3),
        (1, "operation_number", 1),
        (0, "cycle_number", 2),
        (0, "cycle_count", 2),
    ],
)
def test_incorrect_operation_detail_is_rejected(
    operation_index: int,
    field: str,
    value: object,
) -> None:
    values = operation_plan().model_dump()
    operations = list(values["operations"])
    operations[operation_index][field] = value
    values["operations"] = operations
    invalid_plan(values)


@pytest.mark.parametrize("change", ["missing", "extra", "wrong_order"])
def test_incorrect_operation_sequence_is_rejected(change: str) -> None:
    values = operation_plan().model_dump()
    operations = list(values["operations"])
    if change == "missing":
        operations.pop()
    elif change == "extra":
        extra = dict(operations[-1])
        extra["operation_number"] = len(operations) + 1
        operations.append(extra)
    else:
        operations[1], operations[3] = operations[3], operations[1]
    values["operations"] = operations
    invalid_plan(values)


def test_plan_is_immutable_and_operations_are_tuple() -> None:
    result = operation_plan()

    assert isinstance(result.operations, tuple)
    with pytest.raises(ValidationError):
        result.operations = ()


def test_json_round_trip_preserves_types_enums_and_decimals() -> None:
    original = operation_plan(total_volume_ml="4.00", p2_working_volume_ml="0.30")

    restored = P2ReactorToSfOperationPlan.model_validate_json(
        original.model_dump_json()
    )

    assert restored == original
    assert restored.phase is RunPhase.P2_TRANSFER_REACTOR_TO_SF
    assert restored.required_topology_id is TopologyId.LABFORGE_V1_APPROVED_TARGET
    assert restored.transfer_cycle_plan.pump_id is PumpId.P2
    assert isinstance(restored.operations[0], SelectRouteOperation)
    assert isinstance(restored.operations[1], AspirateOperation)
    assert isinstance(restored.operations[2], SelectRouteOperation)
    assert isinstance(restored.operations[3], DispenseOperation)
    assert restored.operations[0].route_id is SymbolicRouteId.REACTOR_TO_P2
    assert restored.operations[2].route_id is SymbolicRouteId.P2_TO_SF_TOP
    assert all(
        isinstance(operation.volume_ml, Decimal)
        for operation in restored.operations
        if isinstance(operation, (AspirateOperation, DispenseOperation))
    )


def test_serialized_plan_has_only_nominal_symbolic_boundary() -> None:
    serialized = operation_plan().model_dump()
    serialized_text = str(serialized)

    assert set(serialized) == {
        "phase",
        "required_topology_id",
        "transfer_cycle_plan",
        "operations",
    }
    forbidden_fields = {
        "mixer_setting",
        "valve",
        "port",
        "angle",
        "step_position",
        "pump_speed",
        "command_id",
        "execution_state",
        "measured_volume_ml",
        "delivered_volume_ml",
        "reactor_empty",
        "physical_topology_confirmed",
    }
    for field in forbidden_fields:
        assert field not in serialized_text
