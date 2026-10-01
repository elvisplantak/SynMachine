"""Process-local continuity across owned phases, deliberately fake-device-only.

No state is reconstructed from plans, journal history or a restarted process.
Initial context is an independent fixture; subsequent state comes from successful
commands in the same session, never from the plan's optimistic final projection.
"""

from threading import Lock
from uuid import uuid4

from app.demo.calibration_models import PumpId
from app.demo.column_fraction_collection_operation_plan import (
    ColumnFractionCollectionConfiguration,
    plan_column_fraction_collection_operations,
)
from app.demo.guided_demo_phase_executor import ColumnFractionCollectionReadiness
from app.demo.p1_reagent_operation_plan import plan_p1_reagent_to_reactor_operations
from app.demo.p1_solvent_operation_plan import plan_p1_solvent_to_reactor_operations
from app.demo.p2_reactor_to_sf_operation_plan import plan_p2_reactor_to_sf_operations
from app.demo.p2_sf_to_column_operation_plan import plan_p2_sf_to_column_operations
from app.demo.phases import EXECUTION_INTENT_PHASES, PAUSABLE_EXECUTION_PHASES, RunPhase
from app.demo.pausable_wait_plan import plan_pausable_wait
from app.demo.run_models import RunStatus
from app.demo.timed_sf_operation_plan import plan_timed_sf_operations
from app.hardware.command_plan_store import PlanSource
from app.hardware.command_planning import ArduinoAction, CommandPlanningContext, SfBottomValveAction
from app.hardware.owned_transfer_runner import OwnedTransferRunner
from app.hardware.simulated_lifecycle import PlanLifecycleCoordinator
from app.hardware.simulated_p1_runner import SimulationBlocked


def source_for_run(run, calibrations, column_readiness):
    """Use the existing phase builders without skipping unsupported phases."""
    if run.phase in PAUSABLE_EXECUTION_PHASES:
        return plan_pausable_wait(run)
    if run.phase is RunPhase.P1_TRANSFER_S_TO_REACTOR:
        return plan_p1_solvent_to_reactor_operations(run.fluid_plan, calibrations)
    if run.phase in (
        RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
        RunPhase.P1_TRANSFER_SECOND_LIQUID_TO_REACTOR,
    ):
        return plan_p1_reagent_to_reactor_operations(run.phase, run.fluid_plan, calibrations)
    if run.phase is RunPhase.P2_TRANSFER_REACTOR_TO_SF:
        return plan_p2_reactor_to_sf_operations(run.fluid_plan, calibrations)
    if run.phase is RunPhase.P2_TRANSFER_SF_TO_COLUMN:
        return plan_p2_sf_to_column_operations(run.fluid_plan, calibrations)
    if run.phase in (RunPhase.SF_MIXING, RunPhase.SF_SETTLING):
        return plan_timed_sf_operations(run)
    if run.phase is RunPhase.COLUMN_FRACTION_COLLECTION:
        if column_readiness is None:
            raise SimulationBlocked("independent Column readiness is required")
        return plan_column_fraction_collection_operations(
            ColumnFractionCollectionConfiguration.from_execution_settings(
                run.execution_settings,
                carousel_ready_confirmed=column_readiness.carousel_ready_confirmed,
                column_bottom_valve_referenced_confirmed=column_readiness.column_bottom_valve_referenced_confirmed,
            )
        )
    raise SimulationBlocked("phase is not supported; it must not be skipped")


