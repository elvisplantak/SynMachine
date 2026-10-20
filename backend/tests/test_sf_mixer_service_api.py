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
ENDPOINT = "/api/v1/service/sf-mixer/command"


class RecordingExecutor:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    def execute(self, **values: object) -> ArduinoCommandJournalEntry:
        self.calls.append(values)
        if self.error is not None:
            raise self.error
        return ArduinoCommandJournalEntry(
            operation_command_id=str(values["operation_command_id"]),
            phase_execution_id=str(values["phase_execution_id"]),
            controller_boot_id=7,
            command=str(values["command"]),
            arguments=values["arguments"],  # type: ignore[arg-type]
            state=ArduinoCommandJournalState.COMPLETED,
            result={},
            error_code=None,
            execution_started=True,
        )


def request(command: str = "START", **overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "phase_execution_id": "service.sf-mixer.start",
        "operation_command_id": OPERATION_ID,
        "command": command,
    }
    values.update(overrides)
    return values


def test_rejects_unconfigured_arduino(tmp_path: Path) -> None:
    with ApiClient(create_app(tmp_path / "labforge.db")) as client:
        response = client.post(ENDPOINT, json=request())

    assert response.status_code == 503
    assert response.json() == {"detail": "Arduino hardware is not configured"}


def test_start_and_stop_map_to_exact_boolean_contract(tmp_path: Path) -> None:
    executor = RecordingExecutor()
    with ApiClient(
        create_app(tmp_path / "labforge.db", arduino_commands=executor)
    ) as client:
        start = client.post(ENDPOINT, json=request("START"))
        stop = client.post(
            ENDPOINT,
            json=request(
                "STOP",
                phase_execution_id="service.sf-mixer.stop",
                operation_command_id="423e4567-e89b-12d3-a456-426614174003",
            ),
        )

    assert start.status_code == 200
    assert stop.status_code == 200
    assert [call["command"] for call in executor.calls] == [
        "SF_MIXER_SET_STATE",
        "SF_MIXER_SET_STATE",
    ]
    assert [call["arguments"] for call in executor.calls] == [
        {"running": True},
        {"running": False},
    ]


def test_invalid_shapes_never_dispatch(tmp_path: Path) -> None:
    executor = RecordingExecutor()
    with ApiClient(
        create_app(tmp_path / "labforge.db", arduino_commands=executor)
    ) as client:
        responses = [
            client.post(ENDPOINT, json=request("RUN")),
            client.post(ENDPOINT, json={**request(), "running": True}),
            client.post(ENDPOINT, json=request(command=True)),
        ]

    assert [response.status_code for response in responses] == [422, 422, 422]
    assert executor.calls == []


def test_transport_failure_and_identity_conflict_are_not_retried(
    tmp_path: Path,
) -> None:
    cases = [
        (ArduinoUnavailableError("outcome unknown"), 503),
        (ArduinoCommandIdentityConflictError("identity conflict"), 409),
    ]
    for index, (error, expected_status) in enumerate(cases):
        executor = RecordingExecutor(error)
        with ApiClient(
            create_app(tmp_path / f"labforge-{index}.db", arduino_commands=executor)
        ) as client:
            response = client.post(ENDPOINT, json=request())

        assert response.status_code == expected_status
        assert len(executor.calls) == 1
