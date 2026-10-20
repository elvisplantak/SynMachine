from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from threading import RLock


class ArduinoCommandJournalError(RuntimeError):
    """Base error for durable Arduino command intent persistence."""


class ArduinoCommandIdentityConflictError(ArduinoCommandJournalError):
    """An operation ID was reused with different command semantics."""


class ArduinoCommandJournalState(StrEnum):
    INTENT_PERSISTED = "INTENT_PERSISTED"
    COMPLETED = "COMPLETED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    OUTCOME_UNKNOWN = "OUTCOME_UNKNOWN"


@dataclass(frozen=True)
class ArduinoCommandJournalEntry:
    operation_command_id: str
    phase_execution_id: str
    controller_boot_id: int
    command: str
    arguments: dict[str, str | int | bool]
    state: ArduinoCommandJournalState
    result: dict[str, str | int | bool] | None
    error_code: str | None
    execution_started: bool | None


@dataclass(frozen=True)
class PersistedArduinoCommandIntent:
    entry: ArduinoCommandJournalEntry
    created: bool


_SCHEMA = """
CREATE TABLE IF NOT EXISTS arduino_command_journal (
    operation_command_id TEXT NOT NULL PRIMARY KEY,
    phase_execution_id TEXT NOT NULL,
    controller_boot_id INTEGER NOT NULL CHECK (controller_boot_id >= 0),
    command TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN (
        'INTENT_PERSISTED', 'COMPLETED', 'REJECTED', 'FAILED', 'OUTCOME_UNKNOWN'
    )),
    result_json TEXT,
    error_code TEXT,
    execution_started INTEGER CHECK (execution_started IN (0, 1))
)
"""


class SQLiteArduinoCommandJournal:
    """Dedicated durable journal; kept separate from the domain event database."""

    def __init__(self, database: str | Path) -> None:
        self._lock = RLock()
        self._connection = sqlite3.connect(
            database, isolation_level=None, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> SQLiteArduinoCommandJournal:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def persist_intent(
        self,
        *,
        operation_command_id: str,
        phase_execution_id: str,
        controller_boot_id: int,
        command: str,
        arguments: dict[str, str | int | bool],
    ) -> PersistedArduinoCommandIntent:
        with self._lock:
            arguments_json = self._encode_map(arguments)
            created = False
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT * FROM arduino_command_journal "
                    "WHERE operation_command_id = ?",
                    (operation_command_id,),
                ).fetchone()
                if row is None:
                    self._connection.execute(
                        "INSERT INTO arduino_command_journal ("
                        "operation_command_id, phase_execution_id, controller_boot_id, "
                        "command, arguments_json, state"
                        ") VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            operation_command_id,
                            phase_execution_id,
                            controller_boot_id,
                            command,
                            arguments_json,
                            ArduinoCommandJournalState.INTENT_PERSISTED.value,
                        ),
                    )
                    created = True
                elif (
                    row["phase_execution_id"] != phase_execution_id
                    or row["controller_boot_id"] != controller_boot_id
                    or row["command"] != command
                    or row["arguments_json"] != arguments_json
                ):
                    raise ArduinoCommandIdentityConflictError(
                        "operation_command_id was reused with different semantics"
                    )
                self._connection.execute("COMMIT")
            except Exception:
                self._connection.execute("ROLLBACK")
                raise
            entry = self.load(operation_command_id)
            assert entry is not None
            return PersistedArduinoCommandIntent(entry=entry, created=created)

    def record_outcome(
        self,
        operation_command_id: str,
        state: ArduinoCommandJournalState,
        *,
        result: dict[str, str | int | bool] | None = None,
        error_code: str | None = None,
        execution_started: bool | None = None,
    ) -> ArduinoCommandJournalEntry:
        with self._lock:
            if state is ArduinoCommandJournalState.INTENT_PERSISTED:
                raise ValueError("record_outcome requires an outcome state")
            existing = self.load(operation_command_id)
            if existing is None:
                raise ArduinoCommandJournalError("Arduino command intent was not found")
            if existing.state in {
                ArduinoCommandJournalState.COMPLETED,
                ArduinoCommandJournalState.REJECTED,
                ArduinoCommandJournalState.FAILED,
            }:
                raise ArduinoCommandJournalError("terminal Arduino outcome is immutable")
            self._connection.execute(
                "UPDATE arduino_command_journal SET state = ?, result_json = ?, "
                "error_code = ?, execution_started = ? WHERE operation_command_id = ?",
                (
                    state.value,
                    None if result is None else self._encode_map(result),
                    error_code,
                    None if execution_started is None else int(execution_started),
                    operation_command_id,
                ),
            )
            entry = self.load(operation_command_id)
            assert entry is not None
            return entry

    def load(self, operation_command_id: str) -> ArduinoCommandJournalEntry | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM arduino_command_journal WHERE operation_command_id = ?",
                (operation_command_id,),
            ).fetchone()
            if row is None:
                return None
            return ArduinoCommandJournalEntry(
                operation_command_id=row["operation_command_id"],
                phase_execution_id=row["phase_execution_id"],
                controller_boot_id=row["controller_boot_id"],
                command=row["command"],
                arguments=json.loads(row["arguments_json"]),
                state=ArduinoCommandJournalState(row["state"]),
                result=(
                    None if row["result_json"] is None else json.loads(row["result_json"])
                ),
                error_code=row["error_code"],
                execution_started=(
                    None
                    if row["execution_started"] is None
                    else bool(row["execution_started"])
                ),
            )

    @staticmethod
    def _encode_map(value: dict[str, str | int | bool]) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
