"""Ephemeral command-path display evidence, never an execution permission.

The scope includes dispatch/awaiting a result, not sensor-confirmed motion or
STARTED telemetry. It is cleared before follow-up actions and on every exit.
No snapshot is persisted or reconstructed from history after restart.
"""
from contextlib import contextmanager
from threading import Lock
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.demo.maintenance_plan import MaintenancePlan
from app.demo.operation_models import OperationKind, SelectRouteOperation
from app.hardware.command_planning import ArduinoAction, CollectionWait


class ExecutionFlowActivity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    phase_execution_id: str
    run_id: str
    operation_number: int
    operation_command_id: str | None
    kind: Literal["ASPIRATE", "DISPENSE", "COLLECT"]
    route: Literal[
        "S_TO_P1", "B1_TO_P1", "B2_TO_P1", "P1_TO_REACTOR",
        "REACTOR_TO_P2", "P2_TO_SF_TOP", "SF_BOTTOM_TO_P2", "P2_TO_COLUMN",
        "COLUMN_TO_FRACTIONS",
    ]


def flow_for_action(plan, operation, action, phase_id):
    # Maintenance preparation expands logical operations into multiple prepared
    # operations. Do not infer a route from their numbering or from HOME targets.
    if isinstance(plan.source.plan, MaintenancePlan):
        return None
    operations = plan.source.plan.operations
    if len(operations) != len(plan.prepared.operations):
        return None
    route = None
    for logical in operations[:operation.operation_number]:
        if isinstance(logical, SelectRouteOperation):
            route = logical.route_id.value
    kind = operation.operation_kind
    if isinstance(action, ArduinoAction) and action.command == "PUMP_MOVE_ABSOLUTE_STEPS":
        if kind in (OperationKind.ASPIRATE, OperationKind.ASPIRATE_FROM_SF):
            kind = "ASPIRATE"
        elif kind is OperationKind.DISPENSE:
            kind = "DISPENSE"
        else:
            return None
        command_id = action.operation_command_id
    elif isinstance(action, CollectionWait) and kind is OperationKind.COLLECT_COLUMN_FRACTION:
        kind, route, command_id = "COLLECT", "COLUMN_TO_FRACTIONS", None
    else:
        return None
    supported = {
        "ASPIRATE": {"S_TO_P1", "B1_TO_P1", "B2_TO_P1", "REACTOR_TO_P2", "SF_BOTTOM_TO_P2"},
        "DISPENSE": {"P1_TO_REACTOR", "P2_TO_SF_TOP", "P2_TO_COLUMN"},
        "COLLECT": {"COLUMN_TO_FRACTIONS"},
    }
    if route not in supported[kind]:
        return None
    return ExecutionFlowActivity(
        phase_execution_id=phase_id, run_id=plan.source.run_id,
        operation_number=operation.operation_number, operation_command_id=command_id,
        kind=kind, route=route,
    )


class ExecutionFlow:
    """Separate small lock: readers never wait for the runner or touch its DB."""

    def __init__(self):
        self._lock = Lock()
        self._activity = None

    def snapshot(self):
        with self._lock:
            return self._activity

    @contextmanager
    def scope(self, activity):
        with self._lock:
            self._activity = activity
        try:
            yield
        finally:
            with self._lock:
                self._activity = None
