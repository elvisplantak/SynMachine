"""Real adapter classes with fake transports only; never opens a device."""

from dataclasses import replace
import json
from pathlib import Path
import sqlite3
from threading import Event

import pytest

from app import wet_reactor_sf as wet
from app.demo.hardware_contract import HardwareCommandError
from app.hardware.arduino_serial import (
    ArduinoSerialClient, ArduinoSerialConfiguration, ArduinoUnavailableError,
)
from app.hardware.command_planning import CommandPlanningContext
from app.hardware.owned_offline_runtime import OwnedOfflineRuntime
from app.hardware.owned_startup_inspection import inspect_owned_startup
from app.hardware.prepared_adapter_device import PreparedAdapterDevice
from app.hardware.sf_bottom_valve import REGISTERS, SfBottomValveActuator, SfBottomValveConfiguration
from tests.test_arduino_serial import Clock, NONCE, hello_ok
from tests.test_owned_offline_runtime import bundle as bundle
from tests.test_owned_pausable_demo import Clock as WaitClock
from tests.test_prepared_adapter_execution import CommandPort, FollowingSession


@pytest.fixture
def case(bundle):
    port = CommandPort()
    port.incoming = bytearray(hello_ok(controller_boot_id=58, capabilities=sorted(wet.CAPABILITIES)))
    client = ArduinoSerialClient(ArduinoSerialConfiguration(port="/dev/fake", command_timeout_seconds=.1),
        port_factory=lambda _: port, nonce_factory=lambda: NONCE,
        monotonic=Clock(), sleep=lambda _: None)
    client.connect()
    position = [2559]
    sessions = []

    class Session(FollowingSession):
        def read(self, device_id, register):
            if register == REGISTERS["present_position"]:
                return position[0]
            return super().read(device_id, register)

        def write(self, device_id, register, value):
            super().write(device_id, register, value)
            if register == REGISTERS["goal_position"]:
                position[0] = value

    def factory(_):
        session = Session()
        session.values[REGISTERS["torque_enable"]] = 0
        sessions.append(session)
        return session

    sf = SfBottomValveActuator(SfBottomValveConfiguration(port="/dev/fake-sf"),
                              session_factory=factory, sleep=lambda _: None)
    device = PreparedAdapterDevice(CommandPlanningContext(phase_execution_id="test-unreferenced",
                                  controller_boot_id=58), client, sf)
    events = []
    clock = WaitClock()
    stopping = Event()

    def run():
        with OwnedOfflineRuntime(bundle, device, timer=clock.timer()) as runtime:
            wet.run(runtime, client, sf, events.append, stopping.is_set)

    yield type("Case", (), dict(bundle=bundle, port=port, client=client, sf=sf, device=device,
                                events=events, clock=clock, stopping=stopping, sessions=sessions,
                                position=position, run=staticmethod(run)))()
    client.close()


def wire(case):
    return [json.loads(value) for value in case.port.writes
            if json.loads(value)["type"] == "COMMAND"]


def starts(case):
    return [event for event in case.events if event["event"] == "ACTION_START"]


