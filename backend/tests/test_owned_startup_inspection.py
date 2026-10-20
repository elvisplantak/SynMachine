from dataclasses import replace
from datetime import UTC, datetime
import sqlite3

import pytest

from app.demo.phases import RunPhase
from app.demo.run_models import RunStatus
from app.hardware.owned_startup_inspection import (
    OfflineDatabaseBundle,
    StartupInspectionError,
    inspect_owned_startup,
)
from app.hardware.simulated_lifecycle import SimulationLifecycleStore
from tests.test_owned_phase_session import session_case as session_case
from tests.test_owned_pausable_demo import Clock


def bundle(c):
    return OfflineDatabaseBundle(
        c.paths[0], c.identities[0], c.paths[1], c.identities[1],
        c.paths[2], c.identities[2],
    )


def inspect_unchanged(c):
    before = tuple(path.read_bytes() for path in c.paths)
    calls = (list(c.runner.device.calls), list(c.runner.device.sf_calls))
    report = inspect_owned_startup(bundle(c))
    assert tuple(path.read_bytes() for path in c.paths) == before
    assert calls == (c.runner.device.calls, c.runner.device.sf_calls)
    assert report.automatic_resume_allowed is False
    return report


def test_fresh_running_fixture_is_not_permission_to_resume(session_case):
    c, _ = session_case(bind=False)
    report = inspect_unchanged(c)
    assert report.runs[0].status is RunStatus.RUNNING
    assert report.owner_id is None
    assert not report.prepared_phase_ids
    assert report.ownership_generation == 0


def test_completed_phase_and_gap_before_next_phase(session_case):
    c, session = session_case()
    session.execute_next()
    report = inspect_unchanged(c)
    assert report.owner_id is None and report.ownership_generation == 1
    assert len(report.prepared_phase_ids) == 1
    assert report.machine.active_execution is None
    assert any(row.total for row in report.journals)
    assert not any(row.non_successful for row in report.journals)


def test_owner_before_lifecycle_claim_is_visible_without_releasing_it(session_case):
    c, _ = session_case(bind=False)
    c.owner.claim("interrupted-before-claim")
    report = inspect_unchanged(c)
    assert report.owner_id == "interrupted-before-claim"
    assert report.owner_state == "ACTIVE"
    assert report.machine.active_execution is None
    assert c.retained() == report.owner_id


def test_unknown_send_retains_owner_and_evidence(session_case, monkeypatch):
    c, session = session_case(phase=RunPhase.P2_TRANSFER_SF_TO_COLUMN)

    def fail(**kwargs):
        raise RuntimeError("send outcome unknown")

    monkeypatch.setattr(c.runner.device, "execute_sf", fail)
    with pytest.raises(Exception):
        session.execute_next()
    report = inspect_unchanged(c)
    assert report.owner_id is not None
    assert report.owner_state == "BLOCKED"
    assert report.machine.active_execution is not None
    sf = next(row for row in report.journals if row.journal == "sf_action_journal")
    assert sf.non_successful
    assert all(state == "OUTCOME_UNKNOWN" for _, state in sf.non_successful)


def test_paused_run_intent_and_wait_survive_inspection(session_case):
    c, _ = session_case(phase=RunPhase.REACTION_HOLD, bind=False)
    store = c.coordinator.store
    run = store.load_demo_run("run-1")
    now = datetime.now(UTC)
    c.owner.claim("paused-phase")
    intent = store.claim_phase_execution(
        run_id=run.run_id, execution_id="paused-phase", claimed_at=now,
        expected_phase=run.phase, expected_run_event_sequence=run.event_sequence,
    )
    store.commit_phase_execution_start(
        intent, expected_run_event_sequence=run.event_sequence,
        expected_phase=run.phase, start_committed_at=now,
    )
    store.set_wait_paused("paused-phase", paused=True, occurred_at=now)
    c.runner._db.execute(
        "INSERT INTO execution_waits VALUES ('paused-phase', 1, '60', 'INTENT_PERSISTED', 0)"
    )
    report = inspect_unchanged(c)
    assert report.paused_run_ids == ("run-1",)
    assert report.owner_id == "paused-phase"
    assert report.machine.active_execution.execution_id == "paused-phase"
    assert report.journals[-1].non_successful == (("paused-phase:1", "INTENT_PERSISTED"),)


