import os
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, field_validator

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
from app.hardware.runtime_configuration import (
    build_sf_bottom_valve_from_environment,
)
from app.hardware.sf_bottom_valve import SfBottomValveControl
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


def _configured_database_path(database_path: str | Path | None) -> Path:
    if database_path is not None:
        return Path(database_path)
    return Path(os.environ.get(DATABASE_PATH_ENVIRONMENT_VARIABLE, DEFAULT_DATABASE_PATH))


def create_app(
    database_path: str | Path | None = None,
    *,
    startup_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    sf_bottom_valve: SfBottomValveControl | None = None,
) -> FastAPI:
    configured_database_path = _configured_database_path(database_path)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        # LabForge v1 startup reconciliation assumes one FastAPI worker.
        occurred_at = startup_clock()
        with SQLiteStore(configured_database_path) as store:
            application.state.process_startup = bootstrap_process_startup(
                store,
                occurred_at,
            )
        yield

    application = FastAPI(title="LabForge backend", lifespan=lifespan)

    def get_store() -> Iterator[SQLiteStore]:
        with SQLiteStore(configured_database_path) as store:
            yield store

    Store = Annotated[SQLiteStore, Depends(get_store)]

    @application.exception_handler(GuidedDemoApplicationError)
    @application.exception_handler(LifecycleTransitionError)
    @application.exception_handler(MachineTransitionError)
    @application.exception_handler(PersistenceConflictError)
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

    @application.post(
        f"{API_PREFIX}/machine/initialize",
        response_model=MachineSnapshot,
        summary="Initialize the machine lifecycle",
        description="Creates the orchestration state only; it does not execute hardware startup.",
    )
    def initialize_machine(command: CommandRequest, store: Store) -> MachineSnapshot:
        return GuidedDemoApplicationService(store).initialize_machine(command.occurred_at).machine

    @application.post(
        f"{API_PREFIX}/machine/startup/complete",
        response_model=MachineSnapshot,
        summary="Confirm machine startup completion",
        description="Executor confirmation of orchestration state; it does not move hardware.",
    )
    def complete_startup(command: CommandRequest, store: Store) -> MachineSnapshot:
        return GuidedDemoApplicationService(store).complete_startup(command.occurred_at).machine

    @application.post(
        f"{API_PREFIX}/machine/flush/start",
        response_model=MachineSnapshot,
        summary="Request a flush transition",
        description="Starts flush orchestration only; it does not execute a physical flush plan.",
    )
    def start_flush(command: CommandRequest, store: Store) -> MachineSnapshot:
        return GuidedDemoApplicationService(store).start_flush(command.occurred_at).machine

    @application.post(
        f"{API_PREFIX}/machine/flush/complete",
        response_model=MachineSnapshot,
        summary="Confirm flush completion",
        description="Executor confirmation of orchestration state; it does not verify hardware.",
    )
    def complete_flush(command: CommandRequest, store: Store) -> MachineSnapshot:
        return GuidedDemoApplicationService(store).complete_flush(command.occurred_at).machine

    @application.post(
        f"{API_PREFIX}/runs",
        response_model=DemoRun,
        summary="Create a Guided Demo run",
    )
    def create_run(command: CreateRunRequest, store: Store) -> DemoRun:
        return GuidedDemoApplicationService(store).create_run(
            command.run_id,
            command.configuration,
            command.execution_settings,
            command.occurred_at,
        ).run

    @application.post(
        f"{API_PREFIX}/runs/{{run_id}}/start",
        response_model=RunMachineResponse,
        summary="Start a Guided Demo run",
    )
    def start_run(
        run_id: str, command: CommandRequest, store: Store
    ) -> RunMachineResponse:
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
        result = GuidedDemoApplicationService(store).complete_current_phase(
            run_id, command.occurred_at
        )
        return RunMachineResponse(run=result.run, machine=result.machine)

    @application.post(
        f"{API_PREFIX}/runs/{{run_id}}/stop/request",
        response_model=RunMachineResponse,
        summary="Request Stop demo",
        description="Requests an orderly domain stop; it does not directly stop hardware.",
    )
    def request_stop_demo(
        run_id: str, command: CommandRequest, store: Store
    ) -> RunMachineResponse:
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
        result = GuidedDemoApplicationService(store).confirm_stop_demo(
            run_id, command.occurred_at
        )
        return RunMachineResponse(run=result.run, machine=result.machine)

    return application


app = create_app(
    sf_bottom_valve=build_sf_bottom_valve_from_environment(os.environ),
)
