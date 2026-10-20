from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.demo.fluid_plan import build_fluid_plan
from app.demo.models import AdditionOrder, DemoConfiguration


def configuration(**overrides: object) -> DemoConfiguration:
    values: dict[str, object] = {
        "b1_ratio_percent": "40",
        "total_mixture_volume_ml": "10",
        "combined_b1_b2_volume_ml": "4",
        "addition_order": AdditionOrder.B1_THEN_B2,
        "addition_speed_command_percent": "50",
        "reactor_mixing_command_percent": "60",
        "sf_mixing_command_percent": "40",
        "simulated_target_temperature_c": "25",
        "reaction_duration_seconds": "600",
        "delay_between_additions_seconds": "5",
    }
    values.update(overrides)
    return DemoConfiguration(**values)


def test_builds_40_60_fluid_plan_and_solvent_volume() -> None:
    plan = build_fluid_plan(configuration())

    assert plan.b1_configured_volume_ml == Decimal("1.6")
    assert plan.b2_configured_volume_ml == Decimal("2.4")
    assert plan.s_configured_volume_ml == Decimal("6")
    assert plan.b1_b2_volume_ratio == (Decimal("40"), Decimal("60"))


def test_builds_51_49_fluid_plan() -> None:
    plan = build_fluid_plan(configuration(b1_ratio_percent="51"))

    assert plan.b1_configured_volume_ml == Decimal("2.04")
    assert plan.b2_configured_volume_ml == Decimal("1.96")


def test_addition_order_changes_liquid_order_only() -> None:
    b1_first = build_fluid_plan(configuration())
    b2_first = build_fluid_plan(configuration(addition_order=AdditionOrder.B2_THEN_B1))

    assert (b2_first.first_liquid, b2_first.second_liquid) == ("B2", "B1")
    assert b2_first.b1_configured_volume_ml == b1_first.b1_configured_volume_ml
    assert b2_first.b2_configured_volume_ml == b1_first.b2_configured_volume_ml
    assert b2_first.s_configured_volume_ml == b1_first.s_configured_volume_ml


def test_preserves_configured_total_volume() -> None:
    plan = build_fluid_plan(
        configuration(total_mixture_volume_ml="10.01", combined_b1_b2_volume_ml="4.03")
    )

    assert (
        plan.b1_configured_volume_ml
        + plan.b2_configured_volume_ml
        + plan.s_configured_volume_ml
        == plan.total_configured_volume_ml
        == Decimal("10.01")
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("total_mixture_volume_ml", "0"),
        ("total_mixture_volume_ml", "-1"),
        ("combined_b1_b2_volume_ml", "0"),
        ("combined_b1_b2_volume_ml", "-1"),
    ],
)
def test_rejects_zero_or_negative_relevant_volume(field: str, value: str) -> None:
    with pytest.raises(ValidationError):
        configuration(**{field: value})


def test_rejects_combined_volume_greater_than_total() -> None:
    with pytest.raises(ValidationError):
        configuration(total_mixture_volume_ml="3", combined_b1_b2_volume_ml="4")


@pytest.mark.parametrize("ratio", ["-1", "101"])
def test_rejects_ratio_outside_frontend_range(ratio: str) -> None:
    with pytest.raises(ValidationError):
        configuration(b1_ratio_percent=ratio)


def test_fluid_plan_is_immutable() -> None:
    plan = build_fluid_plan(configuration())

    with pytest.raises(ValidationError):
        plan.b1_configured_volume_ml = Decimal("2")
