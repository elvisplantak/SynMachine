"""Explicit application binding to the existing owned executor.

One worker owns the runtime/SQLite handles. Read/control requests use separately
validated lifecycle handles; Stop/Pause never queue behind physical work. Deferred
device resources open only after bundle validation/locking, on the worker. No
environment activation, database provisioning or automatic recovery.
"""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
import os
import sqlite3
from threading import Event, RLock
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from app.demo.application_service import GuidedDemoApplicationService
from app.demo.maintenance_plan import MaintenanceKind
from app.demo.machine_models import MachineState
from app.demo.run_models import RunStatus
from app.hardware.owned_offline_runtime import OwnedOfflineRuntime
from app.hardware.simulated_lifecycle import SimulationLifecycleStore
from app.hardware.simulated_p1_runner import SimulationBlocked
from app.hardware.operator_current_input import OperatorCurrentInput, OperatorInputChallenge
from app.hardware.sequence_ownership import OwnershipBlocked
from app.startup_bootstrap import ProcessStartupDisposition, ProcessStartupResult
from app.persistence.sqlite_store import PersistenceError


class ExecutionAccepted(BaseModel):
    model_config = ConfigDict(frozen=True)
    operation_id: str
    action: str
    run_id: str | None


class ApplicationExecutionStatus(BaseModel):
    model_config = ConfigDict(frozen=True)
    configured: bool = True
    busy: bool
    executing: bool
    operation: ExecutionAccepted | None
    error: str | None
    retained_owner_id: str | None
    run_id: str | None
    automatic_resume_allowed: bool = False
    current_input: OperatorInputChallenge | None = None
    operator_current_input_configured: bool = False


