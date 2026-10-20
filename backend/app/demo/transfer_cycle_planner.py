from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from app.demo.calibration_models import PumpCalibration, PumpId


class TransferCycle(BaseModel):
    model_config = ConfigDict(frozen=True)

    cycle_number: StrictInt = Field(ge=1)
    volume_ml: Decimal

    @field_validator("volume_ml")
    @classmethod
    def validate_volume(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("cycle volume must be finite")
        if value <= 0:
            raise ValueError("cycle volume must be greater than zero")
        return value


class TransferCyclePlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    pump_id: PumpId
    requested_volume_ml: Decimal
    working_volume_ml: Decimal
    cycles: tuple[TransferCycle, ...]

    @field_validator("requested_volume_ml")
    @classmethod
    def validate_requested_volume(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("requested volume must be finite")
        if value < 0:
            raise ValueError("requested volume must not be negative")
        return value

    @field_validator("working_volume_ml")
    @classmethod
    def validate_working_volume(cls, value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("working volume must be finite")
        if value <= 0:
            raise ValueError("working volume must be greater than zero")
        return value

    @model_validator(mode="after")
    def validate_plan(self) -> TransferCyclePlan:
        expected_cycle_numbers = tuple(range(1, self.cycle_count + 1))
        actual_cycle_numbers = tuple(cycle.cycle_number for cycle in self.cycles)
        if actual_cycle_numbers != expected_cycle_numbers:
            raise ValueError("cycle numbers must be contiguous and one-based")

        if self.requested_volume_ml == 0:
            if self.cycles:
                raise ValueError("zero requested volume requires no cycles")
            return self

        if not self.cycles:
            raise ValueError("positive requested volume requires at least one cycle")
        if any(cycle.volume_ml > self.working_volume_ml for cycle in self.cycles):
            raise ValueError("cycle volume must not exceed working volume")
        if any(
            cycle.volume_ml != self.working_volume_ml for cycle in self.cycles[:-1]
        ):
            raise ValueError("every non-final cycle must equal working volume")
        if self.planned_volume_ml != self.requested_volume_ml:
            raise ValueError("planned volume must equal requested volume")
        return self

    @property
    def cycle_count(self) -> int:
        return len(self.cycles)

    @property
    def planned_volume_ml(self) -> Decimal:
        return sum((cycle.volume_ml for cycle in self.cycles), start=Decimal("0"))


def plan_transfer_cycles(
    requested_volume_ml: Decimal,
    calibration: PumpCalibration,
) -> TransferCyclePlan:
    if not isinstance(requested_volume_ml, Decimal):
        raise TypeError("requested_volume_ml must be a Decimal")
    if not requested_volume_ml.is_finite():
        raise ValueError("requested_volume_ml must be finite")
    if requested_volume_ml < 0:
        raise ValueError("requested_volume_ml must not be negative")

    full_cycle_count, remainder = divmod(
        requested_volume_ml, calibration.working_volume_ml
    )
    cycle_volumes = [calibration.working_volume_ml] * int(full_cycle_count)
    if remainder > 0:
        cycle_volumes.append(remainder)
    cycles = tuple(
        TransferCycle(cycle_number=index, volume_ml=volume)
        for index, volume in enumerate(cycle_volumes, start=1)
    )

    return TransferCyclePlan(
        pump_id=calibration.pump_id,
        requested_volume_ml=requested_volume_ml,
        working_volume_ml=calibration.working_volume_ml,
        cycles=cycles,
    )