def test_complete_fixed_plan_volumes_routes_and_journals(case):
    # Check durable shared owner and intent from inside the transport boundary.
    def before(message):
        with sqlite3.connect(case.bundle.ownership_path) as db:
            assert db.execute("SELECT sequence_id FROM hardware_owner").fetchone()[0]
        with sqlite3.connect(case.bundle.execution_path) as db:
            assert db.execute("SELECT state FROM arduino_command_journal "
                              "WHERE operation_command_id=?", (message["operation_command_id"],)
                              ).fetchone() == ("INTENT_PERSISTED",)
    case.port.before_command = before
    case.run()
    messages = wire(case)
    assert not any(m["command"].startswith(("COLUMN_", "CAROUSEL_")) for m in messages)
    assert [(m["command"], m["arguments"]) for m in messages if m["command"] == "PUMP_HOME"] == [
        ("PUMP_HOME", {"pump": "P1"}), ("PUMP_HOME", {"pump": "P2"})]
    assert [m["arguments"]["pump"] for m in messages
            if m["command"] == "PUMP_ASPIRATE_FULL_STROKE"] == ["P1", "P2", "P2"]
    assert [m["arguments"]["target_steps"] for m in messages
            if m["command"] == "PUMP_MOVE_ABSOLUTE_STEPS"].count(15375) == 4
    assert not any(m["arguments"].get("target_steps") == 0 for m in messages)
    report = inspect_owned_startup(case.bundle)
    assert report.owner_id is None and report.ownership_generation == 1
    assert not report.runs and report.machine is None
    assert not report.incomplete_wait_operations
    assert all(not j.non_successful for j in report.journals)
    assert case.clock.now == 20_000_000_000
    final = case.events[-1]
    assert final["event"] == "SEQUENCE_COMMANDS_COMPLETED"
    assert final["pumps"] == {"P1": 20500, "P2": 20500}
    assert final["sf_bottom"] == "CLOSED" and final["mixer"] == "STOPPED"
    for route in ("P1_TO_WASTE", "P2_TO_WASTE"):
        assert all(final["valves"][v] == target for v, target in wet.ROUTES[route])
    assert case.position[0] == 2559
    # Opening SF and its full aspiration are immediately followed by required Close.
    steps = starts(case)
    opened = next(i for i, a in enumerate(steps) if a["command"] == wet.SF_ACTION
                  and a["arguments"] == {"state": "OPEN"})
    assert steps[opened + 1]["command"] == "PUMP_ASPIRATE_FULL_STROKE"
    assert steps[opened + 2]["command"] == wet.SF_ACTION
    assert steps[opened + 2]["arguments"] == {"state": "CLOSED"}
    assert steps[opened + 2]["required_followup"]
    # First Valve selection isolates Column via V5 -> Waste before other valve HOME.
    valve_messages = [m for m in messages if m["command"].startswith("VALVE_")]
    assert [(m["command"], m["arguments"]) for m in valve_messages[:2]] == [
        ("VALVE_HOME", {"valve": "V5"}),
        ("VALVE_SET_POSITION", {"valve": "V5", "position_degrees": 180})]


@pytest.mark.parametrize("fault_number", range(1, 1 + sum(
    a.command not in (wet.SF_ACTION, wet.WAIT_ACTION)
    for b in wet.plan() for a in b.primary + b.required_followup)))
def test_every_arduino_transport_failure_retains_owner_and_never_continues(case, fault_number):
    seen = 0

    def fault(message):
        nonlocal seen
        seen += 1
        if seen == fault_number:
            raise ArduinoUnavailableError("injected uncertain wire result")

    case.port.before_command = fault
    with pytest.raises(Exception):
        case.run()
    report = inspect_owned_startup(case.bundle)
    assert report.owner_state == "BLOCKED"
    assert report.owner_id
    assert case.events[-1]["event"] != "SEQUENCE_COMMANDS_COMPLETED"
    messages = wire(case)
    # A failed Start may be followed only by its required Stop.
    assert len(messages) in (fault_number, fault_number + 1)
    if len(messages) > fault_number:
        assert messages[-1]["command"] == "SF_MIXER_SET_STATE"
        assert messages[-1]["arguments"] == {"running": False}
    # Failure while aspirating SF must still attempt independent protected Close.
    if any(e["command"] == wet.SF_ACTION and e["arguments"] == {"state": "OPEN"}
           for e in starts(case)):
        assert case.position[0] == 2559


