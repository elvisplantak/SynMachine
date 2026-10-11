import os
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, Protocol

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.demo.application_service import (
    GuidedDemoApplicationError,
    GuidedDemoApplicationService,
)
from app.demo.hardware_contract import BottomValveState, HardwareCommandError
from app.demo.lifecycle import LifecycleTransitionError
from app.demo.machine_lifecycle import MachineTransitionError
from app.demo.machine_models import MachineSnapshot
from app.demo.models import DemoConfiguration, DemoExecutionSettings
from app.demo.run_models import DemoRun
from app.recipes.models import RecipeDefinition, RecipeReadiness
from app.recipes.planning import preview_recipe
from app.recipes.store import RecipeStore, RecipeConflict
from app.demo.events import DomainEvent
from app.demo.machine_events import MachineEvent
from app.demo.maintenance_plan import MaintenanceKind
from app.hardware.owned_maintenance import MaintenanceReadiness
from app.hardware.operator_current_input import OperatorCredentialRejected, OperatorReferenceInput
from app.hardware.owned_application_execution import OwnedApplicationExecution, ExecutionAccepted
from app.hardware.simulated_p1_runner import SimulationBlocked
from app.hardware.runtime_configuration import (
    ArduinoRuntime,
    build_arduino_runtime_from_environment,
    build_sf_bottom_valve_from_environment,
)
from app.hardware.arduino_command_journal import (
    ArduinoCommandIdentityConflictError,
    ArduinoCommandJournalEntry,
)
from app.hardware.arduino_serial import ArduinoSerialError
from app.hardware.sf_bottom_valve import SfBottomValveControl
from app.hardware.owned_hardware import OwnedHardware
from app.persistence.sqlite_store import PersistenceConflictError, SQLiteStore
from app.startup_bootstrap import bootstrap_process_startup

API_PREFIX = "/api/v1"
DATABASE_PATH_ENVIRONMENT_VARIABLE = "LABFORGE_DATABASE_PATH"
DEFAULT_DATABASE_PATH = Path("labforge.db")


class CommandRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value


class CreateRunRequest(CommandRequest):
    run_id: str
    configuration: DemoConfiguration
    execution_settings: DemoExecutionSettings

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("run_id must not be empty")
        return value


class SaveRecipeRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    definition: RecipeDefinition
    expected_revision: int = Field(default=0, ge=0, strict=True)


class ExecuteRecipeRequest(CommandRequest):
    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=1, strict=True)
    readiness: RecipeReadiness


class MaintenanceCommandRequest(CommandRequest):
    run_id: str | None = None
    readiness: MaintenanceReadiness | None = None


class RunMachineResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    run: DemoRun
    machine: MachineSnapshot | None


class SfBottomValveCommandRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: BottomValveState


class SfBottomValveCommandResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    state: BottomValveState
    position_confirmed: bool


class ArduinoCommandExecutor(Protocol):
    def execute(
        self,
        *,
        phase_execution_id: str,
        operation_command_id: str,
        command: str,
        arguments: dict[str, str | int | bool],
    ) -> ArduinoCommandJournalEntry: ...


class PumpServiceCommandRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    phase_execution_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")]
    operation_command_id: Annotated[
        str,
        Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
    ]
    pump: Literal["P1", "P2"]
    command: Literal["HOME", "MOVE_ABSOLUTE_STEPS"]
    target_steps: int | None = None
    safe_route_confirmed: Literal[True]

    @model_validator(mode="after")
    def validate_command_arguments(self) -> "PumpServiceCommandRequest":
        if self.command == "HOME" and self.target_steps is not None:
            raise ValueError("HOME must not include target_steps")
        if self.command == "MOVE_ABSOLUTE_STEPS" and not (
            self.target_steps is not None and 1 <= self.target_steps <= 20500
        ):
            raise ValueError("MOVE_ABSOLUTE_STEPS requires target_steps in 1..20500")
        return self


class PumpServiceCommandResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    operation_command_id: str
    state: str
    result: dict[str, str | int | bool] | None
    error_code: str | None
    execution_started: bool | None


class ValveServiceCommandRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    phase_execution_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")]
    operation_command_id: Annotated[
        str,
        Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
    ]
    valve: Literal["V1", "V2", "V3", "V4", "V5", "V6", "V7", "V8"]
    command: Literal["HOME", "SET_POSITION"]
    position_degrees: Literal[0, 90, 180] | None = None

    @model_validator(mode="after")
    def validate_command_arguments(self) -> "ValveServiceCommandRequest":
        if self.command == "HOME" and self.position_degrees is not None:
            raise ValueError("HOME must not include position_degrees")
        if self.command == "SET_POSITION" and self.position_degrees is None:
            raise ValueError("SET_POSITION requires position_degrees")
        return self


class ColumnBottomValveServiceCommandRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    phase_execution_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")]
    operation_command_id: Annotated[
        str,
        Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
    ]
    command: Literal["HOME", "SET_POSITION"]
    position_degrees: Literal[4, 94] | None = None

    @model_validator(mode="after")
    def validate_command_arguments(self) -> "ColumnBottomValveServiceCommandRequest":
        if self.command == "HOME" and self.position_degrees is not None:
            raise ValueError("HOME must not include position_degrees")
        if self.command == "SET_POSITION" and self.position_degrees is None:
            raise ValueError("SET_POSITION requires position_degrees")
        return self


class CarouselServiceCommandRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    phase_execution_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")]
    operation_command_id: Annotated[
        str,
        Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
    ]
    command: Literal["SET_REFERENCE", "MOVE_TO_POSITION"]
    position: Annotated[int, Field(ge=1, le=40)]
    manual_alignment_confirmed: Literal[True] | None = None
    column_bottom_valve_closed_confirmed: Literal[True] | None = None

    @model_validator(mode="after")
    def validate_command_boundary(self) -> "CarouselServiceCommandRequest":
        if self.command == "SET_REFERENCE":
            if self.manual_alignment_confirmed is not True:
                raise ValueError("SET_REFERENCE requires manual_alignment_confirmed=true")
            if self.column_bottom_valve_closed_confirmed is not None:
                raise ValueError(
                    "SET_REFERENCE must not include column_bottom_valve_closed_confirmed"
                )
        else:
            if self.column_bottom_valve_closed_confirmed is not True:
                raise ValueError(
                    "MOVE_TO_POSITION requires column_bottom_valve_closed_confirmed=true"
                )
            if self.manual_alignment_confirmed is not None:
                raise ValueError("MOVE_TO_POSITION must not include manual_alignment_confirmed")
        return self


class SfMixerServiceCommandRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    phase_execution_id: Annotated[str, Field(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")]
    operation_command_id: Annotated[
        str,
        Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
    ]
    command: Literal["START", "STOP"]


def _configured_database_path(database_path: str | Path | None) -> Path:
    if database_path is not None:
        return Path(database_path)
    return Path(os.environ.get(DATABASE_PATH_ENVIRONMENT_VARIABLE, DEFAULT_DATABASE_PATH))


def create_app(
    database_path: str | Path | None = None,
    *,
    recipe_database_path: str | Path | None = None,
    startup_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sf_bottom_valve: SfBottomValveControl | None = None,
    arduino_commands: ArduinoCommandExecutor | None = None,
    arduino_runtime: ArduinoRuntime | None = None,
    owned_hardware: OwnedHardware | None = None,
    application_execution: OwnedApplicationExecution | None = None,
) -> FastAPI:
    if application_execution is not None:
        if any(value is not None for value in (
            sf_bottom_valve, arduino_commands, arduino_runtime, owned_hardware
        )):
            raise ValueError("application execution cannot be mixed with other hardware compositions")
        if (database_path is not None
            and Path(database_path).resolve() != application_execution.bundle.lifecycle_path.resolve()):
            raise ValueError("application lifecycle path differs from the owned bundle")
        database_path = application_execution.bundle.lifecycle_path
        arduino_commands = application_execution
    if owned_hardware is not None:
        if any(value is not None for value in (sf_bottom_valve, arduino_commands, arduino_runtime)):
            raise ValueError("owned hardware cannot be mixed with unguarded hardware arguments")
        sf_bottom_valve = owned_hardware.sf_service
        arduino_commands = owned_hardware.arduino_service
    configured_database_path = _configured_database_path(database_path)
    recipe_path = (Path(recipe_database_path) if recipe_database_path is not None
                   else configured_database_path.with_name(configured_database_path.name + ".recipes.sqlite3"))

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # LabForge v1 startup reconciliation assumes one FastAPI worker.
        occurred_at = startup_clock()
        if application_execution is not None:
            application.state.process_startup = application_execution.start(occurred_at)
        else:
            with SQLiteStore(configured_database_path) as store:
                application.state.process_startup = bootstrap_process_startup(store, occurred_at)
        if arduino_runtime is not None:
            arduino_runtime.start()
        try:
            yield
        finally:
            if application_execution is not None:
                application_execution.close(startup_clock())
            if arduino_runtime is not None:
                arduino_runtime.close()

    application = FastAPI(title="LabForge backend", lifespan=lifespan)

    def get_store() -> Iterator[SQLiteStore]:
        if application_execution is not None:
            with application_execution.store() as store:
                yield store
        else:
            with SQLiteStore(configured_database_path) as store:
                yield store

    Store = Annotated[SQLiteStore, Depends(get_store)]

    @application.exception_handler(RecipeConflict)
    @application.exception_handler(GuidedDemoApplicationError)
    @application.exception_handler(LifecycleTransitionError)
    @application.exception_handler(MachineTransitionError)
    @application.exception_handler(PersistenceConflictError)
    @application.exception_handler(SimulationBlocked)
    async def handle_conflict(
        request: Request,
        error: GuidedDemoApplicationError
        | LifecycleTransitionError
        | MachineTransitionError
        | PersistenceConflictError,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(error)},
        )

    def preview_uvp(definition):
        try:
            return (application_execution.preview_recipe(definition) if application_execution
                    else preview_recipe(definition))
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @application.get(f"{API_PREFIX}/recipes")
    def list_recipes():
        with RecipeStore(recipe_path) as recipes:
            return recipes.list()

    @application.post(f"{API_PREFIX}/recipes/preview")
    def preview_recipe_request(definition: RecipeDefinition):
        return preview_uvp(definition)

    @application.post(f"{API_PREFIX}/recipes")
    def create_recipe(command: SaveRecipeRequest):
        if command.expected_revision != 0:
            raise RecipeConflict("a new recipe requires expected revision zero")
        with RecipeStore(recipe_path) as recipes:
            return recipes.save(command.definition)

    @application.get(f"{API_PREFIX}/recipes/{{recipe_id}}")
    def read_recipe(recipe_id: str):
        with RecipeStore(recipe_path) as recipes:
            recipe = recipes.load(recipe_id)
        if recipe is None:
            raise HTTPException(status_code=404, detail="Recipe not found")
        return recipe

    @application.post(f"{API_PREFIX}/recipes/{{recipe_id}}")
    def revise_recipe(recipe_id: str, command: SaveRecipeRequest):
        with RecipeStore(recipe_path) as recipes:
            if recipes.load(recipe_id) is None:
                raise HTTPException(status_code=404, detail="Recipe not found")
            return recipes.save(command.definition, recipe_id=recipe_id,
                expected_revision=command.expected_revision)

    @application.post(f"{API_PREFIX}/recipes/{{recipe_id}}/execute", status_code=202)
    def execute_recipe(recipe_id: str, command: ExecuteRecipeRequest):
        if application_execution is None:
            raise HTTPException(status_code=503, detail="owned application execution is not configured")
        recipe = read_recipe(recipe_id)
        if recipe.revision != command.expected_revision:
            raise RecipeConflict("recipe revision changed; review the latest version before running")
        preview_uvp(recipe.definition)
        application_execution.create_recipe_run(command.run_id, recipe,
            command.readiness, command.occurred_at)
        return application_execution.start_run(command.run_id, command.occurred_at,
            recipe_authorized=True)

    def require_domain_mode():
        if application_execution is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="owned application execution requires command-result resolution",
            )

    @application.get(f"{API_PREFIX}/execution", summary="Read application execution activity")
    def read_execution():
        if application_execution is None:
            raise HTTPException(status_code=503, detail="owned application execution is not configured")
        return application_execution.status()

    def operator_credential(authorization):
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Operator authorization required")
        return authorization[7:]

    @application.post(f"{API_PREFIX}/execution/current-input/{{request_id}}")
    def submit_current_input(request_id: str, references: OperatorReferenceInput,
                             authorization: Annotated[str | None, Header()] = None):
        if application_execution is None:
            raise HTTPException(status_code=503, detail="owned application execution is not configured")
        try:
            return application_execution.submit_current_input(
                request_id, references, operator_credential(authorization)
            )
        except OperatorCredentialRejected as error:
            raise HTTPException(status_code=401, detail=str(error)) from None

    @application.post(f"{API_PREFIX}/execution/current-input/{{request_id}}/cancel")
    def cancel_current_input(request_id: str, authorization: Annotated[str | None, Header()] = None):
        if application_execution is None:
            raise HTTPException(status_code=503, detail="owned application execution is not configured")
        try:
            return application_execution.cancel_current_input(request_id, operator_credential(authorization))
        except OperatorCredentialRejected as error:
            raise HTTPException(status_code=401, detail=str(error)) from None

    @application.exception_handler(HardwareCommandError)
    async def handle_hardware_command_error(
        request: Request,
        error: HardwareCommandError,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": str(error)},
        )

    @application.get("/health", summary="Report backend availability")
    def health() -> dict[str, str]:
        """Report backend application availability only."""
        return {"status": "available"}

    @application.post(
        f"{API_PREFIX}/service/sf-bottom-valve",
        response_model=SfBottomValveCommandResponse,
        summary="Move the host-connected SF bottom valve",
        description=(
            "Service-only synchronous command. Success confirms that the configured "
            "DYNAMIXEL reached the calibrated OPEN or CLOSED target."
        ),
    )
    def set_sf_bottom_valve(
        command: SfBottomValveCommandRequest,
    ) -> SfBottomValveCommandResponse:
        if application_execution is not None:
            application_execution.sf_service_command(command.state)
            return SfBottomValveCommandResponse(state=command.state, position_confirmed=True)
        if sf_bottom_valve is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="SF bottom valve hardware is not configured",
            )
        sf_bottom_valve.set_state(command.state)
        return SfBottomValveCommandResponse(
            state=command.state,
            position_confirmed=True,
        )

    @application.post(
        f"{API_PREFIX}/service/pumps/command",
        response_model=PumpServiceCommandResponse,
        summary="Execute a durable supervised P1/P2 command",
        description=(
            "Service-only command. The caller must durably own both command IDs and "
            "explicitly confirm a physically safe fluid route. Unknown outcomes are "
            "never automatically retried."
        ),
    )
    def execute_pump_service_command(
        request: PumpServiceCommandRequest,
    ) -> PumpServiceCommandResponse:
        executor = arduino_commands
        if executor is None and arduino_runtime is not None:
            executor = arduino_runtime.executor
        if executor is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Arduino hardware is not configured",
            )
        command = (
            "PUMP_HOME"
            if request.command == "HOME"
            else "PUMP_MOVE_ABSOLUTE_STEPS"
        )
        arguments: dict[str, str | int | bool] = {"pump": request.pump}
        if request.target_steps is not None:
            arguments["target_steps"] = request.target_steps
        try:
            entry = executor.execute(
                phase_execution_id=request.phase_execution_id,
                operation_command_id=request.operation_command_id,
                command=command,
                arguments=arguments,
            )
        except ArduinoCommandIdentityConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except ArduinoSerialError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error
        return PumpServiceCommandResponse(
            operation_command_id=entry.operation_command_id,
            state=entry.state.value,
            result=entry.result,
            error_code=entry.error_code,
            execution_started=entry.execution_started,
        )

    @application.post(
        f"{API_PREFIX}/service/valves/command",
        response_model=PumpServiceCommandResponse,
        summary="Execute a durable supervised V1-V8 command",
        description=(
            "Service-only HOME or canonical 0/90/180-degree valve command. "
            "Unknown outcomes are never automatically retried."
        ),
    )
    def execute_valve_service_command(
        request: ValveServiceCommandRequest,
    ) -> PumpServiceCommandResponse:
        executor = arduino_commands
        if executor is None and arduino_runtime is not None:
            executor = arduino_runtime.executor
        if executor is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Arduino hardware is not configured",
            )
        command = "VALVE_HOME" if request.command == "HOME" else "VALVE_SET_POSITION"
        arguments: dict[str, str | int | bool] = {"valve": request.valve}
        if request.position_degrees is not None:
            arguments["position_degrees"] = request.position_degrees
        try:
            entry = executor.execute(
                phase_execution_id=request.phase_execution_id,
                operation_command_id=request.operation_command_id,
                command=command,
                arguments=arguments,
            )
        except ArduinoCommandIdentityConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except ArduinoSerialError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error
        return PumpServiceCommandResponse(
            operation_command_id=entry.operation_command_id,
            state=entry.state.value,
            result=entry.result,
            error_code=entry.error_code,
            execution_started=entry.execution_started,
        )

    @application.post(
        f"{API_PREFIX}/service/column-bottom-valve/command",
        response_model=PumpServiceCommandResponse,
        summary="Execute a durable supervised column bottom valve command",
        description=(
            "Service-only HOME or confirmed 4/94-degree position command. HOME "
            "establishes coordinate zero; CLOSED is the separate 4-degree position. "
            "Unknown outcomes are never automatically retried."
        ),
    )
    def execute_column_bottom_valve_service_command(
        request: ColumnBottomValveServiceCommandRequest,
    ) -> PumpServiceCommandResponse:
        executor = arduino_commands
        if executor is None and arduino_runtime is not None:
            executor = arduino_runtime.executor
        if executor is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Arduino hardware is not configured",
            )
        command = (
            "COLUMN_BOTTOM_VALVE_HOME"
            if request.command == "HOME"
            else "COLUMN_BOTTOM_VALVE_SET_POSITION"
        )
        arguments: dict[str, str | int | bool] = {}
        if request.position_degrees is not None:
            arguments["position_degrees"] = request.position_degrees
        try:
            entry = executor.execute(
                phase_execution_id=request.phase_execution_id,
                operation_command_id=request.operation_command_id,
                command=command,
                arguments=arguments,
            )
        except ArduinoCommandIdentityConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except ArduinoSerialError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error
        return PumpServiceCommandResponse(
            operation_command_id=entry.operation_command_id,
            state=entry.state.value,
            result=entry.result,
            error_code=entry.error_code,
            execution_started=entry.execution_started,
        )

    @application.post(
        f"{API_PREFIX}/service/carousel/command",
        response_model=PumpServiceCommandResponse,
        summary="Execute a durable supervised carousel command",
        description=(
            "Service-only manual reference assertion or move to position 1..40. "
            "Movement also remains protected by the firmware trusted-CLOSED column "
            "valve interlock. Unknown outcomes are never automatically retried."
        ),
    )
    def execute_carousel_service_command(
        request: CarouselServiceCommandRequest,
    ) -> PumpServiceCommandResponse:
        executor = arduino_commands
        if executor is None and arduino_runtime is not None:
            executor = arduino_runtime.executor
        if executor is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Arduino hardware is not configured",
            )
        command = (
            "CAROUSEL_SET_REFERENCE"
            if request.command == "SET_REFERENCE"
            else "CAROUSEL_MOVE_TO_POSITION"
        )
        try:
            entry = executor.execute(
                phase_execution_id=request.phase_execution_id,
                operation_command_id=request.operation_command_id,
                command=command,
                arguments={"position": request.position},
            )
        except ArduinoCommandIdentityConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except ArduinoSerialError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error
        return PumpServiceCommandResponse(
            operation_command_id=entry.operation_command_id,
            state=entry.state.value,
            result=entry.result,
            error_code=entry.error_code,
            execution_started=entry.execution_started,
        )

    @application.post(
        f"{API_PREFIX}/service/sf-mixer/command",
        response_model=PumpServiceCommandResponse,
        summary="Execute a durable supervised SF mixer Start/Stop command",
        description=(
            "Service-only SF mixer commanded-state control at the fixed firmware "
            "commissioning pulse rate. Completion confirms the commanded output "
            "state, not sensed physical rotation. Unknown outcomes are never "
            "automatically retried."
        ),
    )
    def execute_sf_mixer_service_command(
        request: SfMixerServiceCommandRequest,
    ) -> PumpServiceCommandResponse:
        executor = arduino_commands
        if executor is None and arduino_runtime is not None:
            executor = arduino_runtime.executor
        if executor is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Arduino hardware is not configured",
            )
        try:
            entry = executor.execute(
                phase_execution_id=request.phase_execution_id,
                operation_command_id=request.operation_command_id,
                command="SF_MIXER_SET_STATE",
                arguments={"running": request.command == "START"},
            )
        except ArduinoCommandIdentityConflictError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            ) from error
        except ArduinoSerialError as error:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(error),
            ) from error
        return PumpServiceCommandResponse(
            operation_command_id=entry.operation_command_id,
            state=entry.state.value,
            result=entry.result,
            error_code=entry.error_code,
            execution_started=entry.execution_started,
        )

    @application.get(
        f"{API_PREFIX}/machine",
        response_model=MachineSnapshot,
        summary="Read the current machine lifecycle snapshot",
    )
    def read_machine(store: Store) -> MachineSnapshot:
        machine = store.load_machine_snapshot()
        if machine is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Machine not found")
        return machine

    @application.get(
        f"{API_PREFIX}/runs/{{run_id}}",
        response_model=DemoRun,
        summary="Read a Guided Demo run snapshot",
    )
    def read_run(run_id: str, store: Store) -> DemoRun:
        run = store.load_demo_run(run_id)
        if run is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
        return run

    @application.get(f"{API_PREFIX}/runs/{{run_id}}/events", response_model=list[DomainEvent])
    def read_run_events(run_id: str, store: Store):
        if store.load_demo_run(run_id) is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return store.load_events("RUN", run_id)

    @application.get(f"{API_PREFIX}/machine/events", response_model=list[MachineEvent])
    def read_machine_events(store: Store):
        if store.load_machine_snapshot() is None:
            return []
        return store.load_events("MACHINE", "machine")

    @application.post(
        f"{API_PREFIX}/machine/initialize",
        response_model=MachineSnapshot,
        summary="Initialize the machine lifecycle",
        description="Creates orchestration state; injected owned execution requires explicit fresh input and confirms initial READY. No actuator command is sent.",
    )
    def initialize_machine(command: CommandRequest, store: Store) -> MachineSnapshot:
        if application_execution is not None:
            return application_execution.initialize_machine(command.occurred_at)
        require_domain_mode()
        return GuidedDemoApplicationService(store).initialize_machine(command.occurred_at).machine

    @application.post(
        f"{API_PREFIX}/machine/startup/complete",
        response_model=MachineSnapshot,
        summary="Confirm machine startup completion",
        description="Executor confirmation of orchestration state; it does not move hardware.",
    )
    def complete_startup(command: CommandRequest, store: Store) -> MachineSnapshot:
        require_domain_mode()
        return GuidedDemoApplicationService(store).complete_startup(command.occurred_at).machine

    @application.post(
        f"{API_PREFIX}/machine/flush/start",
        response_model=MachineSnapshot | ExecutionAccepted,
        summary="Request a flush transition",
        description="Injected owned execution accepts an explicit flush plan asynchronously; domain-only mode starts a lifecycle transition.",
    )
    def start_flush(command: MaintenanceCommandRequest, store: Store):
        if application_execution is not None:
            machine = store.load_machine_snapshot()
            run_id = command.run_id or (None if machine is None else machine.interrupted_run_id)
            if machine is None or machine.interrupted_maintenance_id is None:
                run_id = run_id or application_execution.status().run_id
            if command.readiness is None:
                raise HTTPException(status_code=422, detail="flush needs current readiness")
            accepted = application_execution.start_maintenance(
                MaintenanceKind.FLUSH, run_id, command.readiness, command.occurred_at
            )
            return JSONResponse(status_code=202, content=accepted.model_dump(mode="json"))
        return GuidedDemoApplicationService(store).start_flush(command.occurred_at).machine

    @application.post(f"{API_PREFIX}/machine/recovery/start", response_model=ExecutionAccepted)
    def start_recovery(command: MaintenanceCommandRequest, store: Store):
        if application_execution is None:
            raise HTTPException(status_code=503, detail="owned application execution is not configured")
        if command.readiness is None:
            raise HTTPException(status_code=422, detail="recovery needs current readiness")
        machine = store.load_machine_snapshot()
        run_id = command.run_id or (None if machine is None else machine.interrupted_run_id)
        accepted = application_execution.start_maintenance(
            MaintenanceKind.RECOVERY, run_id, command.readiness, command.occurred_at
        )
        return JSONResponse(status_code=202, content=accepted.model_dump(mode="json"))

    @application.post(f"{API_PREFIX}/execution/{{operation_id}}/stop")
    def stop_operation(operation_id: str, command: CommandRequest):
        if application_execution is None:
            raise HTTPException(status_code=503, detail="owned application execution is not configured")
        result = application_execution.stop_operation(operation_id, command.occurred_at)
        return result.model_dump(mode="json")

    @application.post(
        f"{API_PREFIX}/machine/flush/complete",
        response_model=MachineSnapshot,
        summary="Confirm flush completion",
        description="Executor confirmation of orchestration state; it does not verify hardware.",
    )
    def complete_flush(command: CommandRequest, store: Store) -> MachineSnapshot:
        require_domain_mode()
        return GuidedDemoApplicationService(store).complete_flush(command.occurred_at).machine

    @application.post(
        f"{API_PREFIX}/runs",
        response_model=DemoRun,
        summary="Create a Guided Demo run",
    )
    def create_run(command: CreateRunRequest, store: Store) -> DemoRun:
        if application_execution is not None:
            return application_execution.create_run(
                command.run_id, command.configuration, command.execution_settings, command.occurred_at
            )
        return GuidedDemoApplicationService(store).create_run(
            command.run_id,
            command.configuration,
            command.execution_settings,
            command.occurred_at,
        ).run

    @application.post(
        f"{API_PREFIX}/runs/{{run_id}}/start",
        response_model=RunMachineResponse | ExecutionAccepted,
        summary="Start a Guided Demo run",
    )
    def start_run(
        run_id: str, command: CommandRequest, store: Store
    ):
        if application_execution is not None:
            accepted = application_execution.start_run(run_id, command.occurred_at)
            return JSONResponse(status_code=202, content=accepted.model_dump(mode="json"))
        current = store.load_demo_run(run_id)
        if current is not None and current.recipe is not None:
            raise HTTPException(status_code=409, detail="recipe steps require owned application execution")
        result = GuidedDemoApplicationService(store).start_run(run_id, command.occurred_at)
        return RunMachineResponse(run=result.run, machine=result.machine)

    @application.post(
        f"{API_PREFIX}/runs/{{run_id}}/phases/current/complete",
        response_model=RunMachineResponse,
        summary="Confirm non-hardware phase completion",
        description=(
            "Completes only the current non-hardware phase; hardware phases must be "
            "completed through execution-result resolution."
        ),
    )
    def complete_current_phase(
        run_id: str, command: CommandRequest, store: Store
    ) -> RunMachineResponse:
        require_domain_mode()
        result = GuidedDemoApplicationService(store).complete_current_phase(
            run_id, command.occurred_at
        )
        return RunMachineResponse(run=result.run, machine=result.machine)

    @application.post(
        f"{API_PREFIX}/runs/{{run_id}}/stop/request",
        response_model=RunMachineResponse | ExecutionAccepted,
        summary="Request Stop demo",
        description="Requests an orderly domain stop; it does not directly stop hardware.",
    )
    def request_stop_demo(
        run_id: str, command: CommandRequest, store: Store
    ):
        if application_execution is not None:
            result = application_execution.request_stop(run_id, command.occurred_at)
            if isinstance(result, ExecutionAccepted):
                return result
            return RunMachineResponse(run=result.run, machine=result.machine)
        result = GuidedDemoApplicationService(store).request_stop_demo(
            run_id, command.occurred_at
        )
        return RunMachineResponse(run=result.run, machine=result.machine)

    @application.post(
        f"{API_PREFIX}/runs/{{run_id}}/stop/confirm",
        response_model=RunMachineResponse,
        summary="Confirm Stop demo completion",
        description=(
            "Executor confirmation after the current physical atomic operation has finished; "
            "it does not stop hardware."
        ),
    )
    def confirm_stop_demo(
        run_id: str, command: CommandRequest, store: Store
    ) -> RunMachineResponse:
        require_domain_mode()
        result = GuidedDemoApplicationService(store).confirm_stop_demo(
            run_id, command.occurred_at
        )
        return RunMachineResponse(run=result.run, machine=result.machine)

    @application.post(f"{API_PREFIX}/runs/{{run_id}}/pause", response_model=RunMachineResponse)
    def pause_run(run_id: str, command: CommandRequest):
        if application_execution is None:
            raise HTTPException(status_code=503, detail="owned application execution is not configured")
        run, machine = application_execution.set_paused(run_id, paused=True, occurred_at=command.occurred_at)
        return RunMachineResponse(run=run, machine=machine)

    @application.post(f"{API_PREFIX}/runs/{{run_id}}/resume", response_model=RunMachineResponse)
    def resume_run(run_id: str, command: CommandRequest):
        if application_execution is None:
            raise HTTPException(status_code=503, detail="owned application execution is not configured")
        run, machine = application_execution.set_paused(run_id, paused=False, occurred_at=command.occurred_at)
        return RunMachineResponse(run=run, machine=machine)

    return application


_arduino_runtime = build_arduino_runtime_from_environment(os.environ)
app = create_app(
    sf_bottom_valve=build_sf_bottom_valve_from_environment(os.environ),
    arduino_runtime=_arduino_runtime,
)
