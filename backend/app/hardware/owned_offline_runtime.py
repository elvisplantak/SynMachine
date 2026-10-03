"""Exclusive candidate execution and explicit interruption reconciliation.

The advisory file locks cover callers of this composition, not historical direct
assemblies, arbitrary SQLite writers or production startup. Never replace/unlink
bundle files while a runtime is open. No lost lease or device state is recovered.
"""

from contextlib import ExitStack, closing
from datetime import datetime
import fcntl
import os
from threading import Lock, get_ident

from app.demo.application_service import GuidedDemoApplicationService
from app.demo.machine_models import MachineState
from app.hardware.owned_phase_session import OwnedPhaseSession
from app.hardware.owned_startup_inspection import inspect_owned_startup
from app.hardware.owned_transfer_runner import OwnedTransferRunner
from app.hardware.sequence_ownership import HardwareOwnership
from app.hardware.simulated_lifecycle import SimulationLifecycleStore, PlanLifecycleCoordinator
from app.hardware.simulated_p1_runner import SimulatedP1Device, SimulationBlocked
from app.hardware.prepared_adapter_device import PreparedAdapterDevice


class OwnedOfflineRuntime:
    """One process owns the bundle until close or death; no startup/API activation.

    Opening validates only. Reconciliation is an explicit method, cannot run in
    an executing session and never performs cleanup or grants further execution.
    First-run entry requires a pristine bundle; new-run entry requires deliberate
    successful flush/completion and independently supplied or retained current state.
    """

    def __init__(self, bundle, device=None, *, timer=None, device_factory=None):
        if (device is None) == (device_factory is None):
            raise TypeError("supply exactly one device or deferred device factory")
        if device_factory is not None and not callable(device_factory):
            raise TypeError("deferred device factory must be callable")
        if device is not None and type(device) not in (SimulatedP1Device, PreparedAdapterDevice):
            raise TypeError("only the explicit fake or prepared adapter device is supported")
        self._resources = ExitStack()
        self._closed = False
        self._thread = get_ident()
        self._pid = os.getpid()
        self._gate = Lock()
        self._session = None
        self._used = False
        self.bundle = bundle
        try:
            # Existing files only. Lock all three to exclude partial-bundle overlap.
            for path in sorted(
                (bundle.ownership_path, bundle.execution_path, bundle.lifecycle_path),
                key=lambda path: str(path.resolve()),
            ):
                stream = self._resources.enter_context(path.open("rb"))
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise SimulationBlocked("offline bundle already has an active runtime") from error
            self.initial_inspection = inspect_owned_startup(bundle)
            self._owner = self._resources.enter_context(closing(HardwareOwnership(
                bundle.ownership_path, bundle.ownership_id
            )))
            self._store = self._resources.enter_context(SimulationLifecycleStore(
                bundle.lifecycle_path, bundle.lifecycle_id, bundle.execution_id
            ))
            if device_factory is not None:
                supplied = device_factory()
                # A resource context owns connection teardown; plain existing
                # fixtures keep their historical caller-owned lifetime.
                device = (supplied if type(supplied) in (SimulatedP1Device, PreparedAdapterDevice)
                    else self._resources.enter_context(supplied))
                if type(device) not in (SimulatedP1Device, PreparedAdapterDevice):
                    raise TypeError("factory must supply an explicit fake or prepared adapter device")
            self._runner = self._resources.enter_context(closing(OwnedTransferRunner(
                bundle.execution_path, bundle.execution_id, self._owner, device, timer=timer
            )))
            self._coordinator = PlanLifecycleCoordinator(self._store, self._runner)
        except BaseException:
            self._resources.close()
            self._closed = True
            raise

    def _check(self):
        if self._closed or os.getpid() != self._pid or get_ident() != self._thread:
            raise SimulationBlocked("runtime is closed or belongs to another process/thread")

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self._closed:
            return
        self._check()
        if not self._gate.acquire(blocking=False):
            raise SimulationBlocked("cannot close during runtime operation")
        try:
            self._closed = True
            self._resources.close()
        finally:
            self._gate.release()

    def start_fresh_run(
        self, run_id, configuration, settings, calibrations, *, occurred_at,
        column_readiness=None,
    ):
        self._check()
        if not self._gate.acquire(blocking=False):
            raise SimulationBlocked("runtime operation already active")
        try:
            initial = self.initial_inspection
            if (
                self._used or initial.machine is not None or initial.runs
                or initial.ownership_generation or initial.prepared_phase_ids
                or any(row.total for row in initial.journals)
            ):
                raise SimulationBlocked("only a pristine bundle can start a fresh offline run")
            self._used = True  # A failed initialization must not be retried here.
            service = GuidedDemoApplicationService(self._store)
            service.initialize_machine(occurred_at)
            service.complete_startup(occurred_at)
            service.create_run(run_id, configuration, settings, occurred_at)
            service.start_run(run_id, occurred_at)
            self._session = OwnedPhaseSession(
                self._coordinator, run_id, calibrations, column_readiness=column_readiness
            )
        finally:
            self._gate.release()

    def execute_next(self):
        self._check()
        if not self._gate.acquire(blocking=False):
            raise SimulationBlocked("runtime operation already active")
        try:
            if self._session is None:
                raise SimulationBlocked("no fresh process-local execution session")
            return self._session.execute_next()
        finally:
            self._gate.release()

    def reconcile_interruption(self, occurred_at: datetime):
        """Persist software interruption only; retain journals and durable exclusion.

        Ownership retention commits BEFORE the lifecycle transaction. Failure or
        death between these commits leaves exclusion, never permission to continue.
        Repeated calls after successful reconciliation do not add lifecycle events.
        """
        self._check()
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("reconciliation timestamp must be timezone-aware")
        if not self._gate.acquire(blocking=False):
            raise SimulationBlocked("runtime operation already active")
        try:
            if self._session is not None or self._used:
                raise SimulationBlocked("close the original runtime before reconciling")
            machine = self._store.load_machine_snapshot()
            if machine is None or machine.state is not MachineState.BUSY:
                # Never interpret READY, a missing machine, or prior metadata
                # reconciliation as proof the retained hardware owner can be freed.
                return machine
            self._owner.retain_for_reconciliation()
            if machine.active_execution is not None:
                result = self._store.reconcile_interrupted_phase_execution_at_startup(
                    occurred_at, allow_paused_wait=True
                )
            else:
                result = self._store.reconcile_interrupted_active_run_at_startup(occurred_at)
            return result.machine
        finally:
            self._gate.release()

    def begin_reference_checks(self, arduino, sf_valve, *, required_commands):
        """Explicit candidate assessment; no production activation or owner release.

        Adapters are caller-supplied; tests inject fake transports. This method
        sends status queries/reads only and never establishes physical readiness.
        """
        from app.hardware.recovery_reference_checks import RecoveryReferenceChecks

        self._check()
        if not self._gate.acquire(blocking=False):
            raise SimulationBlocked("runtime operation already active")
        try:
            previous = getattr(self, "_reference_checks", None)
            if previous is not None:
                previous._valid = False
                previous._confirmations.clear()
            checks = RecoveryReferenceChecks(self, arduino, sf_valve, required_commands)
            self._reference_checks = checks
            return checks
        finally:
            self._gate.release()

    def execute_maintenance(self, run_id, plan, readiness, *, occurred_at, stop_requested=lambda: False):
        """Explicit fake recovery/flush, using the same command runner and owner."""
        from app.hardware.owned_maintenance import execute_maintenance

        self._check()
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("maintenance timestamp must be timezone-aware")
        if not self._gate.acquire(blocking=False):
            raise SimulationBlocked("runtime operation already active")
        try:
            previous = getattr(self, "_reference_checks", None)
            if previous is not None:
                previous._valid = False
            self._used = True
            return execute_maintenance(self, run_id, plan, readiness, occurred_at, stop_requested)
        finally:
            self._gate.release()

    def reconcile_maintenance_interruption(self, occurred_at):
        """Metadata only. Never replay maintenance or release the retained owner."""
        from app.hardware.owned_maintenance import transition
        from app.demo.machine_events import MachineEventType

        self._check()
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("maintenance reconciliation timestamp must be timezone-aware")
        if not self._gate.acquire(blocking=False):
            raise SimulationBlocked("runtime operation already active")
        try:
            if self._used or self._session is not None:
                raise SimulationBlocked("close the original runtime before reconciling")
            machine = self._store.load_machine_snapshot()
            if machine is None or machine.active_maintenance is None:
                return machine
            self._owner.retain_for_reconciliation()
            return transition(self._store, machine, machine.active_maintenance,
                MachineState.RECOVERING, MachineEventType.MAINTENANCE_INTERRUPTED,
                occurred_at, active=False)
        finally:
            self._gate.release()

    def start_new_run(self, run_id, configuration, settings, calibrations, *, occurred_at, column_readiness=None):
        """New identity after successful flush/completion; never adopt an old run."""
        self._check()
        if not self._gate.acquire(blocking=False):
            raise SimulationBlocked("runtime operation already active")
        try:
            generation = self._owner.idle_generation()
            machine = self._store.load_machine_snapshot()
            if (machine is None or machine.state is not MachineState.READY
                or machine.active_execution is not None or machine.active_maintenance is not None
                or self._store.load_demo_run(run_id) is not None):
                raise SimulationBlocked("new run needs READY, no execution and a new identity")
            state = self._fresh_or_retained_state(generation)
            self._used = True
            service = GuidedDemoApplicationService(self._store)
            service.create_run(run_id, configuration, settings, occurred_at)
            service.start_run(run_id, occurred_at)
            self._runner._new_run_binding = (run_id, generation, state)
            self._runner._session = None
            self._session = OwnedPhaseSession(self._coordinator, run_id, calibrations,
                column_readiness=column_readiness)
            self._maintenance = None
        finally:
            self._gate.release()

    def start_created_run(self, run_id, calibrations, *, occurred_at, column_readiness=None):
        """Bind an API-created run to fresh input or current execution state.

        Application construction supplies the same explicit bundle/device inputs.
        No past command evidence or reference report is promoted to current trust.
        """
        from app.demo.run_models import RunStatus

        self._check()
        if not self._gate.acquire(blocking=False):
            raise SimulationBlocked("runtime operation already active")
        try:
            generation = self._owner.idle_generation()
            run = self._store.load_demo_run(run_id)
            if run is None or run.status is not RunStatus.CREATED:
                raise SimulationBlocked("start requires a newly configured CREATED run")
            machine = self._store.load_machine_snapshot()
            if machine is None:
                machine = self._initialize_fresh_machine(occurred_at)
            if (machine.state is not MachineState.READY or machine.active_execution is not None
                or machine.active_maintenance is not None):
                raise SimulationBlocked("start requires READY without active execution or maintenance")
            state = self._fresh_or_retained_state(generation)
            self._used = True
            GuidedDemoApplicationService(self._store).start_run(run_id, occurred_at)
            self._runner._new_run_binding = (run_id, generation, state)
            self._runner._session = None
            self._session = OwnedPhaseSession(
                self._coordinator, run_id, calibrations, column_readiness=column_readiness
            )
            self._maintenance = None
        finally:
            self._gate.release()

    def initialize_fresh_machine(self, occurred_at):
        """Initialize from explicit unused input, never historical position trust."""
        self._check()
        if not self._gate.acquire(blocking=False):
            raise SimulationBlocked("runtime operation already active")
        try:
            return self._initialize_fresh_machine(occurred_at)
        finally:
            self._gate.release()

    def _initialize_fresh_machine(self, occurred_at):
        from app.demo.run_models import RunStatus

        initial = self.initial_inspection
        machine = self._store.load_machine_snapshot()
        if (self._used or (initial.machine is not None and initial.machine.state is not MachineState.STARTING)
            or any(run.status is not RunStatus.CREATED for run in initial.runs)
            or initial.owner_id is not None or initial.prepared_phase_ids
            or any(row.non_successful for row in initial.journals)
            or initial.incomplete_wait_operations
            or (machine is not None and machine.state is not MachineState.STARTING)):
            raise SimulationBlocked("initialization requires unresolved-history-free application state")
        self._fresh_or_retained_state(self._owner.idle_generation())
        service = GuidedDemoApplicationService(self._store)
        if machine is None:
            service.initialize_machine(occurred_at)
        return service.complete_startup(occurred_at).machine

    def reconcile_orphaned_ownership(self, occurred_at):
        """Metadata only for retained Service ownership without an active run."""
        from app.demo.machine_events import MachineEvent, MachineEventType
        from app.demo.machine_models import MachineSnapshot

        self._check()
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("ownership reconciliation timestamp must be timezone-aware")
        if not self._gate.acquire(blocking=False):
            raise SimulationBlocked("runtime operation already active")
        try:
            if self._used or self._session is not None:
                raise SimulationBlocked("close the original runtime before reconciling")
            owner_id = self._owner._validate_owner()
            expected = self._store.load_machine_snapshot()
            if owner_id is None or (expected is not None and expected.state is not MachineState.READY):
                return expected
            self._owner.retain_for_reconciliation()
            machine = MachineSnapshot(state=MachineState.RECOVERING,
                event_sequence=1 if expected is None else expected.event_sequence + 1,
                interrupted_maintenance_id=owner_id)
            event = MachineEvent(sequence_number=machine.event_sequence, occurred_at=occurred_at,
                event_type=MachineEventType.OWNERSHIP_INTERRUPTION_RECONCILED,
                machine_state=machine.state, interrupted_maintenance_id=owner_id,
                message="Retained hardware ownership requires deliberate machine recovery")
            self._store.persist_maintenance_transition(expected, machine, event)
            return machine
        finally:
            self._gate.release()

    def _fresh_or_retained_state(self, generation):
        previous = getattr(self, "_maintenance", None) or self._session
        if previous is not None:
            previous.validate_completion()
            if previous.generation != generation:
                raise SimulationBlocked("hardware ownership changed since final command state")
            return previous._state
        device = self._runner.device
        if generation != self.initial_inspection.ownership_generation:
            raise SimulationBlocked("hardware ownership changed since fresh input was supplied")
        if device.used or device.calls or device.sf_calls:
            raise SimulationBlocked("new run needs an independently supplied unused fixture")
        return device.current
