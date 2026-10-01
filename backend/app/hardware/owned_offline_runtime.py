"""Exclusive fake-only execution and explicit interruption reconciliation.

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


class OwnedOfflineRuntime:
    """One process owns the bundle until close or death; execution remains fake.

    Opening validates only. Reconciliation is an explicit method, cannot run in
    an executing session and never performs cleanup or grants further execution.
    A fresh run can only be created in a bundle that was pristine at open.
    """

    def __init__(self, bundle, device, *, timer=None):
        if type(device) is not SimulatedP1Device:
            raise TypeError("only the exact fake device is supported")
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
