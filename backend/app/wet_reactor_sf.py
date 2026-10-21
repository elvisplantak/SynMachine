"""One explicitly armed commissioning test; default only prints its fixed plan.

Not Recipes activation or a general route planner. Reuses the existing owner,
command/SF/wait journals and required follow-ups, with no Column references,
state provisioning, resume, reconnect, retry or automatic cleanup motion.
"""

import argparse
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import signal
from threading import Event
from uuid import uuid4

from app.demo.hardware_contract import BottomValveState
from app.demo.operation_executor import CollectionTimerOutcome
from app.hardware.arduino_serial import ArduinoSerialClient, ArduinoSerialConfiguration
from app.hardware.command_planning import CollectionWait, CommandPlanningContext
from app.hardware.execution_timer import MonotonicExecutionTimer
from app.hardware.fresh_hardware_observations import observe_current_hardware
from app.hardware.owned_offline_runtime import OwnedOfflineRuntime
from app.hardware.prepared_adapter_device import PreparedAdapterDevice
from app.hardware.sf_bottom_valve import SfBottomValveActuator, SfBottomValveConfiguration
from app.live_execution import _digest, _exclusive_port, load_bundle, load_profile

PROFILE = Path(__file__).resolve().parents[1] / "docs/LIVE_RECIPES_PROFILE.json"
STATE_DIRECTORY = Path.home() / ".local/state/labforge/recipes-live-v1"
PROFILE_DIGEST = "8035b3f152d782faba75c5760e9c9b0570cb6a2d9dd331660cb2806accb98d51"
SF_ACTION = "SF_BOTTOM_SET_STATE"
WAIT_ACTION = "WAIT_SECONDS"
CAPABILITIES = frozenset({"VALVE_HOME", "VALVE_SET_POSITION", "PUMP_HOME",
                          "PUMP_MOVE_ABSOLUTE_STEPS", "PUMP_ASPIRATE_FULL_STROKE",
                          "SF_MIXER_SET_STATE"})
ROUTES = {
    "P1_TO_WASTE": (("V2", 180), ("V1", 180)),
    "P2_TO_WASTE": (("V5", 180), ("V8", 90), ("V7", 90), ("V3", 180)),
    "S_TO_P1": (("V6", 180), ("V1", 90)),
    "B1_TO_P1": (("V4", 180), ("V6", 90), ("V1", 90)),
    "P1_TO_REACTOR": (("V2", 90), ("V1", 180)),
    "REACTOR_TO_P2": (("V3", 90),),
    "P2_TO_SF_TOP": (("V7", 180), ("V3", 180)),
    "SF_BOTTOM_TO_P2": (("V8", 180), ("V7", 90), ("V3", 180)),
}


class WetTestStopped(RuntimeError):
    pass


@dataclass(frozen=True)
class Action:
    command: str
    arguments: tuple[tuple[str, str | int | bool], ...]


@dataclass(frozen=True)
class Block:
    label: str
    primary: tuple[Action, ...]
    required_followup: tuple[Action, ...] = ()


def action(command, **arguments):
    return Action(command, tuple(arguments.items()))


