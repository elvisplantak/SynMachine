from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.demo.calibration_models import PumpCalibration, PumpId
from app.demo.transfer_cycle_planner import (
    TransferCycle,
    TransferCyclePlan,
    plan_transfer_cycles,
)


def calibration(
    pump_id: PumpId = PumpId.P1,
    working_volume_ml: str = "8",
    *,
    full_endpoint: int = 1234,
    empty_endpoint: int = 9876,
) -> PumpCalibration:
    return PumpCalibration(
        pump_id=pump_id,
        working_full_chamber_position_steps=full_endpoint,
        working_empty_chamber_position_steps=empty_endpoint,
        working_volume_ml=working_volume_ml,
    )


def cycle(number: int, volume_ml: str) -> TransferCycle:
    return TransferCycle(cycle_number=number, volume_ml=volume_ml)


def plan(
    requested_volume_ml: str,
    working_volume_ml: str,
    cycles: tuple[TransferCycle | dict[str, object], ...],
) -> TransferCyclePlan:
    return TransferCyclePlan(
        pump_id=PumpId.P1,
        requested_volume_ml=requested_volume_ml,
        working_volume_ml=working_volume_ml,
        cycles=cycles,
    )


@pytest.mark.parametrize(
    ("requested", "expected_volumes"),
    [
        ("3", (Decimal("3"),)),
        ("8", (Decimal("8"),)),
        ("16", (Decimal("8"), Decimal("8"))),
        ("17", (Decimal("8"), Decimal("8"), Decimal("1"))),
    ],
)
def test_basic_planning(requested: str, expected_volumes: tuple[Decimal, ...]) -> None:
    result = plan_transfer_cycles(Decimal(requested), calibration())

    assert tuple(item.volume_ml for item in result.cycles) == expected_volumes
    assert tuple(item.cycle_number for item in result.cycles) == tuple(
        range(1, len(expected_volumes) + 1)
    )


def test_exact_multiple_has_no_final_zero_cycle() -> None:
    result = plan_transfer_cycles(Decimal("24"), calibration())

    assert result.cycle_count == 3
    assert all(item.volume_ml == Decimal("8") for item in result.cycles)


def test_zero_requested_volume_creates_empty_no_op_plan() -> None:
    result = plan_transfer_cycles(Decimal("0"), calibration())

    assert result.cycles == ()
    assert result.cycle_count == 0
    assert result.planned_volume_ml == Decimal("0")


@pytest.mark.parametrize("pump_id", [PumpId.P1, PumpId.P2])
def test_calibration_identity_is_used_in_plan(pump_id: PumpId) -> None:
    result = plan_transfer_cycles(Decimal("3"), calibration(pump_id))

    assert result.pump_id is pump_id


def test_calibrated_working_volume_is_used_in_plan() -> None:
    result = plan_transfer_cycles(Decimal("7"), calibration(working_volume_ml="2.5"))

    assert result.working_volume_ml == Decimal("2.5")
    assert tuple(item.volume_ml for item in result.cycles) == (
        Decimal("2.5"),
        Decimal("2.5"),
        Decimal("2.0"),
    )


def test_fractional_decimal_values_split_and_sum_exactly() -> None:
    result = plan_transfer_cycles(
        Decimal("1.00"), calibration(working_volume_ml="0.30")
    )

    assert tuple(item.volume_ml for item in result.cycles) == (
        Decimal("0.30"),
        Decimal("0.30"),
        Decimal("0.30"),
        Decimal("0.10"),
    )
    assert result.planned_volume_ml == result.requested_volume_ml == Decimal("1.00")
    assert isinstance(result.planned_volume_ml, Decimal)
    assert all(isinstance(item.volume_ml, Decimal) for item in result.cycles)


def test_plan_output_contains_only_pump_identity_and_volume_information() -> None:
    result = plan_transfer_cycles(
        Decimal("5"),
        calibration(full_endpoint=2222, empty_endpoint=7777),
    )

    assert set(TransferCycle.model_fields) == {"cycle_number", "volume_ml"}
    assert set(TransferCyclePlan.model_fields) == {
        "pump_id",
        "requested_volume_ml",
        "working_volume_ml",
        "cycles",
    }
    assert result.model_dump() == {
        "pump_id": PumpId.P1,
        "requested_volume_ml": Decimal("5"),
        "working_volume_ml": Decimal("8"),
        "cycles": ({"cycle_number": 1, "volume_ml": Decimal("5")},),
    }


