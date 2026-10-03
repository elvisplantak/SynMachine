from datetime import UTC, datetime
import sqlite3
import subprocess
import sys

import pytest

from app.demo.calibration_models import PumpCalibrationSet
from app.demo.hardware_contract import BottomValveState
from app.demo.maintenance_plan import (
    FlushPolicy,
    MaintenanceKind,
    MaintenancePlan,
    RecoveryOperation,
)
from app.demo.machine_models import MachineState
from app.demo.operation_models import OperationKind
from app.demo.run_models import RunStatus
from app.hardware.command_planning import ArduinoAction
from app.hardware.owned_maintenance import MaintenanceReadiness
from app.hardware.owned_startup_inspection import inspect_owned_startup
from app.hardware.sequence_ownership import OwnershipBlocked
from app.hardware.arduino_serial import ArduinoUnavailableError
from app.demo.operation_executor import ProtectedOperationError
from app.hardware.simulated_p1_runner import SimulationBlocked
from tests.test_owned_offline_runtime import bundle as bundle, open_runtime, start
from tests.test_owned_phase_session import READINESS
from tests.test_command_planning import context
from tests.test_execution_coordinator import CONFIGURATION
from tests.test_owned_timed_execution import TIMED_SETTINGS
from tests.test_owned_offline_runtime import child_arguments


def readiness():
    return MaintenanceReadiness(
        operator="test operator",
        evidence_note="independent fake-only fixture",
        waste_air_gap_verified=True,
        switching_sequences_verified=True,
        working_calibrations_verified=True,
        reactor_mixer_stopped=True,
        carousel_manually_aligned=True,
    )


def plan(kind):
    ctx = context()
    values = {
        "kind": kind,
        "calibrations": PumpCalibrationSet(
            p1=ctx.pumps[0].calibration, p2=ctx.pumps[1].calibration
        ),
    }
    if kind is MaintenanceKind.RECOVERY:
        values["recovery"] = RecoveryOperation(
            operation_kind=OperationKind.RECOVER_REFERENCES,
            operation_number=1,
            valve_home_order=tuple(f"V{i}" for i in range(1, 9)),
            carousel_position=40,
        )
    else:
        values["flush"] = FlushPolicy(
            liquid_volume_ml="3",
            air_volume_ml="2",
            column_drain_seconds="1",
            safe_tube_volume_ml="8",
            rinse_start_position=40,
        )
    return MaintenancePlan(**values)


def execute(runtime, kind, stop_requested=lambda: False):
    return runtime.execute_maintenance(
        "run-1",
        plan(kind),
        readiness(),
        occurred_at=datetime.now(UTC),
        stop_requested=stop_requested,
    )


def interrupt(bundle):
    with open_runtime(bundle) as runtime:
        start(runtime)
        runtime.execute_next()


def recover(runtime):
    runtime.reconcile_interruption(datetime.now(UTC))
    return execute(runtime, MaintenanceKind.RECOVERY)


def new_run(runtime):
    ctx = context()
    runtime.start_new_run(
        "run-2",
        CONFIGURATION,
        TIMED_SETTINGS,
        PumpCalibrationSet(p1=ctx.pumps[0].calibration, p2=ctx.pumps[1].calibration),
        occurred_at=datetime.now(UTC),
        column_readiness=READINESS,
    )


def test_recovery_flush_new_complete_demo_uses_one_path(bundle):
    interrupt(bundle)
    with open_runtime(bundle) as runtime:
        assert recover(runtime).state is MachineState.FLUSH_REQUIRED
        owner = inspect_owned_startup(bundle).owner_id
        with pytest.raises(OwnershipBlocked):
            new_run(runtime)
        assert execute(runtime, MaintenanceKind.FLUSH).state is MachineState.READY
        assert inspect_owned_startup(bundle).owner_id is None
        assert runtime._store.load_demo_run("run-1").status is RunStatus.FAULTED
        assert runtime._owner._db.execute(
            "SELECT state FROM hardware_sequences WHERE sequence_id=?", (owner,)
        ).fetchone() == ("COMPLETED",)
        new_run(runtime)
        for _ in range(10):
            result = runtime.execute_next()
        assert result.run.status is RunStatus.COMPLETED
        assert runtime._store.load_demo_run("run-1").status is RunStatus.FAULTED


