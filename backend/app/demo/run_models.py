from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from app.demo.fluid_plan import FluidPlan
from app.demo.models import DemoConfiguration, DemoExecutionSettings
from app.demo.phases import RunPhase
from app.recipes.models import SavedRecipe, RecipeReadiness, phase_for_step


class RunStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    ABORTING = "ABORTING"
    ABORTED = "ABORTED"
    COMPLETED = "COMPLETED"
    FAULTED = "FAULTED"


class DemoRun(BaseModel):
    """Immutable state for one run; cross-run exclusivity belongs to an application service."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    configuration: DemoConfiguration | None = None
    execution_settings: DemoExecutionSettings | None = None
    fluid_plan: FluidPlan | None = None
    recipe: SavedRecipe | None = None
    recipe_readiness: RecipeReadiness | None = None
    recipe_step_index: StrictInt | None = Field(default=None, ge=0)
    status: RunStatus
    phase: RunPhase
    event_sequence: int

    @model_validator(mode="after")
    def validate_recipe_snapshot(self):
        if self.recipe is None:
            if any(value is None for value in (self.configuration, self.execution_settings, self.fluid_plan)):
                raise ValueError("Guided Demo requires its configuration, settings and fluid plan")
            if self.recipe_step_index is not None or self.recipe_readiness is not None:
                raise ValueError("recipe metadata requires a recipe snapshot")
        else:
            if any(value is not None for value in (self.configuration, self.execution_settings, self.fluid_plan)):
                raise ValueError("recipe runs cannot mix Guided Demo configuration")
            if self.recipe_step_index is None or self.recipe_readiness is None:
                raise ValueError("recipe run requires progress and fresh operator statement")
            count = len(self.recipe.definition.steps)
            if self.status is RunStatus.COMPLETED:
                if self.recipe_step_index != count or self.phase is not RunPhase.COMPLETED:
                    raise ValueError("completed recipe progress differs from its snapshot")
            elif self.status is RunStatus.CREATED:
                if self.recipe_step_index != 0 or self.phase is not RunPhase.READY:
                    raise ValueError("created recipe must be READY at step zero")
            elif self.recipe_step_index >= count or self.phase != phase_for_step(self.recipe.definition.steps[self.recipe_step_index]):
                raise ValueError("recipe phase differs from its current step")
        return self
