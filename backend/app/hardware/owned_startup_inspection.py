"""Read-only observations for an explicitly identified offline database bundle.

Not a recovery executor or a startup authorization gate. Each database has its
own consistent snapshot; the three snapshots are NOT one atomic observation.
In particular, an ACTIVE owner is not evidence that its process has died.
"""

from contextlib import ExitStack, closing
from dataclasses import dataclass
import hashlib
from pathlib import Path
import sqlite3

from app.demo.machine_models import MachineSnapshot
from app.demo.run_models import DemoRun, RunStatus
from app.hardware.command_plan_store import _decode
from app.hardware.owned_transfer_runner import SCHEMAS
from app.hardware.sequence_ownership import _TABLES
from app.hardware.simulated_lifecycle import SimulationLifecycleStore
from app.hardware.simulated_p1_runner import SimulationBlocked
from app.persistence.sqlite_store import PersistenceError


class StartupInspectionError(RuntimeError):
    """The supplied bundle cannot be inspected; never replace or repair it."""


@dataclass(frozen=True)
class OfflineDatabaseBundle:
    ownership_path: Path
    ownership_id: str
    execution_path: Path
    execution_id: str
    lifecycle_path: Path
    lifecycle_id: str


@dataclass(frozen=True)
class JournalObservation:
    journal: str
    total: int
    # Includes failed/rejected/stopped records, not just unknown outcomes.
    non_successful: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class StartupInspection:
    owner_id: str | None
    owner_state: str | None
    ownership_generation: int
    machine: MachineSnapshot | None
    runs: tuple[DemoRun, ...]
    prepared_phase_ids: tuple[str, ...]
    journals: tuple[JournalObservation, ...]
    incomplete_wait_operations: tuple[tuple[str, int], ...]

    @property
    def paused_run_ids(self) -> tuple[str, ...]:
        return tuple(run.run_id for run in self.runs if run.status is RunStatus.PAUSED)

    @property
    def automatic_resume_allowed(self) -> bool:
        # Even an empty bundle or entirely successful history establishes no
        # current hardware/session trust and cannot recreate a process-local lease.
        return False


def _schema(db):
    return sorted(
        (kind, name, "".join(sql.lower().split()))
        for kind, name, sql in db.execute(
            "SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL"
        )
    )


def _require_schema(db, statements):
    with closing(sqlite3.connect(":memory:")) as expected:
        for statement in statements:
            expected.execute(statement)
        if _schema(db) != _schema(expected):
            raise StartupInspectionError("incompatible database schema")


def _open_snapshot(stack, path):
    db = stack.enter_context(closing(sqlite3.connect(
        path.resolve().as_uri() + "?mode=ro", uri=True, isolation_level=None
    )))
    db.execute("BEGIN")
    return db


