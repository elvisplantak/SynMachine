from __future__ import annotations

from pathlib import Path

from app.hardware.arduino_command_journal import (
    ArduinoCommandIdentityConflictError,
    ArduinoCommandJournalEntry,
    ArduinoCommandJournalState,
)
from app.hardware.arduino_serial import ArduinoUnavailableError
from app.main import create_app
from tests.test_api import ApiClient

OPERATION_ID = "323e4567-e89b-12d3-a456-426614174002"
ENDPOINT = "/api/v1/service/column-bottom-valve/command"


class RecordingExecutor:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def execute(self, **values: object) -> ArduinoCommandJournalEntry:
        self.calls.append(values)
        if self.error is not None:
            raise self.error
        return ArduinoCommandJournalEntry(
            operation_command_id=OPERATION_ID,
            phase_execution_id=str(values["phase_execution_id"]),
            controller_boot_id=7,
            command=str(values["command"]),
            arguments=values["arguments"],  # type: ignore[arg-type]
            state=ArduinoCommandJournalState.COMPLETED,
            result={},
            error_code=None,
            execution_started=True,
        )


def request(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "phase_execution_id": "service.column-bottom-valve.home",
        "operation_command_id": OPERATION_ID,
        "command": "HOME",
    }
    values.update(overrides)
    return values


def test_column_bottom_valve_service_rejects_unconfigured_arduino(
    tmp_path: Path,
) -> None:
    with ApiClient(create_app(tmp_path / "labforge.db")) as client:
        response = client.post(ENDPOINT, json=request())

    assert response.status_code == 503
    assert response.json() == {"detail": "Arduino hardware is not configured"}


def test_home_maps_exact_empty_argument_contract(tmp_path: Path) -> None:
    executor = RecordingExecutor()
    with ApiClient(
        create_app(tmp_path / "labforge.db", arduino_commands=executor)
    ) as client:
        response = client.post(ENDPOINT, json=request())

    assert response.status_code == 200
    assert response.json()["state"] == "COMPLETED"
    assert executor.calls == [
        {
            "phase_execution_id": "service.column-bottom-valve.home",
            "operation_command_id": OPERATION_ID,
            "command": "COLUMN_BOTTOM_VALVE_HOME",
            "arguments": {},
        }
    ]


def test_closed_and_open_map_to_confirmed_positions(tmp_path: Path) -> None:
    executor = RecordingExecutor()
    with ApiClient(
        create_app(tmp_path / "labforge.db", arduino_commands=executor)
    ) as client:
        responses = [
            client.post(
                ENDPOINT,
                json=request(
                    phase_execution_id=f"service.column-bottom-valve.{position}",
                    command="SET_POSITION",
                    position_degrees=position,
                ),
            )
            for position in (4, 94)
        ]

    assert [response.status_code for response in responses] == [200, 200]
    assert [call["arguments"] for call in executor.calls] == [
        {"position_degrees": 4},
        {"position_degrees": 94},
    ]


def test_invalid_command_shapes_never_dispatch(tmp_path: Path) -> None:
    executor = RecordingExecutor()
    with ApiClient(
        create_app(tmp_path / "labforge.db", arduino_commands=executor)
    ) as client:
        responses = [
            client.post(ENDPOINT, json=request(command="HOME", position_degrees=4)),
            client.post(ENDPOINT, json=request(command="SET_POSITION")),
            client.post(
                ENDPOINT,
                json=request(command="SET_POSITION", position_degrees=0),
            ),
            client.post(
                ENDPOINT,
                json=request(command="SET_POSITION", position_degrees=90),
            ),
            client.post(ENDPOINT, json={**request(), "extra": True}),
        ]

    assert [response.status_code for response in responses] == [422] * 5
    assert executor.calls == []


def test_transport_failure_and_identity_conflict_are_not_retried(tmp_path: Path) -> None:
    cases = [
        (ArduinoUnavailableError("outcome unknown"), 503),
        (ArduinoCommandIdentityConflictError("identity conflict"), 409),
    ]
    for error, expected_status in cases:
        executor = RecordingExecutor(error=error)
        with ApiClient(
            create_app(tmp_path / f"labforge-{expected_status}.db", arduino_commands=executor)
        ) as client:
            response = client.post(ENDPOINT, json=request())

        assert response.status_code == expected_status
        assert len(executor.calls) == 1
