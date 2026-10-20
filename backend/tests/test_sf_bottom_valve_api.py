from pathlib import Path

from app.demo.hardware_contract import BottomValveState, HardwareCommandError
from app.main import create_app
from tests.test_api import ApiClient


class RecordingSfBottomValve:
    def __init__(self, error: HardwareCommandError | None = None) -> None:
        self.states: list[BottomValveState] = []
        self.error = error

    def set_state(self, state: BottomValveState) -> None:
        self.states.append(state)
        if self.error is not None:
            raise self.error


def test_service_endpoint_rejects_unconfigured_hardware(tmp_path: Path) -> None:
    with ApiClient(create_app(tmp_path / "labforge.db")) as test_client:
        response = test_client.post("/api/v1/service/sf-bottom-valve", json={"state": "OPEN"})

    assert response.status_code == 503
    assert response.json() == {"detail": "SF bottom valve hardware is not configured"}


def test_service_endpoint_executes_open_and_closed_commands(tmp_path: Path) -> None:
    actuator = RecordingSfBottomValve()
    with ApiClient(
        create_app(
            tmp_path / "labforge.db",
            sf_bottom_valve=actuator,
        )
    ) as test_client:
        open_response = test_client.post("/api/v1/service/sf-bottom-valve", json={"state": "OPEN"})
        closed_response = test_client.post(
            "/api/v1/service/sf-bottom-valve", json={"state": "CLOSED"}
        )

    assert open_response.status_code == 200
    assert open_response.json() == {"state": "OPEN", "position_confirmed": True}
    assert closed_response.status_code == 200
    assert closed_response.json() == {
        "state": "CLOSED",
        "position_confirmed": True,
    }
    assert actuator.states == [BottomValveState.OPEN, BottomValveState.CLOSED]


def test_hardware_failure_is_reported_as_service_unavailable(tmp_path: Path) -> None:
    actuator = RecordingSfBottomValve(HardwareCommandError("U2D2 disconnected"))
    with ApiClient(
        create_app(
            tmp_path / "labforge.db",
            sf_bottom_valve=actuator,
        )
    ) as test_client:
        response = test_client.post("/api/v1/service/sf-bottom-valve", json={"state": "OPEN"})

    assert response.status_code == 503
    assert response.json() == {"detail": "U2D2 disconnected"}


def test_service_endpoint_rejects_unknown_state_without_hardware_call(
    tmp_path: Path,
) -> None:
    actuator = RecordingSfBottomValve()
    with ApiClient(
        create_app(
            tmp_path / "labforge.db",
            sf_bottom_valve=actuator,
        )
    ) as test_client:
        response = test_client.post("/api/v1/service/sf-bottom-valve", json={"state": "HALF_OPEN"})

    assert response.status_code == 422
    assert actuator.states == []