def test_recovery_homes_routes_before_pumps_and_flush_never_rehomes(bundle):
    interrupt(bundle)
    with open_runtime(bundle) as runtime:
        recover(runtime)
        calls = runtime._runner.device.calls
        assert calls[0]["command"] == "SF_MIXER_SET_STATE"
        for pump in ("P1", "P2"):
            index = next(
                i
                for i, c in enumerate(calls)
                if c["command"] == "PUMP_HOME" and c["arguments"]["pump"] == pump
            )
            valves = {}
            for c in calls[:index]:
                if c["command"] == "VALVE_SET_POSITION":
                    valves[c["arguments"]["valve"]] = c["arguments"]["position_degrees"]
            required = (
                {"V1": 180, "V2": 180}
                if pump == "P1"
                else {"V3": 180, "V7": 90, "V8": 90, "V5": 180}
            )
            assert all(valves[v] == target for v, target in required.items())
        boundary = len(calls)
        execute(runtime, MaintenanceKind.FLUSH)
        assert not any(c["command"].endswith("HOME") for c in calls[boundary:])
        assert runtime._maintenance._state.sf_bottom_valve is BottomValveState.CLOSED
        assert runtime._maintenance._state.column_position_degrees == 4


def test_new_run_after_flush_restart_requires_new_fixture_not_old_run(bundle):
    interrupt(bundle)
    with open_runtime(bundle) as runtime:
        recover(runtime)
        execute(runtime, MaintenanceKind.FLUSH)
    with open_runtime(bundle) as runtime:
        new_run(runtime)
        assert runtime.execute_next().run.run_id == "run-2"


def test_flush_cannot_use_restarted_reference_state(bundle):
    interrupt(bundle)
    with open_runtime(bundle) as runtime:
        recover(runtime)
    with open_runtime(bundle) as runtime:
        with pytest.raises(SimulationBlocked, match="continuity"):
            execute(runtime, MaintenanceKind.FLUSH)
        assert runtime._runner.device.calls == []
        assert inspect_owned_startup(bundle).owner_id is not None


@pytest.mark.parametrize("kind", list(MaintenanceKind))
def test_command_failure_keeps_intent_and_owner_and_never_allows_new_run(bundle, kind):
    interrupt(bundle)
    with open_runtime(bundle) as runtime:
        runtime.reconcile_interruption(datetime.now(UTC))
        if kind is MaintenanceKind.FLUSH:
            execute(runtime, MaintenanceKind.RECOVERY)

        def fail(_):
            raise RuntimeError("transport failed")

        runtime._runner.device.before_send = fail
        with pytest.raises(RuntimeError, match="transport failed"):
            execute(runtime, kind)
        assert runtime._store.load_machine_snapshot().active_maintenance.kind is kind
        assert inspect_owned_startup(bundle).owner_id is not None
        with pytest.raises(OwnershipBlocked):
            new_run(runtime)
    with open_runtime(bundle) as runtime:
        assert (
            runtime.reconcile_maintenance_interruption(datetime.now(UTC)).state
            is MachineState.RECOVERING
        )
        assert runtime._runner.device.calls == []
        assert execute(runtime, MaintenanceKind.RECOVERY).state is MachineState.FLUSH_REQUIRED


@pytest.mark.parametrize("kind", list(MaintenanceKind))
def test_stop_at_operation_boundary_retains_owner(bundle, kind):
    interrupt(bundle)
    with open_runtime(bundle) as runtime:
        recover(runtime)
    with open_runtime(bundle) as runtime:
        if kind is MaintenanceKind.FLUSH:
            execute(runtime, MaintenanceKind.RECOVERY)
        flag = [False]
        runtime._runner.device.before_send = lambda _: flag.__setitem__(0, True)
        with pytest.raises(SimulationBlocked, match="stopped"):
            execute(runtime, kind, lambda: flag[0])
        assert inspect_owned_startup(bundle).owner_id is not None
        assert runtime._store.load_machine_snapshot().state is not MachineState.READY


