"""Versioned logical recipes; no firmware details or arbitrary commands."""

from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator

from app.demo.phases import RunPhase


class RecipeModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


PositiveAmount = Annotated[Decimal, Field(gt=0, allow_inf_nan=False)]


class AddStep(RecipeModel):
    kind: Literal["ADD"]
    source: Literal["B1", "B2", "S"]
    volume_ml: PositiveAmount


class TransferStep(RecipeModel):
    kind: Literal["TRANSFER"]
    route: Literal["REACTOR_TO_SF", "SF_TO_COLUMN"]
    volume_ml: PositiveAmount


class WaitStep(RecipeModel):
    kind: Literal["WAIT"]
    duration_seconds: PositiveAmount


class SfMixStep(RecipeModel):
    kind: Literal["SF_MIX"]
    duration_seconds: PositiveAmount


class SfSettleStep(RecipeModel):
    kind: Literal["SF_SETTLE"]
    duration_seconds: PositiveAmount


class CollectStep(RecipeModel):
    kind: Literal["COLLECT"]
    # Existing command planner/firmware support positions 1..40.
    fraction_count: StrictInt = Field(ge=1, le=40)
    fraction_duration_seconds: PositiveAmount


RecipeStep = Annotated[
    AddStep | TransferStep | WaitStep | SfMixStep | SfSettleStep | CollectStep,
    Field(discriminator="kind"),
]


class SourceLabels(RecipeModel):
    B1: str = Field(default="B1", max_length=120)
    B2: str = Field(default="B2", max_length=120)
    S: str = Field(default="S", max_length=120)


class RecipeDefinition(RecipeModel):
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    sources: SourceLabels = Field(default_factory=SourceLabels)
    # Software size limit, not a physical capacity.
    steps: tuple[RecipeStep, ...] = Field(min_length=1, max_length=100)

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("unsupported recipe schema version")
        return value

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value):
        if not value.strip():
            raise ValueError("recipe name must not be blank")
        return value.strip()


class SavedRecipe(RecipeModel):
    recipe_id: str = Field(min_length=1)
    revision: StrictInt = Field(ge=1)
    definition: RecipeDefinition


class RecipeReadiness(RecipeModel):
    operator: str = Field(min_length=1, max_length=120)
    evidence_note: str = Field(min_length=1, max_length=2000)
    sources_match_recipe: Literal[True]
    reactor_sf_column_empty_clean: Literal[True]
    waste_capacity_available: Literal[True]
    collection_tubes_ready: Literal[True]

    @field_validator(
        "sources_match_recipe",
        "reactor_sf_column_empty_clean",
        "waste_capacity_available",
        "collection_tubes_ready",
        mode="before",
    )
    @classmethod
    def exact_confirmation(cls, value):
        if value is not True:
            raise ValueError("explicit true confirmation is required")
        return value

    @field_validator("operator", "evidence_note")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("fresh operator statement must not be blank")
        return value.strip()


def phase_for_step(step: RecipeStep) -> RunPhase:
    if isinstance(step, AddStep):
        return (
            RunPhase.P1_TRANSFER_S_TO_REACTOR
            if step.source == "S"
            else RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR
        )
    if isinstance(step, TransferStep):
        return (
            RunPhase.P2_TRANSFER_REACTOR_TO_SF
            if step.route == "REACTOR_TO_SF"
            else RunPhase.P2_TRANSFER_SF_TO_COLUMN
        )
    return {
        "WAIT": RunPhase.REACTION_HOLD,
        "SF_MIX": RunPhase.SF_MIXING,
        "SF_SETTLE": RunPhase.SF_SETTLING,
        "COLLECT": RunPhase.COLUMN_FRACTION_COLLECTION,
    }[step.kind]


def validate_recipe_flow(definition: RecipeDefinition) -> dict[str, Decimal]:
    """Nominal inventory only. Collection is time based, no measured volume."""
    amounts = {name: Fraction(0) for name in ("REACTOR", "SF", "COLUMN")}
    for index, step in enumerate(definition.steps):
        prefix = f"Step {index + 1}: "
        if isinstance(step, AddStep):
            amounts["REACTOR"] += Fraction(step.volume_ml)
        elif isinstance(step, TransferStep):
            source, target = step.route.split("_TO_")
            if Fraction(step.volume_ml) > amounts[source]:
                raise ValueError(
                    prefix + f"requested transfer exceeds configured contents of {source}"
                )
            amounts[source] -= Fraction(step.volume_ml)
            amounts[target] += Fraction(step.volume_ml)
        elif isinstance(step, (SfMixStep, SfSettleStep)):
            if amounts["SF"] <= 0:
                raise ValueError(prefix + "SF has no configured contents")
        elif isinstance(step, CollectStep):
            if amounts["COLUMN"] <= 0:
                raise ValueError(prefix + "Column has no configured contents")
            if index != len(definition.steps) - 1:
                raise ValueError(
                    prefix + "timed collection must be the final step; remaining volume is unknown"
                )
    with localcontext() as context:
        context.prec = max(
            28, *(len(str(v.numerator)) + len(str(v.denominator)) + 2 for v in amounts.values())
        )
        return {name: Decimal(v.numerator) / Decimal(v.denominator) for name, v in amounts.items()}
