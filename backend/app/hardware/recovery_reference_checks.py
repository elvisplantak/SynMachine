"""Process-local operator attestations scoped to an interrupted offline run.

No physical recovery, reference commands, durable release or production API.
These are explicit operator statements, not fabricated sensor observations.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import uuid4

from app.demo.hardware_contract import BottomValveState
from app.demo.machine_models import MachineState
from app.hardware.fresh_hardware_observations import observe_current_hardware
from app.hardware.owned_startup_inspection import inspect_owned_startup
from app.hardware.simulated_p1_runner import SimulationBlocked


class ReferenceItem(StrEnum):
    V1 = "V1_REFERENCED"
    V2 = "V2_REFERENCED"
    V3 = "V3_REFERENCED"
    V4 = "V4_REFERENCED"
    V5 = "V5_REFERENCED"
    V6 = "V6_REFERENCED"
    V7 = "V7_REFERENCED"
    V8 = "V8_REFERENCED"
    P1 = "P1_REFERENCED"
    P2 = "P2_REFERENCED"
    COLUMN = "COLUMN_VALVE_REFERENCED_AND_CLOSED"
    CAROUSEL = "CAROUSEL_MANUALLY_ALIGNED"
    REACTOR_MIXER = "REACTOR_MIXER_STOPPED"
    SF_MIXER = "SF_MIXER_STOPPED"
    P1_ROUTE = "P1_SAFE_RECOVERY_ROUTE_VERIFIED"
    P2_ROUTE = "P2_SAFE_RECOVERY_ROUTE_VERIFIED"
    P1_CALIBRATION = "P1_WORKING_CALIBRATION_VERIFIED"
    P2_CALIBRATION = "P2_WORKING_CALIBRATION_VERIFIED"


@dataclass(frozen=True)
class ReferenceChallenge:
    check_id: str
    interrupted_run_id: str
    retained_owner_id: str
    controller_boot_id: int
    backend_session_nonce: str
    connection_epoch: int


@dataclass(frozen=True)
class OperatorReferenceConfirmation:
    item: ReferenceItem
    operator: str
    evidence_note: str


@dataclass(frozen=True)
class RecoveryReferenceReport:
    challenge: ReferenceChallenge
    confirmations: tuple[OperatorReferenceConfirmation, ...]
    missing: tuple[ReferenceItem, ...]

    @property
    def may_release_owner(self) -> bool:
        # Even all attestations do not implement recovery/flush or release.
        return False


class RecoveryReferenceChecks:
    """Use only through OwnedOfflineRuntime.begin_reference_checks().

    Every confirmation/report performs new observations while the runtime gate
    and bundle process locks are held. Any sampling/context failure invalidates
    this object permanently. It never rewrites old command evidence.
    """

    def __init__(self, runtime, arduino, sf_valve, required_commands):
        runtime._check()
        if not runtime._gate.locked():
            raise SimulationBlocked("reference checks require the runtime operation gate")
        self._runtime = runtime
        self._arduino = arduino
        self._sf = sf_valve
        self._required = required_commands
        self._valid = True
        self._confirmations = {}
        self._requests = set()
        self._versions = self._database_versions()
        self._snapshot = inspect_owned_startup(runtime.bundle)
        machine = self._snapshot.machine
        if (
            runtime._session is not None or runtime._used
            or self._snapshot.owner_id is None or machine is None
            or machine.state not in {MachineState.RECOVERY_REQUIRED, MachineState.RECOVERING}
            or machine.active_execution is not None or machine.interrupted_run_id is None
        ):
            raise SimulationBlocked("reference checks require reconciled interruption and retained owner")
        observations = self._sample()
        status = observations.arduino_status
        self._challenge = ReferenceChallenge(
            str(uuid4()), machine.interrupted_run_id, self._snapshot.owner_id,
            status.controller_boot_id, status.backend_session_nonce,
            observations.arduino_connection_epoch,
        )
        self._identity = (
            status.controller_boot_id, status.backend_session_nonce,
            observations.arduino_connection_epoch,
        )

    @property
    def challenge(self):
        return self._challenge

    def _database_versions(self):
        # Detect external commits and same-connection writes, including changes
        # not represented by the diagnostic summary. Rollback may invalidate
        # conservatively through total_changes; it never restores old attestations.
        return tuple(
            (connection.execute("PRAGMA data_version").fetchone()[0], connection.total_changes)
            for connection in (
                self._runtime._owner._db, self._runtime._runner._db,
                self._runtime._store._connection,
            )
        )

    def _sample(self):
        if self._database_versions() != self._versions:
            raise SimulationBlocked("recovery database context changed")
        if inspect_owned_startup(self._runtime.bundle) != self._snapshot:
            raise SimulationBlocked("recovery database context changed")
        observations = observe_current_hardware(
            self._arduino, self._sf, required_commands=self._required
        )
        status = observations.arduino_status
        identity = (status.controller_boot_id, status.backend_session_nonce,
                    observations.arduino_connection_epoch)
        if hasattr(self, "_identity") and identity != self._identity:
            raise SimulationBlocked("reference-check controller session changed")
        if status.request_id in self._requests:
            raise SimulationBlocked("reference checks require a new status request")
        if (
            observations.sf_valve.observed_state is not BottomValveState.CLOSED
            or observations.sf_valve.torque_enabled
        ):
            raise SimulationBlocked("reference checks require observed closed SF valve with torque off")
        if inspect_owned_startup(self._runtime.bundle) != self._snapshot:
            raise SimulationBlocked("recovery database context changed during observation")
        if self._database_versions() != self._versions:
            raise SimulationBlocked("recovery database context changed during observation")
        self._requests.add(status.request_id)
        return observations

    def _operate(self, challenge, confirmation=None):
        self._runtime._check()
        if not self._runtime._gate.acquire(blocking=False):
            raise SimulationBlocked("runtime operation already active")
        try:
            if not self._valid or challenge is not self.challenge:
                raise SimulationBlocked("reference challenge is stale or foreign")
            self._sample()
            if confirmation is not None:
                if confirmation.item in self._confirmations:
                    raise SimulationBlocked("reference item already confirmed; start new checks to replace it")
                self._confirmations[confirmation.item] = confirmation
            return RecoveryReferenceReport(
                self.challenge,
                tuple(self._confirmations[item] for item in ReferenceItem if item in self._confirmations),
                tuple(item for item in ReferenceItem if item not in self._confirmations),
            )
        except BaseException:
            self._valid = False
            self._confirmations.clear()
            raise
        finally:
            self._runtime._gate.release()

    def confirm(self, challenge, item, *, operator, evidence_note):
        if (
            type(item) is not ReferenceItem or type(operator) is not str or not operator.strip()
            or type(evidence_note) is not str or not evidence_note.strip()
        ):
            raise ValueError("reference item, operator and evidence note must be explicit")
        return self._operate(
            challenge, OperatorReferenceConfirmation(item, operator.strip(), evidence_note.strip())
        )

    def report(self, challenge):
        return self._operate(challenge)
