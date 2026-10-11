"""Read-only flow evidence over the existing owned executor; fake devices only."""
from threading import Event

import pytest

from app.demo.phases import RunPhase
from app.demo.operation_executor import ProtectedOperationError
from app.hardware.arduino_serial import ArduinoUnavailableError
from tests.test_api import ApiClient
from tests.test_owned_application_api import (
    assembly as assembly, adapters as adapters, start, wait_idle, replacement, PREFIX,
)
from tests.test_owned_offline_runtime import bundle as bundle
from tests.test_owned_transfer_slice import case as case
from tests.test_owned_timed_execution import TIMED_SETTINGS
from tests.test_simulated_lifecycle import PHASES
from tests.test_recipes import save, execute, definition


@pytest.mark.parametrize("phase,expected", [
    (PHASES[0], {("ASPIRATE", "S_TO_P1"), ("DISPENSE", "P1_TO_REACTOR")}),
    (PHASES[1], {("ASPIRATE", "B1_TO_P1"), ("DISPENSE", "P1_TO_REACTOR")}),
    (PHASES[2], {("ASPIRATE", "B2_TO_P1"), ("DISPENSE", "P1_TO_REACTOR")}),
    (PHASES[3], {("ASPIRATE", "REACTOR_TO_P2"), ("DISPENSE", "P2_TO_SF_TOP")}),
    (PHASES[4], {("ASPIRATE", "SF_BOTTOM_TO_P2"), ("DISPENSE", "P2_TO_COLUMN")}),
    (PHASES[5], {("COLLECT", "COLUMN_TO_FRACTIONS")}),
    (RunPhase.SF_MIXING, set()), (RunPhase.SF_SETTLING, set()),
])
def test_scoped_flow_matches_atomic_commands_not_whole_phase(case, phase, expected):
    c = case(phase, settings=TIMED_SETTINGS, mixer_running=False)
    observed = set()

    def check(command):
        flow = c.runner.flow.snapshot()
        if command["command"] == "PUMP_MOVE_ABSOLUTE_STEPS":
            assert flow is not None
            assert flow.operation_command_id == command["operation_command_id"]
            assert flow.phase_execution_id == command["phase_execution_id"] == "test-phase-1"
            assert flow.run_id == "run-1" and flow.operation_number > 0
            observed.add((flow.kind, flow.route))
            # Dispatch uses the existing durable intent; GET adds no command.
            row = c.rows("arduino_command_journal")[-1]
            assert row["state"] == "INTENT_PERSISTED"
        else:
            assert flow is None  # Includes switching, carousel and required CLOSE/STOP.

    def wait(_):
        flow = c.runner.flow.snapshot()
        if phase is RunPhase.COLUMN_FRACTION_COLLECTION:
            assert flow.kind == "COLLECT" and flow.operation_command_id is None
            assert c.runner.device.calls[-1]["arguments"] == {"position_degrees": 94}
            observed.add((flow.kind, flow.route))
        else:
            assert flow is None

    c.runner.device.before_send = check

    def sf(_):
        assert c.runner.flow.snapshot() is None

    c.runner.device.before_sf_send = sf
    c.runner.device.during_wait = wait
    c.execute()
    assert observed == expected
    assert c.runner.flow.snapshot() is None


@pytest.mark.parametrize("recipe", [False, True])
@pytest.mark.parametrize("failure", [False, True])
def test_http_flow_reads_during_command_clear_on_exit_and_never_replay(assembly, bundle, recipe, failure):
    app, _, devices, _ = assembly
    entered, release = Event(), Event()
    with ApiClient(app, lifespan="on") as client:
        assert client.get(PREFIX + "/execution").json()["flow_activity"] is None

        def block(command):
            if command["command"] == "PUMP_MOVE_ABSOLUTE_STEPS" and not entered.is_set():
                entered.set()
                assert release.wait(10)
                if failure:
                    raise ArduinoUnavailableError("fake ambiguous pump outcome")

        devices[0].before_send = block
        try:
            if recipe:
                saved = save(client, definition([{"kind": "ADD", "source": "B2", "volume_ml": "1"}]))
                assert execute(client, saved).status_code == 202
            else:
                start(client)
            assert entered.wait(5)
            sent = len(devices[0].calls)
            for _ in range(3):
                status = client.get(PREFIX + "/execution").json()
                flow = status["flow_activity"]
                assert status["busy"] and status["executing"]
                assert flow["kind"] == "ASPIRATE"
                assert flow["route"] == ("B2_TO_P1" if recipe else "S_TO_P1")
                assert flow["run_id"] == status["run_id"] == status["operation"]["run_id"]
            assert len(devices[0].calls) == sent
        finally:
            release.set()
        status = wait_idle(client)
        assert status["flow_activity"] is None
        assert bool(status["error"]) is failure
    # Reopening reconciles failure or observes completed state, with zero sends.
    with ApiClient(replacement(bundle, devices), lifespan="on") as client:
        assert client.get(PREFIX + "/execution").json()["flow_activity"] is None
        assert devices[-1].calls == devices[-1].sf_calls == []


