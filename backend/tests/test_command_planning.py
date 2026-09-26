"""Offline tests: all positions, route orders and calibrations are fixtures."""

import json
from dataclasses import FrozenInstanceError
from decimal import Decimal, localcontext

import pytest
from pydantic import ValidationError

from app.demo.calibration_models import PumpCalibration, PumpCalibrationSet, PumpId
from app.demo.column_fraction_collection_operation_plan import (
    ColumnFractionCollectionConfiguration,
    plan_column_fraction_collection_operations,
)
from app.demo.fluid_plan import build_fluid_plan
from app.demo.hardware_contract import BottomValveState
from app.demo.operation_models import (
    AspirateOperation,
    DispenseOperation,
    OperationKind,
    SelectRouteOperation,
    SymbolicRouteId,
)
from app.demo.p1_reagent_operation_plan import plan_p1_reagent_to_reactor_operations
from app.demo.p1_solvent_operation_plan import plan_p1_solvent_to_reactor_operations
from app.demo.p2_reactor_to_sf_operation_plan import plan_p2_reactor_to_sf_operations
from app.demo.p2_sf_to_column_operation_plan import plan_p2_sf_to_column_operations
from app.demo.phases import RunPhase
from app.hardware.command_planning import (
    ArduinoAction,
    CollectionWait,
    CommandPlanningContext,
    CommandPlanningError,
    PumpPlanningState,
    RouteSequence,
    SfBottomValveAction,
    ValveTarget,
    prepare_command_plan,
)
from app.hardware.arduino_command_journal import (
    ArduinoCommandIdentityConflictError,
    SQLiteArduinoCommandJournal,
)
from app.protocol import NdjsonStreamParser, ParseSuccess
from tests.test_p1_solvent_operation_plan import configuration

# Explicit hypothetical switching order for unit tests; no production defaults.
ROUTES = {
    SymbolicRouteId.S_TO_P1: (("V6", 180), ("V1", 90)),
    SymbolicRouteId.B1_TO_P1: (("V4", 180), ("V6", 90), ("V1", 90)),
    SymbolicRouteId.B2_TO_P1: (("V4", 90), ("V6", 90), ("V1", 90)),
    SymbolicRouteId.P1_TO_REACTOR: (("V2", 90), ("V1", 180)),
    SymbolicRouteId.REACTOR_TO_P2: (("V3", 90),),
    SymbolicRouteId.P2_TO_SF_TOP: (("V7", 180), ("V3", 180)),
    SymbolicRouteId.SF_BOTTOM_TO_P2: (("V8", 180), ("V7", 90), ("V3", 180)),
    SymbolicRouteId.P2_TO_COLUMN: (("V5", 90), ("V8", 90), ("V7", 90), ("V3", 180)),
}


def calibration(pump_id, *, full=100, empty=4100, volume="4"):
    return PumpCalibration(
        pump_id=pump_id,
        working_full_chamber_position_steps=full,
        working_empty_chamber_position_steps=empty,
        working_volume_ml=volume,
    )


def context(**changes):
    values = dict(
        phase_execution_id="test-phase-1",
        controller_boot_id=58,
        pumps=tuple(
            PumpPlanningState(calibration=calibration(p), position_steps=4100) for p in PumpId
        ),
        valve_positions=tuple(ValveTarget(valve=f"V{i}", position_degrees=0) for i in range(1, 9)),
        route_sequences=tuple(
            RouteSequence(
                route_id=r,
                targets=tuple(ValveTarget(valve=v, position_degrees=d) for v, d in targets),
            )
            for r, targets in ROUTES.items()
        ),
        reactor_mixer_running=False,
        sf_bottom_valve=BottomValveState.CLOSED,
        column_position_degrees=0,
        carousel_position=40,
    )
    values.update(changes)
    return CommandPlanningContext(**values)


def select(route, number=1):
    return SelectRouteOperation(
        operation_kind=OperationKind.SELECT_ROUTE,
        operation_number=number,
        cycle_number=1,
        cycle_count=1,
        route_id=route,
    )


def aspirate(volume="1", pump=PumpId.P1, number=2):
    return AspirateOperation(
        operation_kind=OperationKind.ASPIRATE,
        operation_number=number,
        cycle_number=1,
        cycle_count=1,
        pump_id=pump,
        volume_ml=volume,
    )


def dispense(volume="1", pump=PumpId.P1, number=2):
    return DispenseOperation(
        operation_kind=OperationKind.DISPENSE,
        operation_number=number,
        cycle_number=1,
        cycle_count=1,
        pump_id=pump,
        volume_ml=volume,
    )


