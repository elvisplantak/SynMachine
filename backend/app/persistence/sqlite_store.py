import sqlite3
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from app.demo.events import DomainEvent
from app.demo.machine_events import MachineEvent
from app.demo.machine_models import MachineSnapshot
from app.demo.run_models import DemoRun

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
