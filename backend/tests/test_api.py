import asyncio
import sqlite3
from datetime import UTC, datetime, timedelta
from json import dumps, loads
from pathlib import Path
from socket import AF_INET, SOCK_STREAM, socket
from threading import Event, Thread
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest
from fastapi import FastAPI
from uvicorn import Config, Server

import app.main as main_module
from app.demo.application_service import GuidedDemoApplicationService
from app.demo.machine_events import MachineEventType
from app.demo.machine_lifecycle import (
    complete_recovery,
    complete_startup,
    create_machine,
    detect_interrupted_startup,
    record_runtime_hardware_fault,
    start_flush,
    start_run as start_machine_run,
)
from app.demo.machine_models import MachineState, RuntimeHardwareFaultReason
from app.main import create_app
from app.persistence.sqlite_store import (
    PersistenceDataError,
    SQLiteStore,
    StartupActiveRunReconciliationConflictError,
)
from app.startup_bootstrap import ProcessStartupDisposition

API = "/api/v1"
AWARE_COMMAND = {"occurred_at": "2026-07-19T14:00:00+02:00"}
CREATE_RUN = {
    "run_id": "run-1",
    "configuration": {
        "b1_ratio_percent": "40.125",
        "total_mixture_volume_ml": "10.000000000000000001",
        "combined_b1_b2_volume_ml": "4.250000000000000001",
        "addition_order": "B1_THEN_B2",
        "addition_speed_command_percent": "50.5",
        "reactor_mixing_command_percent": "60.25",
        "sf_mixing_command_percent": "40.75",
        "simulated_target_temperature_c": "25.125",
        "reaction_duration_seconds": "600.000000000000000001",
        "delay_between_additions_seconds": "5.125",
    },
    "execution_settings": {
        "sf_settling_duration_seconds": "12.500000000000000001",
        "fraction_count": 6,
        "fraction_duration_seconds": "45.000000000000000001",
    },
    **AWARE_COMMAND,
}


class ApiResponse:
    def __init__(self, status_code: int, body: bytes) -> None:
        self.status_code = status_code
        self._body = body

    @property
    def text(self) -> str:
        return self._body.decode()

    def json(self) -> Any:
        return loads(self._body)


class ApiClient:
    """HTTP client backed by installed Uvicorn because no HTTP test client extra is installed."""

    def __init__(
        self,
        application: FastAPI,
        *,
        lifespan: str = "off",
    ) -> None:
        self._socket = socket(AF_INET, SOCK_STREAM)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.listen()
        port = self._socket.getsockname()[1]
        self._base_url = f"http://127.0.0.1:{port}"
        self._server = Server(
            Config(application, log_level="critical", lifespan=lifespan)
        )
        self._thread = Thread(
            target=self._server.run,
            kwargs={"sockets": [self._socket]},
            daemon=True,
        )
        self._thread.start()
        while not self._server.started and self._thread.is_alive():
            self._thread.join(0.01)

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=5)
        self._socket.close()

    def get(self, path: str) -> ApiResponse:
        return self._request("GET", path, None)

    def post(self, path: str, *, json: dict[str, Any] | None = None,
             headers: dict[str, str] | None = None) -> ApiResponse:
        return self._request("POST", path, json, headers)

    def _request(
        self, method: str, path: str, json: dict[str, Any] | None,
        extra_headers: dict[str, str] | None = None,
    ) -> ApiResponse:
        request_body = dumps(json).encode() if json is not None else b""
        headers = {"Content-Type": "application/json"} if json is not None else {}
        headers.update(extra_headers or {})
        request = Request(
            f"{self._base_url}{path}", data=request_body or None, headers=headers, method=method
        )
        try:
            with urlopen(request, timeout=5) as response:
                return ApiResponse(response.status, response.read())
        except HTTPError as error:
            return ApiResponse(error.code, error.read())