def test_flush_completion_write_failure_never_releases_owner(bundle, monkeypatch):
    interrupt(bundle)
    with open_runtime(bundle) as runtime:
        recover(runtime)
        original = runtime._store.persist_maintenance_transition

        def fail(expected, machine, event):
            if machine.state is MachineState.READY:
                raise sqlite3.OperationalError("completion failed")
            return original(expected, machine, event)

        monkeypatch.setattr(runtime._store, "persist_maintenance_transition", fail)
        with pytest.raises(sqlite3.OperationalError):
            execute(runtime, MaintenanceKind.FLUSH)
        assert runtime._store.load_machine_snapshot().state is MachineState.FLUSHING
        assert inspect_owned_startup(bundle).owner_id is not None


def test_release_failure_after_ready_requires_deliberate_recovery(bundle, monkeypatch):
    interrupt(bundle)
    with open_runtime(bundle) as runtime:
        recover(runtime)
        monkeypatch.setattr(
            runtime._owner,
            "complete",
            lambda _: (_ for _ in ()).throw(sqlite3.OperationalError("release failed")),
        )
        with pytest.raises(sqlite3.OperationalError):
            execute(runtime, MaintenanceKind.FLUSH)
        assert runtime._store.load_machine_snapshot().state is MachineState.READY
        with pytest.raises(OwnershipBlocked):
            new_run(runtime)
    with open_runtime(bundle) as runtime:
        assert execute(runtime, MaintenanceKind.RECOVERY).state is MachineState.FLUSH_REQUIRED


def test_flush_sf_aspiration_and_column_drain_keep_required_closes(bundle):
    interrupt(bundle)
    with open_runtime(bundle) as runtime:
        recover(runtime)
        execute(runtime, MaintenanceKind.FLUSH)
        stored = runtime._runner.load_plan(runtime._maintenance._phase_id)
        aspiration = [
            op
            for op in stored.prepared.operations
            if op.operation_kind is OperationKind.ASPIRATE_FROM_SF
        ]
        assert len(aspiration) == 3
        assert all(op.required_followup[0].state is BottomValveState.CLOSED for op in aspiration)
        drains = [
            op
            for op in stored.prepared.operations
            if op.operation_kind is OperationKind.COLLECT_COLUMN_FRACTION
        ]
        assert len(drains) == 3
        assert all(
            dict(op.required_followup[0].arguments) == {"position_degrees": 4} for op in drains
        )
        moves = [
            a
            for op in stored.prepared.operations
            for a in op.actions
            if isinstance(a, ArduinoAction) and a.command == "CAROUSEL_MOVE_TO_POSITION"
        ]
        assert [dict(a.arguments)["position"] for a in moves] == [1, 2]


def test_clean_stop_flushes_retained_pump_contents_without_homing(bundle):
    from app.demo.application_service import GuidedDemoApplicationService

    with open_runtime(bundle) as runtime:
        start(runtime)

        def stop_during_aspiration(command):
            if command["command"] == "PUMP_MOVE_ABSOLUTE_STEPS":
                runtime._runner.device.before_send = lambda _: None
                GuidedDemoApplicationService(runtime._store).request_stop_demo(
                    "run-1", datetime.now(UTC)
                )

        runtime._runner.device.before_send = stop_during_aspiration
        result = runtime.execute_next()
        assert result.run.status is RunStatus.ABORTED
        assert result.machine.state is MachineState.FLUSH_REQUIRED
        boundary = len(runtime._runner.device.calls)
        assert execute(runtime, MaintenanceKind.FLUSH).state is MachineState.READY
        calls = runtime._runner.device.calls[boundary:]
        assert not any(command["command"].endswith("HOME") for command in calls)
        empty = next(
            command for command in calls if command["command"] == "PUMP_MOVE_ABSOLUTE_STEPS"
        )
        assert empty["arguments"] == {"pump": "P1", "target_steps": 4100}
        new_run(runtime)
        assert runtime.execute_next().run.run_id == "run-2"