class OwnedApplicationExecution:
    """Caller-injected composition; never enabled by production environment.

    Factories construct resources on the worker and must supply independently
    established input. Tests use fake transports only. Adapters remain private.
    The same owner and command journals serve both Guided Demo and Service.
    """

    def __init__(self, bundle, device_factory, calibrations, *, timer_factory,
                 column_readiness=None, recovery_plan=None, flush_plan=None,
                 operator_input_source=None, current_context_provider=None):
        if not callable(device_factory) or not callable(timer_factory):
            raise TypeError("explicit device and timer factories are required")
        for plan, kind in ((recovery_plan, MaintenanceKind.RECOVERY), (flush_plan, MaintenanceKind.FLUSH)):
            if plan is not None and (plan.kind is not kind or plan.calibrations != calibrations):
                raise ValueError("maintenance plan kind/calibration differs from application inputs")
        if operator_input_source is not None and type(operator_input_source) is not OperatorCurrentInput:
            raise TypeError("explicit operator current-input source required")
        if current_context_provider is not None:
            from app.hardware.adapter_configuration import AdapterCurrentContextProvider
            if type(current_context_provider) is not AdapterCurrentContextProvider:
                raise TypeError("explicit current-context provider required")
        self._current_context_provider = current_context_provider
        self._operator_input_source = operator_input_source
        self.bundle = bundle
        self._device_factory = device_factory
        self._timer_factory = timer_factory
        self._calibrations = calibrations
        self._column_readiness = column_readiness
        self._recovery_plan = recovery_plan
        self._flush_plan = flush_plan
        self._lock = RLock()
        self._maintenance_stop = Event()
        self._run_stop_at = None
        self._control_failure = None
        self._pool = None
        self._runtime = None
        self._started = False
        self._closed = False
        self._closing = False
        self._pid = os.getpid()
        self._busy = False
        self._executing = False
        self._operation = None
        self._error = None
        self._owner_id = None
        self._run_id = None
        self._future = None

    def _check(self):
        if not self._started or self._closed or self._closing or self._pid != os.getpid():
            raise SimulationBlocked("application execution is not available in this process")

    def start(self, occurred_at: datetime):
        with self._lock:
            if self._started or self._closed or self._pid != os.getpid():
                raise SimulationBlocked("application execution startup cannot be repeated or inherited")
            self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="labforge-execution")
            try:
                startup = self._pool.submit(self._open, occurred_at).result()
            except BaseException:
                self._closed = True
                self._pool.shutdown(wait=True)
                raise
            self._started = True
            return startup

    def _open(self, occurred_at):
        runtime = None
        try:
            runtime = OwnedOfflineRuntime(
                self.bundle, device_factory=self._device_factory, timer=self._timer_factory()
            )
            runtime.reconcile_maintenance_interruption(occurred_at)
            runtime.reconcile_interruption(occurred_at)
            runtime.reconcile_orphaned_ownership(occurred_at)
            self._owner_id = runtime._owner._validate_owner()
            self._runtime = runtime
            runtime._coordinator.before_control_poll = self._check_control_failure
            initial = runtime.initial_inspection.machine
            machine = runtime._store.load_machine_snapshot()
            if machine is not None:
                events = runtime._store.load_events("MACHINE", "machine")
                self._run_id = (None if machine.interrupted_maintenance_id is not None else
                    machine.active_run_id or machine.interrupted_run_id or events[-1].run_id)
            if initial is not None and initial.active_maintenance is not None:
                disposition = ProcessStartupDisposition.MAINTENANCE_RECONCILED
            elif initial is not None and initial.state is MachineState.BUSY:
                disposition = (ProcessStartupDisposition.PHASE_EXECUTION_RECONCILED
                    if initial.active_execution is not None else ProcessStartupDisposition.ACTIVE_RUN_RECONCILED)
            elif machine != initial:
                disposition = ProcessStartupDisposition.OWNERSHIP_RECONCILED
            else:
                disposition = ProcessStartupDisposition.UNINITIALIZED if machine is None else {
                    MachineState.STARTING: ProcessStartupDisposition.STARTUP_PENDING,
                    MachineState.READY: ProcessStartupDisposition.READY,
                    MachineState.RECOVERY_REQUIRED: ProcessStartupDisposition.RECOVERY_REQUIRED,
                    MachineState.RECOVERING: ProcessStartupDisposition.RECOVERING,
                    MachineState.FLUSH_REQUIRED: ProcessStartupDisposition.FLUSH_REQUIRED,
                    MachineState.FLUSHING: ProcessStartupDisposition.FLUSHING,
                }[machine.state]
            return ProcessStartupResult(
                disposition=disposition, machine=machine,
                persistent_reconciliation_occurred=machine != initial,
            )
        except BaseException:
            if runtime is not None:
                runtime.close()
            raise

    @contextmanager
    def store(self, *, read_only=True):
        self._check()
        with SimulationLifecycleStore(
            self.bundle.lifecycle_path, self.bundle.lifecycle_id,
            self.bundle.execution_id, read_only=read_only,
        ) as store:
            if read_only:
                # Request snapshots stay internally consistent while the worker
                # commits phases. This handle is never a hardware permission.
                store._connection.execute("BEGIN")
            yield store

    def status(self):
        with self._lock:
            self._check()
            return ApplicationExecutionStatus(
                busy=self._busy, executing=self._executing, operation=self._operation,
                error=self._error, retained_owner_id=self._owner_id,
                run_id=self._run_id,
                operator_current_input_configured=self._operator_input_source is not None,
                current_input=(None if self._operator_input_source is None
                               else self._operator_input_source.pending()),
            )

    def submit_current_input(self, request_id, references, credential):
        with self._lock:
            self._check()
            if self._operator_input_source is None:
                raise SimulationBlocked("operator current input is not configured")
            return self._operator_input_source.submit(request_id, references, credential=credential)

    def cancel_current_input(self, request_id, credential):
        with self._lock:
            self._check()
            if self._operator_input_source is None:
                raise SimulationBlocked("operator current input is not configured")
            return self._operator_input_source.cancel(request_id, credential=credential)

    def _idle(self, callback):
        with self._lock:
            self._check()
            if self._busy:
                raise SimulationBlocked("application execution is busy; Service and competing work are blocked")
            self._busy = True
            future = self._pool.submit(self._call_idle, callback)
        try:
            return future.result()
        except OwnershipBlocked as error:
            raise SimulationBlocked(str(error)) from error
        finally:
            with self._lock:
                self._busy = False

    def _call_idle(self, callback):
        try:
            return callback()
        finally:
            try:
                owner_id = self._runtime._owner._validate_owner()
                with self._lock:
                    self._owner_id = owner_id
            except Exception as error:
                with self._lock:
                    self._error = str(error)
                raise

    def _check_control_failure(self):
        with self._lock:
            if self._control_failure is not None:
                raise SimulationBlocked(self._control_failure)

    def create_run(self, run_id, configuration, settings, occurred_at):
        def create():
            self._runtime._owner.idle_generation()
            machine = self._runtime._store.load_machine_snapshot()
            if machine is not None and machine.state is not MachineState.READY:
                raise SimulationBlocked("new configuration requires READY")
            return GuidedDemoApplicationService(self._runtime._store).create_run(
                run_id, configuration, settings, occurred_at
            ).run
        return self._idle(create)

    def preview_recipe(self, definition):
        from app.recipes.planning import preview_recipe
        return preview_recipe(definition, self._calibrations, self._column_readiness,
                              fresh_collection_context_available=self._current_context_provider is not None)

    def create_recipe_run(self, run_id, recipe, readiness, occurred_at):
        def create():
            self._runtime._owner.idle_generation()
            machine = self._runtime._store.load_machine_snapshot()
            if machine is not None and machine.state is not MachineState.READY:
                raise SimulationBlocked("new recipe requires READY")
            preview = self.preview_recipe(recipe.definition)
            if preview["collection_readiness_status"] == "UNAVAILABLE":
                raise SimulationBlocked("independent Column readiness is required")
            return GuidedDemoApplicationService(self._runtime._store).create_recipe_run(
                run_id, recipe, readiness, occurred_at)
        return self._idle(create)

    def initialize_machine(self, occurred_at):
        return self._idle(lambda: self._runtime.initialize_fresh_machine(occurred_at))

    def _submit(self, action, run_id, callback):
        with self._lock:
            self._check()
            if self._busy:
                raise SimulationBlocked("application execution is already busy")
            self._busy = True
            self._error = None
            self._executing = True
            self._maintenance_stop.clear()
            self._run_stop_at = None
            self._control_failure = None
            accepted = ExecutionAccepted(operation_id=str(uuid4()), action=action, run_id=run_id)
            self._operation = accepted
            self._run_id = run_id
            self._future = self._pool.submit(self._execute, callback)
            return accepted

    def _execute(self, callback):
        try:
            callback()
        except Exception as error:
            with self._lock:
                self._error = str(error)
        finally:
            try:
                owner_id = self._runtime._owner._validate_owner()
                with self._lock:
                    self._owner_id = owner_id
            except Exception as error:
                with self._lock:
                    self._error = self._error or str(error)
            finally:
                with self._lock:
                    self._busy = False
                    self._executing = False

    def start_run(self, run_id, occurred_at, *, recipe_authorized=False):
        with self.store() as store:
            run = store.load_demo_run(run_id)
            if run is not None and run.recipe is not None and not recipe_authorized:
                raise SimulationBlocked("recipe execution requires fresh UVP readiness")
            machine = store.load_machine_snapshot()
            if run is None or run.status is not RunStatus.CREATED:
                raise SimulationBlocked("start requires a newly configured CREATED run")
            if machine is not None and machine.state is not MachineState.READY:
                raise SimulationBlocked("start requires READY")

        def execute():
            self._runtime.start_created_run(
                run_id, self._calibrations, occurred_at=occurred_at,
                column_readiness=self._column_readiness,
            )
            with self._lock:
                if self._run_stop_at is not None:
                    run = self._runtime._store.load_demo_run(run_id)
                    if run.status is RunStatus.RUNNING:
                        GuidedDemoApplicationService(self._runtime._store).request_stop_demo(
                            run_id, self._run_stop_at
                        )
            while True:
                self._check_control_failure()
                result = self._runtime.execute_next()
                if result is None:
                    raise SimulationBlocked("executor cannot skip an unsupported phase")
                if result.run.status in (RunStatus.COMPLETED, RunStatus.ABORTED, RunStatus.FAULTED):
                    return
        return self._submit("RUN", run_id, execute)

    def start_maintenance(self, kind, run_id, readiness, occurred_at):
        plan = self._recovery_plan if kind is MaintenanceKind.RECOVERY else self._flush_plan
        if plan is None or readiness is None:
            raise SimulationBlocked("explicit maintenance plan and per-attempt readiness are required")
        return self._submit(kind.value, run_id, lambda: self._runtime.execute_maintenance(
            run_id, plan, readiness, occurred_at=occurred_at,
            stop_requested=self._maintenance_stop.is_set,
        ))

    def request_stop(self, run_id, occurred_at):
        with self._lock:
            self._check()
            if not self._executing or self._operation is None or self._operation.run_id != run_id:
                raise SimulationBlocked("Stop requires the current executing operation")
            if self._operation.action != "RUN":
                self._maintenance_stop.set()
                if self._operator_input_source is not None:
                    self._operator_input_source.cancel_pending()
                return self._operation
            try:
                with self.store(read_only=False) as store:
                    run = store.load_demo_run(run_id)
                    if run is not None and run.status is RunStatus.CREATED:
                        self._run_stop_at = occurred_at
                        if self._operator_input_source is not None:
                            self._operator_input_source.cancel_pending()
                        return self._operation
                    return GuidedDemoApplicationService(store).request_stop_demo(run_id, occurred_at)
            except (PersistenceError, sqlite3.Error) as error:
                self._control_failure = f"Stop persistence failed; further primary work is blocked: {error}"
                raise

    def stop_operation(self, operation_id, occurred_at):
        with self._lock:
            self._check()
            if not self._executing or self._operation is None or self._operation.operation_id != operation_id:
                raise SimulationBlocked("Stop requires the current executing operation identity")
            return self.request_stop(self._operation.run_id, occurred_at)

    def set_paused(self, run_id, *, paused, occurred_at):
        with self._lock:
            self._check()
            if (not self._executing or self._operation is None or self._operation.action != "RUN"
                or self._operation.run_id != run_id):
                raise SimulationBlocked("Pause/Resume requires the current run")
            with self.store(read_only=False) as store:
                machine = store.load_machine_snapshot()
                intent = None if machine is None else machine.active_execution
                if intent is None or intent.run_id != run_id:
                    raise SimulationBlocked("Pause/Resume requires a started wait")
                run = store.set_wait_paused(intent.execution_id, paused=paused, occurred_at=occurred_at)
                return run, store.load_machine_snapshot()

    def arduino_service_command(self, **values):
        return self._idle(lambda: self._service_ready().arduino_service.execute(**values))

    def execute(self, **values):
        """Existing Service API executor interface, always through shared ownership."""
        return self.arduino_service_command(**values)

    def sf_service_command(self, state):
        return self._idle(lambda: self._service_ready().sf_service.set_state(state))

    def _service_ready(self):
        machine = self._runtime._store.load_machine_snapshot()
        if (machine is not None and (machine.state is not MachineState.READY
            or machine.active_execution is not None or machine.active_maintenance is not None)):
            raise SimulationBlocked("Service requires idle READY lifecycle")
        return self._runtime._runner.hardware

    def close(self, occurred_at):
        with self._lock:
            if self._closed:
                return
            self._check()
            if self._busy and self._operation is not None:
                try:
                    self.request_stop(self._operation.run_id, occurred_at)
                except Exception:
                    # A finished run or failed persistence is not force-aborted.
                    # Outstanding work still retains its existing durable owner.
                    pass
            if self._operator_input_source is not None:
                self._operator_input_source.close()
            self._closing = True
        try:
            self._pool.submit(self._runtime.close).result()
        finally:
            self._pool.shutdown(wait=True)
            with self._lock:
                self._closed = True