def transfer_plan(kind, ctx):
    calibrations = PumpCalibrationSet(p1=ctx.pumps[0].calibration, p2=ctx.pumps[1].calibration)
    fluid = build_fluid_plan(
        configuration(
            total_mixture_volume_ml="10", combined_b1_b2_volume_ml="4", b1_ratio_percent="50"
        )
    )
    if kind == "solvent":
        return plan_p1_solvent_to_reactor_operations(fluid, calibrations)
    if kind in ("first", "second"):
        phase = (
            RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR
            if kind == "first"
            else RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR
        )
        return plan_p1_reagent_to_reactor_operations(phase, fluid, calibrations)
    if kind == "reactor":
        return plan_p2_reactor_to_sf_operations(fluid, calibrations)
    return plan_p2_sf_to_column_operations(fluid, calibrations)


def collection(count=3):
    return plan_column_fraction_collection_operations(
        ColumnFractionCollectionConfiguration(
            fraction_count=count,
            fraction_duration_seconds="2.5",
            carousel_ready_confirmed=True,
            column_bottom_valve_referenced_confirmed=True,
        )
    ).operations


def all_actions(plan):
    return tuple(a for op in plan.operations for a in (*op.actions, *op.required_followup))


@pytest.mark.parametrize("route", list(SymbolicRouteId))
def test_routes_match_topology_and_preserve_explicit_order(route):
    plan = prepare_command_plan((select(route),), context(column_position_degrees=4))
    assert [
        (dict(a.arguments)["valve"], dict(a.arguments)["position_degrees"])
        for a in plan.operations[0].actions
    ] == list(ROUTES[route])


@pytest.mark.parametrize("kind", ["solvent", "first", "second", "reactor", "sf"])
def test_existing_transfer_builders_lower_to_bounded_commands_without_io(kind, monkeypatch):
    import serial

    monkeypatch.setattr(serial, "Serial", lambda *a, **kw: pytest.fail("Serial opened"))
    ctx = context()
    before = ctx.model_dump_json()
    source = transfer_plan(kind, ctx)
    result = prepare_command_plan(source.operations, ctx)
    assert len(result.operations) == len(source.operations)
    assert dict(result.projected_pump_positions) == {PumpId.P1: 4100, PumpId.P2: 4100}
    assert ctx.model_dump_json() == before
    actions = all_actions(result)
    ids = [a.operation_command_id for a in actions if not isinstance(a, CollectionWait)]
    assert len(ids) == len(set(ids))
    targets = [
        dict(a.arguments)["target_steps"]
        for a in actions
        if isinstance(a, ArduinoAction) and a.command == "PUMP_MOVE_ABSOLUTE_STEPS"
    ]
    assert targets and all(100 <= target <= 4100 for target in targets)
    # Repeated whole cycles must aspirate downward then dispense back to empty.
    assert all(targets[i] < targets[i + 1] == 4100 for i in range(0, len(targets), 2))


def test_nominal_1025_steps_per_ml_preserves_direction_for_both_pumps():
    for pump, route_in, route_out in (
        (PumpId.P1, SymbolicRouteId.S_TO_P1, SymbolicRouteId.P1_TO_REACTOR),
        (PumpId.P2, SymbolicRouteId.REACTOR_TO_P2, SymbolicRouteId.P2_TO_SF_TOP),
    ):
        state = PumpPlanningState(
            calibration=calibration(pump, full=0, empty=20500, volume="20"), position_steps=20500
        )
        result = prepare_command_plan(
            (select(route_in), aspirate("2", pump), select(route_out, 3), dispense("2", pump, 4)),
            context(pumps=(state,)),
        )
        assert dict(result.operations[1].actions[0].arguments)["target_steps"] == 18450
        assert dict(result.operations[3].actions[0].arguments)["target_steps"] == 20500


@pytest.mark.parametrize(
    "volume,message",
    [("20", "HOME is not a transfer"), ("21", "working range"), ("0.001", "whole steps")],
)
def test_nominal_boundary_and_quantization_fail_closed(volume, message):
    state = PumpPlanningState(
        calibration=calibration(PumpId.P1, full=0, empty=20500, volume="20"), position_steps=20500
    )
    with pytest.raises(CommandPlanningError, match=message):
        prepare_command_plan(
            (select(SymbolicRouteId.S_TO_P1), aspirate(volume)), context(pumps=(state,))
        )


def test_exact_conversion_is_independent_of_decimal_context():
    with localcontext() as decimal_context:
        decimal_context.prec = 2
        result = prepare_command_plan(
            (select(SymbolicRouteId.S_TO_P1), aspirate("1.234")), context()
        )
    assert dict(result.operations[1].actions[0].arguments)["target_steps"] == 2866


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"route_sequences": ()}, "switching sequence"),
        ({"valve_positions": ()}, "reference/position"),
        ({"pumps": ()}, "reference/position"),
    ],
)
def test_missing_assumptions_reject_entire_plan(changes, message):
    with pytest.raises(CommandPlanningError, match=message):
        prepare_command_plan((select(SymbolicRouteId.S_TO_P1), aspirate()), context(**changes))


