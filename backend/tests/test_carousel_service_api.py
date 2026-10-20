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
ENDPOINT = "/api/v1/service/carousel/command"


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


def reference_request(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "phase_execution_id": "service.carousel.reference",
        "operation_command_id": OPERATION_ID,
        "command": "SET_REFERENCE",
        "position": 1,
        "manual_alignment_confirmed": True,
    }
    values.update(overrides)
    return values


def move_request(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "phase_execution_id": "service.carousel.move",
        "operation_command_id": OPERATION_ID,
        "command": "MOVE_TO_POSITION",
        "position": 40,
        "column_bottom_valve_closed_confirmed": True,
    }
    values.update(overrides)
    return values


def test_carousel_service_rejects_unconfigured_arduino(tmp_path: Path) -> None:
    with ApiClient(create_app(tmp_path / "labforge.db")) as client:
        response = client.post(ENDPOINT, json=reference_request())

    assert response.status_code == 503
    assert response.json() == {"detail": "Arduino hardware is not configured"}


def test_reference_maps_exact_contract_after_manual_alignment_confirmation(
    tmp_path: Path,
) -> None:
    executor = RecordingExecutor()
    with ApiClient(
        create_app(tmp_path / "labforge.db", arduino_commands=executor)
    ) as client:
        response = client.post(ENDPOINT, json=reference_request(position=17))

    assert response.status_code == 200
    assert response.json()["state"] == "COMPLETED"
    assert executor.calls == [
        {
            "phase_execution_id": "service.carousel.reference",
            "operation_command_id": OPERATION_ID,
            "command": "CAROUSEL_SET_REFERENCE",
            "arguments": {"position": 17},
        }
    ]


def test_move_maps_exact_contract_after_column_closed_confirmation(
    tmp_path: Path,
) -> None:
    executor = RecordingExecutor()
    with ApiClient(
        create_app(tmp_path / "labforge.db", arduino_commands=executor)
    ) as client:
        response = client.post(ENDPOINT, json=move_request())

    assert response.status_code == 200
    assert executor.calls[0]["command"] == "CAROUSEL_MOVE_TO_POSITION"
    assert executor.calls[0]["arguments"] == {"position": 40}


def test_reference_requires_only_manual_alignment_confirmation(tmp_path: Path) -> None:
    executor = RecordingExecutor()
    missing = reference_request()
    del missing["manual_alignment_confirmed"]
    with ApiClient(
        create_app(tmp_path / "labforge.db", arduino_commands=executor)
    ) as client:
        responses = [
            client.post(ENDPOINT, json=missing),
            client.post(ENDPOINT, json=reference_request(manual_alignment_confirmed=False)),
            client.post(
                ENDPOINT,
                json=reference_request(column_bottom_valve_closed_confirmed=True),
            ),
        ]

    assert [response.status_code for response in responses] == [422, 422, 422]
    assert executor.calls == []


def test_move_requires_only_column_closed_confirmation(tmp_path: Path) -> None:
    executor = RecordingExecutor()
    missing = move_request()
    del missing["column_bottom_valve_closed_confirmed"]
    with ApiClient(
        create_app(tmp_path / "labforge.db", arduino_commands=executor)
    ) as client:
        responses = [
            client.post(ENDPOINT, json=missing),
            client.post(
                ENDPOINT,
                json=move_request(column_bottom_valve_closed_confirmed=False),
            ),
            client.post(ENDPOINT, json=move_request(manual_alignment_confirmed=True)),
        ]

    assert [response.status_code for response in responses] == [422, 422, 422]
    assert executor.calls == []


def test_position_must_be_strict_integer_in_1_through_40(tmp_path: Path) -> None:
    executor = RecordingExecutor()
    with ApiClient(
        create_app(tmp_path / "labforge.db", arduino_commands=executor)
    ) as client:
        responses = [
            client.post(ENDPOINT, json=reference_request(position=position))
            for position in (0, 41, 1.0, True)
        ]

    assert [response.status_code for response in responses] == [422] * 4
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
            response = client.post(ENDPOINT, json=reference_request())

        assert response.status_code == expected_status
        assert len(executor.calls) == 1
