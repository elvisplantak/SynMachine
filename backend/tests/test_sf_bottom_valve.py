from collections.abc import Iterable

import pytest

from app.demo.hardware_contract import BottomValveState, HardwareCommandError
from app.hardware.sf_bottom_valve import (
    EXPECTED_MODEL_NUMBER,
    REGISTERS,
    Register,
    SfBottomValveActuator,
    SfBottomValveConfiguration,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        self.now += duration


class FakeSession:
    def __init__(
        self,
        *,
        model: int = EXPECTED_MODEL_NUMBER,
        positions: Iterable[int] = (2559,),
        hardware_errors: Iterable[int] = (0,),
        mode: int = 3,
        minimum: int = 0,
        maximum: int = 4095,
        fail_write: Register | None = None,
        fail_close: bool = False,
    ) -> None:
        self.model = model
        self.positions = iter(positions)
        self.last_position = 2559
        self.hardware_errors = iter(hardware_errors)
        self.last_hardware_error = 0
        self.values = {
            REGISTERS["operating_mode"]: mode,
            REGISTERS["min_position_limit"]: minimum,
            REGISTERS["max_position_limit"]: maximum,
        }
        self.fail_write = fail_write
        self.fail_close = fail_close
        self.writes: list[tuple[int, Register, int]] = []
        self.closed = False

    def ping(self, device_id: int) -> int:
        assert device_id == 2
        return self.model

    def read(self, device_id: int, register: Register) -> int:
        assert device_id == 2
        if register == REGISTERS["present_position"]:
            self.last_position = next(self.positions, self.last_position)
            return self.last_position
        if register == REGISTERS["hardware_error_status"]:
            self.last_hardware_error = next(self.hardware_errors, self.last_hardware_error)
            return self.last_hardware_error
        return self.values[register]

    def write(self, device_id: int, register: Register, value: int) -> None:
        assert device_id == 2
        if register == self.fail_write:
            raise RuntimeError("scripted write failure")
        self.writes.append((device_id, register, value))

    def close(self) -> None:
        self.closed = True
        if self.fail_close:
            raise RuntimeError("scripted close failure")


def configuration(**overrides: object) -> SfBottomValveConfiguration:
    values: dict[str, object] = {
        "port": "/dev/serial/by-id/test-u2d2",
        "poll_interval_seconds": 0.05,
        "motion_timeout_seconds": 0.2,
    }
    values.update(overrides)
    return SfBottomValveConfiguration(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("state", "target"),
    [
        (BottomValveState.CLOSED, 2559),
        (BottomValveState.OPEN, 3697),
    ],
)
def test_moves_to_confirmed_target_and_always_disables_torque(
    state: BottomValveState, target: int
) -> None:
    clock = FakeClock()
    session = FakeSession(positions=(2559, target))
    actuator = SfBottomValveActuator(
        configuration(),
        session_factory=lambda _: session,
        clock=clock,
        sleep=clock.sleep,
    )

    actuator.set_state(state)

    assert session.writes == [
        (2, REGISTERS["profile_acceleration"], 1),
        (2, REGISTERS["profile_velocity"], 20),
        (2, REGISTERS["goal_position"], 2559),
        (2, REGISTERS["torque_enable"], 1),
        (2, REGISTERS["goal_position"], target),
        (2, REGISTERS["torque_enable"], 0),
    ]
    assert session.closed


def test_rejects_wrong_model_before_torque_or_motion() -> None:
    session = FakeSession(model=999)
    actuator = SfBottomValveActuator(configuration(), session_factory=lambda _: session)

    with pytest.raises(HardwareCommandError, match="expected XL430 model"):
        actuator.set_state(BottomValveState.OPEN)

    assert session.writes == []
    assert session.closed


@pytest.mark.parametrize(
    ("session", "message"),
    [
        (FakeSession(mode=1), "operating mode must be 3"),
        (FakeSession(hardware_errors=(4,)), "hardware_error_status=4"),
        (FakeSession(maximum=3000), "outside 0..3000"),
    ],
)
def test_rejects_unsafe_device_state_before_torque(session: FakeSession, message: str) -> None:
    actuator = SfBottomValveActuator(configuration(), session_factory=lambda _: session)

    with pytest.raises(HardwareCommandError, match=message):
        actuator.set_state(BottomValveState.OPEN)

    assert session.writes == []
    assert session.closed


def test_hardware_error_during_motion_fails_and_disables_torque() -> None:
    session = FakeSession(
        positions=(2559,),
        hardware_errors=(0, 8),
    )
    actuator = SfBottomValveActuator(configuration(), session_factory=lambda _: session)

    with pytest.raises(HardwareCommandError, match="hardware_error_status=8"):
        actuator.set_state(BottomValveState.OPEN)

    assert session.writes[-1] == (2, REGISTERS["torque_enable"], 0)
    assert session.closed


def test_timeout_reports_last_position_and_disables_torque() -> None:
    clock = FakeClock()
    session = FakeSession(positions=(2559, 2600, 2700, 2800, 2900))
    actuator = SfBottomValveActuator(
        configuration(),
        session_factory=lambda _: session,
        clock=clock,
        sleep=clock.sleep,
    )

    with pytest.raises(HardwareCommandError, match="motion timeout") as caught:
        actuator.set_state(BottomValveState.OPEN)

    assert "last_present_position=" in str(caught.value)
    assert session.writes[-1] == (2, REGISTERS["torque_enable"], 0)
    assert session.closed


def test_write_failure_becomes_hardware_command_error_and_closes_session() -> None:
    session = FakeSession(fail_write=REGISTERS["goal_position"])
    actuator = SfBottomValveActuator(configuration(), session_factory=lambda _: session)

    with pytest.raises(HardwareCommandError, match="OPEN command failed"):
        actuator.set_state(BottomValveState.OPEN)

    assert session.closed


def test_cleanup_failure_after_success_is_reported_and_port_close_is_attempted() -> None:
    session = FakeSession(
        positions=(2559, 3697),
        fail_write=REGISTERS["torque_enable"],
        fail_close=True,
    )
    # Allow torque enable and fail only torque disable.
    original_write = session.write
    torque_writes = 0

    def fail_second_torque_write(device_id: int, register: Register, value: int) -> None:
        nonlocal torque_writes
        if register == REGISTERS["torque_enable"]:
            torque_writes += 1
            if torque_writes == 2:
                raise RuntimeError("scripted torque disable failure")
        fail_write = session.fail_write
        session.fail_write = None
        try:
            original_write(device_id, register, value)
        finally:
            session.fail_write = fail_write

    session.write = fail_second_torque_write  # type: ignore[method-assign]
    actuator = SfBottomValveActuator(configuration(), session_factory=lambda _: session)

    with pytest.raises(HardwareCommandError, match="cleanup failed"):
        actuator.set_state(BottomValveState.OPEN)

    assert session.closed


def test_rejects_overlapping_command_before_opening_second_session() -> None:
    session = FakeSession(positions=(2559, 3697))
    overlapping_error: HardwareCommandError | None = None
    actuator: SfBottomValveActuator

    def session_factory(_: SfBottomValveConfiguration) -> FakeSession:
        nonlocal overlapping_error
        try:
            actuator.set_state(BottomValveState.CLOSED)
        except HardwareCommandError as error:
            overlapping_error = error
        return session

    actuator = SfBottomValveActuator(configuration(), session_factory=session_factory)

    actuator.set_state(BottomValveState.OPEN)

    assert overlapping_error is not None
    assert str(overlapping_error) == "SF bottom valve command already active"
    assert session.closed


@pytest.mark.parametrize(
    "overrides",
    [
        {"port": ""},
        {"device_id": 253},
        {"closed_position": 100, "open_position": 100},
        {"position_tolerance": -1},
        {"motion_timeout_seconds": 0},
        {"poll_interval_seconds": -0.1},
    ],
)
def test_configuration_rejects_invalid_values(overrides: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        configuration(**overrides)