def test_wrong_pump_or_direction_is_rejected():
    for action in (aspirate(pump=PumpId.P2), dispense()):
        with pytest.raises(CommandPlanningError, match="selected route"):
            prepare_command_plan((select(SymbolicRouteId.S_TO_P1), action), context())


def test_unknown_or_open_sf_blocks_p2_switching():
    for state in (None, BottomValveState.OPEN):
        with pytest.raises(CommandPlanningError, match="SF bottom valve CLOSED"):
            prepare_command_plan(
                (select(SymbolicRouteId.REACTOR_TO_P2),), context(sf_bottom_valve=state)
            )


def test_column_filling_requires_closed_column():
    with pytest.raises(CommandPlanningError, match="Column filling"):
        prepare_command_plan((select(SymbolicRouteId.P2_TO_COLUMN),), context())


def test_sf_protected_boundaries_are_not_flattened():
    ctx = context()
    plan = prepare_command_plan(transfer_plan("sf", ctx).operations, ctx)
    prep = plan.operations[0]
    assert prep.actions[0].state is BottomValveState.CLOSED
    assert dict(prep.required_followup[0].arguments) == {"position_degrees": 4}
    for op in plan.operations:
        if op.operation_kind is OperationKind.ASPIRATE_FROM_SF:
            assert isinstance(op.actions[0], SfBottomValveAction)
            assert op.actions[0].state is BottomValveState.OPEN
            assert op.actions[1].command == "PUMP_MOVE_ABSOLUTE_STEPS"
            assert op.required_followup[0].state is BottomValveState.CLOSED


def test_plain_sf_aspiration_is_rejected():
    with pytest.raises(CommandPlanningError, match="protected operation"):
        prepare_command_plan(
            (select(SymbolicRouteId.SF_BOTTOM_TO_P2), aspirate(pump=PumpId.P2)),
            context(column_position_degrees=4),
        )


def test_already_reached_valves_are_skipped_without_losing_scheduler_boundary():
    ctx = context(
        valve_positions=(
            ValveTarget(valve="V6", position_degrees=180),
            ValveTarget(valve="V1", position_degrees=90),
        )
    )
    plan = prepare_command_plan((select(SymbolicRouteId.S_TO_P1),), ctx)
    assert len(plan.operations) == 1
    assert plan.operations[0].actions == ()
    assert (
        prepare_command_plan(collection(1), context(column_position_degrees=4))
        .operations[0]
        .actions
        == ()
    )


def test_collection_uses_explicit_physical_origin_wrap_and_required_close():
    result = prepare_command_plan(collection(), context())
    assert result.projected_carousel_position == 2
    moves = [
        dict(a.arguments)["position"]
        for a in all_actions(result)
        if isinstance(a, ArduinoAction) and a.command == "CAROUSEL_MOVE_TO_POSITION"
    ]
    assert moves == [1, 2]
    for op in result.operations:
        if op.operation_kind is OperationKind.COLLECT_COLUMN_FRACTION:
            assert dict(op.actions[0].arguments) == {"position_degrees": 94}
            assert op.actions[1] == CollectionWait(Decimal("2.5"))
            assert dict(op.required_followup[0].arguments) == {"position_degrees": 4}
    assert result.operations[-1].operation_kind is OperationKind.COLLECT_COLUMN_FRACTION


@pytest.mark.parametrize(
    "changes", [{"carousel_position": None}, {"column_position_degrees": None}]
)
def test_collection_requires_references(changes):
    with pytest.raises(CommandPlanningError):
        prepare_command_plan(collection(), context(**changes))


def test_collection_rejects_reusing_tubes_after_full_revolution():
    assert prepare_command_plan(collection(40), context()).projected_carousel_position == 39
    with pytest.raises(CommandPlanningError):
        prepare_command_plan(collection(41), context())


def test_bad_sequence_does_not_invent_missing_operations():
    with pytest.raises(CommandPlanningError, match="contiguous"):
        prepare_command_plan((select(SymbolicRouteId.S_TO_P1, 2),), context())
    with pytest.raises(CommandPlanningError, match="completed collection"):
        op = collection()[2].model_copy(update={"operation_number": 1})
        prepare_command_plan((op,), context(column_position_degrees=4))


@pytest.mark.parametrize(
    "change",
    [
        {"controller_boot_id": 0},
        {"controller_boot_id": True},
        {"phase_execution_id": "bad/id"},
        {"carousel_position": 0},
        {"carousel_position": 41},
        {"column_position_degrees": True},
    ],
)
def test_context_validation(change):
    with pytest.raises(ValidationError):
        context(**change)


