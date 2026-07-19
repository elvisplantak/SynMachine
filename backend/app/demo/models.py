from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)


class AdditionOrder(StrEnum):
    B1_THEN_B2 = "B1_THEN_B2"
    B2_THEN_B1 = "B2_THEN_B1"


class DemoExecutionSettings(BaseModel):
    """Immutable Service settings snapshot for one Guided Demo run."""

    model_config = ConfigDict(frozen=True)

    sf_settling_duration_seconds: Decimal
    fraction_count: int = Field(ge=1)
    fraction_duration_seconds: Decimal

    @field_validator("sf_settling_duration_seconds", "fraction_duration_seconds")
    @classmethod
    def validate_duration(cls, value: Decimal, info: ValidationInfo) -> Decimal:
        if not value.is_finite():
            raise ValueError("duration must be finite")
        if info.field_name == "sf_settling_duration_seconds" and value < 0:
            raise ValueError("SF settling duration must not be negative")
        if info.field_name == "fraction_duration_seconds" and value <= 0:
            raise ValueError("fraction duration must be greater than zero")
        return value


class DemoConfiguration(BaseModel):
    """Logically validated Guided Demo settings, not physical safety limits."""

    model_config = ConfigDict(frozen=True)

    b1_ratio_percent: Decimal
    total_mixture_volume_ml: Decimal
    combined_b1_b2_volume_ml: Decimal
    addition_order: AdditionOrder
    addition_speed_command_percent: Decimal
    reactor_mixing_command_percent: Decimal
    sf_mixing_command_percent: Decimal
    simulated_target_temperature_c: Decimal
    reaction_duration_seconds: Decimal
    delay_between_additions_seconds: Decimal

    @field_validator("b1_ratio_percent")
    @classmethod
    def validate_ratio(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or not Decimal("0") <= value <= Decimal("100"):
            raise ValueError("B1 ratio must be between 0 and 100 percent")
        return value

    @field_validator(
        "addition_speed_command_percent",
        "reactor_mixing_command_percent",
        "sf_mixing_command_percent",
    )
    @classmethod
    def validate_command_percent(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or not Decimal("0") <= value <= Decimal("100"):
            raise ValueError("command percentage must be between 0 and 100")
        return value

    @field_validator("total_mixture_volume_ml", "combined_b1_b2_volume_ml")
    @classmethod
    def validate_positive_volume(cls, value: Decimal) -> Decimal:
        if not value.is_finite() or value <= 0:
            raise ValueError("configured volume must be greater than zero")
        return value

    @field_validator(
        "simulated_target_temperature_c",
        "reaction_duration_seconds",
        "delay_between_additions_seconds",
    )
    @classmethod
    def validate_finite_value(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("value must be finite")
        return value

    @field_validator("reaction_duration_seconds", "delay_between_additions_seconds")
    @classmethod
    def validate_non_negative_duration(cls, value: Decimal) -> Decimal:
        if value < 0:
            raise ValueError("duration must not be negative")
        return value

    @model_validator(mode="after")
    def validate_combined_volume(self) -> Self:
        if self.combined_b1_b2_volume_ml > self.total_mixture_volume_ml:
            raise ValueError("combined B1+B2 volume must not exceed total mixture volume")
        return self
