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


class RecordingExecutor:
    def __init__(
        self,
        *,
        entry: ArduinoCommandJournalEntry | None = None,
        error: Exception | None = None,
    ) -> None:
        self.entry = entry or ArduinoCommandJournalEntry(
            operation_command_id=OPERATION_ID,
            phase_execution_id="service.p1.home",
            controller_boot_id=7,
            command="PUMP_HOME",
            arguments={"pump": "P1"},
            state=ArduinoCommandJournalState.COMPLETED,
            result={"position_steps": 0},
            error_code=None,
            execution_started=True,
        )
        self.error = error
        self.calls: list[dict[str, object]] = []

    def execute(self, **values: object) -> ArduinoCommandJournalEntry:
        self.calls.append(values)
        if self.error is not None:
            raise self.error
        return self.entry


def request(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "phase_execution_id": "service.p1.home",
        "operation_command_id": OPERATION_ID,
        "pump": "P1",
        "command": "HOME",
        "safe_route_confirmed": True,
    }
    values.update(overrides)
    return values


def test_pump_service_rejects_unconfigured_arduino(tmp_path: Path) -> None:
    with ApiClient(create_app(tmp_path / "labforge.db")) as client:
        response = client.post("/api/v1/service/pumps/command", json=request())

    assert response.status_code == 503
    assert response.json() == {"detail": "Arduino hardware is not configured"}


def test_pump_home_uses_caller_owned_identity_and_safe_route_confirmation(
    tmp_path: Path,
) -> None:
    executor = RecordingExecutor()
    with ApiClient(
        create_app(tmp_path / "labforge.db", arduino_commands=executor)
    ) as client:
        response = client.post("/api/v1/service/pumps/command", json=request())

    assert response.status_code == 200
    assert response.json() == {
        "operation_command_id": OPERATION_ID,
        "state": "COMPLETED",
        "result": {"position_steps": 0},
        "error_code": None,
        "execution_started": True,
    }
    assert executor.calls == [
        {
            "phase_execution_id": "service.p1.home",
            "operation_command_id": OPERATION_ID,
            "command": "PUMP_HOME",
            "arguments": {"pump": "P1"},
        }
    ]


def test_absolute_move_maps_exact_p2_contract(tmp_path: Path) -> None:
    executor = RecordingExecutor()
    with ApiClient(
        create_app(tmp_path / "labforge.db", arduino_commands=executor)
    ) as client:
        response = client.post(
            "/api/v1/service/pumps/command",
            json=request(
                phase_execution_id="service.p2.move",
                pump="P2",
                command="MOVE_ABSOLUTE_STEPS",
                target_steps=20500,
            ),
        )

    assert response.status_code == 200
    assert executor.calls[0]["command"] == "PUMP_MOVE_ABSOLUTE_STEPS"
    assert executor.calls[0]["arguments"] == {"pump": "P2", "target_steps": 20500}


def test_pump_service_requires_explicit_true_safe_route(tmp_path: Path) -> None:
    executor = RecordingExecutor()
    with ApiClient(
        create_app(tmp_path / "labforge.db", arduino_commands=executor)
    ) as client:
        missing = request()
        del missing["safe_route_confirmed"]
        responses = [
            client.post("/api/v1/service/pumps/command", json=missing),
            client.post(
                "/api/v1/service/pumps/command",
                json=request(safe_route_confirmed=False),
            ),
        ]

    assert [response.status_code for response in responses] == [422, 422]
    assert executor.calls == []


def test_pump_service_rejects_invalid_command_shape_without_dispatch(
    tmp_path: Path,
) -> None:
    executor = RecordingExecutor()
    with ApiClient(
        create_app(tmp_path / "labforge.db", arduino_commands=executor)
    ) as client:
        responses = [
            client.post(
                "/api/v1/service/pumps/command",
                json=request(command="HOME", target_steps=1),
            ),
            client.post(
                "/api/v1/service/pumps/command",
                json=request(command="MOVE_ABSOLUTE_STEPS"),
            ),
            client.post(
                "/api/v1/service/pumps/command",
                json=request(command="MOVE_ABSOLUTE_STEPS", target_steps=20501),
            ),
        ]

    assert [response.status_code for response in responses] == [422, 422, 422]
    assert executor.calls == []


def test_unknown_transport_outcome_is_service_unavailable_without_retry(
    tmp_path: Path,
) -> None:
    executor = RecordingExecutor(error=ArduinoUnavailableError("outcome unknown"))
    with ApiClient(
        create_app(tmp_path / "labforge.db", arduino_commands=executor)
    ) as client:
        response = client.post("/api/v1/service/pumps/command", json=request())

    assert response.status_code == 503
    assert response.json() == {"detail": "outcome unknown"}
    assert len(executor.calls) == 1


def test_identity_conflict_is_reported_without_second_hardware_dispatch(
    tmp_path: Path,
) -> None:
    executor = RecordingExecutor(
        error=ArduinoCommandIdentityConflictError("identity conflict")
    )
    with ApiClient(
        create_app(tmp_path / "labforge.db", arduino_commands=executor)
    ) as client:
        response = client.post("/api/v1/service/pumps/command", json=request())

    assert response.status_code == 409
    assert response.json() == {"detail": "identity conflict"}
    assert len(executor.calls) == 1