def test_stop_during_sf_aspiration_closes_before_retaining_owner(bundle):
    interrupt(bundle)
    with open_runtime(bundle) as runtime:
        recover(runtime)
        flag = [False]

        def stop(command):
            if (
                command["command"] == "PUMP_MOVE_ABSOLUTE_STEPS"
                and runtime._maintenance._state.sf_bottom_valve is BottomValveState.OPEN
            ):
                flag[0] = True

        runtime._runner.device.before_send = stop
        with pytest.raises(SimulationBlocked, match="stopped"):
            execute(runtime, MaintenanceKind.FLUSH, lambda: flag[0])
        assert runtime._runner.device.sf_calls[-1]["state"] == "CLOSED"
        assert inspect_owned_startup(bundle).owner_id is not None
        assert runtime._store.load_machine_snapshot().state is MachineState.FLUSHING


def test_stop_during_column_drain_closes_and_does_not_move_carousel(bundle):
    from app.hardware.execution_timer import MonotonicExecutionTimer

    interrupt(bundle)
    with open_runtime(bundle) as runtime:
        recover(runtime)
        flag = [False]
        runtime._runner._timer = MonotonicExecutionTimer(
            sleeper=lambda _: flag.__setitem__(0, True)
        )
        with pytest.raises(SimulationBlocked, match="stopped"):
            execute(runtime, MaintenanceKind.FLUSH, lambda: flag[0])
        calls = runtime._runner.device.calls
        assert calls[-1]["command"] == "COLUMN_BOTTOM_VALVE_SET_POSITION"
        assert calls[-1]["arguments"] == {"position_degrees": 4}
        assert not any(command["command"] == "CAROUSEL_MOVE_TO_POSITION" for command in calls)


@pytest.mark.parametrize("kind", list(MaintenanceKind))
def test_actual_process_death_never_replays_maintenance(bundle, kind):
    interrupt(bundle)
    script = """
import json, os, sys
from pathlib import Path
from datetime import UTC, datetime
from app.hardware.owned_startup_inspection import OfflineDatabaseBundle
from app.demo.maintenance_plan import MaintenanceKind
from tests.test_owned_offline_runtime import open_runtime
from tests.test_owned_maintenance import execute
values = json.loads(sys.argv[1])
for key in values:
    if key.endswith("_path"): values[key] = Path(values[key])
bundle = OfflineDatabaseBundle(**values)
with open_runtime(bundle) as runtime:
    runtime.reconcile_interruption(datetime.now(UTC))
    kind = MaintenanceKind(sys.argv[2])
    if kind is MaintenanceKind.FLUSH: execute(runtime, MaintenanceKind.RECOVERY)
    runtime._runner.device.before_send = lambda _: os._exit(81)
    execute(runtime, kind)
"""
    result = subprocess.run(
        [sys.executable, "-c", script, child_arguments(bundle), kind.value], timeout=15
    )
    assert result.returncode == 81
    evidence = bundle.execution_path.read_bytes()
    with open_runtime(bundle) as runtime:
        machine = runtime._store.load_machine_snapshot()
        assert machine.active_maintenance.kind is kind
        runtime.reconcile_maintenance_interruption(datetime.now(UTC))
        assert runtime._runner.device.calls == []
        assert runtime._runner.device.sf_calls == []
        assert inspect_owned_startup(bundle).owner_id is not None
        with pytest.raises(OwnershipBlocked):
            new_run(runtime)
    assert evidence == bundle.execution_path.read_bytes()


def test_final_command_session_change_blocks_completion(bundle):
    interrupt(bundle)
    with open_runtime(bundle) as runtime:
        runtime.reconcile_interruption(datetime.now(UTC))

        def change(command):
            if command["command"] == "CAROUSEL_SET_REFERENCE":
                runtime._runner.device.arduino_session_id = "replacement"

        runtime._runner.device.before_send = change
        with pytest.raises(SimulationBlocked, match="session"):
            execute(runtime, MaintenanceKind.RECOVERY)
        assert runtime._store.load_machine_snapshot().state is MachineState.RECOVERING
        assert runtime._store.load_machine_snapshot().active_maintenance is not None
        assert inspect_owned_startup(bundle).owner_id is not None


