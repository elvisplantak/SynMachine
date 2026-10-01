import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from app.demo.execution_lifecycle import (
    ExecutionIdAlreadyUsedError,
    PhaseExecutionClaimError,
    PhaseExecutionStartCommitResult,
    commit_phase_execution_start as commit_phase_execution_start_transition,
    claim_phase_execution as claim_phase_execution_transition,
)
from app.demo.events import DomainEvent
from app.demo.machine_events import MachineEvent, MachineEventType
from app.demo.machine_models import (
    MachineSnapshot,
    MachineState,
    PhaseExecutionIntent,
    PhaseExecutionOutcome,
    PhaseExecutionResult,
    PhaseExecutionStartupInterruptionKind,
)
from app.demo.phase_result_resolution import (
    ExecutionAlreadyResolvedError,
    NoActiveExecutionError,
    PhaseExecutionResolution,
    resolve_phase_execution as resolve_phase_execution_transition,
)
from app.demo.phases import EXECUTION_INTENT_PHASES, PAUSABLE_EXECUTION_PHASES, RunPhase
from app.demo.run_models import DemoRun, RunStatus
from app.demo.startup_execution_reconciliation import (
    StartupExecutionReconciliationError,
    StartupExecutionReconciliationResult,
    reconcile_interrupted_phase_execution_at_startup as reconcile_startup_transition,
)
from app.demo.startup_active_run_reconciliation import (
    StartupActiveRunReconciliationError,
    StartupActiveRunReconciliationResult,
    reconcile_interrupted_active_run_at_startup as reconcile_active_run_transition,
)

SCHEMA_VERSION = 1
RUN_AGGREGATE = "RUN"
MACHINE_AGGREGATE = "MACHINE"
MACHINE_AGGREGATE_ID = "machine"

_CREATE_SCHEMA = """
CREATE TABLE demo_runs (
    run_id TEXT NOT NULL PRIMARY KEY,
    snapshot_json TEXT NOT NULL,
    event_sequence INTEGER NOT NULL,
    status TEXT NOT NULL,
    phase TEXT NOT NULL
);

CREATE TABLE machine_snapshot (
    singleton_id INTEGER NOT NULL PRIMARY KEY CHECK (singleton_id = 1),
    snapshot_json TEXT NOT NULL,
    event_sequence INTEGER NOT NULL,
    state TEXT NOT NULL
);

CREATE TABLE domain_events (
    aggregate_type TEXT NOT NULL CHECK (aggregate_type IN ('RUN', 'MACHINE')),
    aggregate_id TEXT NOT NULL,
    event_sequence INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    run_status TEXT,
    run_phase TEXT,
    machine_state TEXT,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (aggregate_type, aggregate_id, event_sequence)
);
"""

_EXPECTED_COLUMNS = {
    "demo_runs": (
        ("run_id", "TEXT", 1, 1),
        ("snapshot_json", "TEXT", 1, 0),
        ("event_sequence", "INTEGER", 1, 0),
        ("status", "TEXT", 1, 0),
        ("phase", "TEXT", 1, 0),
    ),
    "machine_snapshot": (
        ("singleton_id", "INTEGER", 1, 1),
        ("snapshot_json", "TEXT", 1, 0),
        ("event_sequence", "INTEGER", 1, 0),
        ("state", "TEXT", 1, 0),
    ),
    "domain_events": (
        ("aggregate_type", "TEXT", 1, 1),
        ("aggregate_id", "TEXT", 1, 2),
        ("event_sequence", "INTEGER", 1, 3),
        ("event_type", "TEXT", 1, 0),
        ("occurred_at", "TEXT", 1, 0),
        ("run_status", "TEXT", 0, 0),
        ("run_phase", "TEXT", 0, 0),
        ("machine_state", "TEXT", 0, 0),
        ("payload_json", "TEXT", 1, 0),
    ),
}

_REQUIRED_CHECKS = {
    "machine_snapshot": "check(singleton_id=1)",
    "domain_events": "check(aggregate_typein('run','machine'))",
}


class PersistenceError(RuntimeError):
    """Base error for the SQLite persistence adapter."""


class PersistenceSchemaError(PersistenceError):
    """Raised when the database schema is missing, unsupported, or malformed."""


class PersistenceDataError(PersistenceError):
    """Raised when persisted JSON or metadata is inconsistent with domain models."""


class PersistenceConflictError(PersistenceError):
    """Raised for stale, duplicate, skipped, overlapping, or replayed writes."""


class StartupExecutionReconciliationConflictError(
    PersistenceConflictError,
    StartupExecutionReconciliationError,
):
    """Raised when startup execution reconciliation cannot consume a token."""


class StartupActiveRunReconciliationConflictError(
    PersistenceConflictError,
    StartupActiveRunReconciliationError,
):
    """Raised when startup active-run reconciliation cannot consume a run."""


