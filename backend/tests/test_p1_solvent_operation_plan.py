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
)
from app.demo.p1_solvent_operation_plan import (
    P1SolventToReactorOperationPlan,
    plan_p1_solvent_to_reactor_operations,
)
from app.demo.phases import RunPhase
from app.demo.transfer_cycle_planner import TransferCyclePlan


def configuration(**overrides: object) -> DemoConfiguration:
    values: dict[str, object] = {
        "b1_ratio_percent": "40",
        "total_mixture_volume_ml": "10",
        "combined_b1_b2_volume_ml": "3",
        "addition_order": AdditionOrder.B1_THEN_B2,
        "addition_speed_command_percent": "50",
        "reactor_mixing_command_percent": "60",
        "sf_mixing_command_percent": "40",
        "simulated_target_temperature_c": "25",
        "reaction_duration_seconds": "600",
        "delay_between_additions_seconds": "5",
    }
    values.update(overrides)
    return DemoConfiguration(**values)


def calibration(pump_id: PumpId, working_volume_ml: str) -> PumpCalibration:
    return PumpCalibration(
        pump_id=pump_id,
        working_full_chamber_position_steps=1234,
        working_empty_chamber_position_steps=9876,
        working_volume_ml=working_volume_ml,
    )


def calibration_set(p1_working_volume_ml: str = "3") -> PumpCalibrationSet:
    return PumpCalibrationSet(
        p1=calibration(PumpId.P1, p1_working_volume_ml),
        p2=calibration(PumpId.P2, "8"),
    )


def operation_plan(
    *,
    total_volume_ml: str = "10",
    combined_volume_ml: str = "3",
    p1_working_volume_ml: str = "3",
) -> P1SolventToReactorOperationPlan:
    fluid_plan = build_fluid_plan(
        configuration(
            total_mixture_volume_ml=total_volume_ml,
            combined_b1_b2_volume_ml=combined_volume_ml,
        )
    )
    return plan_p1_solvent_to_reactor_operations(
        fluid_plan,
        calibration_set(p1_working_volume_ml),
    )