def plan():
    """Exact operator-approved nominal volumes; only fresh bootstrap receipts.

    Return-to-Reactor priming uses the same confirmed bidirectional V3=90
    connection, not a newly invented valve route. Every route is set with pumps
    stationary; unchanged valve targets are omitted using prior plan receipts.
    V5 is first homed/selected to Waste, isolating Column before P2-side setup.
    """
    positions = {}
    blocks = []

    def route(name):
        steps = []
        for valve, target in ROUTES[name]:
            if positions.get(valve) != target:
                steps.append(action("VALVE_SET_POSITION", valve=valve, position_degrees=target))
                positions[valve] = target
        return tuple(steps)

    def move(pump, target):
        return action("PUMP_MOVE_ABSOLUTE_STEPS", pump=pump, target_steps=target)

    closed = action(SF_ACTION, state="CLOSED")
    stop = action("SF_MIXER_SET_STATE", running=False)
    bootstrap = [stop, closed, action("VALVE_HOME", valve="V5"),
                 action("VALVE_SET_POSITION", valve="V5", position_degrees=180)]
    positions["V5"] = 180
    for valve in ("V1", "V2", "V4", "V6", "V3", "V7", "V8"):
        bootstrap.append(action("VALVE_HOME", valve=valve))
        positions[valve] = 0
    for pump in ("P1", "P2"):
        bootstrap.extend(route(pump + "_TO_WASTE"))
        bootstrap.extend((action("PUMP_HOME", pump=pump), move(pump, 20500)))
    blocks.append(Block("Initialize on open Waste air-gap routes", tuple(bootstrap)))
    for cycle in (1, 2):
        blocks.append(Block(f"Prime P1: S to Waste 5 mL, cycle {cycle}",
                            route("S_TO_P1") + (move("P1", 15375),)
                            + route("P1_TO_WASTE") + (move("P1", 20500),)))
    blocks.append(Block("B1 to Reactor, one nominal 20 mL stroke",
                        route("B1_TO_P1") + (action("PUMP_ASPIRATE_FULL_STROKE", pump="P1"),)
                        + route("P1_TO_REACTOR") + (move("P1", 20500),)))
    for cycle in (1, 2):
        blocks.append(Block(f"Prime P2: Reactor to P2 to Reactor 5 mL, cycle {cycle}",
                            route("REACTOR_TO_P2") + (move("P2", 15375), move("P2", 20500))))
    blocks.append(Block("Reactor to SF, nominal 20 mL",
                        route("REACTOR_TO_P2") + (action("PUMP_ASPIRATE_FULL_STROKE", pump="P2"),)
                        + route("P2_TO_SF_TOP") + (move("P2", 20500),)))
    blocks.append(Block("Mix SF for 20 s at installed 600 pulses/s trial",
                        (action("SF_MIXER_SET_STATE", running=True),
                         action(WAIT_ACTION, seconds=20)), (stop,)))
    blocks.append(Block("Select SF aspiration route with bottom CLOSED", route("SF_BOTTOM_TO_P2")))
    blocks.append(Block("Aspirate SF, nominal 20 mL; mandatory bottom CLOSE",
                        (action(SF_ACTION, state="OPEN"),
                         action("PUMP_ASPIRATE_FULL_STROKE", pump="P2")), (closed,)))
    blocks.append(Block("Dispense P2 to Waste and leave both pumps on Waste",
                        route("P2_TO_WASTE") + (move("P2", 20500),) + route("P1_TO_WASTE")))
    assert set(positions) == {f"V{i}" for i in range(1, 9)}
    assert all(value in (90, 180) for value in positions.values())
    return tuple(blocks)


def plan_payload():
    return [asdict(block) for block in plan()]


def plan_digest():
    return hashlib.sha256(json.dumps(plan_payload(), sort_keys=True).encode()).hexdigest()


def require_pristine(report):
    # This first supervised commissioning test is deliberately single-use.
    # Existing successful or unresolved execution is never erased to rerun it.
    if (report.owner_id is not None or report.ownership_generation != 0
        or report.machine is not None or report.runs or report.prepared_phase_ids
        or report.incomplete_wait_operations or any(j.total for j in report.journals)):
        raise RuntimeError("wet test requires the existing pristine bundle; no reset or replay")


