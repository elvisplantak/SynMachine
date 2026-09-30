"""Durable, explicitly provisioned ownership shared across hardware command paths."""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from threading import Lock, RLock
from typing import TypeVar
from uuid import uuid4

from app.demo.hardware_contract import HardwareCommandError

T = TypeVar("T")


class OwnershipBlocked(HardwareCommandError):
    """No command may run until the unresolved owner is deliberately reconciled."""


_TABLES = {
    "ownership_identity": "CREATE TABLE ownership_identity (id TEXT NOT NULL)",
    "hardware_sequences": """CREATE TABLE hardware_sequences (
        sequence_id TEXT PRIMARY KEY NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('ACTIVE', 'BLOCKED', 'COMPLETED'))
    )""",
    "hardware_owner": """CREATE TABLE hardware_owner (
        slot INTEGER PRIMARY KEY CHECK(slot=1), sequence_id TEXT
    )""",
}


def provision_ownership(database: Path) -> str:
    """Create only a new file. Startup/reopen must never call this function."""
    with database.open("xb"):
        pass
    identity = str(uuid4())
    with sqlite3.connect(database) as db:
        for statement in _TABLES.values():
            db.execute(statement)
        db.execute("INSERT INTO ownership_identity VALUES (?)", (identity,))
        db.execute("INSERT INTO hardware_owner VALUES (1, NULL)")
    return identity


@dataclass(frozen=True)
class SequenceLease:
    sequence_id: str
    phase_execution_id: str


class HardwareOwnership:
    """One durable owner across processes, one active operation per local lease.

    Leases are process-local object identities, never reconstructed from a stored
    sequence ID. No TTL, restart release, automatic recovery, or implicit success.
    """

    def __init__(self, database: Path, expected_identity: str):
        self._gate = Lock()
        self._db_lock = RLock()
        self._leases: dict[str, SequenceLease] = {}
        self._poisoned: set[str] = set()
        self._closed = False
        self._db = sqlite3.connect(
            database.resolve().as_uri() + "?mode=rw",
            uri=True,
            isolation_level=None,
            check_same_thread=False,
        )
        try:
            self._db.execute("PRAGMA synchronous=FULL")
            actual = dict(
                self._db.execute(
                    "SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            )

            def normalize(value):
                return "".join(value.lower().split())

            if {k: normalize(v) for k, v in actual.items()} != {
                k: normalize(v) for k, v in _TABLES.items()
            }:
                raise OwnershipBlocked("incompatible ownership schema")
            if self._db.execute("SELECT id FROM ownership_identity").fetchall() != [
                (expected_identity,)
            ]:
                raise OwnershipBlocked("wrong ownership database identity")
            self._validate_owner()
        except BaseException:
            self._db.close()
            raise

    def _validate_owner(self):
        rows = self._db.execute("SELECT slot, sequence_id FROM hardware_owner").fetchall()
        if len(rows) != 1 or rows[0][0] != 1:
            raise OwnershipBlocked("missing or invalid owner slot")
        current = rows[0][1]
        unfinished = self._db.execute(
            "SELECT sequence_id FROM hardware_sequences WHERE state != 'COMPLETED'"
        ).fetchall()
        if unfinished != ([] if current is None else [(current,)]):
            raise OwnershipBlocked("ownership history is inconsistent")
        return current

    def claim(self, sequence_id: str, *, phase_execution_id: str | None = None) -> SequenceLease:
        if type(sequence_id) is not str or not sequence_id.strip():
            raise ValueError("sequence ID must be a non-empty string")
        phase_execution_id = sequence_id if phase_execution_id is None else phase_execution_id
        if type(phase_execution_id) is not str or not phase_execution_id.strip():
            raise ValueError("phase ID must be a non-empty string")
        with self._db_lock:
            if self._closed:
                raise OwnershipBlocked("ownership connection is closed")
            self._db.execute("BEGIN IMMEDIATE")
            try:
                if self._validate_owner() is not None:
                    raise OwnershipBlocked("hardware sequence already owned or unresolved")
                if self._db.execute(
                    "SELECT 1 FROM hardware_sequences WHERE sequence_id=?", (sequence_id,)
                ).fetchone():
                    raise OwnershipBlocked("sequence identity already attempted")
                self._db.execute(
                    "INSERT INTO hardware_sequences VALUES (?, 'ACTIVE')", (sequence_id,)
                )
                self._db.execute(
                    "UPDATE hardware_owner SET sequence_id=? WHERE slot=1", (sequence_id,)
                )
                self._db.execute("COMMIT")
            except BaseException:
                self._db.execute("ROLLBACK")
                raise
            lease = SequenceLease(sequence_id, phase_execution_id)
            self._leases[sequence_id] = lease
            return lease

    def _check(self, lease: SequenceLease):
        if (
            self._closed
            or self._leases.get(lease.sequence_id) is not lease
            or lease.sequence_id in self._poisoned
        ):
            raise OwnershipBlocked("lease is foreign, expired or blocked")
        with self._db_lock:
            if self._validate_owner() != lease.sequence_id:
                raise OwnershipBlocked("lease does not own hardware")
            state = self._db.execute(
                "SELECT state FROM hardware_sequences WHERE sequence_id=?", (lease.sequence_id,)
            ).fetchone()
            if state != ("ACTIVE",):
                raise OwnershipBlocked("sequence requires recovery")

    def _retain(self, lease: SequenceLease):
        self._poisoned.add(lease.sequence_id)
        with self._db_lock:
            self._db.execute(
                "UPDATE hardware_sequences SET state='BLOCKED' WHERE sequence_id=?",
                (lease.sequence_id,),
            )

    def invoke(self, lease: SequenceLease, operation: Callable[[], T]) -> T:
        if not self._gate.acquire(blocking=False):
            raise OwnershipBlocked("another hardware operation is active")
        try:
            self._check(lease)
            try:
                return operation()
            except BaseException as error:
                try:
                    self._retain(lease)
                except BaseException as persistence_error:
                    error.add_note(f"Ownership retention write failed: {persistence_error}")
                raise
        finally:
            self._gate.release()

    def block(self, lease: SequenceLease) -> None:
        """Record Stop at an operation boundary; do not release ownership."""
        self.invoke(lease, lambda: self._retain(lease))

    def complete(self, lease: SequenceLease) -> None:
        """Caller must first persist successful sequence/lifecycle resolution."""

        def release():
            with self._db_lock:
                self._db.execute("BEGIN IMMEDIATE")
                try:
                    self._db.execute(
                        "UPDATE hardware_sequences SET state='COMPLETED' WHERE sequence_id=?",
                        (lease.sequence_id,),
                    )
                    self._db.execute("UPDATE hardware_owner SET sequence_id=NULL WHERE slot=1")
                    self._db.execute("COMMIT")
                except BaseException:
                    self._db.execute("ROLLBACK")
                    raise
            del self._leases[lease.sequence_id]

        self.invoke(lease, release)

    def close(self):
        if not self._gate.acquire(blocking=False):
            raise OwnershipBlocked("cannot close during an active operation")
        try:
            with self._db_lock:
                self._closed = True
                self._leases.clear()
                self._db.close()
        finally:
            self._gate.release()
