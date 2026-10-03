import hashlib
import json
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier

import pytest
from pydantic import ValidationError

from app.demo.column_fraction_collection_operation_plan import (
    ColumnFractionCollectionConfiguration,
    plan_column_fraction_collection_operations,
)
from app.demo.phases import RunPhase
from app.hardware.command_plan_store import (
    PlanIdentityConflictError,
    PlanIntegrityError,
    PlanSource,
    SQLiteCommandPlanStore,
)
from app.hardware.command_planning import (
    ValveTarget,
    prepare_command_plan,
)
from tests.test_command_planning import context, transfer_plan


def source(kind="solvent", ctx=None, **changes):
    ctx = ctx or context()
    if kind == "column":
        plan = plan_column_fraction_collection_operations(
            ColumnFractionCollectionConfiguration(
                fraction_count=3,
                fraction_duration_seconds=Decimal("2.5"),
                carousel_ready_confirmed=True,
                column_bottom_valve_referenced_confirmed=True,
            )
        )
    else:
        plan = transfer_plan(kind, ctx)
    values = dict(run_id="run-1", run_event_sequence=12, plan=plan)
    values.update(changes)
    return PlanSource(**values)


def test_only_machine_maintenance_may_omit_run_identity(tmp_path):
    from app.demo.maintenance_plan import MaintenanceKind
    from tests.test_owned_maintenance import plan

    with pytest.raises(ValidationError, match="only machine maintenance"):
        source(run_id=None)
    ctx = context()
    original = PlanSource(run_id=None, run_event_sequence=2, plan=plan(MaintenanceKind.FLUSH))
    path = tmp_path / "machine-maintenance.db"
    with SQLiteCommandPlanStore(path) as store:
        saved = store.persist(original, ctx).plan
    with SQLiteCommandPlanStore(path) as store:
        assert store.load(ctx.phase_execution_id) == saved


@pytest.mark.parametrize("kind", ["solvent", "first", "second", "reactor", "sf", "column"])
def test_exact_roundtrip_for_all_source_plans_after_reopening(tmp_path, kind):
    path = tmp_path / "plans.db"
    original = source(kind)
    ctx = context()
    with SQLiteCommandPlanStore(path) as store:
        saved = store.persist(original, ctx)
        assert saved.created
        assert saved.plan.source == original
        assert saved.plan.prepared == prepare_command_plan(original.plan.operations, ctx)
    with SQLiteCommandPlanStore(path) as store:
        loaded = store.load(ctx.phase_execution_id)
        assert loaded == saved.plan
        repeated = store.persist(original, ctx)
        assert not repeated.created and repeated.plan == loaded
        assert store.load("absent-phase") is None


def test_restart_in_fresh_process_only_loads_and_does_not_open_hardware(tmp_path):
    path = tmp_path / "plans.db"
    with SQLiteCommandPlanStore(path) as store:
        saved = store.persist(source("sf"), context())
    code = """
import sys
import serial
from app.hardware.command_plan_store import SQLiteCommandPlanStore

def forbidden(*args, **kwargs):
    raise AssertionError("hardware access during plan load")
serial.Serial = forbidden
with SQLiteCommandPlanStore(sys.argv[1]) as store:
    plan = store.load("test-phase-1")
    print(plan.model_dump_json())
"""
    before = path.read_bytes()
    result = subprocess.run(
        [sys.executable, "-c", code, str(path)], check=True, capture_output=True, text=True
    )
    assert json.loads(result.stdout) == saved.plan.model_dump(mode="json")
    assert path.read_bytes() == before
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == [
            ("prepared_command_plans",)
        ]


def test_changed_source_phase_with_identical_commands_conflicts(tmp_path):
    original = source("first")
    changed_plan = original.plan.model_copy(
        update={"phase": RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR}
    )
    changed = source("first", plan=changed_plan)
    assert prepare_command_plan(original.plan.operations, context()) == prepare_command_plan(
        changed.plan.operations, context()
    )
    with SQLiteCommandPlanStore(tmp_path / "plans.db") as store:
        saved = store.persist(original, context())
        with pytest.raises(PlanIdentityConflictError):
            store.persist(changed, context())
        assert store.load("test-phase-1") == saved.plan


@pytest.mark.parametrize("change", [{"run_id": "run-2"}, {"run_event_sequence": 13}])
def test_run_provenance_is_part_of_identity(tmp_path, change):
    with SQLiteCommandPlanStore(tmp_path / "plans.db") as store:
        store.persist(source(), context())
        with pytest.raises(PlanIdentityConflictError):
            store.persist(source(**change), context())


