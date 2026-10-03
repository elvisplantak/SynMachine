"""Recovery and mandatory flush through the existing owned command runner.

No transport, database or diagnostic path is duplicated. Adapter preparation uses
fake transports in tests; supplied readiness values are not physical proof.
"""

from typing import Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, StrictBool, model_validator

from app.demo.hardware_contract import BottomValveState
from app.demo.maintenance_plan import MaintenanceIntent, MaintenanceKind, MaintenancePlan
from app.demo.machine_events import MachineEvent, MachineEventType
from app.demo.machine_models import MachineSnapshot, MachineState
from app.demo.run_models import RunStatus
from app.hardware.command_plan_store import PlanSource
from app.hardware.command_planning import ArduinoAction, CommandPlanningContext
from app.hardware.owned_phase_session import OwnedPhaseSession
from app.hardware.simulated_p1_runner import SimulationBlocked
from app.hardware.sequence_ownership import OwnershipBlocked


class MaintenanceReadiness(BaseModel):
    """Explicit per-attempt policy input, never an old reference report."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    operator: str
    evidence_note: str
    waste_air_gap_verified: StrictBool
    switching_sequences_verified: StrictBool
    working_calibrations_verified: StrictBool
    reactor_mixer_stopped: StrictBool
    carousel_manually_aligned: StrictBool

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        if any(
            value is not True
            for value in (
                self.waste_air_gap_verified,
                self.switching_sequences_verified,
                self.working_calibrations_verified,
                self.reactor_mixer_stopped,
                self.carousel_manually_aligned,
            )
        ):
            raise ValueError("all required maintenance readiness items must be explicit true")
        if not self.operator.strip() or not self.evidence_note.strip():
            raise ValueError("readiness needs explicit operator and evidence")
        return self


def transition(store, expected, intent, state, event_type, occurred_at, *, active):
    machine = MachineSnapshot(
        state=state,
        event_sequence=expected.event_sequence + 1,
        interrupted_run_id=None if state is MachineState.READY else intent.run_id,
        interrupted_maintenance_id=(intent.execution_id
            if state is not MachineState.READY and intent.run_id is None else None),
        active_maintenance=intent if active else None,
    )
    event = MachineEvent(
        sequence_number=machine.event_sequence,
        occurred_at=occurred_at,
        event_type=event_type,
        machine_state=state,
        run_id=intent.run_id,
        interrupted_maintenance_id=machine.interrupted_maintenance_id,
        maintenance_intent=intent,
        message=f"Owned {intent.kind.value.lower()} {event_type.value.lower()}",
    )
    store.persist_maintenance_transition(expected, machine, event)
    return machine


class OwnedMaintenanceSession(OwnedPhaseSession):
    """Process-local command-confirmed state; restart cannot reconstruct it."""

    def __init__(self, runtime, state):
        self.runner = runtime._runner
        self.coordinator = runtime._coordinator
        self._device = self.runner.device
        self._owner = runtime._owner
        self._valid = True
        self._executing = True
        self._phase_id = None
        self._initial_context = self._device.current
        self._state = state
        self._mixer = self._device.sf_mixer_running
        self._boot = self._device.controller_boot_id
        self._arduino_session = self._device.arduino_session_id
        self._sf_session = self._device.sf_session_id
        self._counts = (len(self._device.calls), len(self._device.sf_calls))
        self._homed_pumps = set()
        self.generation = self._owner._db.execute(
            "SELECT COUNT(*) FROM hardware_sequences"
        ).fetchone()[0]
        self.runner._session = self

    def observe(self, action):
        if isinstance(action, ArduinoAction) and action.command in (
            "VALVE_HOME",
            "COLUMN_BOTTOM_VALVE_HOME",
            "PUMP_HOME",
            "CAROUSEL_SET_REFERENCE",
        ):
            self.check_connections()
            data = self._state.model_dump()
            args = dict(action.arguments)
            if action.command == "PUMP_HOME":
                # HOME zero may lie outside the configured working stroke. Do
                # not fabricate an in-stroke position until the empty move succeeds.
                self._homed_pumps.add(args["pump"])
            elif action.command == "VALVE_HOME":
                for valve in data["valve_positions"]:
                    if valve["valve"] == args["valve"]:
                        valve["position_degrees"] = 0
                        break
                else:
                    data["valve_positions"] = (
                        *data["valve_positions"],
                        {"valve": args["valve"], "position_degrees": 0},
                    )
            elif action.command == "COLUMN_BOTTOM_VALVE_HOME":
                data["column_position_degrees"] = 0
            else:
                data["carousel_position"] = args["position"]
            self._state = CommandPlanningContext.model_validate(data)
            self._counts = (len(self._device.calls), len(self._device.sf_calls))
            return
        super().observe(action)
        if isinstance(action, ArduinoAction) and action.command == "PUMP_MOVE_ABSOLUTE_STEPS":
            self._homed_pumps.discard(dict(action.arguments)["pump"])

    def validate_completion(self):
        super().validate_completion()
        if (
            self._homed_pumps
            or self._state.sf_bottom_valve is not BottomValveState.CLOSED
            or (self._state.column_position_degrees != 4 or self._mixer is not False)
        ):
            raise SimulationBlocked(
                "maintenance did not establish its required final command state"
            )


def execute_maintenance(runtime, run_id, plan, readiness, occurred_at, stop_requested):
    """Called with runtime operation gate and exclusive bundle locks held."""
    if type(plan) is not MaintenancePlan or type(readiness) is not MaintenanceReadiness:
        raise TypeError("explicit maintenance plan and readiness are required")
    plan = MaintenancePlan.model_validate(plan.model_dump())
    readiness = MaintenanceReadiness.model_validate(readiness.model_dump())
    machine = runtime._store.load_machine_snapshot()
    run = None if run_id is None else runtime._store.load_demo_run(run_id)
    if (
        machine is None
        or machine.active_execution is not None
        or machine.active_maintenance is not None
        or (run_id is not None and (run is None
            or run.status not in (RunStatus.FAULTED, RunStatus.ABORTED, RunStatus.COMPLETED)))
        or machine.state is MachineState.BUSY
        or machine.interrupted_run_id not in (None, run_id)
        or (run_id is not None and machine.interrupted_maintenance_id is not None)
    ):
        raise SimulationBlocked("maintenance requires resolved terminal run and machine context")
    standalone = plan.kind is MaintenanceKind.FLUSH and machine.state is MachineState.READY
    if run_id is None and not standalone and machine.interrupted_maintenance_id is None:
        raise SimulationBlocked("machine-only maintenance requires explicit interruption scope")
    if plan.kind is MaintenanceKind.FLUSH and machine.state not in (MachineState.FLUSH_REQUIRED, MachineState.READY):
        raise SimulationBlocked("flush requires READY or FLUSH_REQUIRED")
    if plan.kind is MaintenanceKind.RECOVERY and machine.state not in (
        MachineState.RECOVERING,
        MachineState.RECOVERY_REQUIRED,
        MachineState.FLUSH_REQUIRED,
        MachineState.READY,
    ):
        raise SimulationBlocked("recovery requires an explicitly retained interruption")
    current_owner = runtime._owner._validate_owner()
    if standalone and current_owner is not None:
        raise SimulationBlocked("READY with retained ownership still requires recovery")
    if not standalone and current_owner is None:
        raise SimulationBlocked("maintenance requires retained ownership")
    previous = getattr(runtime, "_maintenance", None)
    if standalone:
        generation = runtime._owner.idle_generation()
        state = runtime._fresh_or_retained_state(generation)
    elif plan.kind is MaintenanceKind.FLUSH:
        # A restart or stale diagnostic report is never sufficient to skip recovery.
        if previous is not None and previous._valid and previous._kind is MaintenanceKind.RECOVERY:
            previous.validate_completion()
            if previous._owner_id != current_owner:
                raise SimulationBlocked("retained recovery owner changed")
        else:
            previous = runtime._session
            if previous is None or not getattr(previous, "_stopped_cleanly", False):
                raise SimulationBlocked(
                    "flush requires current successful recovery or clean Stop continuity"
                )
            if previous._expected_run.run_id != run_id:
                raise SimulationBlocked("clean Stop belongs to another run")
            previous.check_arduino()
            previous.check_sf()
            previous._check_fixture()
            if previous._stopped_owner != current_owner:
                raise SimulationBlocked("retained Stop owner changed")
        state = previous._state
    else:
        state = runtime._runner.device.current
    phase_id = str(uuid4())
    state = state.model_copy(update={"phase_execution_id": phase_id})
    source_sequence = machine.event_sequence if run is None else run.event_sequence
    stored = runtime._runner._plans.persist(
        PlanSource(run_id=run_id, run_event_sequence=source_sequence, plan=plan), state
    ).plan
    if standalone:
        lease = runtime._owner.claim(phase_id, expected_generation=generation)
        current_owner = lease.sequence_id
    # Identity binds readiness attribution to the same durable lifecycle intent.
    intent = MaintenanceIntent(
        execution_id=phase_id,
        owner_id=current_owner,
        run_id=run_id,
        kind=plan.kind,
        started_at=occurred_at,
        operator=readiness.operator,
        evidence_note=readiness.evidence_note,
    )
    if not standalone:
        lease = runtime._owner.begin_maintenance(current_owner, phase_id)
    session = OwnedMaintenanceSession(runtime, state)
    session._phase_id = phase_id
    session._kind = plan.kind
    session._owner_id = current_owner
    runtime._maintenance = session
    runtime._session = None
    expected = machine

    def start():
        nonlocal expected
        expected = transition(
            runtime._store,
            expected,
            intent,
            MachineState.RECOVERING
            if plan.kind is MaintenanceKind.RECOVERY
            else MachineState.FLUSHING,
            MachineEventType.MAINTENANCE_STARTED,
            occurred_at,
            active=True,
        )

    def stopped():
        if (
            runtime._store.load_machine_snapshot() != expected
            or (run_id is not None and runtime._store.load_demo_run(run_id) != run)
        ):
            raise SimulationBlocked("maintenance lifecycle changed during execution")
        result = stop_requested()
        if type(result) is not bool:
            raise ValueError("maintenance Stop callback must return a boolean")
        return result

    def finish(outcome, completed):
        nonlocal expected
        if stopped() or outcome != "COMPLETED" or completed != len(stored.prepared.operations):
            session._valid = False
            return False
        session.validate_completion()
        expected = transition(
            runtime._store,
            expected,
            intent,
            MachineState.FLUSH_REQUIRED
            if plan.kind is MaintenanceKind.RECOVERY
            else MachineState.READY,
            MachineEventType.MAINTENANCE_COMPLETED,
            runtime._coordinator.clock(),
            active=False,
        )
        # Recovery keeps exclusion. Only successful required flush grants release.
        return plan.kind is MaintenanceKind.FLUSH

    try:
        outcome, _ = runtime._runner.run(
            phase_id,
            run_id=run_id,
            run_event_sequence=source_sequence,
            stop_requested=stopped,
            before_execute=start,
            before_finish=finish,
            maintenance_lease=lease,
        )
        if outcome != "COMPLETED" or not session._valid:
            raise SimulationBlocked("maintenance stopped; deliberate recovery is required")
        session.validate_completion()
        return expected
    except BaseException as error:
        session._valid = False
        try:
            runtime._owner.block(lease)
        except OwnershipBlocked:
            pass  # The command runner already retained/poisoned this lease.
        except BaseException as write_error:
            error.add_note(f"Maintenance ownership retention failed: {write_error}")
        raise
    finally:
        session._executing = False