def test_legacy_domain_completion_cannot_clear_owned_flush(bundle):
    from app.demo.application_service import (
        GuidedDemoApplicationService,
        GuidedDemoApplicationError,
    )

    interrupt(bundle)
    with open_runtime(bundle) as runtime:
        recover(runtime)

        def bypass(command):
            with pytest.raises(GuidedDemoApplicationError, match="command-result"):
                GuidedDemoApplicationService(runtime._store).complete_flush(datetime.now(UTC))

        runtime._runner.device.before_send = bypass
        execute(runtime, MaintenanceKind.FLUSH)


@pytest.mark.parametrize(
    "target", ["mixer-stop", "column-home", "V8-home", "P1-home", "P2-empty", "carousel-reference"]
)
def test_unknown_recovery_command_at_each_safety_stage_retains_evidence(bundle, target):
    interrupt(bundle)
    with open_runtime(bundle) as runtime:
        runtime.reconcile_interruption(datetime.now(UTC))

        def fail(command):
            args = command["arguments"]
            selected = {
                "mixer-stop": command["command"] == "SF_MIXER_SET_STATE",
                "column-home": command["command"] == "COLUMN_BOTTOM_VALVE_HOME",
                "V8-home": command["command"] == "VALVE_HOME" and args.get("valve") == "V8",
                "P1-home": command["command"] == "PUMP_HOME" and args.get("pump") == "P1",
                "P2-empty": command["command"] == "PUMP_MOVE_ABSOLUTE_STEPS"
                and args.get("pump") == "P2",
                "carousel-reference": command["command"] == "CAROUSEL_SET_REFERENCE",
            }
            if selected[target]:
                raise ArduinoUnavailableError("unknown recovery outcome")

        runtime._runner.device.before_send = fail
        with pytest.raises(ArduinoUnavailableError, match="unknown recovery outcome"):
            execute(runtime, MaintenanceKind.RECOVERY)
        row = runtime._runner._db.execute(
            "SELECT state FROM arduino_command_journal WHERE phase_execution_id=? AND state='OUTCOME_UNKNOWN'",
            (runtime._maintenance._phase_id,),
        ).fetchall()
        assert row == [("OUTCOME_UNKNOWN",)]
        assert runtime._store.load_machine_snapshot().active_maintenance is not None
        assert inspect_owned_startup(bundle).owner_id is not None


def test_sf_primary_and_required_close_failure_preserve_both_errors(bundle):
    interrupt(bundle)
    with open_runtime(bundle) as runtime:
        recover(runtime)

        def primary(command):
            if (
                command["command"] == "PUMP_MOVE_ABSOLUTE_STEPS"
                and runtime._maintenance._state.sf_bottom_valve is BottomValveState.OPEN
            ):
                raise ArduinoUnavailableError("primary unknown")

        def close(command):
            if (
                command["state"] == "CLOSED"
                and runtime._maintenance._state.sf_bottom_valve is BottomValveState.OPEN
            ):
                raise RuntimeError("required close unknown")

        runtime._runner.device.before_send = primary
        runtime._runner.device.before_sf_send = close
        with pytest.raises(ProtectedOperationError) as result:
            execute(runtime, MaintenanceKind.FLUSH)
        assert str(result.value.primary_error) == "primary unknown"
        assert str(result.value.followup_error) == "required close unknown"
        assert inspect_owned_startup(bundle).owner_id is not None
        assert runtime._store.load_machine_snapshot().state is MachineState.FLUSHING


@pytest.mark.parametrize(
    "field,value",
    [
        ("liquid_volume_ml", "0"),
        ("air_volume_ml", "NaN"),
        ("column_drain_seconds", "-1"),
        ("safe_tube_volume_ml", "10"),
        ("rinse_start_position", 0),
    ],
)
def test_missing_or_unsafe_flush_values_are_not_invented(field, value):
    from pydantic import ValidationError

    values = plan(MaintenanceKind.FLUSH).flush.model_dump()
    values[field] = value
    with pytest.raises(ValidationError):
        FlushPolicy(**values)


def test_new_run_after_normal_completion_does_not_require_flush(bundle):
    with open_runtime(bundle) as runtime:
        start(runtime)
        for _ in range(10):
            runtime.execute_next()
        new_run(runtime)
        assert runtime.execute_next().run.run_id == "run-2"


