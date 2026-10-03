"""Existing Serial/DYNAMIXEL adapters, injected fake transports, owned runtime."""

from datetime import UTC, datetime
import json

import pytest

from app.demo.hardware_contract import HardwareCommandError, BottomValveState
from app.demo.maintenance_plan import MaintenanceKind
from app.demo.machine_models import MachineState
from app.hardware.arduino_serial import (
    ArduinoSerialClient,
    ArduinoSerialConfiguration,
    ArduinoUnavailableError,
)
from app.hardware.owned_offline_runtime import OwnedOfflineRuntime
from app.hardware.prepared_adapter_device import PreparedAdapterDevice
from app.hardware.sf_bottom_valve import SfBottomValveActuator, REGISTERS
from app.hardware.simulated_p1_runner import SimulationBlocked
from tests.test_arduino_serial import FakePort, NONCE, Clock, frame, hello_ok
from tests.test_command_planning import context
from tests.test_owned_offline_runtime import bundle as bundle
from tests.test_owned_pausable_demo import Clock as WaitClock
from tests.test_owned_maintenance import interrupt, execute, new_run
from tests.test_sf_bottom_valve import FakeSession, configuration


CAPABILITIES = [
    "PUMP_HOME",
    "PUMP_MOVE_ABSOLUTE_STEPS",
    "VALVE_HOME",
    "VALVE_SET_POSITION",
    "COLUMN_BOTTOM_VALVE_HOME",
    "COLUMN_BOTTOM_VALVE_SET_POSITION",
    "CAROUSEL_SET_REFERENCE",
    "CAROUSEL_MOVE_TO_POSITION",
    "SF_MIXER_SET_STATE",
]


class CommandPort(FakePort):
    def __init__(self):
        super().__init__(hello_ok(controller_boot_id=58, capabilities=CAPABILITIES))
        self.before_command = lambda _: None

    def write(self, value):
        count = super().write(value)
        message = json.loads(value)
        if message["type"] == "COMMAND":
            self.before_command(message)
            identity = {
                key: message[key]
                for key in (
                    "backend_session_nonce",
                    "controller_boot_id",
                    "phase_execution_id",
                    "operation_command_id",
                )
            }
            for kind in ("ACCEPTED", "STARTED", "COMPLETED"):
                self.incoming.extend(
                    frame(type=kind, **identity, **({"result": {}} if kind == "COMPLETED" else {}))
                )
        elif message["type"] == "QUERY_STATUS":
            self.incoming.extend(
                frame(
                    type="STATUS",
                    backend_session_nonce=message["backend_session_nonce"],
                    controller_boot_id=message["controller_boot_id"],
                    request_id=message["request_id"],
                    controller_state="IDLE",
                    software_state_trust="TRUSTED",
                    active_operation_command_id=None,
                )
            )
        return count


class FollowingSession(FakeSession):
    def write(self, device_id, register, value):
        super().write(device_id, register, value)
        self.values[register] = value

    def read(self, device_id, register):
        if register == REGISTERS["present_position"]:
            return self.values.get(REGISTERS["goal_position"], 2559)
        return super().read(device_id, register)


@pytest.fixture
def adapters():
    port = CommandPort()
    client = ArduinoSerialClient(
        ArduinoSerialConfiguration(port="/dev/test", command_timeout_seconds=0.1),
        port_factory=lambda _: port,
        nonce_factory=lambda: NONCE,
        sleep=lambda _: None,
        monotonic=Clock(),
    )
    client.connect()
    sessions = []

    def factory(_):
        session = FollowingSession()
        session.values[REGISTERS["torque_enable"]] = 0
        sessions.append(session)
        return session

    sf = SfBottomValveActuator(configuration(), session_factory=factory, sleep=lambda _: None)
    yield client, sf, port, sessions
    client.close()


def test_existing_adapters_use_same_recovery_flush_and_new_run_path(bundle, adapters):
    interrupt(bundle)
    client, sf, port, sessions = adapters
    device = PreparedAdapterDevice(context(), client, sf)
    device.sf_mixer_running = False
    with OwnedOfflineRuntime(bundle, device, timer=WaitClock().timer()) as runtime:
        runtime.reconcile_interruption(datetime.now(UTC))
        assert execute(runtime, MaintenanceKind.RECOVERY).state is MachineState.FLUSH_REQUIRED
        assert execute(runtime, MaintenanceKind.FLUSH).state is MachineState.READY
        new_run(runtime)
        assert runtime.execute_next().run.run_id == "run-2"
        sends = [
            json.loads(value) for value in port.writes if json.loads(value)["type"] == "COMMAND"
        ]
        assert len(sends) == len(device.calls)
        assert len({value["operation_command_id"] for value in sends}) == len(sends)
        rows = runtime._runner._db.execute(
            "SELECT state FROM arduino_command_journal WHERE phase_execution_id IN (SELECT phase_execution_id FROM prepared_command_plans)"
        ).fetchall()
        assert rows and all(row == ("COMPLETED",) for row in rows)
        assert sessions and all(session.closed for session in sessions)
        assert all(
            session.writes[-1] == (2, REGISTERS["torque_enable"], 0)
            for session in sessions
            if session.writes
        )


def test_intent_is_committed_before_first_serial_byte_and_service_is_blocked(bundle, adapters):
    interrupt(bundle)
    client, sf, port, _ = adapters
    device = PreparedAdapterDevice(context(), client, sf)
    device.sf_mixer_running = False
    with OwnedOfflineRuntime(bundle, device, timer=WaitClock().timer()) as runtime:
        runtime.reconcile_interruption(datetime.now(UTC))
        observed = []

        def check(message):
            row = runtime._runner._journal.load(message["operation_command_id"])
            assert row.state.value == "INTENT_PERSISTED"
            assert runtime._store.load_machine_snapshot().active_maintenance is not None
            with pytest.raises(HardwareCommandError):
                runtime._runner.hardware.sf_service.set_state(BottomValveState.CLOSED)
            observed.append(message["operation_command_id"])

        port.before_command = check
        execute(runtime, MaintenanceKind.RECOVERY)
        assert len(observed) == len(device.calls)


def test_adapter_disconnect_keeps_owner_and_never_replays_after_restart(bundle, adapters):
    interrupt(bundle)
    client, sf, _, _ = adapters
    device = PreparedAdapterDevice(context(), client, sf)
    device.sf_mixer_running = False
    with OwnedOfflineRuntime(bundle, device, timer=WaitClock().timer()) as runtime:
        runtime.reconcile_interruption(datetime.now(UTC))
        device.before_send = lambda _: client.close()
        with pytest.raises(ArduinoUnavailableError):
            execute(runtime, MaintenanceKind.RECOVERY)
        assert runtime._owner._validate_owner() is not None
    from tests.test_owned_offline_runtime import open_runtime

    with open_runtime(bundle) as restarted:
        restarted.reconcile_maintenance_interruption(datetime.now(UTC))
        with pytest.raises(SimulationBlocked):
            restarted.execute_next()
        assert restarted._runner.device.calls == []