class OwnedPhaseSession:
    """One explicit run binding, one live process, no reset/rebind/resume method.

    Initialization requires fresh execution/ownership stores and a fresh fixture.
    This intentionally does not implement production recovery or live trust.
    Service activity between phases invalidates continuity even if it completed.
    """

    def __init__(
        self,
        coordinator,
        run_id,
        calibrations,
        *,
        column_readiness: ColumnFractionCollectionReadiness | None = None,
    ):
        if (
            type(coordinator) is not PlanLifecycleCoordinator
            or type(coordinator.runner) is not OwnedTransferRunner
        ):
            raise TypeError("an explicit owned offline coordinator is required")
        self.coordinator = coordinator
        self.runner = coordinator.runner
        self._device = self.runner.device
        self._gate = Lock()
        self._valid = True
        self._executing = False
        self._phase_id = None
        self._calibrations = calibrations
        self._column_readiness = column_readiness
        self._owner = self.runner.hardware.ownership
        self.generation = self._owner.idle_generation()
        if self.generation != 0:
            raise SimulationBlocked("a new session cannot adopt existing ownership history")
        if (
            self.runner._session is not None
            or self._device.used
            or self._device.calls
            or self._device.sf_calls
        ):
            raise SimulationBlocked("session needs an unused runner and independent fixture")
        for table in (
            "prepared_command_plans",
            "arduino_command_journal",
            "sf_action_journal",
            "execution_waits",
            "execution_carousel_projection",
        ):
            if self.runner._db.execute(f"SELECT 1 FROM {table} LIMIT 1").fetchone():
                raise SimulationBlocked("a new session cannot adopt previous execution evidence")
        self._expected_run = coordinator.store.load_demo_run(run_id)
        machine = coordinator.store.load_machine_snapshot()
        if (
            self._expected_run is None
            or self._expected_run.status is not RunStatus.RUNNING
            or machine is None
            or machine.active_run_id != run_id
            or machine.active_execution is not None
        ):
            raise SimulationBlocked("session requires a running run without active execution")
        if self._device.sf_mixer_running is not False:
            raise SimulationBlocked("initial mixer state must be independently stopped")
        self._initial_context = self._device.current
        self._state = self._initial_context
        supplied = {PumpId.P1: calibrations.p1, PumpId.P2: calibrations.p2}
        if any(p.calibration != supplied[p.calibration.pump_id] for p in self._state.pumps):
            raise SimulationBlocked("calibration differs from independent fixture")
        self._mixer = False
        self._boot = self._device.controller_boot_id
        self._arduino_session = self._device.arduino_session_id
        self._sf_session = self._device.sf_session_id
        self._counts = (0, 0)
        self.check_connections()
        if (
            self._boot != self._state.controller_boot_id
            or self._device.carousel_position != self._state.carousel_position
        ):
            raise SimulationBlocked("initial fixture references do not match current session")
        self.runner._session = self

    def check_arduino(self):
        # A failed SF connection must not suppress required Arduino mixer STOP.
        if (
            not self._arduino_session
            or self._device.controller_boot_id != self._boot
            or self._device.arduino_session_id != self._arduino_session
        ):
            self._valid = False
            self._device.carousel_position = None
            self._device.sf_mixer_running = None
            raise SimulationBlocked("Arduino session changed")

    def check_sf(self):
        # Likewise, valid SF CLOSE remains possible after an Arduino failure.
        if not self._sf_session or self._device.sf_session_id != self._sf_session:
            self._valid = False
            raise SimulationBlocked("SF session changed")

    def check_connections(self):
        self.check_arduino()
        self.check_sf()
        if not self._valid:
            raise SimulationBlocked("phase session is invalid")

    def _check_idle(self):
        self.check_connections()
        if self._owner.idle_generation() != self.generation:
            raise SimulationBlocked("Service or another phase changed hardware claim history")
        if self.coordinator.store.load_demo_run(self._expected_run.run_id) != self._expected_run:
            raise SimulationBlocked("run changed outside this phase session")
        self._check_fixture()

    def _check_fixture(self):
        if (
            self._device.current != self._initial_context
            or (len(self._device.calls), len(self._device.sf_calls)) != self._counts
            or self._device.carousel_position != self._state.carousel_position
            or self._device.sf_mixer_running is not self._mixer
        ):
            raise SimulationBlocked("current fixture changed outside owned execution")

    def validate_completion(self):
        """Check handoff while ownership is still retained after lifecycle commit."""
        self.check_connections()
        self._check_fixture()

    def validate_plan(self, plan):
        self.check_connections()
        self._check_fixture()
        if not self._executing or plan.phase_execution_id != self._phase_id:
            raise SimulationBlocked("phase is not authorized by the active session")
        if plan.prepared.assumptions != self._state.model_copy(
            update={"phase_execution_id": self._phase_id}
        ):
            raise SimulationBlocked("plan does not match current command-confirmed state")

    def observe(self, action):
        """Called only after terminal success and result persistence in the runner."""
        if not self._executing:
            raise SimulationBlocked("cannot observe outside active owned execution")
        if not self._valid:
            return  # Cleanup evidence stays in journals, never restores continuity.
        data = self._state.model_dump()
        if isinstance(action, SfBottomValveAction):
            data["sf_bottom_valve"] = action.state
        elif isinstance(action, ArduinoAction):
            args = dict(action.arguments)
            if action.command == "VALVE_SET_POSITION":
                for valve in data["valve_positions"]:
                    if valve["valve"] == args["valve"]:
                        valve["position_degrees"] = args["position_degrees"]
                        break
                else:
                    raise SimulationBlocked("completed valve lacks an initial reference")
            elif action.command == "PUMP_MOVE_ABSOLUTE_STEPS":
                for pump in data["pumps"]:
                    if pump["calibration"]["pump_id"] == args["pump"]:
                        pump["position_steps"] = args["target_steps"]
                        break
                else:
                    raise SimulationBlocked("completed pump lacks an initial reference")
            elif action.command == "COLUMN_BOTTOM_VALVE_SET_POSITION":
                data["column_position_degrees"] = args["position_degrees"]
            elif action.command == "CAROUSEL_MOVE_TO_POSITION":
                data["carousel_position"] = args["position"]
            elif action.command == "SF_MIXER_SET_STATE":
                self._mixer = args["running"]
            else:
                raise SimulationBlocked("unsupported command-confirmed state update")
        else:
            raise SimulationBlocked("unsupported observation")
        self._state = CommandPlanningContext.model_validate(data)
        self._counts = (len(self._device.calls), len(self._device.sf_calls))

    def execute_next(self):
        if not self._gate.acquire(blocking=False):
            raise SimulationBlocked("phase session is already executing")
        try:
            self._check_idle()
            if self._expected_run.status is not RunStatus.RUNNING:
                raise SimulationBlocked("run is no longer running")
            if self._expected_run.phase not in EXECUTION_INTENT_PHASES:
                return None  # Never invent completion of an unsupported phase.
            if self._expected_run.phase in PAUSABLE_EXECUTION_PHASES and self.runner._timer is None:
                raise SimulationBlocked("pausable phases require an explicit monotonic timer")
            self._phase_id = str(uuid4())
            source = source_for_run(self._expected_run, self._calibrations, self._column_readiness)
            context = self._state.model_copy(update={"phase_execution_id": self._phase_id})
            self.runner._plans.persist(
                PlanSource(
                    run_id=self._expected_run.run_id,
                    run_event_sequence=self._expected_run.event_sequence,
                    plan=source,
                ),
                context,
            )
            self._executing = True
            result = self.coordinator.execute(
                self._phase_id, self._calibrations, column_readiness=self._column_readiness
            )
            if result.run.status not in (RunStatus.RUNNING, RunStatus.COMPLETED):
                self._valid = False
                return result
            self.check_connections()
            self._check_fixture()
            self.generation += 1  # Exactly our claim; never adopt a later observed generation.
            self._expected_run = result.run
            return result
        except BaseException:
            self._valid = False
            raise
        finally:
            self._executing = False
            self._phase_id = None
            self._gate.release()
