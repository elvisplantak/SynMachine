from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.demo.models import AdditionOrder, DemoConfiguration


class FluidPlan(BaseModel):
    """Immutable configured-volume plan; values are not delivery measurements."""

    model_config = ConfigDict(frozen=True)

    b1_configured_volume_ml: Decimal
    b2_configured_volume_ml: Decimal
    s_configured_volume_ml: Decimal
    total_configured_volume_ml: Decimal
    combined_b1_b2_configured_volume_ml: Decimal
    b1_b2_volume_ratio: tuple[Decimal, Decimal]
    addition_order: AdditionOrder
    first_liquid: str
    second_liquid: str


def build_fluid_plan(configuration: DemoConfiguration) -> FluidPlan:
    ratio_fraction = configuration.b1_ratio_percent / Decimal("100")
    b1_volume = configuration.combined_b1_b2_volume_ml * ratio_fraction
    b2_volume = configuration.combined_b1_b2_volume_ml - b1_volume
    solvent_volume = (
        configuration.total_mixture_volume_ml - configuration.combined_b1_b2_volume_ml
    )
    first_liquid = "B1" if configuration.addition_order is AdditionOrder.B1_THEN_B2 else "B2"
    second_liquid = "B2" if first_liquid == "B1" else "B1"

    return FluidPlan(
        b1_configured_volume_ml=b1_volume,
        b2_configured_volume_ml=b2_volume,
        s_configured_volume_ml=solvent_volume,
        total_configured_volume_ml=b1_volume + b2_volume + solvent_volume,
        combined_b1_b2_configured_volume_ml=configuration.combined_b1_b2_volume_ml,
        b1_b2_volume_ratio=(
            configuration.b1_ratio_percent,
            Decimal("100") - configuration.b1_ratio_percent,
        ),
        addition_order=configuration.addition_order,
        first_liquid=first_liquid,
        second_liquid=second_liquid,
    )