@pytest.mark.parametrize("point", ["pump", "wait", "close"])
def test_failure_and_stop_clear_flow_before_protected_cleanup(case, point):
    phase = PHASES[4] if point == "pump" else PHASES[5]
    c = case(phase, settings=TIMED_SETTINGS, mixer_running=False)
    seen = []

    def command(value):
        if point == "close" and value["arguments"] == {"position_degrees": 4} and seen:
            assert c.runner.flow.snapshot() is None
            raise ArduinoUnavailableError("fake close ambiguity")
        if point == "pump" and value["command"] == "PUMP_MOVE_ABSOLUTE_STEPS":
            assert c.runner.flow.snapshot() is not None
            raise ArduinoUnavailableError("fake pump ambiguity")

    def sf(_):
        assert c.runner.flow.snapshot() is None
        seen.append("sf action")

    def wait(_):
        assert c.runner.flow.snapshot().kind == "COLLECT"
        seen.append("collection")
        if point == "wait":
            c.stop()

    c.runner.device.before_send = command
    c.runner.device.before_sf_send = sf
    c.runner.device.during_wait = wait
    if point == "wait":
        result = c.execute()
        assert result.run.status.value == "ABORTED"
    else:
        with pytest.raises((ArduinoUnavailableError, ProtectedOperationError)):
            c.execute()
    assert c.runner.flow.snapshot() is None
    if point == "pump":
        assert seen == ["sf action", "sf action", "sf action"]  # prepare CLOSE, OPEN, required CLOSE


def test_existing_serial_adapter_exposes_command_scope_without_changing_transport(bundle, adapters):
    from app.hardware.owned_application_execution import OwnedApplicationExecution
    from app.hardware.prepared_adapter_device import PreparedAdapterDevice
    from app.main import create_app
    from tests.test_command_planning import context
    from tests.test_owned_maintenance import plan
    from app.demo.maintenance_plan import MaintenanceKind
    from tests.test_owned_phase_session import READINESS
    from tests.test_owned_pausable_demo import Clock

    arduino, sf, port, _ = adapters
    clock = Clock()
    seen = set()

    def factory():
        device = PreparedAdapterDevice(context(), arduino, sf)
        device.sf_mixer_running = False
        return device

    execution = OwnedApplicationExecution(bundle, factory, plan(MaintenanceKind.RECOVERY).calibrations,
        timer_factory=clock.timer, column_readiness=READINESS)

    def command(message):
        flow = execution.status().flow_activity
        entry = execution._runtime._runner._journal.load(message["operation_command_id"])
        assert entry.state.value == "INTENT_PERSISTED"
        if message["command"] == "PUMP_MOVE_ABSOLUTE_STEPS":
            assert flow.operation_command_id == message["operation_command_id"]
            seen.add(flow.route)
        else:
            assert flow is None

    def wait():
        flow = execution.status().flow_activity
        if flow is not None:
            assert flow.kind == "COLLECT"
            seen.add(flow.route)

    clock.hook = wait
    port.before_command = command
    with ApiClient(create_app(application_execution=execution), lifespan="on") as client:
        start(client)
        assert wait_idle(client)["flow_activity"] is None
        assert client.get(PREFIX + "/runs/run-api").json()["status"] == "COMPLETED"
    assert seen == {"S_TO_P1", "B1_TO_P1", "B2_TO_P1", "P1_TO_REACTOR", "REACTOR_TO_P2",
        "P2_TO_SF_TOP", "SF_BOTTOM_TO_P2", "P2_TO_COLUMN", "COLUMN_TO_FRACTIONS"}


def test_maintenance_does_not_infer_flow_from_expanded_or_home_operations(assembly):
    from tests.test_owned_application_api import maintenance, COMMAND
    app, execution, devices, _ = assembly
    with ApiClient(app, lifespan="on") as client:
        assert client.post(PREFIX + "/machine/initialize", json=COMMAND).status_code == 200

        def no_flow(_):
            assert execution.status().flow_activity is None

        devices[0].before_send = no_flow
        devices[0].during_wait = no_flow
        maintenance(client, "FLUSH")
        assert wait_idle(client)["error"] is None
