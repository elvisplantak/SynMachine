from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.demo import lifecycle as run_lifecycle
from app.demo import machine_lifecycle
from app.demo.events import DomainEvent
from app.demo.machine_events import MachineEvent
from app.demo.machine_models import MachineSnapshot, MachineState
from app.demo.models import DemoConfiguration, DemoExecutionSettings
from app.demo.run_models import DemoRun, RunStatus
from app.persistence.sqlite_store import SQLiteStore


class GuidedDemoApplicationError(RuntimeError):
    """Raised when persisted state cannot satisfy an orchestration precondition."""


class GuidedDemoApplicationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run: DemoRun
    machine: MachineSnapshot | None
    run_events: tuple[DomainEvent, ...]
    machine_events: tuple[MachineEvent, ...] = ()


class GuidedDemoMachineApplicationResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    machine: MachineSnapshot
    machine_events: tuple[MachineEvent, ...]


class GuidedDemoApplicationService:
    """Synchronous orchestration for Guided Demo domain transitions."""

    def __init__(self, store: SQLiteStore) -> None:
        self._store = store

    def initialize_machine(
        self, occurred_at: datetime
    ) -> GuidedDemoMachineApplicationResult:
        if self._store.load_machine_snapshot() is not None:
            raise GuidedDemoApplicationError("machine snapshot already exists")
        result = machine_lifecycle.create_machine(occurred_at)
        self._store.persist_machine_transition(result.machine, result.events)
        return GuidedDemoMachineApplicationResult(
            machine=result.machine,
            machine_events=result.events,
        )

    def complete_startup(
        self, occurred_at: datetime
    ) -> GuidedDemoMachineApplicationResult:
        result = machine_lifecycle.complete_startup(
            self._load_machine(), occurred_at
        )
        self._store.persist_machine_transition(result.machine, result.events)
        return GuidedDemoMachineApplicationResult(
            machine=result.machine,
            machine_events=result.events,
        )

    def start_flush(
        self, occurred_at: datetime
    ) -> GuidedDemoMachineApplicationResult:
        result = machine_lifecycle.start_flush(self._load_machine(), occurred_at)
        self._store.persist_machine_transition(result.machine, result.events)
        return GuidedDemoMachineApplicationResult(
            machine=result.machine,
            machine_events=result.events,
        )

    def complete_flush(
        self, occurred_at: datetime
    ) -> GuidedDemoMachineApplicationResult:
        result = machine_lifecycle.complete_flush(self._load_machine(), occurred_at)
        self._store.persist_machine_transition(result.machine, result.events)
        return GuidedDemoMachineApplicationResult(
            machine=result.machine,
            machine_events=result.events,
        )

    def create_run(
        self,
        run_id: str,
        configuration: DemoConfiguration,
        execution_settings: DemoExecutionSettings,
        occurred_at: datetime,
    ) -> GuidedDemoApplicationResult:
        result = run_lifecycle.create_demo_run(
            run_id, configuration, execution_settings, occurred_at
        )
        self._store.persist_run_transition(result.run, result.events)
        return GuidedDemoApplicationResult(
            run=result.run,
            machine=None,
            run_events=result.events,
        )

    def start_run(
        self, run_id: str, occurred_at: datetime
    ) -> GuidedDemoApplicationResult:
        run = self._load_run(run_id)
        machine = self._load_machine()
        run_result = run_lifecycle.start_run(run, occurred_at)
        machine_result = machine_lifecycle.start_run(machine, run_id, occurred_at)
        self._store.persist_run_and_machine_transition(
            run_result.run,
            run_result.events,
            machine_result.machine,
            machine_result.events,
        )
        return GuidedDemoApplicationResult(
            run=run_result.run,
            machine=machine_result.machine,
            run_events=run_result.events,
            machine_events=machine_result.events,
        )

    def complete_current_phase(
        self, run_id: str, occurred_at: datetime
    ) -> GuidedDemoApplicationResult:
        run = self._load_run(run_id)
        machine = self._require_active_machine(run_id)
        run_result = run_lifecycle.complete_current_phase(run, occurred_at)
        if run_result.run.status is not RunStatus.COMPLETED:
            self._store.persist_run_transition(run_result.run, run_result.events)
            return GuidedDemoApplicationResult(
                run=run_result.run,
                machine=machine,
                run_events=run_result.events,
            )

        machine_result = machine_lifecycle.complete_run(machine, run_id, occurred_at)
        self._store.persist_run_and_machine_transition(
            run_result.run,
            run_result.events,
            machine_result.machine,
            machine_result.events,
        )
        return GuidedDemoApplicationResult(
            run=run_result.run,
            machine=machine_result.machine,
            run_events=run_result.events,
            machine_events=machine_result.events,
        )

    def request_stop_demo(
        self, run_id: str, occurred_at: datetime
    ) -> GuidedDemoApplicationResult:
        run = self._load_run(run_id)
        machine = self._require_active_machine(run_id)
        run_result = run_lifecycle.request_abort(run, occurred_at)
        self._store.persist_run_transition(run_result.run, run_result.events)
        return GuidedDemoApplicationResult(
            run=run_result.run,
            machine=machine,
            run_events=run_result.events,
        )

    def confirm_stop_demo(
        self, run_id: str, occurred_at: datetime
    ) -> GuidedDemoApplicationResult:
        run = self._load_run(run_id)
        machine = self._require_active_machine(run_id)
        run_result = run_lifecycle.confirm_abort(run, occurred_at)
        machine_result = machine_lifecycle.complete_stop_demo(
            machine, run_id, occurred_at
        )
        self._store.persist_run_and_machine_transition(
            run_result.run,
            run_result.events,
            machine_result.machine,
            machine_result.events,
        )
        return GuidedDemoApplicationResult(
            run=run_result.run,
            machine=machine_result.machine,
            run_events=run_result.events,
            machine_events=machine_result.events,
        )

    def _load_run(self, run_id: str) -> DemoRun:
        run = self._store.load_demo_run(run_id)
        if run is None:
            raise GuidedDemoApplicationError(f"Guided Demo run {run_id!r} was not found")
        return run

    def _load_machine(self) -> MachineSnapshot:
        machine = self._store.load_machine_snapshot()
        if machine is None:
            raise GuidedDemoApplicationError("machine snapshot was not found")
        return machine

    def _require_active_machine(self, run_id: str) -> MachineSnapshot:
        machine = self._load_machine()
        if machine.state is not MachineState.BUSY:
            raise GuidedDemoApplicationError(
                f"machine must be BUSY for run operation, got {machine.state.value}"
            )
        if machine.active_run_id != run_id:
            raise GuidedDemoApplicationError(
                f"machine active_run_id {machine.active_run_id!r} does not match "
                f"requested run_id {run_id!r}"
            )
        return machine
