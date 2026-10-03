"""Immutable offline plan storage. Loading never authorizes or resumes execution."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from threading import RLock
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    TypeAdapter,
    model_validator,
)

from app.demo.column_fraction_collection_operation_plan import ColumnFractionCollectionOperationPlan
from app.demo.p1_reagent_operation_plan import P1ReagentToReactorOperationPlan
from app.demo.p1_solvent_operation_plan import P1SolventToReactorOperationPlan
from app.demo.p2_reactor_to_sf_operation_plan import P2ReactorToSfOperationPlan
from app.demo.p2_sf_to_column_operation_plan import P2SfToColumnOperationPlan
from app.hardware.command_planning import (
    CommandPlanningContext,
    PreparedCommandPlan,
    prepare_command_plan,
)
from app.hardware.provenance import reject_lost_keys
from app.demo.pausable_wait_plan import PausableWaitPlan
from app.demo.timed_sf_operation_plan import TimedSfOperationPlan
from app.protocol.models import PhaseExecutionId
from app.demo.maintenance_plan import MaintenancePlan
from app.demo.calibration_models import PumpId

SourcePlan = (
    MaintenancePlan
    | P1SolventToReactorOperationPlan
    | P1ReagentToReactorOperationPlan
    | P2ReactorToSfOperationPlan
    | P2SfToColumnOperationPlan
    | ColumnFractionCollectionOperationPlan
    | TimedSfOperationPlan
    | PausableWaitPlan
)


class PlanIdentityConflictError(RuntimeError):
    """The phase execution ID already belongs to a different complete plan."""


class PlanIntegrityError(RuntimeError):
    """Stored plan is corrupt, unsupported, or incompatible with this compiler."""


class PlanSource(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="wrap")
    @classmethod
    def preserve_input_keys(cls, value, handler):
        validated = handler(value)
        reject_lost_keys(value, validated)
        return validated

    run_id: Annotated[StrictStr, Field(min_length=1, pattern=r"\S")]
    run_event_sequence: Annotated[StrictInt, Field(ge=0)]
    plan: SourcePlan


_PREPARED_ADAPTER = TypeAdapter(PreparedCommandPlan)
_PHASE_ID_ADAPTER = TypeAdapter(PhaseExecutionId)


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"unsupported plan value: {type(value).__name__}")


def _model_data(value: object) -> object:
    # Inspect actual field values before Pydantic serialization can coerce a
    # model_copy/model_construct payload (e.g. bool masquerading as StrictInt).
    if isinstance(value, BaseModel):
        return {
            key: _model_data(item)
            for key, item in {**value.__dict__, **(value.model_extra or {})}.items()
        }
    if isinstance(value, (tuple, list)):
        return [_model_data(item) for item in value]
    if isinstance(value, dict):
        return {key: _model_data(item) for key, item in value.items()}
    return value


def _canonical(value: object) -> str:
    # Decimal values are serialized by Pydantic as strings, never binary floats.
    # Preserve all array order and Decimal spelling: equality is conservative.
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=_json_default,
    )


def _prepared_json(plan: PreparedCommandPlan) -> object:
    return _PREPARED_ADAPTER.dump_python(plan, mode="json")


class StoredCommandPlan(BaseModel):
    """A persisted preparation, NOT an execution claim or current position trust."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    source: PlanSource
    prepared: PreparedCommandPlan

    @model_validator(mode="after")
    def validate_derivation(self) -> Self:
        plan = self.source.plan
        context = self.prepared.assumptions
        if not isinstance(
            plan, (MaintenancePlan, ColumnFractionCollectionOperationPlan, TimedSfOperationPlan, PausableWaitPlan)
        ):
            cycle_plan = plan.transfer_cycle_plan
            pump = next(
                (p for p in context.pumps if p.calibration.pump_id == cycle_plan.pump_id), None
            )
            if pump is None or pump.calibration.working_volume_ml != cycle_plan.working_volume_ml:
                raise ValueError("source cycle capacity does not match planning calibration")
        if isinstance(plan, MaintenancePlan):
            supplied = {PumpId.P1: plan.calibrations.p1, PumpId.P2: plan.calibrations.p2}
            if {p.calibration.pump_id for p in context.pumps} != set(supplied) or any(
                p.calibration != supplied[p.calibration.pump_id] for p in context.pumps
            ):
                raise ValueError("maintenance calibrations must match the independent context")
        expected = prepare_command_plan(plan.operations, context)
        if _canonical(_prepared_json(expected)) != _canonical(_prepared_json(self.prepared)):
            raise ValueError("prepared commands do not match the validated source and assumptions")
        return self

    @property
    def phase_execution_id(self) -> str:
        return self.prepared.assumptions.phase_execution_id