@pytest.mark.parametrize(
    "change",
    [
        {"controller_boot_id": 59},
        {"carousel_position": 2},
        {"reactor_mixer_running": True},
        {"sf_bottom_valve": "OPEN"},
    ],
)
def test_even_unused_changed_assumptions_conflict(tmp_path, change):
    original, changed = context(), context(**change)
    plan = source().plan
    assert (
        prepare_command_plan(plan.operations, original).operations
        == prepare_command_plan(plan.operations, changed).operations
    )
    with SQLiteCommandPlanStore(tmp_path / "plans.db") as store:
        store.persist(source(), original)
        with pytest.raises(PlanIdentityConflictError):
            store.persist(source(), changed)


def test_changed_initial_pump_position_conflicts(tmp_path):
    ctx = context()
    # Reagent partial cycle still fits with a different starting position.
    pumps = (ctx.pumps[0].model_copy(update={"position_steps": 4000}), ctx.pumps[1])
    with SQLiteCommandPlanStore(tmp_path / "plans.db") as store:
        store.persist(source("first"), ctx)
        with pytest.raises(PlanIdentityConflictError):
            store.persist(source("first"), context(pumps=pumps))


def test_changed_route_order_conflicts_even_when_all_its_actions_are_omitted(tmp_path):
    ctx = context(
        valve_positions=(
            ValveTarget(valve="V6", position_degrees=180),
            ValveTarget(valve="V1", position_degrees=90),
            ValveTarget(valve="V2", position_degrees=90),
        )
    )
    routes = (
        ctx.route_sequences[0].model_copy(
            update={"targets": tuple(reversed(ctx.route_sequences[0].targets))}
        ),
        *ctx.route_sequences[1:],
    )
    changed = context(valve_positions=ctx.valve_positions, route_sequences=routes)
    # One solvent cycle: the reversed initial route is entirely a no-op.
    from tests.test_p1_solvent_operation_plan import configuration
    from app.demo.fluid_plan import build_fluid_plan
    from app.demo.calibration_models import PumpCalibrationSet
    from app.demo.p1_solvent_operation_plan import plan_p1_solvent_to_reactor_operations

    plan = plan_p1_solvent_to_reactor_operations(
        build_fluid_plan(configuration(total_mixture_volume_ml="5", combined_b1_b2_volume_ml="3")),
        PumpCalibrationSet(p1=ctx.pumps[0].calibration, p2=ctx.pumps[1].calibration),
    )
    src = source(plan=plan)
    assert (
        prepare_command_plan(plan.operations, ctx).operations
        == prepare_command_plan(plan.operations, changed).operations
    )
    with SQLiteCommandPlanStore(tmp_path / "plans.db") as store:
        store.persist(src, ctx)
        with pytest.raises(PlanIdentityConflictError):
            store.persist(src, changed)


@pytest.mark.parametrize("mutation", ["omit", "order", "cycle_count", "topology", "phase"])
def test_invalid_copied_source_is_revalidated_before_storage(tmp_path, mutation):
    src = source()
    plan = src.plan
    if mutation == "omit":
        plan = plan.model_copy(update={"operations": plan.operations[:-1]})
    elif mutation == "order":
        plan = plan.model_copy(update={"operations": tuple(reversed(plan.operations))})
    elif mutation == "cycle_count":
        op = plan.operations[0].model_copy(update={"cycle_count": 99})
        plan = plan.model_copy(update={"operations": (op, *plan.operations[1:])})
    elif mutation == "topology":
        plan = plan.model_copy(update={"required_topology_id": "OTHER_TOPOLOGY"})
    else:
        plan = plan.model_copy(update={"phase": RunPhase.REACTION_HOLD})
    with SQLiteCommandPlanStore(tmp_path / "plans.db") as store:
        with pytest.raises(ValueError):
            store.persist(src.model_copy(update={"plan": plan}), context())
        assert store.load("test-phase-1") is None
        assert store.persist(src, context()).created


def test_changed_volume_and_fraction_count_conflict(tmp_path):
    with SQLiteCommandPlanStore(tmp_path / "plans.db") as store:
        original = source("column")
        store.persist(original, context())
        cfg = original.plan.configuration.model_copy(update={"fraction_count": 2})
        changed = source("column", plan=plan_column_fraction_collection_operations(cfg))
        with pytest.raises(PlanIdentityConflictError):
            store.persist(changed, context())
        # Valid different transfer volumes, same phase identity.
        with pytest.raises(PlanIdentityConflictError):
            store.persist(source("first"), context())


