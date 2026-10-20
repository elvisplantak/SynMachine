from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.demo.calibration_models import PumpCalibration, PumpCalibrationSet, PumpId


def calibration(pump_id: PumpId, **overrides: object) -> PumpCalibration:
    values: dict[str, object] = {
        "pump_id": pump_id,
        "working_full_chamber_position_steps": 1234,
        "working_empty_chamber_position_steps": 9876,
        "working_volume_ml": "4.321",
    }
    values.update(overrides)
    return PumpCalibration(**values)


def calibration_set() -> PumpCalibrationSet:
    return PumpCalibrationSet(
        p1=calibration(PumpId.P1),
        p2=calibration(
            PumpId.P2,
            working_full_chamber_position_steps=2345,
            working_empty_chamber_position_steps=8765,
            working_volume_ml="3.21",
        ),
    )


def test_valid_independent_p1_calibration_preserves_values() -> None:
    pump = calibration(PumpId.P1)

    assert pump.pump_id is PumpId.P1
    assert pump.working_full_chamber_position_steps == 1234
    assert pump.working_empty_chamber_position_steps == 9876
    assert pump.working_volume_ml == Decimal("4.321")


def test_valid_independent_p2_calibration_preserves_values() -> None:
    pump = calibration(
        PumpId.P2,
        working_full_chamber_position_steps=2468,
        working_empty_chamber_position_steps=9753,
        working_volume_ml="5.678900",
    )

    assert pump.pump_id is PumpId.P2
    assert pump.working_full_chamber_position_steps == 2468
    assert pump.working_empty_chamber_position_steps == 9753
    assert pump.working_volume_ml == Decimal("5.678900")
    assert pump.working_volume_ml.as_tuple().exponent == -6


def test_pump_calibration_is_immutable() -> None:
    pump = calibration(PumpId.P1)

    with pytest.raises(ValidationError):
        pump.working_volume_ml = Decimal("1")


def test_pump_calibration_set_is_immutable() -> None:
    calibrations = calibration_set()

    with pytest.raises(ValidationError):
        calibrations.p1 = calibration(PumpId.P1, working_volume_ml="1")


def test_derived_working_stroke_steps() -> None:
    pump = calibration(
        PumpId.P1,
        working_full_chamber_position_steps=1350,
        working_empty_chamber_position_steps=9750,
    )

    assert pump.working_stroke_steps == 8400


def test_derived_steps_per_ml_uses_exact_decimal_arithmetic() -> None:
    pump = calibration(
        PumpId.P2,
        working_full_chamber_position_steps=1500,
        working_empty_chamber_position_steps=9500,
        working_volume_ml="4",
    )

    assert pump.steps_per_ml == Decimal("2000")
    assert isinstance(pump.steps_per_ml, Decimal)


@pytest.mark.parametrize("working_volume_ml", ["0", "-0.001", "NaN", "Infinity"])
def test_invalid_working_volume_is_rejected(working_volume_ml: str) -> None:
    with pytest.raises(ValidationError):
        calibration(PumpId.P1, working_volume_ml=working_volume_ml)


@pytest.mark.parametrize(
    "field",
    [
        "working_full_chamber_position_steps",
        "working_empty_chamber_position_steps",
    ],
)
def test_negative_step_positions_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        calibration(PumpId.P1, **{field: -1})


@pytest.mark.parametrize(
    ("working_full_chamber_position_steps", "working_empty_chamber_position_steps"),
    [(5000, 5000), (5001, 5000)],
)
def test_equal_or_reversed_endpoints_are_rejected(
    working_full_chamber_position_steps: int,
    working_empty_chamber_position_steps: int,
) -> None:
    with pytest.raises(ValidationError):
        calibration(
            PumpId.P1,
            working_full_chamber_position_steps=working_full_chamber_position_steps,
            working_empty_chamber_position_steps=working_empty_chamber_position_steps,
        )


@pytest.mark.parametrize(
    "field",
    [
        "working_full_chamber_position_steps",
        "working_empty_chamber_position_steps",
    ],
)
def test_boolean_step_positions_are_rejected(field: str) -> None:
    with pytest.raises(ValidationError):
        calibration(PumpId.P1, **{field: True})


def test_p1_field_rejects_p2_identity() -> None:
    with pytest.raises(ValidationError, match="p1 calibration must have pump_id P1"):
        PumpCalibrationSet(p1=calibration(PumpId.P2), p2=calibration(PumpId.P2))


def test_p2_field_rejects_p1_identity() -> None:
    with pytest.raises(ValidationError, match="p2 calibration must have pump_id P2"):
        PumpCalibrationSet(p1=calibration(PumpId.P1), p2=calibration(PumpId.P1))


@pytest.mark.parametrize("pump_id", [PumpId.P1, PumpId.P2])
def test_duplicate_pump_identities_are_rejected(pump_id: PumpId) -> None:
    with pytest.raises(ValidationError):
        PumpCalibrationSet(p1=calibration(pump_id), p2=calibration(pump_id))


def test_json_round_trip_preserves_all_entered_values_exactly() -> None:
    original = calibration_set()

    restored = PumpCalibrationSet.model_validate_json(original.model_dump_json())

    assert restored == original
    assert restored.p1.working_volume_ml.as_tuple() == original.p1.working_volume_ml.as_tuple()
    assert restored.p2.working_volume_ml.as_tuple() == original.p2.working_volume_ml.as_tuple()
