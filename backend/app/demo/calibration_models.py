from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator


class PumpId(StrEnum):
    P1 = "P1"
    P2 = "P2"


class PumpCalibration(BaseModel):
    model_config = ConfigDict(frozen=True)

    pump_id: PumpId
    working_full_chamber_position_steps: StrictInt = Field(ge=0)
    working_empty_chamber_position_steps: StrictInt = Field(ge=0)
    working_volume_ml: Decimal

    @field_validator("working_volume_ml")
    @classmethod
    def validate_working_volume(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("working volume must be finite")
        if value <= 0:
            raise ValueError("working volume must be greater than zero")
        return value

    @model_validator(mode="after")
    def validate_working_endpoints(self) -> Self:
        if (
            self.working_full_chamber_position_steps
            >= self.working_empty_chamber_position_steps
        ):
            raise ValueError(
                "working full chamber position must be less than "
                "working empty chamber position"
            )
        return self

    @property
    def working_stroke_steps(self) -> int:
        return (
            self.working_empty_chamber_position_steps
            - self.working_full_chamber_position_steps
        )

    @property
    def steps_per_ml(self) -> Decimal:
        return Decimal(self.working_stroke_steps) / self.working_volume_ml


class PumpCalibrationSet(BaseModel):
    model_config = ConfigDict(frozen=True)

    p1: PumpCalibration
    p2: PumpCalibration

    @model_validator(mode="after")
    def validate_pump_identities(self) -> Self:
        if self.p1.pump_id is not PumpId.P1:
            raise ValueError("p1 calibration must have pump_id P1")
        if self.p2.pump_id is not PumpId.P2:
            raise ValueError("p2 calibration must have pump_id P2")
        return self
