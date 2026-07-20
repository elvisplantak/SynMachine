import sqlite3
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
from app.demo.phases import RunPhase
from app.main import create_app
from app.persistence.sqlite_store import SQLiteStore

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

    def __init__(self, application: FastAPI) -> None:
        self._socket = socket(AF_INET, SOCK_STREAM)
        self._socket.bind(("127.0.0.1", 0))
        self._socket.listen()
        port = self._socket.getsockname()[1]
        self._base_url = f"http://127.0.0.1:{port}"
        self._server = Server(Config(application, log_level="critical", lifespan="off"))
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

    def post(self, path: str, *, json: dict[str, Any]) -> ApiResponse:
        return self._request("POST", path, json)

    def _request(
        self, method: str, path: str, json: dict[str, Any] | None
    ) -> ApiResponse:
        request_body = dumps(json).encode() if json is not None else b""
        headers = {"Content-Type": "application/json"} if json is not None else {}
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
    assert client.get(f"{API}/machine").json()["state"] == "STARTING"

    ready = client.post(f"{API}/machine/startup/complete", json=AWARE_COMMAND)
    assert ready.json()["state"] == "READY"
    flushing = client.post(f"{API}/machine/flush/start", json=AWARE_COMMAND)
    assert flushing.json()["state"] == "FLUSHING"
    assert client.get(f"{API}/machine").json()["state"] == "FLUSHING"
    completed = client.post(f"{API}/machine/flush/complete", json=AWARE_COMMAND)
    assert completed.json()["state"] == "READY"


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


def test_start_and_intermediate_phase_completion_keep_machine_busy(
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

    advanced = client.post(
        f"{API}/runs/run-1/phases/current/complete", json=AWARE_COMMAND
    ).json()
    assert advanced["run"]["phase"] == "P1_TRANSFER_FIRST_LIQUID_TO_REACTOR"
    assert advanced["machine"]["state"] == "BUSY"


def test_final_phase_confirmation_completes_run_and_releases_machine(
    client: ApiClient,
) -> None:
    initialize_ready_machine(client)
    create_and_start_run(client)

    current_phase = "P1_TRANSFER_S_TO_REACTOR"
    while current_phase != RunPhase.COLUMN_FRACTION_COLLECTION:
        response = client.post(
            f"{API}/runs/run-1/phases/current/complete", json=AWARE_COMMAND
        )
        assert response.status_code == 200
        current_phase = response.json()["run"]["phase"]

    completed = client.post(
        f"{API}/runs/run-1/phases/current/complete", json=AWARE_COMMAND
    ).json()
    assert (completed["run"]["status"], completed["run"]["phase"]) == (
        "COMPLETED",
        "COMPLETED",
    )
    assert completed["machine"]["state"] == "READY"
    assert completed["machine"]["active_run_id"] is None


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
