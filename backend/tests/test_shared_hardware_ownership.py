from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import sqlite3
import subprocess
import sys
from threading import Event
from uuid import uuid4

import pytest

from app.demo.hardware_contract import BottomValveState, HardwareCommandError
from app.demo.operation_executor import ProtectedOperationError
from app.hardware.arduino_command_journal import (
    ArduinoCommandJournalEntry,
    ArduinoCommandJournalState,
    SQLiteArduinoCommandJournal,
)
from app.hardware.arduino_serial import ArduinoUnavailableError, ArduinoCommandResult
from app.hardware.durable_arduino import DurableArduinoCommandExecutor
from app.hardware.owned_hardware import OwnedHardware
from app.hardware.sequence_ownership import HardwareOwnership, OwnershipBlocked, provision_ownership
from app.main import create_app
from tests.test_api import ApiClient
from tests.test_arduino_service_api import request


class Arduino:
    def __init__(self):
        self.calls = []
        self.hook = lambda values: None
        self.state = ArduinoCommandJournalState.COMPLETED

    def execute(self, **values):
        self.hook(values)
        self.calls.append(values)
        return ArduinoCommandJournalEntry(
            controller_boot_id=1,
            state=self.state,
            result={},
            error_code=None,
            execution_started=True,
            **values,
        )


class Sf:
    def __init__(self):
        self.calls = []
        self.hook = lambda state: None

    def set_state(self, state):
        self.hook(state)
        self.calls.append(state)


@pytest.fixture
def setup(tmp_path):
    path = tmp_path / "ownership.db"
    identity = provision_ownership(path)
    owner = HardwareOwnership(path, identity)
    a, sf = Arduino(), Sf()
    hardware = OwnedHardware(owner, a, sf)
    yield path, identity, owner, hardware, a, sf
    owner.close()


def command(phase="phase"):
    return dict(
        phase_execution_id=phase,
        operation_command_id=str(uuid4()),
        command="VALVE_HOME",
        arguments={"valve": "V7"},
    )


def current(path):
    with sqlite3.connect(path) as db:
        return db.execute("SELECT sequence_id FROM hardware_owner").fetchone()[0]


def test_sequence_holds_owner_across_arduino_sf_and_idle_gap(setup):
    path, _, owner, hw, a, sf = setup
    lease = owner.claim("phase")
    hw.run_operation(lease, lambda io: io.execute(**command()))
    for service in (
        lambda: hw.arduino_service.execute(**command("service")),
        lambda: hw.sf_service.set_state(BottomValveState.OPEN),
    ):
        with pytest.raises(OwnershipBlocked):
            service()
    hw.run_operation(lease, lambda io: io.set_state(BottomValveState.CLOSED))
    assert len(a.calls) == len(sf.calls) == 1
    assert current(path) == "phase"
    owner.complete(lease)
    assert current(path) is None
    hw.sf_service.set_state(BottomValveState.OPEN)


def test_distinct_service_commands_share_phase_but_not_sequence_identity(setup):
    _, _, _, hw, a, _ = setup
    first, second = command(), command()
    hw.arduino_service.execute(**first)
    hw.arduino_service.execute(**second)
    assert len(a.calls) == 2
    with pytest.raises(OwnershipBlocked):
        hw.arduino_service.execute(**first)
    assert len(a.calls) == 2


@pytest.mark.parametrize("active", ["arduino", "sf"])
def test_concurrent_service_channels_cannot_interleave(setup, active):
    _, _, _, hw, a, sf = setup
    entered, release = Event(), Event()

    def hold(_):
        entered.set()
        assert release.wait(5)

    if active == "arduino":
        a.hook = hold

        def action():
            return hw.arduino_service.execute(**command())

        def competing():
            return hw.sf_service.set_state(BottomValveState.CLOSED)
    else:
        sf.hook = hold

        def action():
            return hw.sf_service.set_state(BottomValveState.OPEN)

        def competing():
            return hw.arduino_service.execute(**command())

    with ThreadPoolExecutor() as pool:
        future = pool.submit(action)
        try:
            assert entered.wait(5)
            with pytest.raises(OwnershipBlocked):
                competing()
        finally:
            release.set()
        future.result()