def test_readiness_rejects_integer_disguised_as_confirmation():
    from pydantic import ValidationError

    values = readiness().model_dump()
    values["waste_air_gap_verified"] = 1
    with pytest.raises(ValidationError):
        MaintenanceReadiness(**values)


def test_completed_service_after_reopen_invalidates_new_run_fixture(bundle):
    interrupt(bundle)
    with open_runtime(bundle) as runtime:
        recover(runtime)
        execute(runtime, MaintenanceKind.FLUSH)
    with open_runtime(bundle) as runtime:
        lease = runtime._owner.claim("intervening-service")
        runtime._owner.complete(lease)
        with pytest.raises(SimulationBlocked, match="ownership changed"):
            new_run(runtime)
        assert runtime._runner.device.calls == []


def test_recovery_flush_does_not_rewrite_unknown_old_command_evidence(bundle):
    from uuid import uuid4
    from tests.test_owned_offline_runtime import interrupted_wait

    with open_runtime(bundle) as runtime:
        interrupted_wait(runtime, started=True)
        old_id = str(uuid4())
        runtime._runner._journal.persist_intent(
            operation_command_id=old_id,
            phase_execution_id="interrupted-wait",
            controller_boot_id=58,
            command="PUMP_MOVE_ABSOLUTE_STEPS",
            arguments={"pump": "P1", "target_steps": 2000},
        )
        before = runtime._runner._journal.load(old_id)
    with open_runtime(bundle) as runtime:
        recover(runtime)
        execute(runtime, MaintenanceKind.FLUSH)
        assert runtime._runner._journal.load(old_id) == before
        assert runtime._store.load_demo_run("run-1").status is RunStatus.FAULTED


@pytest.mark.parametrize("kind", list(MaintenanceKind))
def test_stop_during_final_command_cannot_authorize_completion(bundle, kind):
    interrupt(bundle)
    with open_runtime(bundle) as runtime:
        runtime.reconcile_interruption(datetime.now(UTC))
        if kind is MaintenanceKind.FLUSH:
            execute(runtime, MaintenanceKind.RECOVERY)
        flag = [False]

        def stop_last(command):
            if kind is MaintenanceKind.RECOVERY:
                if command["command"] == "CAROUSEL_SET_REFERENCE":
                    flag[0] = True
            elif (
                command["command"] == "COLUMN_BOTTOM_VALVE_SET_POSITION"
                and command["arguments"]["position_degrees"] == 4
            ):
                openings = sum(
                    c["command"] == "COLUMN_BOTTOM_VALVE_SET_POSITION"
                    and c["arguments"]["position_degrees"] == 94
                    for c in runtime._runner.device.calls
                )
                if openings == 3:
                    flag[0] = True

        runtime._runner.device.before_send = stop_last
        with pytest.raises(SimulationBlocked, match="stopped"):
            execute(runtime, kind, lambda: flag[0])
        assert flag[0]
        assert runtime._store.load_machine_snapshot().active_maintenance is not None
        assert inspect_owned_startup(bundle).owner_id is not None


def test_recovery_establishes_missing_references_only_after_successful_commands(bundle):
    from app.hardware.simulated_p1_runner import SimulatedP1Device
    from app.hardware.owned_offline_runtime import OwnedOfflineRuntime
    from tests.test_owned_pausable_demo import Clock

    interrupt(bundle)
    device = SimulatedP1Device(
        context(
            valve_positions=(),
            carousel_position=None,
            column_position_degrees=None,
            sf_bottom_valve=None,
        )
    )
    with OwnedOfflineRuntime(bundle, device, timer=Clock().timer()) as runtime:
        runtime.reconcile_interruption(datetime.now(UTC))
        assert execute(runtime, MaintenanceKind.RECOVERY).state is MachineState.FLUSH_REQUIRED
        assert len(runtime._maintenance._state.valve_positions) == 8
        assert runtime._maintenance._state.carousel_position == 40
        assert execute(runtime, MaintenanceKind.FLUSH).state is MachineState.READY