@pytest.fixture
def database(tmp_path: Path) -> Path:
    return tmp_path / "api.db"


@pytest.fixture
def client(database: Path) -> ApiClient:
    with ApiClient(create_app(database)) as test_client:
        yield test_client


def initialize_ready_machine(client: ApiClient) -> None:
    assert client.post(f"{API}/machine/initialize", json=AWARE_COMMAND).status_code == 200
    assert client.post(f"{API}/machine/startup/complete", json=AWARE_COMMAND).status_code == 200


def create_and_start_run(client: ApiClient) -> None:
    assert client.post(f"{API}/runs", json=CREATE_RUN).status_code == 200
    assert client.post(f"{API}/runs/run-1/start", json=AWARE_COMMAND).status_code == 200


def test_health_route_is_preserved(client: ApiClient) -> None:
    assert client.get("/health").json() == {"status": "available"}


def test_request_scoped_file_store_persists_and_closes(
    database: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    closed_connections = 0
    both_closed = Event()
    original_close = main_module.SQLiteStore.close

    def tracked_close(store: SQLiteStore) -> None:
        nonlocal closed_connections
        closed_connections += 1
        original_close(store)
        if closed_connections == 2:
            both_closed.set()

    monkeypatch.setattr(main_module.SQLiteStore, "close", tracked_close)
    with ApiClient(create_app(database)) as client:
        initialized = client.post(f"{API}/machine/initialize", json=AWARE_COMMAND)
        loaded = client.get(f"{API}/machine")

        assert initialized.json()["state"] == "STARTING"
        assert loaded.json() == initialized.json()
        assert database.is_file()
        assert str(database) != ":memory:"
        assert both_closed.wait(timeout=1)
        assert closed_connections == 2


def test_machine_endpoints_are_explicit_and_persist_each_state(client: ApiClient) -> None:
    assert client.get(f"{API}/machine").status_code == 404

    initialized = client.post(f"{API}/machine/initialize", json=AWARE_COMMAND)
    assert initialized.status_code == 200
    assert initialized.json()["state"] == "STARTING"
    assert initialized.json()["runtime_fault_reason"] is None
    assert initialized.json()["hardware_outcome_unknown"] is False
    assert initialized.json()["carousel_position_untrusted"] is False
    assert client.get(f"{API}/machine").json()["state"] == "STARTING"

    ready = client.post(f"{API}/machine/startup/complete", json=AWARE_COMMAND)
    assert ready.json()["state"] == "READY"
    flushing = client.post(f"{API}/machine/flush/start", json=AWARE_COMMAND)
    assert flushing.json()["state"] == "FLUSHING"
    assert client.get(f"{API}/machine").json()["state"] == "FLUSHING"
    completed = client.post(f"{API}/machine/flush/complete", json=AWARE_COMMAND)
    assert completed.json()["state"] == "READY"


def test_persisted_runtime_hardware_fault_is_serialized_truthfully(
    database: Path,
) -> None:
    created = create_machine(datetime.fromisoformat(AWARE_COMMAND["occurred_at"]))
    ready = complete_startup(created.machine, created.events[0].occurred_at)
    busy = start_machine_run(
        ready.machine,
        "run-1",
        created.events[0].occurred_at,
    )
    fault = record_runtime_hardware_fault(
        busy.machine,
        run_id="run-1",
        occurred_at=created.events[0].occurred_at,
        reason=RuntimeHardwareFaultReason.CAROUSEL_MOVEMENT_FAILED,
    )
    with SQLiteStore(database) as store:
        for transition in (created, ready, busy, fault):
            store.persist_machine_transition(
                transition.machine,
                transition.events,
            )

    with ApiClient(create_app(database)) as client:
        body = client.get(f"{API}/machine").json()

    assert body["state"] == "RECOVERY_REQUIRED"
    assert body["runtime_fault_reason"] == "CAROUSEL_MOVEMENT_FAILED"
    assert body["hardware_outcome_unknown"] is True
    assert body["carousel_position_untrusted"] is True


def test_duplicate_initialize_and_invalid_machine_state_are_409_without_writes(
    client: ApiClient,
) -> None:
    first = client.post(f"{API}/machine/initialize", json=AWARE_COMMAND).json()

    assert client.post(f"{API}/machine/initialize", json=AWARE_COMMAND).status_code == 409
    assert client.post(f"{API}/machine/flush/start", json=AWARE_COMMAND).status_code == 409
    assert client.get(f"{API}/machine").json() == first


def test_create_and_read_run_preserve_nested_decimal_json(client: ApiClient) -> None:
    created = client.post(f"{API}/runs", json=CREATE_RUN)

    assert created.status_code == 200
    body = created.json()
    assert body["configuration"]["total_mixture_volume_ml"] == "10.000000000000000001"
    assert body["configuration"]["combined_b1_b2_volume_ml"] == "4.250000000000000001"
    assert (
        body["execution_settings"]["sf_settling_duration_seconds"]
        == "12.500000000000000001"
    )
    assert (
        body["execution_settings"]["fraction_duration_seconds"]
        == "45.000000000000000001"
    )
    assert body["execution_settings"]["fraction_count"] == 6
    assert client.get(f"{API}/runs/run-1").json() == body
    assert client.get(f"{API}/runs/missing").status_code == 404


def test_hardware_phase_completion_returns_409_without_advancing_run(
    client: ApiClient,
) -> None:
    initialize_ready_machine(client)
    assert client.post(f"{API}/runs", json=CREATE_RUN).status_code == 200

    started = client.post(f"{API}/runs/run-1/start", json=AWARE_COMMAND).json()
    assert (started["run"]["status"], started["run"]["phase"]) == (
        "RUNNING",
        "P1_TRANSFER_S_TO_REACTOR",
    )
    assert started["machine"]["state"] == "BUSY"
    assert started["machine"]["active_run_id"] == "run-1"

    original_machine = client.get(f"{API}/machine").json()
    rejected = client.post(
        f"{API}/runs/run-1/phases/current/complete", json=AWARE_COMMAND
    )

    assert rejected.status_code == 409
    assert client.get(f"{API}/runs/run-1").json() == started["run"]
    assert client.get(f"{API}/machine").json() == original_machine


def test_stop_request_and_confirmation_have_separate_persisted_states(
    client: ApiClient,
) -> None:
    initialize_ready_machine(client)
    create_and_start_run(client)

    requested = client.post(
        f"{API}/runs/run-1/stop/request", json=AWARE_COMMAND
    ).json()
    assert requested["run"]["status"] == "ABORTING"
    assert requested["machine"]["state"] == "BUSY"
    confirmed = client.post(
        f"{API}/runs/run-1/stop/confirm", json=AWARE_COMMAND
    ).json()
    assert confirmed["run"]["status"] == "ABORTED"
    assert confirmed["machine"]["state"] == "FLUSH_REQUIRED"


def test_wrong_active_run_returns_409_without_writes(client: ApiClient) -> None:
    initialize_ready_machine(client)
    create_and_start_run(client)
    second = CREATE_RUN | {"run_id": "run-2"}
    assert client.post(f"{API}/runs", json=second).status_code == 200
    original_run = client.get(f"{API}/runs/run-2").json()
    original_machine = client.get(f"{API}/machine").json()

    response = client.post(
        f"{API}/runs/run-2/phases/current/complete", json=AWARE_COMMAND
    )

    assert response.status_code == 409
    assert client.get(f"{API}/runs/run-2").json() == original_run
    assert client.get(f"{API}/machine").json() == original_machine


def test_missing_machine_and_duplicate_run_are_409_without_overwrite(
    client: ApiClient,
) -> None:
    created = client.post(f"{API}/runs", json=CREATE_RUN).json()

    assert client.post(f"{API}/runs/run-1/start", json=AWARE_COMMAND).status_code == 409
    assert client.post(f"{API}/runs", json=CREATE_RUN).status_code == 409
    assert client.get(f"{API}/runs/run-1").json() == created


@pytest.mark.parametrize("run_id", ["", "   "])
def test_empty_run_id_returns_422_without_writes(
    database: Path, run_id: str
) -> None:
    with ApiClient(create_app(database)) as client:
        response = client.post(f"{API}/runs", json=CREATE_RUN | {"run_id": run_id})

    assert response.status_code == 422
    with SQLiteStore(database) as store:
        assert store.load_events() == ()


@pytest.mark.parametrize(
    "payload",
    [
        {"occurred_at": "2026-07-19T12:00:00"},
        {"occurred_at": "not-a-timestamp"},
    ],
)
def test_invalid_timestamp_returns_422_without_writes(
    client: ApiClient, payload: dict[str, str]
) -> None:
    assert client.post(f"{API}/machine/initialize", json=payload).status_code == 422
    assert client.get(f"{API}/machine").status_code == 404


def test_timezone_offset_is_accepted_and_invalid_configuration_is_422(
    client: ApiClient,
) -> None:
    assert client.post(f"{API}/machine/initialize", json=AWARE_COMMAND).status_code == 200
    invalid = CREATE_RUN | {
        "configuration": CREATE_RUN["configuration"] | {"b1_ratio_percent": "101"}
    }
    assert client.post(f"{API}/runs", json=invalid).status_code == 422
    assert client.get(f"{API}/runs/run-1").status_code == 404


def test_persisted_corruption_remains_server_error(database: Path) -> None:
    with ApiClient(create_app(database)) as client:
        assert client.post(f"{API}/machine/initialize", json=AWARE_COMMAND).status_code == 200
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE machine_snapshot SET snapshot_json = '{broken'")

    with ApiClient(create_app(database)) as client:
        response = client.get(f"{API}/machine")

    assert response.status_code == 500
    assert response.status_code not in {404, 409}
    assert "broken" not in response.text


def _run_lifespan(application: FastAPI) -> None:
    async def run() -> None:
        async with application.router.lifespan_context(application):
            pass

    asyncio.run(run())


def _persist_api_ready_machine(database: Path) -> None:
    occurred_at = datetime.fromisoformat(AWARE_COMMAND["occurred_at"])
    with SQLiteStore(database) as store:
        service = GuidedDemoApplicationService(store)
        service.initialize_machine(occurred_at)
        service.complete_startup(occurred_at)


def test_lifespan_runs_before_first_request_for_ready_database(
    database: Path,
) -> None:
    _persist_api_ready_machine(database)
    occurred_at = datetime.fromisoformat(AWARE_COMMAND["occurred_at"])
    application = create_app(database, startup_clock=lambda: occurred_at)

    with ApiClient(application, lifespan="on") as client:
        assert application.state.process_startup.disposition is (
            ProcessStartupDisposition.READY
        )
        assert client.get(f"{API}/machine").json()["state"] == "READY"


def test_lifespan_reconciles_busy_machine_before_first_read(
    database: Path,
) -> None:
    occurred_at = datetime.fromisoformat(AWARE_COMMAND["occurred_at"])
    with SQLiteStore(database) as store:
        service = GuidedDemoApplicationService(store)
        service.initialize_machine(occurred_at)
        service.complete_startup(occurred_at)
        service.create_run(
            CREATE_RUN["run_id"],
            main_module.DemoConfiguration(**CREATE_RUN["configuration"]),
            main_module.DemoExecutionSettings(
                **CREATE_RUN["execution_settings"]
            ),
            occurred_at,
        )
        service.start_run("run-1", occurred_at)
    application = create_app(
        database,
        startup_clock=lambda: occurred_at + timedelta(seconds=1),
    )

    with ApiClient(application, lifespan="on") as client:
        result = application.state.process_startup
        assert result.disposition is (
            ProcessStartupDisposition.ACTIVE_RUN_RECONCILED
        )
        assert client.get(f"{API}/machine").json()["state"] == "RECOVERING"


@pytest.mark.parametrize(
    "state",
    [
        MachineState.RECOVERY_REQUIRED,
        MachineState.RECOVERING,
        MachineState.FLUSH_REQUIRED,
        MachineState.FLUSHING,
    ],
)
def test_lifespan_preserves_blocked_recovery_and_flush_states(
    database: Path,
    state: MachineState,
) -> None:
    occurred_at = datetime.fromisoformat(AWARE_COMMAND["occurred_at"])
    created = create_machine(occurred_at)
    with SQLiteStore(database) as store:
        store.persist_machine_transition(created.machine, created.events)
        if state in {MachineState.RECOVERING, MachineState.FLUSH_REQUIRED}:
            recovering = detect_interrupted_startup(
                created.machine, "run-1", occurred_at
            )
            store.persist_machine_transition(
                recovering.machine, recovering.events
            )
            if state is MachineState.FLUSH_REQUIRED:
                transition = complete_recovery(
                    recovering.machine, occurred_at
                )
                store.persist_machine_transition(
                    transition.machine, transition.events
                )
        else:
            ready = complete_startup(created.machine, occurred_at)
            store.persist_machine_transition(ready.machine, ready.events)
            if state is MachineState.RECOVERY_REQUIRED:
                busy = start_machine_run(ready.machine, "run-1", occurred_at)
                store.persist_machine_transition(busy.machine, busy.events)
                transition = record_runtime_hardware_fault(
                    busy.machine,
                    run_id="run-1",
                    occurred_at=occurred_at,
                    reason=RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED,
                )
            else:
                transition = start_flush(ready.machine, occurred_at)
            store.persist_machine_transition(
                transition.machine, transition.events
            )
        before = store.load_events("MACHINE", "machine")

    application = create_app(database, startup_clock=lambda: occurred_at)
    with ApiClient(application, lifespan="on") as client:
        assert client.get(f"{API}/machine").json()["state"] == state.value

    with SQLiteStore(database) as store:
        assert store.load_events("MACHINE", "machine") == before


def test_uninitialized_lifespan_preserves_explicit_initialize_endpoint(
    database: Path,
) -> None:
    occurred_at = datetime.fromisoformat(AWARE_COMMAND["occurred_at"])
    application = create_app(database, startup_clock=lambda: occurred_at)

    with ApiClient(application, lifespan="on") as client:
        assert application.state.process_startup.disposition is (
            ProcessStartupDisposition.UNINITIALIZED
        )
        assert client.post(
            f"{API}/machine/initialize", json=AWARE_COMMAND
        ).status_code == 200


def test_naive_startup_clock_prevents_lifespan_startup(database: Path) -> None:
    application = create_app(
        database,
        startup_clock=lambda: datetime(2026, 7, 30, 15),
    )

    with pytest.raises(
        ValueError,
        match="process startup occurred_at must be timezone-aware",
    ):
        _run_lifespan(application)


def test_corrupted_database_prevents_lifespan_startup(database: Path) -> None:
    occurred_at = datetime(2026, 7, 30, 15, tzinfo=UTC)
    created = create_machine(occurred_at)
    with SQLiteStore(database) as store:
        store.persist_machine_transition(created.machine, created.events)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE machine_snapshot SET state = 'READY'"
        )
    application = create_app(database, startup_clock=lambda: occurred_at)

    with pytest.raises(
        PersistenceDataError,
        match="machine snapshot metadata does not match JSON",
    ):
        _run_lifespan(application)