@dataclass(frozen=True)
class PersistedCommandPlan:
    plan: StoredCommandPlan
    created: bool


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _decode(payload: str) -> StoredCommandPlan:
    # Canonical round-trip comparison rejects omitted/defaulted, unknown,
    # duplicate, or silently coerced persisted fields, including nested models.
    raw = json.loads(payload, object_pairs_hook=_reject_duplicate_keys)
    if type(raw) is not dict or type(raw.get("schema_version")) is not int:
        raise ValueError("missing or invalid plan schema version")
    if raw["schema_version"] != 1:
        raise ValueError("unsupported plan schema version")
    plan = StoredCommandPlan.model_validate_json(payload)
    if _canonical(plan.model_dump(mode="json")) != payload:
        raise ValueError("plan payload is not the exact canonical validated representation")
    return plan


_SCHEMA = """
CREATE TABLE IF NOT EXISTS prepared_command_plans (
    phase_execution_id TEXT NOT NULL PRIMARY KEY,
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL
)
"""


class SQLiteCommandPlanStore:
    """Explicit-path offline store, with atomic insert-or-compare and no updates.

    This store is not constructed at application startup. It neither opens Serial
    nor alters run state, command journals, or hardware position trust. SHA-256
    detects accidental corruption, not malicious edits by a database writer.
    """

    def __init__(self, database: str | Path) -> None:
        self._lock = RLock()
        self._connection = sqlite3.connect(database, isolation_level=None, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        try:
            self._connection.execute("PRAGMA synchronous = FULL")
            self._connection.execute(_SCHEMA)
            columns = self._connection.execute(
                "PRAGMA table_info(prepared_command_plans)"
            ).fetchall()
            actual = [(c["name"], c["type"], c["notnull"], c["pk"]) for c in columns]
            expected = [
                ("phase_execution_id", "TEXT", 1, 1),
                ("schema_version", "INTEGER", 1, 0),
                ("payload_json", "TEXT", 1, 0),
                ("payload_sha256", "TEXT", 1, 0),
            ]
            if actual != expected:
                raise PlanIntegrityError("incompatible prepared command plan table schema")
        except Exception:
            self._connection.close()
            raise

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> SQLiteCommandPlanStore:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def persist(self, source: PlanSource, context: CommandPlanningContext) -> PersistedCommandPlan:
        # Revalidate raw model values, including model_copy/model_construct
        # instances. Unknown nested fields must not disappear from provenance.
        source_data = _model_data(source)
        context_data = _model_data(context)
        source = PlanSource.model_validate(source_data)
        context = CommandPlanningContext.model_validate(context_data)
        source_json = _canonical(source_data)
        context_json = _canonical(context_data)
        if (
            _canonical(source.model_dump(mode="json")) != source_json
            or _canonical(context.model_dump(mode="json")) != context_json
        ):
            raise ValueError("source or assumptions lost information during validation")
        prepared = prepare_command_plan(source.plan.operations, context)
        candidate = StoredCommandPlan(source=source, prepared=prepared)
        payload = _canonical(candidate.model_dump(mode="json"))
        # Validate the precise representation we will later read after restart.
        candidate = _decode(payload)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        phase_id = candidate.phase_execution_id
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT * FROM prepared_command_plans WHERE phase_execution_id = ?",
                    (phase_id,),
                ).fetchone()
                created = row is None
                if row is None:
                    self._connection.execute(
                        "INSERT INTO prepared_command_plans VALUES (?, ?, ?, ?)",
                        (phase_id, 1, payload, digest),
                    )
                else:
                    candidate = self._read_row(row)
                    # Compare the entire payload, not a digest alone.
                    if row["payload_json"] != payload:
                        raise PlanIdentityConflictError(
                            "phase_execution_id was reused with different source, commands, or assumptions"
                        )
                self._connection.execute("COMMIT")
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
        return PersistedCommandPlan(candidate, created)

    def load(self, phase_execution_id: str) -> StoredCommandPlan | None:
        phase_id = _PHASE_ID_ADAPTER.validate_python(phase_execution_id)
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM prepared_command_plans WHERE phase_execution_id = ?", (phase_id,)
            ).fetchone()
            return None if row is None else self._read_row(row)

    @staticmethod
    def _read_row(row: sqlite3.Row) -> StoredCommandPlan:
        try:
            payload = row["payload_json"]
            if row["schema_version"] != 1 or not isinstance(payload, str):
                raise ValueError("unsupported plan record")
            digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            if digest != row["payload_sha256"]:
                raise ValueError("plan checksum mismatch")
            plan = _decode(payload)
            if plan.phase_execution_id != row["phase_execution_id"]:
                raise ValueError("stored phase identity mismatch")
            return plan
        except (ValueError, TypeError, KeyError, IndexError) as error:
            raise PlanIntegrityError("stored command plan cannot be trusted") from error