def inspect_owned_startup(bundle: OfflineDatabaseBundle) -> StartupInspection:
    """Inspect existing offline files without a device, dispatch path or writes.

    Missing files, identity/binding mismatches, incompatible schemas and corrupt
    plans fail explicitly. No database is created, migrated or repaired. A report
    is diagnostic only: callers must not use it to release an owner or send work.
    """
    paths = (bundle.ownership_path, bundle.execution_path, bundle.lifecycle_path)
    identities = (bundle.ownership_id, bundle.execution_id, bundle.lifecycle_id)
    if any(type(value) is not str or not value.strip() for value in identities):
        raise StartupInspectionError("expected identities must be explicit non-empty strings")
    if len({path.resolve() for path in paths}) != 3:
        raise StartupInspectionError("the three databases must have distinct paths")
    try:
        with ExitStack() as stack:
            owner = _open_snapshot(stack, paths[0])
            _require_schema(owner, _TABLES.values())
            if owner.execute("SELECT id FROM ownership_identity").fetchall() != [
                (bundle.ownership_id,)
            ]:
                raise StartupInspectionError("wrong ownership identity")
            rows = owner.execute("SELECT slot, sequence_id FROM hardware_owner").fetchall()
            if len(rows) != 1 or rows[0][0] != 1:
                raise StartupInspectionError("invalid ownership slot")
            owner_id = rows[0][1]
            unfinished = owner.execute(
                "SELECT sequence_id, state FROM hardware_sequences WHERE state != 'COMPLETED'"
            ).fetchall()
            if (owner_id is None and unfinished) or (
                owner_id is not None
                and (len(unfinished) != 1 or unfinished[0][0] != owner_id)
            ):
                raise StartupInspectionError("inconsistent retained ownership")
            generation = owner.execute("SELECT COUNT(*) FROM hardware_sequences").fetchone()[0]

            execution = _open_snapshot(stack, paths[1])
            _require_schema(execution, SCHEMAS)
            if execution.execute("SELECT id, ownership_id FROM execution_identity").fetchall() != [
                (bundle.execution_id, bundle.ownership_id)
            ]:
                raise StartupInspectionError("wrong execution identity or ownership binding")
            phase_ids = []
            for phase_id, version, payload, digest in execution.execute(
                "SELECT * FROM prepared_command_plans ORDER BY phase_execution_id"
            ):
                if version != 1 or hashlib.sha256(payload.encode()).hexdigest() != digest:
                    raise StartupInspectionError("stored plan checksum or version mismatch")
                plan = _decode(payload)
                if plan.phase_execution_id != phase_id:
                    raise StartupInspectionError("stored plan identity mismatch")
                phase_ids.append(phase_id)
            observations = []
            for table, key in (
                ("arduino_command_journal", "operation_command_id"),
                ("sf_action_journal", "action_id"),
                ("execution_waits", "phase_id || ':' || operation_number"),
            ):
                # Identifiers are constants, never caller-supplied SQL.
                records = execution.execute(
                    f"SELECT {key}, state FROM {table} ORDER BY {key}"
                ).fetchall()
                non_successful = tuple((key, state) for key, state in records if state != "COMPLETED")
                observations.append(JournalObservation(table, len(records), non_successful))

            life = stack.enter_context(SimulationLifecycleStore(
                paths[2], bundle.lifecycle_id, bundle.execution_id, read_only=True
            ))
            life._connection.execute("BEGIN")
            machine = life.load_machine_snapshot()
            runs = tuple(life.load_demo_run(row[0]) for row in life._connection.execute(
                "SELECT run_id FROM demo_runs ORDER BY run_id"
            ))
            if machine is not None and machine.active_run_id is not None:
                active = next((run for run in runs if run.run_id == machine.active_run_id), None)
                if active is None:
                    raise StartupInspectionError("active lifecycle run is absent")
                intent = machine.active_execution
                if intent is not None and (intent.run_id != active.run_id or intent.phase != active.phase):
                    raise StartupInspectionError("active lifecycle intent differs from run")
            return StartupInspection(
                owner_id, unfinished[0][1] if unfinished else None, generation,
                machine, runs, tuple(phase_ids), tuple(observations),
                tuple(execution.execute(
                    "SELECT phase_id, operation_number FROM execution_waits "
                    "WHERE operation_completed=0 ORDER BY phase_id, operation_number"
                )),
            )
    except StartupInspectionError:
        raise
    except (sqlite3.Error, ValueError, TypeError, AttributeError, SimulationBlocked, PersistenceError) as error:
        raise StartupInspectionError("offline bundle inspection failed") from error


def main() -> int:
    """Explicit diagnostic command; never invoked by production startup."""
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("ownership", "execution", "lifecycle"):
        parser.add_argument(f"--{name}-path", type=Path, required=True)
        parser.add_argument(f"--{name}-id", required=True)
    arguments = parser.parse_args()
    try:
        report = inspect_owned_startup(OfflineDatabaseBundle(**vars(arguments)))
    except StartupInspectionError as error:
        print(json.dumps({"error": str(error), "automatic_resume_allowed": False}), file=sys.stderr)
        return 2
    payload = {
        "observation_only": True,
        "cross_database_atomic": False,
        "automatic_resume_allowed": report.automatic_resume_allowed,
        "owner_id": report.owner_id,
        "owner_state": report.owner_state,
        "ownership_generation": report.ownership_generation,
        "machine": None if report.machine is None else report.machine.model_dump(mode="json"),
        "runs": [run.model_dump(mode="json") for run in report.runs],
        "paused_run_ids": report.paused_run_ids,
        "prepared_phase_ids": report.prepared_phase_ids,
        "journals": [
            {"journal": row.journal, "total": row.total, "non_successful": row.non_successful}
            for row in report.journals
        ],
        "incomplete_wait_operations": report.incomplete_wait_operations,
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