def test_different_phase_ids_keep_independent_records(tmp_path):
    with SQLiteCommandPlanStore(tmp_path / "plans.db") as store:
        a = store.persist(source(), context())
        b = store.persist(source(), context(phase_execution_id="phase-2"))
        assert a.created and b.created
        assert store.load("test-phase-1") == a.plan
        assert store.load("phase-2") == b.plan


def test_invalid_context_and_mismatched_capacity_write_nothing(tmp_path):
    with SQLiteCommandPlanStore(tmp_path / "plans.db") as store:
        with pytest.raises(ValidationError):
            store.persist(source(), context().model_copy(update={"controller_boot_id": True}))
        ctx = context()
        pump = ctx.pumps[0]
        changed = pump.model_copy(
            update={
                "calibration": pump.calibration.model_copy(
                    update={"working_volume_ml": Decimal("8")}
                )
            }
        )
        with pytest.raises(ValueError, match="capacity"):
            store.persist(source(), context(pumps=(changed, ctx.pumps[1])))
        assert store.load("test-phase-1") is None


def test_two_connections_racing_identical_input_create_once(tmp_path):
    path = tmp_path / "plans.db"
    with SQLiteCommandPlanStore(path):
        pass
    barrier = Barrier(2)

    def write():
        with SQLiteCommandPlanStore(path) as store:
            barrier.wait(timeout=5)
            return store.persist(source(), context())

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: write(), range(2)))
    assert sorted(result.created for result in results) == [False, True]
    assert results[0].plan == results[1].plan


def test_two_connections_racing_changed_input_cannot_overwrite(tmp_path):
    path = tmp_path / "plans.db"
    with SQLiteCommandPlanStore(path):
        pass
    barrier = Barrier(2)

    def write(run_id):
        with SQLiteCommandPlanStore(path) as store:
            barrier.wait(timeout=5)
            try:
                return store.persist(source(run_id=run_id), context())
            except PlanIdentityConflictError:
                return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, ("run-a", "run-b")))
    winners = [r for r in results if r is not None]
    assert len(winners) == 1 and winners[0].created
    with SQLiteCommandPlanStore(path) as store:
        assert store.load("test-phase-1") == winners[0].plan


def test_interrupted_uncommitted_insert_is_not_visible_after_restart(tmp_path):
    path = tmp_path / "plans.db"
    with SQLiteCommandPlanStore(path) as store:
        store.persist(source(), context())
    code = """
import os, sqlite3, sys
c = sqlite3.connect(sys.argv[1], isolation_level=None)
c.execute("BEGIN IMMEDIATE")
c.execute("INSERT INTO prepared_command_plans SELECT 'interrupted', schema_version, payload_json, payload_sha256 FROM prepared_command_plans")
os._exit(0)
"""
    subprocess.run([sys.executable, "-c", code, str(path)], check=True)
    with SQLiteCommandPlanStore(path) as store:
        assert store.load("interrupted") is None
        assert store.load("test-phase-1") is not None


@pytest.mark.parametrize(
    "mutation",
    [
        "checksum",
        "version",
        "identity",
        "commands",
        "followup",
        "source_unknown_field",
        "missing_source",
        "duplicate_key",
        "invalid_json",
    ],
)
def test_corrupt_or_incompatible_records_fail_closed_without_repair(tmp_path, mutation):
    path = tmp_path / "plans.db"
    with SQLiteCommandPlanStore(path) as store:
        store.persist(source("sf"), context())
    with sqlite3.connect(path) as db:
        payload, digest = db.execute(
            "SELECT payload_json, payload_sha256 FROM prepared_command_plans"
        ).fetchone()
        data = json.loads(payload)
        if mutation == "checksum":
            digest = "0" * 64
        else:
            if mutation == "version":
                data["schema_version"] = 2
            elif mutation == "identity":
                data["prepared"]["assumptions"]["phase_execution_id"] = "other"
            elif mutation == "commands":
                data["prepared"]["operations"][1]["actions"] = []
            elif mutation == "followup":
                data["prepared"]["operations"][2]["required_followup"] = []
            elif mutation == "source_unknown_field":
                data["source"]["plan"]["untracked_parameter"] = 12
            elif mutation == "missing_source":
                del data["source"]
            payload = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            if mutation == "duplicate_key":
                payload = '{"schema_version":1,' + payload[1:]
            if mutation == "invalid_json":
                payload = "{"
            digest = hashlib.sha256(payload.encode()).hexdigest()
        db.execute(
            "UPDATE prepared_command_plans SET payload_json=?, payload_sha256=?", (payload, digest)
        )
    with SQLiteCommandPlanStore(path) as store:
        with pytest.raises(PlanIntegrityError):
            store.load("test-phase-1")
        with pytest.raises(PlanIntegrityError):
            store.persist(source("sf"), context())
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT payload_json, payload_sha256 FROM prepared_command_plans"
        ).fetchone() == (payload, digest)


