from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.demo.calibration_models import PumpCalibration, PumpCalibrationSet, PumpId
from app.demo.fluid_plan import FluidPlan, build_fluid_plan
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
from app.demo.p1_reagent_operation_plan import (
    P1ReagentOperationPlanningError,
    P1ReagentToReactorOperationPlan,
    ReagentId,
    plan_p1_reagent_to_reactor_operations,
)
from app.demo.phases import RunPhase
from app.demo.transfer_cycle_planner import TransferCycle, TransferCyclePlan


def configuration(**overrides: object) -> DemoConfiguration:
    values: dict[str, object] = {
        "b1_ratio_percent": "20",
        "total_mixture_volume_ml": "10",
        "combined_b1_b2_volume_ml": "5",
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


def calibration_set(
    p1_working_volume_ml: str = "1.5",
    p2_working_volume_ml: str = "7",
) -> PumpCalibrationSet:
    return PumpCalibrationSet(
        p1=calibration(PumpId.P1, p1_working_volume_ml),
        p2=calibration(PumpId.P2, p2_working_volume_ml),
    )


def reagent_plan(
    phase: RunPhase = RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
    *,
    addition_order: AdditionOrder = AdditionOrder.B1_THEN_B2,
    b1_ratio_percent: str = "20",
    p1_working_volume_ml: str = "1.5",
    p2_working_volume_ml: str = "7",
) -> P1ReagentToReactorOperationPlan:
    return plan_p1_reagent_to_reactor_operations(
        phase,
        build_fluid_plan(
            configuration(
                addition_order=addition_order,
                b1_ratio_percent=b1_ratio_percent,
            )
        ),
        calibration_set(p1_working_volume_ml, p2_working_volume_ml),
    )


def invalid_plan(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        P1ReagentToReactorOperationPlan.model_validate(values)


def test_shared_operation_models_and_routes_have_expected_ownership() -> None:
    assert SelectRouteOperation.__module__ == "app.demo.operation_models"
    assert AspirateOperation.__module__ == "app.demo.operation_models"
    assert DispenseOperation.__module__ == "app.demo.operation_models"
    assert set(SymbolicRouteId) == {
        SymbolicRouteId.S_TO_P1,
        SymbolicRouteId.B1_TO_P1,
        SymbolicRouteId.B2_TO_P1,
        SymbolicRouteId.P1_TO_REACTOR,
        SymbolicRouteId.REACTOR_TO_P2,
        SymbolicRouteId.P2_TO_SF_TOP,
    }


def test_operation_kind_remains_fixed_for_discriminated_models() -> None:
    with pytest.raises(ValidationError):
        SelectRouteOperation(
            operation_kind=OperationKind.ASPIRATE,
            operation_number=1,
            cycle_number=1,
            cycle_count=1,
            route_id=SymbolicRouteId.B1_TO_P1,
        )


def test_shared_builder_uses_cycle_plan_pump_and_exact_four_operation_pattern() -> None:
    cycle_plan = TransferCyclePlan(
        pump_id=PumpId.P2,
        requested_volume_ml="2.5",
        working_volume_ml="2.5",
        cycles=(TransferCycle(cycle_number=1, volume_ml="2.5"),),
    )

    operations = build_syringe_transfer_operations(
        cycle_plan,
        aspiration_route_id=SymbolicRouteId.B2_TO_P1,
        dispense_route_id=SymbolicRouteId.P1_TO_REACTOR,
    )

    assert tuple(operation.operation_kind for operation in operations) == (
        OperationKind.SELECT_ROUTE,
        OperationKind.ASPIRATE,
        OperationKind.SELECT_ROUTE,
        OperationKind.DISPENSE,
    )
    assert operations[0].route_id is SymbolicRouteId.B2_TO_P1
    assert operations[2].route_id is SymbolicRouteId.P1_TO_REACTOR
    assert operations[1].pump_id is operations[3].pump_id is PumpId.P2
    assert operations[1].volume_ml == operations[3].volume_ml == Decimal("2.5")


def test_shared_builder_returns_empty_tuple_for_zero_cycle_plan() -> None:
    cycle_plan = TransferCyclePlan(
        pump_id=PumpId.P1,
        requested_volume_ml="0",
        working_volume_ml="3",
        cycles=(),
    )

    assert build_syringe_transfer_operations(
        cycle_plan,
        aspiration_route_id=SymbolicRouteId.B1_TO_P1,
        dispense_route_id=SymbolicRouteId.P1_TO_REACTOR,
    ) == ()


@pytest.mark.parametrize(
    ("addition_order", "phase", "expected_reagent", "expected_volume", "expected_route"),
    [
        (
            AdditionOrder.B1_THEN_B2,
            RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
            ReagentId.B1,
            Decimal("1"),
            SymbolicRouteId.B1_TO_P1,
        ),
        (
            AdditionOrder.B1_THEN_B2,
            RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
            ReagentId.B2,
            Decimal("4"),
            SymbolicRouteId.B2_TO_P1,
        ),
        (
            AdditionOrder.B2_THEN_B1,
            RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
            ReagentId.B2,
            Decimal("4"),
            SymbolicRouteId.B2_TO_P1,
        ),
        (
            AdditionOrder.B2_THEN_B1,
            RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
            ReagentId.B1,
            Decimal("1"),
            SymbolicRouteId.B1_TO_P1,
        ),
    ],
)
def test_both_addition_orders_resolve_reagent_volume_and_symbolic_route(
    addition_order: AdditionOrder,
    phase: RunPhase,
    expected_reagent: ReagentId,
    expected_volume: Decimal,
    expected_route: SymbolicRouteId,
) -> None:
    result = reagent_plan(phase, addition_order=addition_order)

    assert result.reagent_id is expected_reagent
    assert result.transfer_cycle_plan.requested_volume_ml == expected_volume
    assert result.transfer_cycle_plan.pump_id is PumpId.P1
    assert result.required_topology_id is TopologyId.LABFORGE_V1_APPROVED_TARGET
    for index in range(0, result.operation_count, 4):
        assert result.operations[index].route_id is expected_route
        assert result.operations[index + 2].route_id is SymbolicRouteId.P1_TO_REACTOR
        assert result.operations[index + 1].pump_id is PumpId.P1
        assert result.operations[index + 3].pump_id is PumpId.P1


def test_p1_calibration_controls_cycles_and_p2_calibration_does_not() -> None:
    first = reagent_plan(
        RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
        p1_working_volume_ml="1.5",
        p2_working_volume_ml="0.1",
    )
    second = reagent_plan(
        RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
        p1_working_volume_ml="1.5",
        p2_working_volume_ml="9",
    )

    assert first == second
    assert tuple(cycle.volume_ml for cycle in first.transfer_cycle_plan.cycles) == (
        Decimal("1.5"),
        Decimal("1.5"),
        Decimal("1.0"),
    )
    assert tuple(
        operation.volume_ml
        for operation in first.operations
        if isinstance(operation, (AspirateOperation, DispenseOperation))
    ) == (
        Decimal("1.5"),
        Decimal("1.5"),
        Decimal("1.5"),
        Decimal("1.5"),
        Decimal("1.0"),
        Decimal("1.0"),
    )


def test_exact_multiple_has_no_zero_volume_operation() -> None:
    result = reagent_plan(b1_ratio_percent="60", p1_working_volume_ml="1.5")

    assert tuple(cycle.volume_ml for cycle in result.transfer_cycle_plan.cycles) == (
        Decimal("1.5"),
        Decimal("1.5"),
    )
    assert all(
        operation.volume_ml > 0
        for operation in result.operations
        if isinstance(operation, (AspirateOperation, DispenseOperation))
    )


@pytest.mark.parametrize(
    ("addition_order", "phase", "b1_ratio_percent", "expected_reagent"),
    [
        (
            AdditionOrder.B1_THEN_B2,
            RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
            "0",
            ReagentId.B1,
        ),
        (
            AdditionOrder.B1_THEN_B2,
            RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
            "100",
            ReagentId.B2,
        ),
        (
            AdditionOrder.B2_THEN_B1,
            RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
            "100",
            ReagentId.B2,
        ),
        (
            AdditionOrder.B2_THEN_B1,
            RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
            "0",
            ReagentId.B1,
        ),
    ],
)
def test_zero_reagent_volume_is_empty_no_op_plan(
    addition_order: AdditionOrder,
    phase: RunPhase,
    b1_ratio_percent: str,
    expected_reagent: ReagentId,
) -> None:
    result = reagent_plan(
        phase,
        addition_order=addition_order,
        b1_ratio_percent=b1_ratio_percent,
    )

    assert result.reagent_id is expected_reagent
    assert result.transfer_cycle_plan.requested_volume_ml == Decimal("0")
    assert result.transfer_cycle_plan.cycle_count == 0
    assert result.operations == ()
    assert result.operation_count == 0


SUPPORTED_PHASES = {
    RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
    RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
}


@pytest.mark.parametrize("phase", [phase for phase in RunPhase if phase not in SUPPORTED_PHASES])
def test_every_other_phase_is_rejected(phase: RunPhase) -> None:
    with pytest.raises(P1ReagentOperationPlanningError, match=phase.value):
        plan_p1_reagent_to_reactor_operations(
            phase,
            build_fluid_plan(configuration()),
            calibration_set(),
        )


@pytest.mark.parametrize(
    ("phase", "identity_field"),
    [
        (RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR, "first_liquid"),
        (RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR, "second_liquid"),
    ],
)
def test_unexpected_reagent_identity_is_rejected(
    phase: RunPhase,
    identity_field: str,
) -> None:
    valid_plan = build_fluid_plan(configuration())
    values = valid_plan.model_dump()
    values[identity_field] = "unexpected"

    with pytest.raises(P1ReagentOperationPlanningError, match="unexpected"):
        plan_p1_reagent_to_reactor_operations(
            phase,
            FluidPlan.model_validate(values),
            calibration_set(),
        )


def test_plan_fields_are_exact_and_operation_count_is_derived() -> None:
    assert set(P1ReagentToReactorOperationPlan.model_fields) == {
        "phase",
        "reagent_id",
        "required_topology_id",
        "transfer_cycle_plan",
        "operations",
    }
    assert "operation_count" not in P1ReagentToReactorOperationPlan.model_fields


def test_wrong_required_topology_is_rejected() -> None:
    values = reagent_plan().model_dump()
    values["required_topology_id"] = "CURRENT_MACHINE"
    invalid_plan(values)


def test_p2_transfer_cycle_plan_is_rejected() -> None:
    values = reagent_plan().model_dump()
    transfer_values = values["transfer_cycle_plan"]
    assert isinstance(transfer_values, dict)
    transfer_values["pump_id"] = PumpId.P2
    invalid_plan(values)


@pytest.mark.parametrize(
    ("operation_index", "field", "value"),
    [
        (0, "route_id", SymbolicRouteId.B2_TO_P1),
        (2, "route_id", SymbolicRouteId.B1_TO_P1),
        (1, "pump_id", PumpId.P2),
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
    values = reagent_plan().model_dump()
    operations = list(values["operations"])
    operations[operation_index][field] = value
    values["operations"] = operations
    invalid_plan(values)


@pytest.mark.parametrize("change", ["missing", "extra", "wrong_order"])
def test_incorrect_operation_sequence_is_rejected(change: str) -> None:
    values = reagent_plan().model_dump()
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


def test_non_empty_operations_for_zero_cycle_plan_are_rejected() -> None:
    zero_values = reagent_plan(b1_ratio_percent="0").model_dump()
    zero_values["operations"] = reagent_plan().model_dump()["operations"]
    invalid_plan(zero_values)


def test_plan_is_immutable_and_operations_are_tuple() -> None:
    result = reagent_plan()

    assert isinstance(result.operations, tuple)
    with pytest.raises(ValidationError):
        result.operations = ()


def test_json_round_trip_preserves_domain_types_and_decimals() -> None:
    original = reagent_plan(
        RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
        addition_order=AdditionOrder.B2_THEN_B1,
        p1_working_volume_ml="0.30",
    )

    restored = P1ReagentToReactorOperationPlan.model_validate_json(
        original.model_dump_json()
    )

    assert restored == original
    assert restored.phase is RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR
    assert restored.reagent_id is ReagentId.B2
    assert isinstance(restored.operations[0], SelectRouteOperation)
    assert isinstance(restored.operations[1], AspirateOperation)
    assert isinstance(restored.operations[2], SelectRouteOperation)
    assert isinstance(restored.operations[3], DispenseOperation)
    assert restored.operations[0].route_id is SymbolicRouteId.B2_TO_P1
    assert all(
        isinstance(operation.volume_ml, Decimal)
        for operation in restored.operations
        if isinstance(operation, (AspirateOperation, DispenseOperation))
    )