def test_sf_close_attempt_survives_arduino_disconnect(case):
    full_count = 0
    def fault(message):
        nonlocal full_count
        if message["command"] == "PUMP_ASPIRATE_FULL_STROKE":
            full_count += 1
            if full_count == 3:
                case.client.close()
                raise ArduinoUnavailableError("disconnected during SF aspiration")
    case.port.before_command = fault
    with pytest.raises(ArduinoUnavailableError):
        case.run()
    assert case.position[0] == 2559
    assert starts(case)[-1]["arguments"] == {"state": "CLOSED"}
    assert starts(case)[-1]["required_followup"]
    assert inspect_owned_startup(case.bundle).owner_state == "BLOCKED"


@pytest.mark.parametrize("failure", ["wait", "stop", "host-interrupt"])
def test_mixing_failure_attempts_required_stop_and_no_sf_open(case, failure):
    if failure == "stop":
        case.clock.hook = case.stopping.set
    elif failure == "wait":
        case.clock.hook = lambda: (_ for _ in ()).throw(RuntimeError("timer failure"))
    else:
        case.clock.hook = lambda: (_ for _ in ()).throw(KeyboardInterrupt())
    with pytest.raises(Exception):
        case.run()
    assert wire(case)[-1]["command"] == "SF_MIXER_SET_STATE"
    assert wire(case)[-1]["arguments"] == {"running": False}
    assert not any(e["arguments"] == {"state": "OPEN"} for e in starts(case))
    assert inspect_owned_startup(case.bundle).owner_state == "BLOCKED"


@pytest.mark.parametrize("state", ["open-failure", "close-failure"])
def test_sf_transport_failure_retains_unknown_and_blocks_dispense(case, state, monkeypatch):
    original = case.sf.set_state
    calls = []
    def fault(target):
        calls.append(target.value)
        if target.value == "OPEN" and state == "open-failure":
            raise HardwareCommandError("injected uncertain SF Open")
        if target.value == "CLOSED" and len(calls) > 1 and state == "close-failure":
            raise HardwareCommandError("injected uncertain SF Close")
        return original(target)
    monkeypatch.setattr(case.sf, "set_state", fault)
    with pytest.raises(HardwareCommandError):
        case.run()
    assert calls[-2:] == ["OPEN", "CLOSED"]
    assert inspect_owned_startup(case.bundle).owner_state == "BLOCKED"
    assert not any(e["label"].startswith("Dispense P2 to Waste") for e in case.events
                   if e["event"] == "BLOCK_START")
    assert any(j.non_successful for j in inspect_owned_startup(case.bundle).journals)


def test_success_cannot_be_replayed_in_existing_bundle(case):
    case.run()
    count = len(wire(case))
    with pytest.raises(RuntimeError, match="pristine"):
        case.run()
    assert len(wire(case)) == count


def test_bad_sf_preflight_and_missing_capability_send_nothing(case, monkeypatch):
    monkeypatch.setattr(case.client, "_capabilities", frozenset({"PUMP_HOME"}))
    with pytest.raises(Exception, match="capabilities"):
        case.run()
    assert not wire(case)
    assert inspect_owned_startup(case.bundle).owner_state == "BLOCKED"


def test_open_sf_preflight_blocks_without_motion(case):
    case.position[0] = 3697
    with pytest.raises(RuntimeError, match="CLOSED"):
        case.run()
    assert not wire(case) and not starts(case)
    assert inspect_owned_startup(case.bundle).owner_state == "BLOCKED"


def test_initial_operator_stop_sends_nothing(case):
    case.stopping.set()
    with pytest.raises(wet.WetTestStopped):
        case.run()
    assert not wire(case)
    assert inspect_owned_startup(case.bundle).owner_state == "BLOCKED"


def test_session_change_before_primary_blocks_progress(case):
    def emit(event):
        case.events.append(event)
        if event.get("label", "").startswith("B1 to Reactor") and event["event"] == "BLOCK_START":
            case.client._connection_epoch += 1
    with OwnedOfflineRuntime(case.bundle, case.device, timer=case.clock.timer()) as runtime:
        with pytest.raises(RuntimeError, match="session changed"):
            wet.run(runtime, case.client, case.sf, emit, case.stopping.is_set)
    assert not any(m["command"] == "PUMP_ASPIRATE_FULL_STROKE" for m in wire(case))
    assert inspect_owned_startup(case.bundle).owner_state == "BLOCKED"