def test_same_lease_concurrent_operation_and_completion_rejected(setup):
    path, _, owner, hw, _, _ = setup
    lease = owner.claim("phase")
    entered, release = Event(), Event()

    def hold(io):
        entered.set()
        assert release.wait(5)

    with ThreadPoolExecutor() as pool:
        future = pool.submit(hw.run_operation, lease, hold)
        try:
            assert entered.wait(5)
            with pytest.raises(OwnershipBlocked):
                owner.complete(lease)
            with pytest.raises(OwnershipBlocked):
                hw.run_operation(lease, lambda io: io.execute(**command()))
            assert current(path) == "phase"
        finally:
            release.set()
        future.result()
    owner.complete(lease)


@pytest.mark.parametrize(
    "error",
    [
        ArduinoUnavailableError("unknown"),
        HardwareCommandError("failed"),
        RuntimeError("unexpected"),
        KeyboardInterrupt(),
    ],
)
def test_failure_retains_owner_and_original_error(setup, error):
    path, identity, owner, hw, a, _ = setup

    def fail(_):
        raise error

    a.hook = fail
    lease = owner.claim("phase")
    with pytest.raises(type(error)) as caught:
        hw.run_operation(lease, lambda io: io.execute(**command()))
    assert caught.value is error
    assert current(path) == "phase"
    with pytest.raises(OwnershipBlocked):
        owner.complete(lease)
    fresh = HardwareOwnership(path, identity)
    try:
        with pytest.raises(OwnershipBlocked):
            fresh.claim("other")
        with pytest.raises(OwnershipBlocked):
            fresh.invoke(lease, lambda: pytest.fail("sent"))
    finally:
        fresh.close()


def test_required_close_keeps_owner_and_preserves_both_errors(setup):
    path, _, owner, hw, a, sf = setup
    primary, followup = ArduinoUnavailableError("lost result"), HardwareCommandError("close failed")

    def fail(_):
        raise primary

    a.hook = fail

    def close_check(state):
        assert current(path) == "phase"
        with pytest.raises(OwnershipBlocked):
            hw.arduino_service.execute(**command("service"))
        if state is BottomValveState.CLOSED:
            raise followup

    sf.hook = close_check
    lease = owner.claim("phase")

    def run(io):
        io.set_state(BottomValveState.OPEN)
        io.execute(**command())

    with pytest.raises(ProtectedOperationError) as caught:
        hw.run_operation(
            lease, run, required_followup=lambda io: io.set_state(BottomValveState.CLOSED)
        )
    assert caught.value.primary_error is primary
    assert caught.value.followup_error is followup
    assert current(path) == "phase"


def test_successful_close_does_not_erase_unknown_or_release_owner(setup):
    path, _, owner, hw, a, sf = setup
    error = ArduinoUnavailableError("unknown")

    def fail(_):
        raise error

    a.hook = fail
    lease = owner.claim("phase")
    with pytest.raises(ArduinoUnavailableError):
        hw.run_operation(
            lease,
            lambda io: io.execute(**command()),
            required_followup=lambda io: io.set_state(BottomValveState.CLOSED),
        )
    assert sf.calls == [BottomValveState.CLOSED]
    assert current(path) == "phase"


def test_swallowed_error_cannot_continue_or_complete(setup):
    _, _, owner, hw, a, sf = setup
    a.state = ArduinoCommandJournalState.OUTCOME_UNKNOWN
    lease = owner.claim("phase")

    def swallow(io):
        try:
            io.execute(**command())
        except OwnershipBlocked:
            pass
        with pytest.raises(OwnershipBlocked):
            io.set_state(BottomValveState.OPEN)

    with pytest.raises(OwnershipBlocked):
        hw.run_operation(lease, swallow)
    assert not sf.calls
    with pytest.raises(OwnershipBlocked):
        owner.complete(lease)


def test_scope_and_copied_lease_cannot_escape(setup):
    _, _, owner, hw, a, _ = setup
    lease = owner.claim("phase")
    saved = []
    hw.run_operation(lease, saved.append)
    with pytest.raises(OwnershipBlocked):
        saved[0].execute(**command())
    with pytest.raises(OwnershipBlocked):
        hw.run_operation(replace(lease), lambda io: io.execute(**command()))
    assert not a.calls


def test_stop_blocks_without_release(setup):
    path, _, owner, hw, _, sf = setup
    lease = owner.claim("phase")
    owner.block(lease)
    with pytest.raises(OwnershipBlocked):
        hw.run_operation(lease, lambda io: io.set_state(BottomValveState.OPEN))
    assert not sf.calls and current(path) == "phase"


