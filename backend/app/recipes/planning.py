"""Compile logical steps to existing validated operation plans."""

from fractions import Fraction

from app.demo.column_fraction_collection_operation_plan import (
    ColumnFractionCollectionConfiguration,
    plan_column_fraction_collection_operations,
)
from app.demo.operation_models import (
    OperationKind,
    PausableWaitOperation,
    SymbolicRouteId,
    TimedSfOperation,
    TopologyId,
    build_syringe_transfer_operations,
)
from app.demo.p1_reagent_operation_plan import P1ReagentToReactorOperationPlan, ReagentId
from app.demo.p1_solvent_operation_plan import P1SolventToReactorOperationPlan
from app.demo.p2_reactor_to_sf_operation_plan import P2ReactorToSfOperationPlan
from app.demo.p2_sf_to_column_operation_plan import (
    P2SfToColumnOperationPlan,
    build_p2_sf_to_column_operations,
)
from app.demo.pausable_wait_plan import PausableWaitPlan
from app.demo.timed_sf_operation_plan import TimedSfOperationPlan
from app.demo.transfer_cycle_planner import plan_transfer_cycles
from app.recipes.models import (
    AddStep,
    CollectStep,
    SfMixStep,
    SfSettleStep,
    TransferStep,
    WaitStep,
    phase_for_step,
    validate_recipe_flow,
)


def compile_step(step, calibrations, column_readiness=None):
    phase = phase_for_step(step)
    if isinstance(step, WaitStep):
        return PausableWaitPlan(
            phase=phase,
            duration_seconds=step.duration_seconds,
            operations=(
                PausableWaitOperation(
                    operation_kind=OperationKind.PAUSABLE_RUN_WAIT,
                    operation_number=1,
                    duration_seconds=step.duration_seconds,
                ),
            ),
        )
    if isinstance(step, (SfMixStep, SfSettleStep)):
        kind = (
            OperationKind.TIMED_SF_MIXING
            if isinstance(step, SfMixStep)
            else OperationKind.SF_SETTLING_WAIT
        )
        return TimedSfOperationPlan(
            phase=phase,
            duration_seconds=step.duration_seconds,
            operations=(
                TimedSfOperation(
                    operation_kind=kind, operation_number=1, duration_seconds=step.duration_seconds
                ),
            ),
        )
    if isinstance(step, CollectStep):
        if column_readiness is None:
            raise ValueError("independent Column readiness is required")
        return plan_column_fraction_collection_operations(
            ColumnFractionCollectionConfiguration(
                fraction_count=step.fraction_count,
                fraction_duration_seconds=step.fraction_duration_seconds,
                carousel_ready_confirmed=column_readiness.carousel_ready_confirmed,
                column_bottom_valve_referenced_confirmed=column_readiness.column_bottom_valve_referenced_confirmed,
            )
        )
    if isinstance(step, AddStep):
        pump, cls = calibrations.p1, P1SolventToReactorOperationPlan
        aspiration, dispense = SymbolicRouteId.S_TO_P1, SymbolicRouteId.P1_TO_REACTOR
        extra = {}
        if step.source != "S":
            cls = P1ReagentToReactorOperationPlan
            aspiration = (
                SymbolicRouteId.B1_TO_P1 if step.source == "B1" else SymbolicRouteId.B2_TO_P1
            )
            extra = {"reagent_id": ReagentId(step.source)}
    elif isinstance(step, TransferStep):
        pump, extra = calibrations.p2, {}
        if step.route == "REACTOR_TO_SF":
            cls, aspiration, dispense = (
                P2ReactorToSfOperationPlan,
                SymbolicRouteId.REACTOR_TO_P2,
                SymbolicRouteId.P2_TO_SF_TOP,
            )
        else:
            cls, aspiration, dispense = (
                P2SfToColumnOperationPlan,
                SymbolicRouteId.SF_BOTTOM_TO_P2,
                SymbolicRouteId.P2_TO_COLUMN,
            )
    else:
        raise ValueError("unsupported recipe operation")
    if step.volume_ml / pump.working_volume_ml > 1000:
        raise ValueError("transfer exceeds software planning limit of 1000 pump cycles")
    cycles = plan_transfer_cycles(step.volume_ml, pump)
    for cycle in cycles.cycles:
        steps = (
            Fraction(cycle.volume_ml) * pump.working_stroke_steps / Fraction(pump.working_volume_ml)
        )
        if steps.denominator != 1:
            raise ValueError("volume is not representable as whole steps; no rounding policy")
        target = pump.working_empty_chamber_position_steps - int(steps)
        if not 1 <= target <= 20500:
            raise ValueError("absolute target must be 1..20500; HOME is not a transfer")
    return cls(
        phase=phase,
        required_topology_id=TopologyId.LABFORGE_V1_APPROVED_TARGET,
        transfer_cycle_plan=cycles,
        operations=(
            build_p2_sf_to_column_operations(cycles)
            if cls is P2SfToColumnOperationPlan
            else build_syringe_transfer_operations(
                cycles, aspiration_route_id=aspiration, dispense_route_id=dispense
            )
        ),
        **extra,
    )


def preview_recipe(definition, calibrations=None, column_readiness=None):
    amounts = validate_recipe_flow(definition)
    steps = []
    for index, step in enumerate(definition.steps):
        item = {"step_number": index + 1, "phase": phase_for_step(step), "step": step}
        if calibrations is not None:
            # Collection readiness is a live precondition, never fabricated for preview.
            if not isinstance(step, CollectStep) or column_readiness is not None:
                plan = compile_step(step, calibrations, column_readiness)
                item["operation_count"] = len(plan.operations)
        steps.append(item)
    return {
        "steps": steps,
        "configured_contents_ml": amounts,
        "calibrations_checked": calibrations is not None,
        "collection_readiness_required": any(
            isinstance(step, CollectStep) for step in definition.steps
        ),
        "volumes_are_measured": False,
    }


def source_for_recipe_run(run, calibrations, column_readiness):
    if run.recipe is None or run.recipe_step_index is None:
        raise ValueError("run has no recipe snapshot")
    step = run.recipe.definition.steps[run.recipe_step_index]
    if phase_for_step(step) != run.phase:
        raise ValueError("recipe step and current phase differ")
    return compile_step(step, calibrations, column_readiness)