@pytest.mark.parametrize("index", range(3))
@pytest.mark.parametrize("damage", ["missing", "empty", "wrong_identity", "extra_schema"])
def test_invalid_bundle_never_repaired(session_case, tmp_path, index, damage):
    c, _ = session_case(bind=False)
    value = bundle(c)
    fields = ("ownership_path", "execution_path", "lifecycle_path")
    ids = ("ownership_id", "execution_id", "lifecycle_id")
    if damage == "wrong_identity":
        value = replace(value, **{ids[index]: "wrong"})
    else:
        path = tmp_path / f"invalid-{index}.db"
        if damage == "empty":
            path.touch()
        elif damage == "extra_schema":
            path.write_bytes(c.paths[index].read_bytes())
            with sqlite3.connect(path) as db:
                db.execute("CREATE TABLE unexpected(value TEXT)")
        value = replace(value, **{fields[index]: path})
    paths = (value.ownership_path, value.execution_path, value.lifecycle_path)
    before = tuple(path.read_bytes() if path.exists() else None for path in paths)
    with pytest.raises(StartupInspectionError):
        inspect_owned_startup(value)
    assert before == tuple(path.read_bytes() if path.exists() else None for path in paths)


def test_corrupt_plan_rejected_without_repair(session_case):
    c, session = session_case()
    session.execute_next()
    c.runner._db.execute("UPDATE prepared_command_plans SET payload_sha256='broken'")
    before = tuple(path.read_bytes() for path in c.paths)
    with pytest.raises(StartupInspectionError, match="checksum"):
        inspect_owned_startup(bundle(c))
    assert before == tuple(path.read_bytes() for path in c.paths)


def test_read_only_lifecycle_rejects_mutation(session_case):
    c, _ = session_case(bind=False)
    with SimulationLifecycleStore(
        c.paths[2], c.identities[2], c.identities[1], read_only=True
    ) as store:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            store._connection.execute("DELETE FROM domain_events")
    inspect_unchanged(c)


def test_completed_demo_does_not_authorize_restart(session_case):
    c, session = session_case(phase=RunPhase.P1_TRANSFER_S_TO_REACTOR, timer=Clock().timer())
    while c.coordinator.store.load_demo_run("run-1").status is RunStatus.RUNNING:
        session.execute_next()
    report = inspect_unchanged(c)
    assert report.runs[0].status is RunStatus.COMPLETED
    assert len(report.prepared_phase_ids) == 10
    assert report.owner_id is None
    assert not report.paused_run_ids


def test_completed_wait_is_not_completed_operation(session_case):
    c, _ = session_case(bind=False)
    c.runner._db.execute(
        "INSERT INTO execution_waits VALUES ('interrupted-cleanup', 1, '5', 'COMPLETED', 0)"
    )
    report = inspect_unchanged(c)
    assert report.journals[-1].non_successful == ()
    assert report.incomplete_wait_operations == (("interrupted-cleanup", 1),)


def test_owner_released_but_unresolved_evidence_is_still_reported(session_case):
    c, _ = session_case(bind=False)
    c.runner._db.execute(
        "INSERT INTO sf_action_journal VALUES ('sf-1', 'phase-1', 'session-1', "
        "'OPEN', 'INTENT_PERSISTED', NULL)"
    )
    report = inspect_unchanged(c)
    assert report.owner_id is None
    assert report.journals[1].non_successful == (("sf-1", "INTENT_PERSISTED"),)


def test_inconsistent_ownership_history_fails_closed(session_case):
    c, _ = session_case(bind=False)
    c.owner._db.execute("INSERT INTO hardware_sequences VALUES ('orphan', 'ACTIVE')")
    with pytest.raises(StartupInspectionError, match="inconsistent"):
        inspect_owned_startup(bundle(c))


@pytest.mark.parametrize("binding", ["execution", "lifecycle"])
def test_wrong_cross_database_binding_is_rejected(session_case, binding):
    c, _ = session_case(bind=False)
    if binding == "execution":
        c.runner._db.execute("UPDATE execution_identity SET ownership_id='other'")
    else:
        c.coordinator.store._connection.execute(
            "UPDATE offline_lifecycle_identity SET simulation_id='other'"
        )
    with pytest.raises(StartupInspectionError):
        inspect_owned_startup(bundle(c))


def test_cli_reports_without_opening_devices_or_modifying_files(session_case):
    import json
    import subprocess
    import sys

    c, _ = session_case(bind=False)
    arguments = []
    for name, path, identity in zip(
        ("ownership", "execution", "lifecycle"), c.paths, c.identities, strict=True
    ):
        arguments.extend((f"--{name}-path", str(path), f"--{name}-id", identity))
    before = tuple(path.read_bytes() for path in c.paths)
    result = subprocess.run(
        [sys.executable, "-m", "app.hardware.owned_startup_inspection", *arguments],
        capture_output=True, text=True, timeout=10, check=True,
    )
    report = json.loads(result.stdout)
    assert report["observation_only"] is True
    assert report["cross_database_atomic"] is False
    assert report["automatic_resume_allowed"] is False
    assert before == tuple(path.read_bytes() for path in c.paths)
    arguments[-1] = "wrong-identity"
    failed = subprocess.run(
        [sys.executable, "-m", "app.hardware.owned_startup_inspection", *arguments],
        capture_output=True, text=True, timeout=10,
    )
    assert failed.returncode == 2 and not failed.stdout
    assert json.loads(failed.stderr)["automatic_resume_allowed"] is False