def run(runtime, client, sf, emit, stop_requested):
    """Run under an already exclusively locked runtime; no port lifecycle here."""
    require_pristine(runtime.initial_inspection)
    owner, runner = runtime._owner, runtime._runner
    phase = "wet-reactor-sf-" + str(uuid4())
    lease = owner.claim(phase, expected_generation=0)
    identity = client.controller_boot_id, client.backend_session_nonce, client.connection_epoch
    wait_numbers = []
    sf_closed = False
    mixer_stopped = False
    pumps = {}
    valves = {}

    def check_session():
        if not client.connected or identity != (client.controller_boot_id,
                                                client.backend_session_nonce,
                                                client.connection_epoch):
            raise RuntimeError("controller session changed; no continuation")

    def execute(commands, step, *, followup=False):
        nonlocal sf_closed, mixer_stopped
        try:
            # SF Close has its own retained adapter scope and must still run
            # after an Arduino disconnect; never reconnect Arduino for cleanup.
            if not (followup and step.command == SF_ACTION):
                check_session()
            if not followup and stop_requested():
                raise WetTestStopped("operator Stop; no next primary command")
            args = dict(step.arguments)
            command_id = str(uuid4())
            emit({"event": "ACTION_START", "phase_id": phase, "command_id": command_id,
                  "command": step.command, "arguments": args, "required_followup": followup})
            if step.command == SF_ACTION:
                if args["state"] == "OPEN" and not mixer_stopped:
                    raise RuntimeError("SF aspiration requires commanded mixer Stop")
                # Until a CLOSED receipt, even a definitely attempted Close is not truth.
                sf_closed = False
                commands.execute_sf(phase_execution_id=phase, operation_command_id=command_id,
                                    state=BottomValveState(args["state"]))
                sf_closed = args["state"] == "CLOSED"
            elif step.command == WAIT_ACTION:
                number = len(wait_numbers) + 1
                wait_numbers.append(number)
                outcome = runner._wait(phase, number, CollectionWait(Decimal(args["seconds"])),
                                       stop_requested)
                if outcome is not CollectionTimerOutcome.COMPLETED:
                    raise WetTestStopped("operator Stop during SF mixing")
            else:
                if step.command in {"VALVE_HOME", "VALVE_SET_POSITION"} and not sf_closed:
                    raise RuntimeError("route switching requires commanded SF CLOSED")
                entry = commands.execute(phase_execution_id=phase, operation_command_id=command_id,
                                         command=step.command, arguments=args)
                if step.command == "SF_MIXER_SET_STATE":
                    mixer_stopped = args["running"] is False
                elif step.command.startswith("PUMP_"):
                    pumps[args["pump"]] = (args["target_steps"]
                        if step.command == "PUMP_MOVE_ABSOLUTE_STEPS" else 0)
                elif step.command.startswith("VALVE_"):
                    valves[args["valve"]] = args.get("position_degrees", 0)
                emit({"event": "ARDUINO_RESULT", "command_id": command_id,
                      "state": entry.state.value, "result": entry.result})
            emit({"event": "ACTION_COMPLETED", "command_id": command_id})
        except (KeyboardInterrupt, SystemExit) as error:
            # Existing required-followup executor catches Exception; preserve its
            # Close/Stop semantics even for a host-level interruption.
            raise WetTestStopped("host interrupted; mandatory follow-up remains required") from error

    try:
        observations = owner.invoke(lease, lambda: observe_current_hardware(
            client, sf, required_commands=CAPABILITIES))
        if (observations.sf_valve.observed_state is not BottomValveState.CLOSED
            or observations.sf_valve.torque_enabled):
            raise RuntimeError("fresh SF observation must be CLOSED and torque disabled")
        emit({"event": "READ_ONLY_PREFLIGHT", "controller_boot_id": identity[0],
              "sf_present_position": observations.sf_valve.present_position,
              "plan_sha256": plan_digest()})
        for block in plan():
            emit({"event": "BLOCK_START", "label": block.label})

            def primary(commands):
                for step in block.primary:
                    execute(commands, step)

            def followup(commands):
                for step in block.required_followup:
                    execute(commands, step, followup=True)

            runner.hardware.run_operation(lease, primary,
                required_followup=followup if block.required_followup else None)
            emit({"event": "BLOCK_COMPLETED", "label": block.label})
        check_session()
        if stop_requested():
            raise WetTestStopped("operator Stop before final completion")
        if (not sf_closed or not mixer_stopped or pumps != {"P1": 20500, "P2": 20500}
            or len(valves) != 8 or any(value not in (90, 180) for value in valves.values())
            or any(valves[v] != p for route in ("P1_TO_WASTE", "P2_TO_WASTE")
                   for v, p in ROUTES[route])):
            raise RuntimeError("unexpected final command state; owner retained")
        for number in wait_numbers:
            runner._db.execute("UPDATE execution_waits SET operation_completed=1 "
                               "WHERE phase_id=? AND operation_number=?", (phase, number))
        emit({"event": "SEQUENCE_COMMANDS_COMPLETED", "phase_id": phase,
              "pumps": pumps, "valves": valves, "sf_bottom": "CLOSED", "mixer": "STOPPED",
              "physical_observation": "requires separate operator confirmation"})
        owner.complete(lease)
    except BaseException as error:
        try:
            owner.block(lease)
        except BaseException as retention_error:
            error.add_note(f"Owner retention check: {retention_error}")
        raise