class SQLiteStore:
    """Minimal synchronous SQLite snapshot and event store."""

    def __init__(self, database: str | Path = ":memory:") -> None:
        self._connection = sqlite3.connect(database, isolation_level=None)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        try:
            self._initialize_or_validate_schema()
        except Exception:
            self._connection.close()
            raise

    def __enter__(self) -> "SQLiteStore":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def load_demo_run(self, run_id: str) -> DemoRun | None:
        row = self._connection.execute(
            "SELECT * FROM demo_runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            self._validate_aggregate_consistency(RUN_AGGREGATE, run_id)
            return None
        run = self._parse_model(DemoRun, row["snapshot_json"], "demo run snapshot")
        if (
            run.run_id != row["run_id"]
            or run.event_sequence != row["event_sequence"]
            or run.status.value != row["status"]
            or run.phase.value != row["phase"]
        ):
            raise PersistenceDataError("demo run snapshot metadata does not match JSON")
        self._validate_aggregate_consistency(RUN_AGGREGATE, run_id)
        return run

    def load_machine_snapshot(self) -> MachineSnapshot | None:
        row = self._connection.execute(
            "SELECT * FROM machine_snapshot WHERE singleton_id = 1"
        ).fetchone()
        if row is None:
            self._validate_aggregate_consistency(
                MACHINE_AGGREGATE, MACHINE_AGGREGATE_ID
            )
            return None
        machine = self._parse_model(
            MachineSnapshot, row["snapshot_json"], "machine snapshot"
        )
        if (
            machine.event_sequence != row["event_sequence"]
            or machine.state.value != row["state"]
        ):
            raise PersistenceDataError("machine snapshot metadata does not match JSON")
        self._validate_aggregate_consistency(
            MACHINE_AGGREGATE, MACHINE_AGGREGATE_ID
        )
        return machine

    def load_events(
        self,
        aggregate_type: Literal["RUN", "MACHINE"] | None = None,
        aggregate_id: str | None = None,
    ) -> tuple[DomainEvent | MachineEvent, ...]:
        if aggregate_id is not None and aggregate_type is None:
            raise ValueError("aggregate_type is required when aggregate_id is supplied")

        query = "SELECT rowid, * FROM domain_events"
        parameters: tuple[object, ...] = ()
        if aggregate_type is not None and aggregate_id is not None:
            query += " WHERE aggregate_type = ? AND aggregate_id = ?"
            parameters = (aggregate_type, aggregate_id)
        elif aggregate_type is not None:
            query += " WHERE aggregate_type = ?"
            parameters = (aggregate_type,)
        query += " ORDER BY rowid"

        rows = self._connection.execute(query, parameters).fetchall()
        keys = {(row["aggregate_type"], row["aggregate_id"]) for row in rows}
        if aggregate_type is not None and aggregate_id is not None:
            keys.add((aggregate_type, aggregate_id))
        else:
            if aggregate_type in {None, RUN_AGGREGATE}:
                run_rows = self._connection.execute(
                    "SELECT run_id FROM demo_runs"
                ).fetchall()
                keys.update((RUN_AGGREGATE, row["run_id"]) for row in run_rows)
            if aggregate_type in {None, MACHINE_AGGREGATE}:
                machine_row = self._connection.execute(
                    "SELECT singleton_id FROM machine_snapshot WHERE singleton_id = 1"
                ).fetchone()
                if machine_row is not None:
                    keys.add((MACHINE_AGGREGATE, MACHINE_AGGREGATE_ID))
        for stored_type, stored_id in keys:
            self._validate_aggregate_consistency(stored_type, stored_id)
        return tuple(self._event_from_row(row) for row in rows)

    def persist_run_transition(
        self, run: DemoRun, events: Sequence[DomainEvent]
    ) -> None:
        self._validate_run_transition(run, events)
        self._persist_transition(
            aggregate_type=RUN_AGGREGATE,
            aggregate_id=run.run_id,
            snapshot=run,
            events=events,
        )

    def persist_run_transition_and_load_machine(
        self,
        run: DemoRun,
        events: Sequence[DomainEvent],
    ) -> MachineSnapshot:
        self._validate_run_transition(run, events)
        normalized_events = self._normalize_events(events)

        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._write_transition(
                RUN_AGGREGATE,
                run.run_id,
                run,
                normalized_events,
            )
            machine = self.load_machine_snapshot()
            if machine is None:
                raise PersistenceConflictError("machine snapshot was not found")
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        return machine

    def persist_machine_transition(
        self, machine: MachineSnapshot, events: Sequence[MachineEvent]
    ) -> None:
        self._validate_machine_transition(machine, events)
        self._persist_transition(
            aggregate_type=MACHINE_AGGREGATE,
            aggregate_id=MACHINE_AGGREGATE_ID,
            snapshot=machine,
            events=events,
        )

    def persist_run_transition_with_machine_precondition(
        self,
        run: DemoRun,
        events: Sequence[DomainEvent],
        *,
        expected_machine_event_sequence: int,
    ) -> None:
        self._validate_run_transition(run, events)
        normalized_events = self._normalize_events(events)

        self._connection.execute("BEGIN IMMEDIATE")
        try:
            machine = self.load_machine_snapshot()
            if machine is None:
                raise PersistenceConflictError("machine snapshot was not found")
            if machine.event_sequence != expected_machine_event_sequence:
                raise PersistenceConflictError(
                    "machine event sequence precondition failed"
                )
            self._write_transition(
                RUN_AGGREGATE,
                run.run_id,
                run,
                normalized_events,
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    def claim_phase_execution(
        self,
        *,
        run_id: str,
        execution_id: str,
        claimed_at: datetime,
        expected_run_event_sequence: int,
        expected_phase: RunPhase,
    ) -> PhaseExecutionIntent:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            run = self.load_demo_run(run_id)
            if run is None:
                raise PhaseExecutionClaimError(
                    f"Guided Demo run {run_id!r} was not found"
                )
            if run.phase != expected_phase:
                raise PersistenceConflictError(
                    "run phase precondition failed"
                )
            if run.event_sequence != expected_run_event_sequence:
                raise PersistenceConflictError(
                    "run event sequence precondition failed"
                )
            machine = self.load_machine_snapshot()
            if machine is None:
                raise PhaseExecutionClaimError(
                    "machine snapshot was not found"
                )
            machine_events = self.load_events(
                MACHINE_AGGREGATE, MACHINE_AGGREGATE_ID
            )
            self._validate_startup_interruption_history(machine_events)
            self._validate_active_execution_start_history(
                machine, machine_events
            )
            active_execution = machine.active_execution
            if active_execution is not None:
                if active_execution.execution_id in self._resolved_execution_ids(
                    machine_events
                ):
                    raise PersistenceDataError(
                        "active execution is already historically resolved"
                    )
                if (
                    active_execution.execution_id
                    in self._startup_interrupted_execution_ids(machine_events)
                ):
                    raise PersistenceDataError(
                        "active execution is already historically interrupted"
                    )
            used_ids = {
                event.execution_id
                for event in machine_events
                if isinstance(event, MachineEvent)
                and event.event_type
                in {
                    MachineEventType.PHASE_EXECUTION_CLAIMED,
                    MachineEventType.PHASE_EXECUTION_RESOLVED,
                    MachineEventType.PHASE_EXECUTION_INTERRUPTED_AT_STARTUP,
                }
            }
            if execution_id in used_ids:
                raise ExecutionIdAlreadyUsedError(
                    f"execution_id {execution_id!r} was already used"
                )
            result = claim_phase_execution_transition(
                run,
                machine,
                execution_id=execution_id,
                claimed_at=claimed_at,
            )
            self._validate_machine_transition(result.machine, result.events)
            normalized_events = self._normalize_events(result.events)
            self._write_transition(
                MACHINE_AGGREGATE,
                MACHINE_AGGREGATE_ID,
                result.machine,
                normalized_events,
            )
            active_execution = result.machine.active_execution
            if active_execution is None:
                raise PersistenceDataError(
                    "phase execution claim did not persist an active execution"
                )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

        return active_execution

    def resolve_phase_execution(
        self,
        result: PhaseExecutionResult,
        *,
        defer_paused_wait: bool = False,
    ) -> PhaseExecutionResolution | None:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            machine = self.load_machine_snapshot()
            if machine is None:
                raise PersistenceConflictError("machine snapshot was not found")
            machine_events = self.load_events(
                MACHINE_AGGREGATE, MACHINE_AGGREGATE_ID
            )
            self._validate_startup_interruption_history(machine_events)
            self._validate_active_execution_start_history(
                machine, machine_events
            )
            resolved_ids = self._resolved_execution_ids(machine_events)
            interrupted_ids = self._startup_interrupted_execution_ids(
                machine_events
            )
            intent = machine.active_execution
            if intent is not None and intent.execution_id in resolved_ids:
                raise PersistenceDataError(
                    "active execution is already historically resolved"
                )
            if intent is not None and intent.execution_id in interrupted_ids:
                raise PersistenceDataError(
                    "active execution is already historically interrupted"
                )
            if result.execution_id in resolved_ids:
                raise ExecutionAlreadyResolvedError(
                    "EXECUTION_ALREADY_RESOLVED"
                )
            if result.execution_id in interrupted_ids:
                raise ExecutionAlreadyResolvedError(
                    "EXECUTION_ALREADY_TERMINALLY_CONSUMED"
                )
            if intent is None:
                raise NoActiveExecutionError("NO_ACTIVE_EXECUTION")
            run_id = intent.run_id
            run = self.load_demo_run(run_id)
            if run is None:
                raise PersistenceConflictError(
                    f"Guided Demo run {run_id!r} was not found"
                )
            if (
                defer_paused_wait
                and run.status is RunStatus.PAUSED
                and run.phase in PAUSABLE_EXECUTION_PHASES
                and result.outcome is PhaseExecutionOutcome.COMPLETED
            ):
                # Validate the token, timestamps, start evidence and aggregate using
                # the existing resolver, without persisting any hypothetical result.
                resolve_phase_execution_transition(
                    run.model_copy(update={"status": RunStatus.RUNNING}), machine, result
                )
                self._connection.execute("COMMIT")
                return None  # The caller retains ownership until Resume or Stop.
            resolution = resolve_phase_execution_transition(run, machine, result)
            self._validate_phase_execution_resolution(
                resolution,
                active_execution=intent,
                result=result,
                previous_machine_sequence=machine.event_sequence,
            )
            self._validate_run_transition(
                resolution.run, resolution.run_events
            )
            self._validate_machine_transition(
                resolution.machine, resolution.machine_events
            )
            self._write_transition(
                RUN_AGGREGATE,
                resolution.run.run_id,
                resolution.run,
                self._normalize_events(resolution.run_events),
            )
            self._write_transition(
                MACHINE_AGGREGATE,
                MACHINE_AGGREGATE_ID,
                resolution.machine,
                self._normalize_events(resolution.machine_events),
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        return resolution

    def commit_phase_execution_start(
        self,
        intent: PhaseExecutionIntent,
        *,
        expected_run_event_sequence: int,
        expected_phase: RunPhase,
        start_committed_at: datetime,
    ) -> PhaseExecutionStartCommitResult:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            run = self.load_demo_run(intent.run_id)
            if run is None:
                raise PersistenceConflictError(
                    f"Guided Demo run {intent.run_id!r} was not found"
                )
            machine = self.load_machine_snapshot()
            if machine is None:
                raise PersistenceConflictError(
                    "machine snapshot was not found"
                )
            machine_events = self.load_events(
                MACHINE_AGGREGATE, MACHINE_AGGREGATE_ID
            )
            self._validate_startup_interruption_history(machine_events)
            self._validate_active_execution_start_history(
                machine, machine_events
            )
            result = commit_phase_execution_start_transition(
                run,
                machine,
                intent,
                expected_run_event_sequence=expected_run_event_sequence,
                expected_phase=expected_phase,
                start_committed_at=start_committed_at,
            )
            if result.events:
                self._validate_machine_transition(
                    result.machine, result.events
                )
                self._write_transition(
                    MACHINE_AGGREGATE,
                    MACHINE_AGGREGATE_ID,
                    result.machine,
                    self._normalize_events(result.events),
                )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        return result

    def reconcile_interrupted_phase_execution_at_startup(
        self,
        occurred_at: datetime,
    ) -> StartupExecutionReconciliationResult:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            machine = self.load_machine_snapshot()
            if machine is None:
                raise StartupExecutionReconciliationConflictError(
                    "machine snapshot was not found"
                )
            if (
                machine.state is not MachineState.BUSY
                or machine.active_run_id is None
                or machine.active_execution is None
            ):
                raise StartupExecutionReconciliationConflictError(
                    "startup execution reconciliation requires BUSY machine "
                    "with an active run and execution"
                )
            machine_events = self.load_events(
                MACHINE_AGGREGATE, MACHINE_AGGREGATE_ID
            )
            self._validate_startup_interruption_history(machine_events)
            self._validate_active_execution_start_history(
                machine, machine_events
            )
            intent = machine.active_execution
            if intent.execution_id in self._terminal_execution_ids(machine_events):
                raise PersistenceDataError(
                    "active execution is already historically terminal"
                )
            run = self.load_demo_run(machine.active_run_id)
            if run is None:
                raise StartupExecutionReconciliationConflictError(
                    f"Guided Demo run {machine.active_run_id!r} was not found"
                )
            if (
                run.run_id != intent.run_id
                or run.phase != intent.phase
                or run.phase not in EXECUTION_INTENT_PHASES
            ):
                raise StartupExecutionReconciliationConflictError(
                    "startup execution reconciliation requires matching "
                    "run and execution"
                )
            try:
                reconciliation = reconcile_startup_transition(
                    run, machine, occurred_at
                )
            except StartupExecutionReconciliationError as error:
                raise StartupExecutionReconciliationConflictError(
                    str(error)
                ) from error
            self._validate_run_transition(
                reconciliation.run, reconciliation.run_events
            )
            self._validate_machine_transition(
                reconciliation.machine, reconciliation.machine_events
            )
            self._validate_startup_reconciliation(
                reconciliation,
                active_execution=intent,
                previous_machine_sequence=machine.event_sequence,
            )
            self._write_transition(
                RUN_AGGREGATE,
                reconciliation.run.run_id,
                reconciliation.run,
                self._normalize_events(reconciliation.run_events),
            )
            self._write_transition(
                MACHINE_AGGREGATE,
                MACHINE_AGGREGATE_ID,
                reconciliation.machine,
                self._normalize_events(reconciliation.machine_events),
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        return reconciliation

    def reconcile_interrupted_active_run_at_startup(
        self,
        occurred_at: datetime,
    ) -> StartupActiveRunReconciliationResult:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            machine = self.load_machine_snapshot()
            if machine is None:
                raise StartupActiveRunReconciliationConflictError(
                    "machine snapshot was not found"
                )
            if (
                machine.state is not MachineState.BUSY
                or machine.active_run_id is None
                or machine.active_execution is not None
            ):
                raise StartupActiveRunReconciliationConflictError(
                    "startup active-run reconciliation requires BUSY machine "
                    "with an active run and no active execution"
                )
            self.load_events(MACHINE_AGGREGATE, MACHINE_AGGREGATE_ID)
            run = self.load_demo_run(machine.active_run_id)
            if run is None:
                raise StartupActiveRunReconciliationConflictError(
                    f"Guided Demo run {machine.active_run_id!r} was not found"
                )
            self.load_events(RUN_AGGREGATE, run.run_id)
            try:
                reconciliation = reconcile_active_run_transition(
                    run, machine, occurred_at
                )
            except StartupActiveRunReconciliationError as error:
                raise StartupActiveRunReconciliationConflictError(
                    str(error)
                ) from error
            self._validate_run_transition(
                reconciliation.run, reconciliation.run_events
            )
            self._validate_machine_transition(
                reconciliation.machine, reconciliation.machine_events
            )
            self._validate_active_run_startup_reconciliation(
                reconciliation,
                previous_active_run_id=machine.active_run_id,
                previous_machine_sequence=machine.event_sequence,
            )
            self._write_transition(
                RUN_AGGREGATE,
                reconciliation.run.run_id,
                reconciliation.run,
                self._normalize_events(reconciliation.run_events),
            )
            self._write_transition(
                MACHINE_AGGREGATE,
                MACHINE_AGGREGATE_ID,
                reconciliation.machine,
                self._normalize_events(reconciliation.machine_events),
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        return reconciliation

    @staticmethod
    def _validate_active_run_startup_reconciliation(
        reconciliation: StartupActiveRunReconciliationResult,
        *,
        previous_active_run_id: str,
        previous_machine_sequence: int,
    ) -> None:
        if len(reconciliation.machine_events) != 1:
            raise PersistenceConflictError(
                "active-run startup reconciliation requires exactly one "
                "machine event"
            )
        event = reconciliation.machine_events[0]
        comparisons = (
            (
                "event type",
                event.event_type,
                MachineEventType.RUN_INTERRUPTED_AT_STARTUP,
            ),
            (
                "event sequence",
                event.sequence_number,
                previous_machine_sequence + 1,
            ),
            ("event machine state", event.machine_state, reconciliation.machine.state),
            ("machine state", reconciliation.machine.state, MachineState.RECOVERING),
            ("event run ID", event.run_id, previous_active_run_id),
            (
                "interrupted run ID",
                reconciliation.machine.interrupted_run_id,
                previous_active_run_id,
            ),
            (
                "event and interrupted run ID",
                event.run_id,
                reconciliation.machine.interrupted_run_id,
            ),
            ("run ID", reconciliation.run.run_id, previous_active_run_id),
            ("active run ID", reconciliation.machine.active_run_id, None),
            ("active execution", reconciliation.machine.active_execution, None),
            ("event runtime fault reason", event.runtime_fault_reason, None),
            (
                "snapshot runtime fault reason",
                reconciliation.machine.runtime_fault_reason,
                None,
            ),
            ("event startup recovery reason", event.startup_recovery_reason, None),
            (
                "snapshot startup recovery reason",
                reconciliation.machine.startup_recovery_reason,
                None,
            ),
            ("event hardware outcome unknown", event.hardware_outcome_unknown, False),
            (
                "snapshot hardware outcome unknown",
                reconciliation.machine.hardware_outcome_unknown,
                False,
            ),
            (
                "event carousel position untrusted",
                event.carousel_position_untrusted,
                False,
            ),
            (
                "snapshot carousel position untrusted",
                reconciliation.machine.carousel_position_untrusted,
                False,
            ),
        )
        for field_name, actual, expected in comparisons:
            if actual != expected:
                raise PersistenceConflictError(
                    f"active-run startup reconciliation audit {field_name} mismatch"
                )

    @staticmethod
    def _resolved_execution_ids(
        events: Sequence[DomainEvent | MachineEvent],
    ) -> set[str | None]:
        return {
            event.execution_id
            for event in events
            if isinstance(event, MachineEvent)
            and event.event_type is MachineEventType.PHASE_EXECUTION_RESOLVED
        }

    @staticmethod
    def _startup_interrupted_execution_ids(
        events: Sequence[DomainEvent | MachineEvent],
    ) -> set[str | None]:
        return {
            event.execution_id
            for event in events
            if isinstance(event, MachineEvent)
            and event.event_type
            is MachineEventType.PHASE_EXECUTION_INTERRUPTED_AT_STARTUP
        }

    @classmethod
    def _terminal_execution_ids(
        cls,
        events: Sequence[DomainEvent | MachineEvent],
    ) -> set[str | None]:
        return cls._resolved_execution_ids(
            events
        ) | cls._startup_interrupted_execution_ids(events)

    @staticmethod
    def _validate_startup_interruption_history(
        events: Sequence[DomainEvent | MachineEvent],
    ) -> None:
        machine_events = tuple(
            event for event in events if isinstance(event, MachineEvent)
        )
        interruptions = tuple(
            event
            for event in machine_events
            if event.event_type
            is MachineEventType.PHASE_EXECUTION_INTERRUPTED_AT_STARTUP
        )
        for interruption in interruptions:
            claims = tuple(
                event
                for event in machine_events
                if event.event_type is MachineEventType.PHASE_EXECUTION_CLAIMED
                and event.execution_id == interruption.execution_id
            )
            if len(claims) != 1:
                raise PersistenceDataError(
                    "startup interruption requires exactly one matching claim"
                )
            claim = claims[0]
            comparisons = (
                ("run_id", interruption.run_id, claim.run_id),
                (
                    "execution_phase",
                    interruption.execution_phase,
                    claim.execution_phase,
                ),
                (
                    "execution_claimed_at",
                    interruption.execution_claimed_at,
                    claim.occurred_at,
                ),
            )
            for field_name, actual, expected in comparisons:
                if actual != expected:
                    raise PersistenceDataError(
                        f"startup interruption {field_name} does not match claim"
                    )
            starts = tuple(
                event
                for event in machine_events
                if event.event_type
                is MachineEventType.PHASE_EXECUTION_START_COMMITTED
                and event.execution_id == interruption.execution_id
            )
            if (
                interruption.startup_interruption_kind
                is PhaseExecutionStartupInterruptionKind.CLAIMED_NOT_STARTED
            ):
                if starts:
                    raise PersistenceDataError(
                        "claimed-not-started interruption has a start-commit event"
                    )
            else:
                if len(starts) != 1:
                    raise PersistenceDataError(
                        "start-committed interruption requires exactly one "
                        "matching start event"
                    )
                start = starts[0]
                start_comparisons = (
                    ("run_id", interruption.run_id, start.run_id),
                    (
                        "execution_phase",
                        interruption.execution_phase,
                        start.execution_phase,
                    ),
                    (
                        "execution_claimed_at",
                        interruption.execution_claimed_at,
                        start.execution_claimed_at,
                    ),
                    (
                        "execution_start_committed_at",
                        interruption.execution_start_committed_at,
                        start.occurred_at,
                    ),
                )
                for field_name, actual, expected in start_comparisons:
                    if actual != expected:
                        raise PersistenceDataError(
                            f"startup interruption {field_name} does not "
                            "match start event"
                        )
            terminals = tuple(
                event
                for event in machine_events
                if event.execution_id == interruption.execution_id
                and event.event_type
                in {
                    MachineEventType.PHASE_EXECUTION_RESOLVED,
                    MachineEventType.PHASE_EXECUTION_INTERRUPTED_AT_STARTUP,
                }
            )
            if terminals != (interruption,):
                raise PersistenceDataError(
                    "startup-interrupted execution must have exactly one "
                    "terminal event"
                )

    @staticmethod
    def _validate_active_execution_start_history(
        machine: MachineSnapshot,
        events: Sequence[DomainEvent | MachineEvent],
    ) -> None:
        active = machine.active_execution
        if active is None:
            return
        claims = tuple(
            event
            for event in events
            if isinstance(event, MachineEvent)
            and event.event_type is MachineEventType.PHASE_EXECUTION_CLAIMED
            and event.execution_id == active.execution_id
        )
        if len(claims) != 1:
            raise PersistenceDataError(
                "active execution requires exactly one matching claim event"
            )
        claim = claims[0]
        claim_comparisons = (
            ("execution_id", claim.execution_id, active.execution_id),
            ("run_id", claim.run_id, active.run_id),
            ("execution_phase", claim.execution_phase, active.phase),
            ("occurred_at", claim.occurred_at, active.claimed_at),
        )
        for field_name, event_value, active_value in claim_comparisons:
            if event_value != active_value:
                raise PersistenceDataError(
                    f"active execution claim event {field_name} does not "
                    f"match active execution {field_name}"
                )
        matching = tuple(
            event
            for event in events
            if isinstance(event, MachineEvent)
            and event.event_type
            is MachineEventType.PHASE_EXECUTION_START_COMMITTED
            and event.execution_id == active.execution_id
        )
        if active.start_committed_at is None:
            if matching:
                raise PersistenceDataError(
                    "active execution start is historically committed"
                )
            return
        if len(matching) != 1:
            raise PersistenceDataError(
                "start-committed active execution requires exactly one "
                "matching start event"
            )
        event = matching[0]
        comparisons = (
            ("execution_id", event.execution_id, active.execution_id),
            ("run_id", event.run_id, active.run_id),
            ("execution_phase", event.execution_phase, active.phase),
            (
                "execution_claimed_at",
                event.execution_claimed_at,
                active.claimed_at,
            ),
            ("occurred_at", event.occurred_at, active.start_committed_at),
        )
        for field_name, event_value, active_value in comparisons:
            if event_value != active_value:
                raise PersistenceDataError(
                    f"active execution start event {field_name} does not "
                    f"match active execution {field_name}"
                )

    @staticmethod
    def _validate_startup_reconciliation(
        reconciliation: StartupExecutionReconciliationResult,
        *,
        active_execution: PhaseExecutionIntent,
        previous_machine_sequence: int,
    ) -> None:
        if len(reconciliation.machine_events) != 1:
            raise PersistenceConflictError(
                "startup reconciliation requires exactly one machine event"
            )
        event = reconciliation.machine_events[0]
        comparisons = (
            (
                "event_type",
                event.event_type,
                MachineEventType.PHASE_EXECUTION_INTERRUPTED_AT_STARTUP,
            ),
            (
                "sequence_number",
                event.sequence_number,
                previous_machine_sequence + 1,
            ),
            ("execution_id", event.execution_id, active_execution.execution_id),
            ("run_id", event.run_id, active_execution.run_id),
            ("execution_phase", event.execution_phase, active_execution.phase),
            (
                "execution_claimed_at",
                event.execution_claimed_at,
                active_execution.claimed_at,
            ),
            (
                "execution_start_committed_at",
                event.execution_start_committed_at,
                active_execution.start_committed_at,
            ),
            (
                "startup_interruption_kind",
                event.startup_interruption_kind,
                reconciliation.interruption_kind,
            ),
            ("machine_state", event.machine_state, reconciliation.machine.state),
        )
        for field_name, actual, expected in comparisons:
            if actual != expected:
                raise PersistenceConflictError(
                    f"startup reconciliation audit {field_name} mismatch"
                )
        if reconciliation.machine.active_execution is not None:
            raise PersistenceConflictError(
                "startup reconciliation must clear active_execution"
            )

    @staticmethod
    def _validate_phase_execution_resolution(
        resolution: PhaseExecutionResolution,
        *,
        active_execution: PhaseExecutionIntent,
        result: PhaseExecutionResult,
        previous_machine_sequence: int,
    ) -> None:
        if not resolution.machine_events:
            raise PersistenceConflictError(
                "phase execution resolution requires a machine audit event"
            )
        event = resolution.machine_events[0]
        if event.event_type is not MachineEventType.PHASE_EXECUTION_RESOLVED:
            raise PersistenceConflictError(
                "phase execution resolution must begin with PHASE_EXECUTION_RESOLVED"
            )
        if (
            sum(
                machine_event.event_type
                is MachineEventType.PHASE_EXECUTION_RESOLVED
                for machine_event in resolution.machine_events
            )
            != 1
        ):
            raise PersistenceConflictError(
                "phase execution resolution requires exactly one resolution audit"
            )
        comparisons = (
            ("sequence_number", event.sequence_number, previous_machine_sequence + 1),
            ("machine_state", event.machine_state, MachineState.BUSY),
            ("execution_id", event.execution_id, active_execution.execution_id),
            ("run_id", event.run_id, active_execution.run_id),
            ("execution_phase", event.execution_phase, active_execution.phase),
            (
                "execution_claimed_at",
                event.execution_claimed_at,
                active_execution.claimed_at,
            ),
            ("execution_outcome", event.execution_outcome, result.outcome),
            ("occurred_at", event.occurred_at, result.reported_at),
            (
                "runtime_fault_reason",
                event.runtime_fault_reason,
                result.runtime_fault_reason,
            ),
            ("failure_reason", event.failure_reason, result.failure_reason),
            (
                "cleanup_failure_reason",
                event.cleanup_failure_reason,
                result.cleanup_failure_reason,
            ),
            (
                "primary_failure_reason",
                event.primary_failure_reason,
                result.primary_failure_reason,
            ),
        )
        for field_name, actual, expected in comparisons:
            if actual != expected:
                raise PersistenceConflictError(
                    f"phase resolution audit {field_name} mismatch"
                )
        if resolution.machine.active_execution is not None:
            raise PersistenceConflictError(
                "phase execution resolution must clear active_execution"
            )

    def persist_run_and_machine_transition(
        self,
        run: DemoRun,
        run_events: Sequence[DomainEvent],
        machine: MachineSnapshot,
        machine_events: Sequence[MachineEvent],
    ) -> None:
        self._validate_run_transition(run, run_events)
        self._validate_machine_transition(machine, machine_events)
        normalized_run_events = self._normalize_events(run_events)
        normalized_machine_events = self._normalize_events(machine_events)

        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._write_transition(
                RUN_AGGREGATE, run.run_id, run, normalized_run_events
            )
            self._write_transition(
                MACHINE_AGGREGATE,
                MACHINE_AGGREGATE_ID,
                machine,
                normalized_machine_events,
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _validate_run_transition(
        run: DemoRun, events: Sequence[DomainEvent]
    ) -> None:
        if any(event.run_id != run.run_id for event in events):
            raise PersistenceConflictError("run event run_id does not match snapshot run_id")
        if events:
            final_event = events[-1]
            if final_event.run_status != run.status:
                raise PersistenceConflictError(
                    "final run event status does not match snapshot status"
                )
            if final_event.run_phase != run.phase:
                raise PersistenceConflictError(
                    "final run event phase does not match snapshot phase"
                )

    @staticmethod
    def _validate_machine_transition(
        machine: MachineSnapshot, events: Sequence[MachineEvent]
    ) -> None:
        if events:
            final_event = events[-1]
            comparisons = (
                ("state", final_event.machine_state, machine.state),
                (
                    "runtime_fault_reason",
                    final_event.runtime_fault_reason,
                    machine.runtime_fault_reason,
                ),
                (
                    "startup_recovery_reason",
                    final_event.startup_recovery_reason,
                    machine.startup_recovery_reason,
                ),
                (
                    "hardware_outcome_unknown",
                    final_event.hardware_outcome_unknown,
                    machine.hardware_outcome_unknown,
                ),
                (
                    "carousel_position_untrusted",
                    final_event.carousel_position_untrusted,
                    machine.carousel_position_untrusted,
                ),
            )
            for field_name, event_value, snapshot_value in comparisons:
                if event_value != snapshot_value:
                    raise PersistenceConflictError(
                        f"final machine event {field_name} does not match "
                        f"snapshot {field_name}"
                    )
            active_execution = machine.active_execution
            if final_event.event_type is MachineEventType.PHASE_EXECUTION_CLAIMED:
                if active_execution is None:
                    raise PersistenceConflictError(
                        "final machine claim event requires snapshot active_execution"
                    )
                execution_comparisons = (
                    (
                        "execution_id",
                        final_event.execution_id,
                        active_execution.execution_id,
                    ),
                    ("run_id", final_event.run_id, active_execution.run_id),
                    (
                        "execution_phase",
                        final_event.execution_phase,
                        active_execution.phase,
                    ),
                    (
                        "occurred_at",
                        final_event.occurred_at,
                        active_execution.claimed_at,
                    ),
                )
                for field_name, event_value, snapshot_value in execution_comparisons:
                    if event_value != snapshot_value:
                        raise PersistenceConflictError(
                            f"final machine event {field_name} does not match "
                            f"snapshot active_execution {field_name}"
                        )
            elif (
                final_event.event_type
                is MachineEventType.PHASE_EXECUTION_START_COMMITTED
            ):
                if active_execution is None:
                    raise PersistenceConflictError(
                        "start-commit event requires snapshot active_execution"
                    )
                execution_comparisons = (
                    (
                        "execution_id",
                        final_event.execution_id,
                        active_execution.execution_id,
                    ),
                    ("run_id", final_event.run_id, active_execution.run_id),
                    (
                        "execution_phase",
                        final_event.execution_phase,
                        active_execution.phase,
                    ),
                    (
                        "execution_claimed_at",
                        final_event.execution_claimed_at,
                        active_execution.claimed_at,
                    ),
                    (
                        "occurred_at",
                        final_event.occurred_at,
                        active_execution.start_committed_at,
                    ),
                )
                for field_name, event_value, snapshot_value in execution_comparisons:
                    if event_value != snapshot_value:
                        raise PersistenceConflictError(
                            f"final machine event {field_name} does not match "
                            f"snapshot active_execution {field_name}"
                        )
            elif final_event.event_type in {
                MachineEventType.PHASE_EXECUTION_RESOLVED,
                MachineEventType.PHASE_EXECUTION_INTERRUPTED_AT_STARTUP,
            }:
                if active_execution is not None:
                    raise PersistenceConflictError(
                        "terminal machine event requires cleared active_execution"
                    )
            else:
                if (
                    final_event.execution_id is not None
                    or final_event.execution_phase is not None
                ):
                    raise PersistenceConflictError(
                        "non-claim machine event must not contain execution metadata"
                    )
                if active_execution is not None:
                    raise PersistenceConflictError(
                        "snapshot active_execution requires final "
                        "PHASE_EXECUTION_CLAIMED event"
                    )

    def _initialize_or_validate_schema(self) -> None:
        version = self._connection.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            existing_tables = self._user_tables()
            if existing_tables:
                raise PersistenceSchemaError(
                    "database has user_version 0 but already contains tables: "
                    + ", ".join(existing_tables)
                )
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                for statement in _CREATE_SCHEMA.split(";"):
                    if statement.strip():
                        self._connection.execute(statement)
                self._connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                self._validate_schema_structure()
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
            return
        if version != SCHEMA_VERSION:
            raise PersistenceSchemaError(
                f"unsupported schema version {version}; expected {SCHEMA_VERSION}"
            )
        self._validate_schema_structure()

    def _validate_schema_structure(self) -> None:
        tables = self._user_tables()
        if tuple(tables) != tuple(sorted(_EXPECTED_COLUMNS)):
            raise PersistenceSchemaError(
                f"unexpected schema tables {tables!r}; expected {sorted(_EXPECTED_COLUMNS)!r}"
            )
        for table, expected in _EXPECTED_COLUMNS.items():
            rows = self._connection.execute(f'PRAGMA table_info("{table}")').fetchall()
            actual = tuple(
                (row["name"], row["type"].upper(), row["notnull"], row["pk"])
                for row in rows
            )
            if actual != expected:
                raise PersistenceSchemaError(
                    f"table {table!r} has unexpected structure {actual!r}; expected {expected!r}"
                )
        for table, required_check in _REQUIRED_CHECKS.items():
            row = self._connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).fetchone()
            normalized_sql = "".join(row["sql"].lower().split())
            if required_check not in normalized_sql:
                raise PersistenceSchemaError(
                    f"table {table!r} is missing required CHECK constraint"
                )

    def _user_tables(self) -> list[str]:
        rows = self._connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return [row["name"] for row in rows]

    def _persist_transition(
        self,
        *,
        aggregate_type: Literal["RUN", "MACHINE"],
        aggregate_id: str,
        snapshot: DemoRun | MachineSnapshot,
        events: Sequence[DomainEvent] | Sequence[MachineEvent],
    ) -> None:
        normalized_events = self._normalize_events(events)

        self._connection.execute("BEGIN IMMEDIATE")
        try:
            self._write_transition(
                aggregate_type, aggregate_id, snapshot, normalized_events
            )
            self._connection.execute("COMMIT")
        except Exception:
            self._connection.execute("ROLLBACK")
            raise

    def _write_transition(
        self,
        aggregate_type: Literal["RUN", "MACHINE"],
        aggregate_id: str,
        snapshot: DemoRun | MachineSnapshot,
        events: Sequence[DomainEvent] | Sequence[MachineEvent],
    ) -> None:
        current_sequence = self._current_sequence(aggregate_type, aggregate_id)
        expected_sequences = tuple(
            range(current_sequence + 1, current_sequence + len(events) + 1)
        )
        actual_sequences = tuple(event.sequence_number for event in events)
        if actual_sequences != expected_sequences:
            raise PersistenceConflictError(
                f"event sequence conflict for {aggregate_type}/{aggregate_id}: "
                f"expected {expected_sequences}, got {actual_sequences}"
            )
        if snapshot.event_sequence != actual_sequences[-1]:
            raise PersistenceConflictError(
                "snapshot event_sequence must equal the final event sequence"
            )

        for event in events:
            self._insert_event(aggregate_type, aggregate_id, event)
        self._write_snapshot(aggregate_type, aggregate_id, snapshot, current_sequence)

    def _normalize_events(
        self, events: Sequence[DomainEvent] | Sequence[MachineEvent]
    ) -> tuple[DomainEvent | MachineEvent, ...]:
        if not events:
            raise PersistenceConflictError("transition must contain at least one event")
        return tuple(self._normalize_event(event) for event in events)

    def _current_sequence(
        self, aggregate_type: Literal["RUN", "MACHINE"], aggregate_id: str
    ) -> int:
        return self._validate_aggregate_consistency(aggregate_type, aggregate_id)

    def _validate_aggregate_consistency(
        self, aggregate_type: str, aggregate_id: str
    ) -> int:
        if aggregate_type == RUN_AGGREGATE:
            snapshot_row = self._connection.execute(
                "SELECT event_sequence FROM demo_runs WHERE run_id = ?", (aggregate_id,)
            ).fetchone()
        else:
            snapshot_row = self._connection.execute(
                "SELECT event_sequence FROM machine_snapshot WHERE singleton_id = 1"
            ).fetchone()
        event_rows = self._connection.execute(
            "SELECT event_sequence FROM domain_events "
            "WHERE aggregate_type = ? AND aggregate_id = ? ORDER BY event_sequence",
            (aggregate_type, aggregate_id),
        ).fetchall()
        sequences = tuple(row["event_sequence"] for row in event_rows)
        if snapshot_row is None and sequences:
            raise PersistenceDataError(
                f"events exist without snapshot for {aggregate_type}/{aggregate_id}"
            )
        if snapshot_row is not None and not sequences:
            raise PersistenceDataError(
                f"snapshot exists without event history for {aggregate_type}/{aggregate_id}"
            )
        if snapshot_row is None:
            return 0
        snapshot_sequence = snapshot_row["event_sequence"]
        if sequences != tuple(range(1, len(sequences) + 1)):
            raise PersistenceDataError(
                f"non-contiguous event history for {aggregate_type}/{aggregate_id}"
            )
        if snapshot_sequence != sequences[-1]:
            raise PersistenceDataError(
                f"snapshot/event sequence mismatch for {aggregate_type}/{aggregate_id}"
            )
        return snapshot_sequence

    def _write_snapshot(
        self,
        aggregate_type: Literal["RUN", "MACHINE"],
        aggregate_id: str,
        snapshot: DemoRun | MachineSnapshot,
        previous_sequence: int,
    ) -> None:
        payload = snapshot.model_dump_json()
        if aggregate_type == RUN_AGGREGATE:
            if not isinstance(snapshot, DemoRun):
                raise TypeError("RUN aggregate requires DemoRun snapshot")
            if previous_sequence == 0:
                self._connection.execute(
                    "INSERT INTO demo_runs "
                    "(run_id, snapshot_json, event_sequence, status, phase) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        aggregate_id,
                        payload,
                        snapshot.event_sequence,
                        snapshot.status.value,
                        snapshot.phase.value,
                    ),
                )
            else:
                cursor = self._connection.execute(
                    "UPDATE demo_runs SET snapshot_json = ?, event_sequence = ?, "
                    "status = ?, phase = ? WHERE run_id = ? AND event_sequence = ?",
                    (
                        payload,
                        snapshot.event_sequence,
                        snapshot.status.value,
                        snapshot.phase.value,
                        aggregate_id,
                        previous_sequence,
                    ),
                )
                if cursor.rowcount != 1:
                    raise PersistenceConflictError("stale demo run snapshot")
            return

        if not isinstance(snapshot, MachineSnapshot):
            raise TypeError("MACHINE aggregate requires MachineSnapshot")
        if previous_sequence == 0:
            self._connection.execute(
                "INSERT INTO machine_snapshot "
                "(singleton_id, snapshot_json, event_sequence, state) VALUES (1, ?, ?, ?)",
                (payload, snapshot.event_sequence, snapshot.state.value),
            )
        else:
            cursor = self._connection.execute(
                "UPDATE machine_snapshot SET snapshot_json = ?, event_sequence = ?, state = ? "
                "WHERE singleton_id = 1 AND event_sequence = ?",
                (
                    payload,
                    snapshot.event_sequence,
                    snapshot.state.value,
                    previous_sequence,
                ),
            )
            if cursor.rowcount != 1:
                raise PersistenceConflictError("stale machine snapshot")

    def _insert_event(
        self,
        aggregate_type: Literal["RUN", "MACHINE"],
        aggregate_id: str,
        event: DomainEvent | MachineEvent,
    ) -> None:
        if aggregate_type == RUN_AGGREGATE and not isinstance(event, DomainEvent):
            raise TypeError("RUN aggregate requires DomainEvent")
        if aggregate_type == MACHINE_AGGREGATE and not isinstance(event, MachineEvent):
            raise TypeError("MACHINE aggregate requires MachineEvent")
        occurred_at = self._timestamp_text(event.occurred_at)
        run_status = event.run_status.value if isinstance(event, DomainEvent) else None
        run_phase = event.run_phase.value if isinstance(event, DomainEvent) else None
        machine_state = event.machine_state.value if isinstance(event, MachineEvent) else None
        self._connection.execute(
            "INSERT INTO domain_events "
            "(aggregate_type, aggregate_id, event_sequence, event_type, occurred_at, "
            "run_status, run_phase, machine_state, payload_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                aggregate_type,
                aggregate_id,
                event.sequence_number,
                event.event_type.value,
                occurred_at,
                run_status,
                run_phase,
                machine_state,
                event.model_dump_json(),
            ),
        )

    def _event_from_row(self, row: sqlite3.Row) -> DomainEvent | MachineEvent:
        if row["aggregate_type"] == RUN_AGGREGATE:
            event = self._parse_model(DomainEvent, row["payload_json"], "run event")
            expected_metadata = (
                event.run_id,
                event.sequence_number,
                event.event_type.value,
                self._timestamp_text(event.occurred_at),
                event.run_status.value,
                event.run_phase.value,
                None,
            )
        elif row["aggregate_type"] == MACHINE_AGGREGATE:
            event = self._parse_model(MachineEvent, row["payload_json"], "machine event")
            expected_metadata = (
                MACHINE_AGGREGATE_ID,
                event.sequence_number,
                event.event_type.value,
                self._timestamp_text(event.occurred_at),
                None,
                None,
                event.machine_state.value,
            )
        else:
            raise PersistenceDataError(
                f"unsupported aggregate type {row['aggregate_type']!r}"
            )
        actual_metadata = (
            row["aggregate_id"],
            row["event_sequence"],
            row["event_type"],
            row["occurred_at"],
            row["run_status"],
            row["run_phase"],
            row["machine_state"],
        )
        if actual_metadata != expected_metadata:
            raise PersistenceDataError("event metadata does not match JSON payload")
        return event

    @staticmethod
    def _normalize_event(event: DomainEvent | MachineEvent) -> DomainEvent | MachineEvent:
        occurred_at = event.occurred_at
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise PersistenceDataError("event occurred_at must be timezone-aware")
        return event.model_copy(update={"occurred_at": occurred_at.astimezone(UTC)})

    @staticmethod
    def _timestamp_text(value: datetime) -> str:
        if value.tzinfo is None or value.utcoffset() is None:
            raise PersistenceDataError("event occurred_at must be timezone-aware")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _parse_model(model_type: type, payload: str, label: str):
        try:
            return model_type.model_validate_json(payload)
        except (ValidationError, ValueError) as error:
            raise PersistenceDataError(f"invalid {label} JSON: {error}") from error