def test_wrong_command_phase_sends_nothing(setup):
    _, _, owner, hw, a, _ = setup
    with pytest.raises(OwnershipBlocked):
        hw.run_operation(owner.claim("phase"), lambda io: io.execute(**command("other")))
    assert not a.calls


@pytest.mark.parametrize("bad", ["missing", "empty", "identity", "schema", "slot"])
def test_open_does_not_create_or_repair(setup, tmp_path, bad):
    path, identity, *_ = setup
    if bad in ("missing", "empty"):
        path = tmp_path / "bad.db"
        if bad == "empty":
            path.touch()
    elif bad == "identity":
        identity = "wrong"
    else:
        with sqlite3.connect(path) as db:
            db.execute(
                "DROP TABLE hardware_sequences" if bad == "schema" else "DELETE FROM hardware_owner"
            )
    before = path.read_bytes() if path.exists() else None
    with pytest.raises((OwnershipBlocked, sqlite3.Error)):
        HardwareOwnership(path, identity)
    assert (path.read_bytes() if path.exists() else None) == before


def test_process_crash_keeps_owner_without_restart_send(setup):
    path, identity, _, _, _, _ = setup
    code = """
import os, sys
from pathlib import Path
from app.hardware.sequence_ownership import HardwareOwnership
owner=HardwareOwnership(Path(sys.argv[1]), sys.argv[2])
lease=owner.claim('crashed')
owner.invoke(lease, lambda: os._exit(73))
"""
    assert subprocess.run([sys.executable, "-c", code, str(path), identity]).returncode == 73
    before = path.read_bytes()
    other = HardwareOwnership(path, identity)
    try:
        with pytest.raises(OwnershipBlocked):
            other.claim("restart")
    finally:
        other.close()
    assert path.read_bytes() == before


def test_actual_service_endpoints_share_sequence_owner(setup, tmp_path):
    _, _, owner, hw, a, sf = setup
    with ApiClient(
        create_app(
            tmp_path / "app.db", arduino_commands=hw.arduino_service, sf_bottom_valve=hw.sf_service
        )
    ) as client:
        lease = owner.claim("demo-phase")
        assert client.post("/api/v1/service/pumps/command", json=request()).status_code == 503
        assert (
            client.post("/api/v1/service/sf-bottom-valve", json={"state": "OPEN"}).status_code
            == 503
        )
        assert not a.calls and not sf.calls
        owner.complete(lease)
        assert client.post("/api/v1/service/pumps/command", json=request()).status_code == 200
        assert (
            client.post("/api/v1/service/sf-bottom-valve", json={"state": "CLOSED"}).status_code
            == 200
        )


def test_real_durable_executor_persists_intent_under_shared_owner(setup, tmp_path):
    path, _, owner, _, _, sf = setup

    class Client:
        controller_boot_id = 7

        def execute(self, **values):
            assert current(path) == "phase"
            assert (
                journal.load(values["operation_command_id"]).state
                is ArduinoCommandJournalState.INTENT_PERSISTED
            )
            return ArduinoCommandResult(result={}, accepted=True, started=True)

    with SQLiteArduinoCommandJournal(tmp_path / "journal.db") as journal:
        hw = OwnedHardware(owner, DurableArduinoCommandExecutor(Client(), journal), sf)
        lease = owner.claim("phase")
        hw.run_operation(lease, lambda io: io.execute(**command()))
        owner.complete(lease)


def test_every_service_endpoint_respects_active_sequence(setup, tmp_path):
    from tests.test_arduino_valve_service_api import request as valve_request
    from tests.test_column_bottom_valve_service_api import request as column_request
    from tests.test_carousel_service_api import move_request, reference_request
    from tests.test_sf_mixer_service_api import request as mixer_request

    _, _, owner, hw, a, sf = setup
    endpoints = [
        ("pumps", request()),
        ("valves", valve_request()),
        ("column-bottom-valve", column_request()),
        ("carousel", reference_request()),
        ("carousel", move_request()),
        ("sf-mixer", mixer_request("START")),
        ("sf-mixer", mixer_request("STOP")),
    ]
    with ApiClient(
        create_app(
            tmp_path / "all-services.db",
            owned_hardware=hw,
        )
    ) as client:
        owner.claim("demo")
        for device, data in endpoints:
            assert (
                client.post("/api/v1/service/" + device + "/command", json=data).status_code == 503
            )
        assert (
            client.post("/api/v1/service/sf-bottom-valve", json={"state": "OPEN"}).status_code
            == 503
        )
    assert not a.calls and not sf.calls