@contextmanager
def connected_device(configuration, bundle, emit):
    # Called by OwnedOfflineRuntime only after its existing bundle locks/inspection.
    from app.hardware.owned_startup_inspection import inspect_owned_startup
    require_pristine(inspect_owned_startup(bundle))
    client = ArduinoSerialClient(ArduinoSerialConfiguration(**configuration.arduino.model_dump()),
                                 port_factory=_exclusive_port)
    device = None
    try:
        hello = client.connect()
        emit({"event": "HELLO", "hello": hello.model_dump(mode="json")})
        sf = SfBottomValveActuator(SfBottomValveConfiguration(**configuration.sf.model_dump()))
        device = PreparedAdapterDevice(CommandPlanningContext(phase_execution_id="wet-unreferenced",
                                        controller_boot_id=client.controller_boot_id), client, sf)
        yield device
    finally:
        if device is not None:
            device.close()
        client.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--procedure-approved", action="store_true")
    parser.add_argument("--conditions-confirmed", action="store_true")
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    args = parser.parse_args(argv)
    if not args.execute:
        print(json.dumps({"mode": "PLAN_ONLY_NO_DEVICE_OPENED", "sha256": plan_digest(),
                          "blocks": plan_payload()}, indent=2))
        return
    if not (args.procedure_approved and args.conditions_confirmed
            and args.state_dir and args.evidence_dir):
        parser.error("fresh wet procedure/power/air-gap/readiness approval and existing state required")
    if args.state_dir.absolute() != STATE_DIRECTORY.absolute():
        raise RuntimeError("only the existing bound live state directory is allowed; no replacement")
    configuration = load_profile(PROFILE)
    if _digest(configuration) != PROFILE_DIGEST:
        raise RuntimeError("live profile changed; no device opened")
    bundle = load_bundle(args.state_dir, configuration)
    if input("Motor power ready, Waste air gap verified, empty Reactor/SF and safe mixers; "
             "type RUN_WET_TEST for this one supervised block: ").strip() != "RUN_WET_TEST":
        print("CANCELLED_NO_DEVICE_OPENED")
        return
    # Evidence must be a new directory, never a replacement of failed history.
    args.evidence_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
    (args.evidence_dir / "plan.json").write_text(json.dumps(
        {"sha256": plan_digest(), "blocks": plan_payload()}, indent=2) + "\n")
    stopping = Event()
    previous = {sig: signal.signal(sig, lambda *_: stopping.set())
                for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        with (args.evidence_dir / "events.jsonl").open("x") as log:
            def emit(event):
                line = json.dumps({"at_utc": datetime.now(UTC).isoformat(), **event})
                log.write(line + "\n")
                log.flush()
                os.fsync(log.fileno())
                print(line, flush=True)

            emit({"event": "OPERATOR_PREREQUISITES", "motor_power_ready": True,
                  "s_water_and_intake_submerged": True, "b1_colored_water": True,
                  "reactor_and_sf_empty": True, "waste_open_with_air_gap": True,
                  "sf_mixer_free_and_direction_safe": True, "reactor_mixer_stopped": True,
                  "p1_prime_cycles": 2, "p2_return_prime_cycles": 2, "prime_ml": 5,
                  "source": "fresh operator declarations; not sensors", "plan_sha256": plan_digest()})
            with OwnedOfflineRuntime(bundle, timer=MonotonicExecutionTimer(),
                    device_factory=lambda: connected_device(configuration, bundle, emit)) as runtime:
                device = runtime._runner.device
                try:
                    run(runtime, device._arduino, device._sf_valve, emit, stopping.is_set)
                except BaseException as error:
                    emit({"event": "STOPPED_NO_RETRY", "error": str(error),
                          "error_type": type(error).__name__})
                    raise
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    main()