def test_changed_volume_in_same_source_phase_conflicts(tmp_path):
    from app.demo.operation_models import SymbolicRouteId, build_syringe_transfer_operations
    from app.demo.transfer_cycle_planner import plan_transfer_cycles

    ctx = context()
    original = source()
    cycles = plan_transfer_cycles(Decimal("5"), ctx.pumps[0].calibration)
    operations = build_syringe_transfer_operations(
        cycles,
        aspiration_route_id=SymbolicRouteId.S_TO_P1,
        dispense_route_id=SymbolicRouteId.P1_TO_REACTOR,
    )
    changed = original.model_copy(
        update={
            "plan": original.plan.model_copy(
                update={"transfer_cycle_plan": cycles, "operations": operations}
            )
        }
    )
    with SQLiteCommandPlanStore(tmp_path / "plans.db") as store:
        saved = store.persist(original, ctx)
        with pytest.raises(PlanIdentityConflictError):
            store.persist(changed, ctx)
        assert store.load(ctx.phase_execution_id) == saved.plan


def test_unknown_nested_input_cannot_disappear_from_identity(tmp_path):
    original = source()
    modified = original.model_copy(
        update={"plan": original.plan.model_copy(update={"untracked_parameter": 42})}
    )
    with SQLiteCommandPlanStore(tmp_path / "plans.db") as store:
        with pytest.raises(ValueError, match="lost information"):
            store.persist(modified, context())
        assert store.load("test-phase-1") is None


def test_load_detects_compiler_drift_without_replacing_saved_commands(tmp_path, monkeypatch):
    from dataclasses import replace
    import app.hardware.command_plan_store as module

    path = tmp_path / "plans.db"
    with SQLiteCommandPlanStore(path) as store:
        store.persist(source(), context())
    real_prepare = module.prepare_command_plan

    def changed_prepare(operations, ctx):
        return replace(real_prepare(operations, ctx), operations=())

    monkeypatch.setattr(module, "prepare_command_plan", changed_prepare)
    before = path.read_bytes()
    with SQLiteCommandPlanStore(path) as store:
        with pytest.raises(PlanIntegrityError):
            store.load("test-phase-1")
    assert path.read_bytes() == before


def test_single_store_serializes_cross_thread_writers(tmp_path):
    with SQLiteCommandPlanStore(tmp_path / "plans.db") as store:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: store.persist(source(), context()), range(2)))
        assert sorted(result.created for result in results) == [False, True]
        assert results[0].plan == results[1].plan


@pytest.mark.parametrize("location", ["plan", "operation", "calibration"])
@pytest.mark.parametrize("json_input", [False, True])
def test_raw_unknown_provenance_rejected_before_insert(tmp_path, location, json_input):
    from app.hardware.command_planning import CommandPlanningContext

    raw_source = source().model_dump(mode="json")
    raw_context = context().model_dump(mode="json")
    target = {
        "plan": raw_source["plan"],
        "operation": raw_source["plan"]["operations"][0],
        "calibration": raw_context["pumps"][0]["calibration"],
    }[location]
    target["untracked_parameter"] = 42
    with SQLiteCommandPlanStore(tmp_path / "plans.db") as store:
        with pytest.raises(ValueError, match="lost information"):
            if json_input:
                src = PlanSource.model_validate_json(json.dumps(raw_source))
                ctx = CommandPlanningContext.model_validate_json(json.dumps(raw_context))
            else:
                src = PlanSource(**raw_source)
                ctx = CommandPlanningContext(**raw_context)
            store.persist(src, ctx)
        assert store.load("test-phase-1") is None


def test_incompatible_table_rejected_without_repair(tmp_path):
    path = tmp_path / "plans.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE prepared_command_plans (phase_execution_id TEXT PRIMARY KEY)")
        db.execute("INSERT INTO prepared_command_plans VALUES ('existing')")
    before = path.read_bytes()
    with pytest.raises(PlanIntegrityError, match="schema"):
        SQLiteCommandPlanStore(path)
    assert path.read_bytes() == before
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT * FROM prepared_command_plans").fetchall() == [("existing",)]