class WriteFault:
    def __init__(self, db, prefix):
        self.db, self.prefix = db, prefix

    def execute(self, sql, *args):
        if sql.startswith(self.prefix):
            raise sqlite3.OperationalError("injected write failure")
        return self.db.execute(sql, *args)

    def close(self):
        self.db.close()


@pytest.mark.parametrize(
    "prefix", ["INSERT INTO hardware_sequences", "UPDATE hardware_owner", "COMMIT"]
)
def test_claim_write_failure_sends_nothing_and_rolls_back(setup, prefix):
    path, _, owner, hw, a, sf = setup
    owner._db = WriteFault(owner._db, prefix)
    with pytest.raises(sqlite3.OperationalError):
        hw.arduino_service.execute(**command())
    assert not a.calls and not sf.calls
    assert current(path) is None


def test_block_write_failure_preserves_primary_and_local_poison(setup):
    path, identity, owner, hw, a, _ = setup
    lease = owner.claim("phase")
    owner._db = WriteFault(owner._db, "UPDATE hardware_sequences")
    error = ArduinoUnavailableError("unknown")

    def fail(_):
        raise error

    a.hook = fail
    with pytest.raises(ArduinoUnavailableError) as caught:
        hw.run_operation(lease, lambda io: io.execute(**command()))
    assert caught.value is error
    assert any("retention write failed" in note for note in error.__notes__)
    with pytest.raises(OwnershipBlocked):
        owner.complete(lease)
    reopened = HardwareOwnership(path, identity)
    try:
        with pytest.raises(OwnershipBlocked):
            reopened.claim("restart")
    finally:
        reopened.close()


@pytest.mark.parametrize("prefix", ["UPDATE hardware_sequences", "UPDATE hardware_owner", "COMMIT"])
def test_success_release_fault_retains_owner(setup, prefix):
    path, _, owner, hw, _, _ = setup
    lease = owner.claim("phase")
    hw.run_operation(lease, lambda io: io.execute(**command()))
    owner._db = WriteFault(owner._db, prefix)
    with pytest.raises(sqlite3.OperationalError):
        owner.complete(lease)
    assert current(path) == "phase"
    with pytest.raises(OwnershipBlocked):
        owner.complete(lease)


def test_second_process_cannot_claim_while_owner_is_held(setup):
    path, identity, owner, *_ = setup
    owner.claim("held")
    code = """
from pathlib import Path
import sys
from app.hardware.sequence_ownership import HardwareOwnership, OwnershipBlocked
owner=HardwareOwnership(Path(sys.argv[1]), sys.argv[2])
try:
    owner.claim('competitor')
except OwnershipBlocked:
    sys.exit(0)
sys.exit(1)
"""
    assert subprocess.run([sys.executable, "-c", code, str(path), identity]).returncode == 0


def test_service_mixer_start_cannot_release_owner_while_motor_keeps_running(setup):
    _, _, _, hw, a, _ = setup
    values = command()
    values.update(command="SF_MIXER_SET_STATE", arguments={"running": True})
    with pytest.raises(OwnershipBlocked, match="continuous mixer"):
        hw.arduino_service.execute(**values)
    assert not a.calls


def test_scope_cannot_be_used_by_another_thread(setup):
    _, _, owner, hw, a, _ = setup
    lease = owner.claim("phase")

    def operation(io):
        with ThreadPoolExecutor() as pool:
            future = pool.submit(io.execute, **command())
            with pytest.raises(OwnershipBlocked):
                future.result()

    hw.run_operation(lease, operation)
    assert not a.calls


@pytest.mark.parametrize("argument", ["arduino_commands", "sf_bottom_valve", "arduino_runtime"])
def test_app_rejects_mixed_guarded_and_unguarded_hardware(setup, tmp_path, argument):
    hw = setup[3]
    with pytest.raises(ValueError, match="cannot be mixed"):
        create_app(tmp_path / "mixed.db", owned_hardware=hw, **{argument: object()})


def test_explicit_owned_app_injection_blocks_both_paths(setup, tmp_path):
    _, _, owner, hw, a, sf = setup
    owner.claim("phase")
    with ApiClient(create_app(tmp_path / "owned-app.db", owned_hardware=hw)) as client:
        assert client.post("/api/v1/service/pumps/command", json=request()).status_code == 503
        assert (
            client.post("/api/v1/service/sf-bottom-valve", json={"state": "OPEN"}).status_code
            == 503
        )
    assert not a.calls and not sf.calls