def test_route_rejects_wrong_missing_duplicate_and_extra_targets():
    for targets in (
        (("V1", 180), ("V6", 180)),
        (("V1", 90),),
        (("V1", 90), ("V6", 180), ("V1", 90)),
        (("V1", 90), ("V6", 180), ("V2", 90)),
    ):
        with pytest.raises(ValidationError):
            RouteSequence(
                route_id=SymbolicRouteId.S_TO_P1,
                targets=tuple(ValveTarget(valve=v, position_degrees=d) for v, d in targets),
            )


def test_repreparation_is_stable_and_changes_conflict_in_journal(tmp_path):
    ctx = context()
    operations = (select(SymbolicRouteId.S_TO_P1), aspirate())
    first = prepare_command_plan(operations, ctx)
    assert prepare_command_plan(operations, ctx) == first
    changed = prepare_command_plan((operations[0], aspirate("2")), ctx)
    original_action = first.operations[1].actions[0]
    changed_action = changed.operations[1].actions[0]
    assert original_action.operation_command_id == changed_action.operation_command_id
    with SQLiteArduinoCommandJournal(tmp_path / "intents.db") as journal:

        def persist(action):
            return journal.persist_intent(
                operation_command_id=action.operation_command_id,
                phase_execution_id=ctx.phase_execution_id,
                controller_boot_id=ctx.controller_boot_id,
                command=action.command,
                arguments=dict(action.arguments),
            )

        assert persist(original_action).created
        assert not persist(original_action).created
        with pytest.raises(ArduinoCommandIdentityConflictError):
            persist(changed_action)
    other = prepare_command_plan(operations, context(phase_execution_id="other-phase"))
    assert (
        other.operations[1].actions[0].operation_command_id != original_action.operation_command_id
    )


def test_prepared_actions_are_immutable():
    result = prepare_command_plan((select(SymbolicRouteId.S_TO_P1),), context())
    with pytest.raises(FrozenInstanceError):
        result.operations[0].actions[0].command = "PUMP_HOME"


def test_all_generated_arduino_frames_pass_existing_protocol_parser():
    ctx = context(phase_execution_id="x" * 64, controller_boot_id=2**32 - 1)
    plans = [
        prepare_command_plan(transfer_plan(kind, ctx).operations, ctx)
        for kind in ("solvent", "first", "second", "reactor", "sf")
    ]
    plans.append(prepare_command_plan(collection(), ctx))
    for plan in plans:
        for action in all_actions(plan):
            if not isinstance(action, ArduinoAction):
                continue
            frame = dict(
                protocol="LABFORGE/1",
                type="COMMAND",
                backend_session_nonce="123e4567-e89b-12d3-a456-426614174000",
                controller_boot_id=ctx.controller_boot_id,
                phase_execution_id=ctx.phase_execution_id,
                operation_command_id=action.operation_command_id,
                command=action.command,
                arguments=dict(action.arguments),
            )
            encoded = json.dumps(frame, separators=(",", ":")).encode()
            assert len(encoded) <= 512
            parsed = NdjsonStreamParser().feed(encoded + b"\n")
            assert len(parsed) == 1 and isinstance(parsed[0], ParseSuccess)


@pytest.mark.parametrize("running", [None, True])
def test_reactor_transfer_requires_explicit_stopped_mixer(running):
    with pytest.raises(CommandPlanningError, match="Reactor mixer OFF"):
        prepare_command_plan(
            (select(SymbolicRouteId.REACTOR_TO_P2),), context(reactor_mixer_running=running)
        )


def test_late_failure_returns_no_partial_plan_and_does_not_change_input():
    ctx = context()
    before = ctx.model_dump_json()
    with pytest.raises(CommandPlanningError, match="working range"):
        prepare_command_plan(
            (
                select(SymbolicRouteId.S_TO_P1),
                aspirate("1"),
                select(SymbolicRouteId.P1_TO_REACTOR, 3),
                dispense("2", number=4),
            ),
            ctx,
        )
    assert ctx.model_dump_json() == before


def test_route_order_is_supplied_not_invented():
    ctx = context(
        route_sequences=(
            RouteSequence(
                route_id=SymbolicRouteId.S_TO_P1,
                targets=(
                    ValveTarget(valve="V1", position_degrees=90),
                    ValveTarget(valve="V6", position_degrees=180),
                ),
            ),
        )
    )
    plan = prepare_command_plan((select(SymbolicRouteId.S_TO_P1),), ctx)
    assert [dict(action.arguments)["valve"] for action in plan.operations[0].actions] == [
        "V1",
        "V6",
    ]