def invalid_plan(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        P1SolventToReactorOperationPlan.model_validate(values)


def test_basic_plan_uses_existing_p1_cycle_plan_and_configured_solvent_volume() -> None:
    result = operation_plan(total_volume_ml="8.5", combined_volume_ml="3.25")

    assert result.phase is RunPhase.P1_TRANSFER_S_TO_REACTOR
    assert result.required_topology_id is TopologyId.LABFORGE_V1_APPROVED_TARGET
    assert isinstance(result.transfer_cycle_plan, TransferCyclePlan)
    assert result.transfer_cycle_plan.pump_id is PumpId.P1
    assert result.transfer_cycle_plan.requested_volume_ml == Decimal("5.25")
    assert result.transfer_cycle_plan.working_volume_ml == Decimal("3")


def test_one_partial_cycle_has_exact_symbolic_operation_sequence() -> None:
    result = operation_plan(
        total_volume_ml="5",
        combined_volume_ml="3",
        p1_working_volume_ml="3",
    )

    assert result.operations == (
        SelectRouteOperation(
            operation_kind=OperationKind.SELECT_ROUTE,
            operation_number=1,
            cycle_number=1,
            cycle_count=1,
            route_id=SymbolicRouteId.S_TO_P1,
        ),
        AspirateOperation(
            operation_kind=OperationKind.ASPIRATE,
            operation_number=2,
            cycle_number=1,
            cycle_count=1,
            pump_id=PumpId.P1,
            volume_ml=Decimal("2"),
        ),
        SelectRouteOperation(
            operation_kind=OperationKind.SELECT_ROUTE,
            operation_number=3,
            cycle_number=1,
            cycle_count=1,
            route_id=SymbolicRouteId.P1_TO_REACTOR,
        ),
        DispenseOperation(
            operation_kind=OperationKind.DISPENSE,
            operation_number=4,
            cycle_number=1,
            cycle_count=1,
            pump_id=PumpId.P1,
            volume_ml=Decimal("2"),
        ),
    )


def test_multiple_cycles_repeat_pattern_and_preserve_remainder() -> None:
    result = operation_plan(
        total_volume_ml="10",
        combined_volume_ml="3",
        p1_working_volume_ml="3",
    )

    assert result.transfer_cycle_plan.cycle_count == 3
    assert result.operation_count == 12
    assert tuple(operation.operation_number for operation in result.operations) == tuple(
        range(1, 13)
    )
    for index, cycle in enumerate(result.transfer_cycle_plan.cycles):
        operations = result.operations[index * 4 : index * 4 + 4]
        assert tuple(operation.operation_kind for operation in operations) == (
            OperationKind.SELECT_ROUTE,
            OperationKind.ASPIRATE,
            OperationKind.SELECT_ROUTE,
            OperationKind.DISPENSE,
        )
        assert operations[0].route_id is SymbolicRouteId.S_TO_P1
        assert operations[2].route_id is SymbolicRouteId.P1_TO_REACTOR
        assert all(operation.cycle_number == cycle.cycle_number for operation in operations)
        assert all(operation.cycle_count == 3 for operation in operations)
        assert operations[1].volume_ml == operations[3].volume_ml == cycle.volume_ml
    assert result.transfer_cycle_plan.cycles[-1].volume_ml == Decimal("1")


def test_exact_multiple_has_no_zero_volume_operations() -> None:
    result = operation_plan(
        total_volume_ml="9",
        combined_volume_ml="3",
        p1_working_volume_ml="3",
    )

    assert result.transfer_cycle_plan.cycle_count == 2
    assert result.operation_count == 8
    assert all(
        operation.volume_ml > 0
        for operation in result.operations
        if isinstance(operation, (AspirateOperation, DispenseOperation))
    )


def test_zero_solvent_volume_is_empty_no_op_plan() -> None:
    result = operation_plan(total_volume_ml="3", combined_volume_ml="3")

    assert result.transfer_cycle_plan.cycle_count == 0
    assert result.operations == ()
    assert result.operation_count == 0


def test_stored_model_fields_are_exact_and_operation_count_is_derived() -> None:
    assert set(P1SolventToReactorOperationPlan.model_fields) == {
        "phase",
        "required_topology_id",
        "transfer_cycle_plan",
        "operations",
    }
    assert "operation_count" not in P1SolventToReactorOperationPlan.model_fields
    assert set(SelectRouteOperation.model_fields) == {
        "operation_kind",
        "operation_number",
        "cycle_number",
        "cycle_count",
        "route_id",
    }
    assert set(AspirateOperation.model_fields) == {
        "operation_kind",
        "operation_number",
        "cycle_number",
        "cycle_count",
        "pump_id",
        "volume_ml",
    }
    assert set(DispenseOperation.model_fields) == set(AspirateOperation.model_fields)


def test_non_p1_phase_is_rejected() -> None:
    values = operation_plan().model_dump()
    values["phase"] = RunPhase.P2_TRANSFER_REACTOR_TO_SF
    invalid_plan(values)


def test_unapproved_required_topology_is_rejected() -> None:
    values = operation_plan().model_dump()
    values["required_topology_id"] = "CURRENT_MACHINE"
    invalid_plan(values)


def test_p2_transfer_cycle_plan_is_rejected() -> None:
    values = operation_plan().model_dump()
    transfer_values = values["transfer_cycle_plan"]
    assert isinstance(transfer_values, dict)
    transfer_values["pump_id"] = PumpId.P2
    invalid_plan(values)


@pytest.mark.parametrize("change", ["missing", "extra"])
def test_missing_or_extra_operation_is_rejected(change: str) -> None:
    values = operation_plan().model_dump()
    operations = values["operations"]
    assert isinstance(operations, tuple)
    changed = list(operations)
    if change == "missing":
        changed.pop()
    else:
        extra = dict(changed[-1])
        extra["operation_number"] = len(changed) + 1
        changed.append(extra)
    values["operations"] = changed
    invalid_plan(values)


@pytest.mark.parametrize(
    ("operation_index", "route_id"),
    [
        (0, SymbolicRouteId.P1_TO_REACTOR),
        (2, SymbolicRouteId.S_TO_P1),
    ],
)
def test_wrong_route_order_is_rejected(
    operation_index: int,
    route_id: SymbolicRouteId,
) -> None:
    values = operation_plan().model_dump()
    operations = list(values["operations"])
    operations[operation_index]["route_id"] = route_id
    values["operations"] = operations
    invalid_plan(values)


def test_dispense_before_aspirate_is_rejected() -> None:
    values = operation_plan().model_dump()
    operations = list(values["operations"])
    operations[1], operations[3] = operations[3], operations[1]
    values["operations"] = operations
    invalid_plan(values)


def test_p2_operation_pump_identity_is_rejected() -> None:
    values = operation_plan().model_dump()
    operations = list(values["operations"])
    operations[1]["pump_id"] = PumpId.P2
    values["operations"] = operations
    invalid_plan(values)


@pytest.mark.parametrize("operation_index", [1, 3])
def test_operation_volume_mismatch_is_rejected(operation_index: int) -> None:
    values = operation_plan().model_dump()
    operations = list(values["operations"])
    operations[operation_index]["volume_ml"] = Decimal("0.5")
    values["operations"] = operations
    invalid_plan(values)


@pytest.mark.parametrize(
    ("operation_index", "operation_number"),
    [(1, 3), (1, 1)],
)
def test_skipped_or_duplicated_operation_number_is_rejected(
    operation_index: int,
    operation_number: int,
) -> None:
    values = operation_plan().model_dump()
    operations = list(values["operations"])
    operations[operation_index]["operation_number"] = operation_number
    values["operations"] = operations
    invalid_plan(values)


@pytest.mark.parametrize(
    ("field", "value"),
    [("cycle_number", 2), ("cycle_count", 2)],
)
def test_incorrect_cycle_metadata_is_rejected(field: str, value: int) -> None:
    values = operation_plan().model_dump()
    operations = list(values["operations"])
    operations[0][field] = value
    values["operations"] = operations
    invalid_plan(values)


def test_non_empty_operations_for_zero_cycle_plan_are_rejected() -> None:
    zero_values = operation_plan(total_volume_ml="3", combined_volume_ml="3").model_dump()
    nonzero_operations = operation_plan().model_dump()["operations"]
    zero_values["operations"] = nonzero_operations
    invalid_plan(zero_values)


@pytest.mark.parametrize(
    "model",
    [
        SelectRouteOperation(
            operation_kind=OperationKind.SELECT_ROUTE,
            operation_number=1,
            cycle_number=1,
            cycle_count=1,
            route_id=SymbolicRouteId.S_TO_P1,
        ),
        AspirateOperation(
            operation_kind=OperationKind.ASPIRATE,
            operation_number=2,
            cycle_number=1,
            cycle_count=1,
            pump_id=PumpId.P1,
            volume_ml="1",
        ),
        DispenseOperation(
            operation_kind=OperationKind.DISPENSE,
            operation_number=4,
            cycle_number=1,
            cycle_count=1,
            pump_id=PumpId.P1,
            volume_ml="1",
        ),
    ],
)
def test_operation_models_are_immutable(model: object) -> None:
    with pytest.raises(ValidationError):
        model.operation_number = 9


def test_plan_is_immutable_and_operations_are_tuple() -> None:
    result = operation_plan()

    assert isinstance(result.operations, tuple)
    with pytest.raises(ValidationError):
        result.operations = ()


def test_json_round_trip_preserves_types_enums_and_decimals() -> None:
    original = operation_plan(
        total_volume_ml="4.00",
        combined_volume_ml="3.00",
        p1_working_volume_ml="0.30",
    )

    restored = P1SolventToReactorOperationPlan.model_validate_json(
        original.model_dump_json()
    )

    assert restored == original
    assert restored.phase is RunPhase.P1_TRANSFER_S_TO_REACTOR
    assert restored.required_topology_id is TopologyId.LABFORGE_V1_APPROVED_TARGET
    assert all(isinstance(operation.operation_kind, OperationKind) for operation in restored.operations)
    assert all(
        isinstance(operation.volume_ml, Decimal)
        for operation in restored.operations
        if isinstance(operation, (AspirateOperation, DispenseOperation))
    )
    assert restored.transfer_cycle_plan.requested_volume_ml.as_tuple() == (
        original.transfer_cycle_plan.requested_volume_ml.as_tuple()
    )


@pytest.mark.parametrize("model_class", [AspirateOperation, DispenseOperation])
@pytest.mark.parametrize("volume_ml", ["0", "-1", "NaN", "Infinity"])
def test_pump_operation_rejects_invalid_volume(
    model_class: type[AspirateOperation] | type[DispenseOperation],
    volume_ml: str,
) -> None:
    with pytest.raises(ValidationError):
        model_class(
            operation_kind=(
                OperationKind.ASPIRATE
                if model_class is AspirateOperation
                else OperationKind.DISPENSE
            ),
            operation_number=1,
            cycle_number=1,
            cycle_count=1,
            pump_id=PumpId.P1,
            volume_ml=volume_ml,
        )


@pytest.mark.parametrize("field", ["operation_number", "cycle_number", "cycle_count"])
@pytest.mark.parametrize("value", [0, -1, True, 1.5, "1"])
def test_operation_integer_fields_are_strict_and_positive(field: str, value: object) -> None:
    values: dict[str, object] = {
        "operation_kind": OperationKind.SELECT_ROUTE,
        "operation_number": 1,
        "cycle_number": 1,
        "cycle_count": 1,
        "route_id": SymbolicRouteId.S_TO_P1,
    }
    values[field] = value
    with pytest.raises(ValidationError):
        SelectRouteOperation(**values)


def test_operation_cycle_number_must_not_exceed_cycle_count() -> None:
    with pytest.raises(ValidationError, match="cycle number"):
        SelectRouteOperation(
            operation_kind=OperationKind.SELECT_ROUTE,
            operation_number=1,
            cycle_number=2,
            cycle_count=1,
            route_id=SymbolicRouteId.S_TO_P1,
        )