def test_missing_active_run_prevents_lifespan_startup(
    database: Path,
) -> None:
    occurred_at = datetime(2026, 7, 30, 15, tzinfo=UTC)
    created = create_machine(occurred_at)
    ready = complete_startup(created.machine, occurred_at)
    busy = start_machine_run(ready.machine, "missing-run", occurred_at)
    with SQLiteStore(database) as store:
        for transition in (created, ready, busy):
            store.persist_machine_transition(
                transition.machine, transition.events
            )
        machine_before = store.load_machine_snapshot()
        events_before = store.load_events("MACHINE", "machine")
    application = create_app(database, startup_clock=lambda: occurred_at)

    with pytest.raises(
        StartupActiveRunReconciliationConflictError,
        match="Guided Demo run 'missing-run' was not found",
    ):
        _run_lifespan(application)

    assert not hasattr(application.state, "process_startup")
    with SQLiteStore(database) as store:
        assert store.load_machine_snapshot() == machine_before
        assert store.load_events("MACHINE", "machine") == events_before
        assert all(
            event.event_type is not MachineEventType.RUN_INTERRUPTED_AT_STARTUP
            for event in store.load_events("MACHINE", "machine")
        )


@pytest.mark.parametrize("active_execution", [True, False])
def test_lifespan_reconciliation_failure_rolls_back_all_persistence(
    database: Path,
    monkeypatch: pytest.MonkeyPatch,
    active_execution: bool,
) -> None:
    occurred_at = datetime(2026, 7, 30, 15, tzinfo=UTC)
    with SQLiteStore(database) as store:
        service = GuidedDemoApplicationService(store)
        service.initialize_machine(occurred_at)
        service.complete_startup(occurred_at)
        service.create_run(
            CREATE_RUN["run_id"],
            main_module.DemoConfiguration(**CREATE_RUN["configuration"]),
            main_module.DemoExecutionSettings(
                **CREATE_RUN["execution_settings"]
            ),
            occurred_at,
        )
        service.start_run("run-1", occurred_at)
        if active_execution:
            run = store.load_demo_run("run-1")
            assert run is not None
            store.claim_phase_execution(
                run_id=run.run_id,
                execution_id="execution-1",
                claimed_at=occurred_at + timedelta(seconds=1),
                expected_run_event_sequence=run.event_sequence,
                expected_phase=run.phase,
            )
        before = (
            store.load_demo_run("run-1"),
            store.load_machine_snapshot(),
            store.load_events("RUN", "run-1"),
            store.load_events("MACHINE", "machine"),
        )

    original_write = SQLiteStore._write_transition
    run_write_executed = False

    def fail_second_aggregate_write(
        store,
        aggregate_type,
        aggregate_id,
        snapshot,
        events,
    ):
        nonlocal run_write_executed
        if aggregate_type == "MACHINE" and run_write_executed:
            raise RuntimeError("injected machine write failure")
        result = original_write(
            store,
            aggregate_type,
            aggregate_id,
            snapshot,
            events,
        )
        if aggregate_type == "RUN":
            run_write_executed = True
        return result

    monkeypatch.setattr(SQLiteStore, "_write_transition", fail_second_aggregate_write)
    application = create_app(
        database,
        startup_clock=lambda: occurred_at + timedelta(seconds=2),
    )

    with pytest.raises(
        RuntimeError,
        match="injected machine write failure",
    ):
        _run_lifespan(application)

    assert run_write_executed is True
    assert not hasattr(application.state, "process_startup")
    with SQLiteStore(database) as store:
        after = (
            store.load_demo_run("run-1"),
            store.load_machine_snapshot(),
            store.load_events("RUN", "run-1"),
            store.load_events("MACHINE", "machine"),
        )
        assert after == before
        assert all(
            event.event_type
            not in {
                MachineEventType.PHASE_EXECUTION_INTERRUPTED_AT_STARTUP,
                MachineEventType.RUN_INTERRUPTED_AT_STARTUP,
            }
            for event in store.load_events("MACHINE", "machine")
        )