def test_plan_only_and_missing_approval_do_not_open_devices(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(wet, "load_bundle", lambda *_: pytest.fail("must not load state"))
    monkeypatch.setattr(wet, "load_profile", lambda *_: pytest.fail("must not load profile"))
    wet.main([])
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "PLAN_ONLY_NO_DEVICE_OPENED"
    assert payload["sha256"] == wet.plan_digest()
    with pytest.raises(SystemExit):
        wet.main(["--execute"])


def test_nonpristine_bundle_blocks_before_connection_factory(case, monkeypatch):
    case.run()
    opened = []
    monkeypatch.setattr(wet, "ArduinoSerialClient", lambda *_a, **_kw: opened.append(True))
    configuration = wet.load_profile(wet.PROFILE)
    with pytest.raises(RuntimeError, match="pristine"):
        with OwnedOfflineRuntime(case.bundle, timer=case.clock.timer(),
             device_factory=lambda: wet.connected_device(configuration, case.bundle, lambda _: None)):
            pass
    assert not opened


def test_existing_runtime_lock_excludes_second_device_factory(case):
    opened = []
    with OwnedOfflineRuntime(case.bundle, case.device, timer=case.clock.timer()):
        with pytest.raises(Exception, match="active runtime"):
            with OwnedOfflineRuntime(case.bundle, timer=case.clock.timer(),
                 device_factory=lambda: opened.append(True)):
                pass
    assert not opened


def test_known_profile_digest_and_fixed_source_are_unchanged():
    assert wet._digest(wet.load_profile(wet.PROFILE)) == wet.PROFILE_DIGEST
    configuration = wet.load_profile(wet.PROFILE)
    actual = {r.route_id.value: tuple((t.valve, t.position_degrees) for t in r.targets)
              for r in configuration.route_sequences}
    assert all(actual[name] == targets for name, targets in wet.ROUTES.items())
    assert Path(wet.PROFILE).is_file()


def test_pristine_check_rejects_every_nonempty_history(case):
    report = inspect_owned_startup(case.bundle)
    wet.require_pristine(report)
    for changed in [replace(report, ownership_generation=1), replace(report, owner_id="blocked"),
                    replace(report, incomplete_wait_operations=(("phase", 1),))]:
        with pytest.raises(RuntimeError, match="pristine"):
            wet.require_pristine(changed)


def test_stop_after_sf_open_closes_without_aspiration_or_dispense(case):
    def emit(event):
        case.events.append(event)
        if event["event"] == "ACTION_COMPLETED":
            last = starts(case)[-1]
            if last["command"] == wet.SF_ACTION and last["arguments"] == {"state": "OPEN"}:
                case.stopping.set()
    with OwnedOfflineRuntime(case.bundle, case.device, timer=case.clock.timer()) as runtime:
        with pytest.raises(wet.WetTestStopped):
            wet.run(runtime, case.client, case.sf, emit, case.stopping.is_set)
    assert case.position[0] == 2559
    assert starts(case)[-1]["required_followup"]
    assert len([m for m in wire(case) if m["command"] == "PUMP_ASPIRATE_FULL_STROKE"]) == 2
    assert inspect_owned_startup(case.bundle).owner_state == "BLOCKED"


def test_replacement_state_directory_rejected_before_profile_or_device(monkeypatch, tmp_path):
    monkeypatch.setattr(wet, "load_profile", lambda *_: pytest.fail("must not load profile"))
    with pytest.raises(RuntimeError, match="existing bound live state"):
        wet.main(["--execute", "--procedure-approved", "--conditions-confirmed",
                  "--state-dir", str(tmp_path), "--evidence-dir", str(tmp_path / "events")])