def test_json_round_trip_preserves_stored_decimal_values() -> None:
    original = plan_transfer_cycles(
        Decimal("1.00"), calibration(working_volume_ml="0.30")
    )

    restored = TransferCyclePlan.model_validate_json(original.model_dump_json())

    assert restored == original
    assert restored.requested_volume_ml.as_tuple() == original.requested_volume_ml.as_tuple()
    assert restored.working_volume_ml.as_tuple() == original.working_volume_ml.as_tuple()
    assert tuple(item.volume_ml.as_tuple() for item in restored.cycles) == tuple(
        item.volume_ml.as_tuple() for item in original.cycles
    )


@pytest.mark.parametrize(
    "requested",
    [Decimal("-0.01"), Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")],
)
def test_invalid_decimal_requested_volume_is_rejected(requested: Decimal) -> None:
    with pytest.raises((ValueError, ValidationError)):
        plan_transfer_cycles(requested, calibration())


@pytest.mark.parametrize("requested", [1, 1.0, True, "1"])
def test_non_decimal_requested_volume_is_rejected(requested: object) -> None:
    with pytest.raises(TypeError, match="requested_volume_ml must be a Decimal"):
        plan_transfer_cycles(requested, calibration())


@pytest.mark.parametrize(
    "volume_ml", ["0", "-0.01", "NaN", "Infinity", "-Infinity"]
)
def test_invalid_cycle_volume_is_rejected(volume_ml: str) -> None:
    with pytest.raises(ValidationError):
        cycle(1, volume_ml)


@pytest.mark.parametrize("cycle_number", [0, -1, True, 1.0, 1.5, "1"])
def test_invalid_cycle_number_is_rejected(cycle_number: object) -> None:
    with pytest.raises(ValidationError):
        TransferCycle(cycle_number=cycle_number, volume_ml="1")


def test_positive_requested_volume_requires_cycles() -> None:
    with pytest.raises(ValidationError, match="requires at least one cycle"):
        plan("1", "8", ())


def test_zero_requested_volume_requires_empty_cycles() -> None:
    with pytest.raises(ValidationError, match="requires no cycles"):
        plan("0", "8", (cycle(1, "1"),))


@pytest.mark.parametrize(
    "cycles",
    [
        ({"cycle_number": 0, "volume_ml": "1"},),
        (cycle(1, "8"), cycle(3, "1")),
        (cycle(1, "8"), cycle(1, "1")),
    ],
)
def test_cycle_numbers_must_be_contiguous_and_one_based(
    cycles: tuple[TransferCycle | dict[str, object], ...],
) -> None:
    with pytest.raises(ValidationError):
        plan("9", "8", cycles)


def test_cycle_volume_must_not_exceed_working_volume() -> None:
    with pytest.raises(ValidationError, match="must not exceed working volume"):
        plan("9", "8", (cycle(1, "9"),))


def test_non_final_partial_cycle_is_rejected() -> None:
    with pytest.raises(ValidationError, match="non-final cycle"):
        plan("9", "8", (cycle(1, "1"), cycle(2, "8")))


@pytest.mark.parametrize(
    ("requested_volume_ml", "cycles"),
    [
        ("9", (cycle(1, "8"),)),
        ("8", (cycle(1, "8"), cycle(2, "1"))),
    ],
)
def test_planned_volume_must_equal_requested_volume(
    requested_volume_ml: str,
    cycles: tuple[TransferCycle, ...],
) -> None:
    with pytest.raises(ValidationError, match="planned volume"):
        plan(requested_volume_ml, "8", cycles)


@pytest.mark.parametrize(
    "working_volume_ml", ["0", "-1", "NaN", "Infinity", "-Infinity"]
)
def test_invalid_plan_working_volume_is_rejected(working_volume_ml: str) -> None:
    with pytest.raises(ValidationError):
        plan("0", working_volume_ml, ())


def test_transfer_cycle_is_immutable() -> None:
    item = cycle(1, "1")

    with pytest.raises(ValidationError):
        item.volume_ml = Decimal("2")


def test_transfer_cycle_plan_is_immutable_and_stores_tuple() -> None:
    result = plan_transfer_cycles(Decimal("1"), calibration())

    assert isinstance(result.cycles, tuple)
    with pytest.raises(ValidationError):
        result.cycles = ()
