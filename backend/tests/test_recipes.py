"""Recipe library, immutable execution snapshots, and real owned path with fake devices."""

from datetime import UTC, datetime
import sqlite3
from threading import Event

import pytest
from pydantic import ValidationError

from app.demo import lifecycle
from app.demo.calibration_models import PumpCalibrationSet
from app.demo.phases import RunPhase
from app.demo.run_models import RunStatus
from app.main import create_app
from app.persistence.sqlite_store import PersistenceConflictError
from app.recipes.models import RecipeDefinition, RecipeReadiness, SavedRecipe, validate_recipe_flow, recipe_content_digest
from app.recipes.planning import compile_step, preview_recipe
from app.recipes.store import RecipeStore, RecipeConflict
from tests.test_api import ApiClient
from tests.test_command_planning import context
from tests.test_owned_application_api import (
    assembly as assembly,
    wait_idle,
    COMMAND,
    maintenance,
    replacement,
)
from tests.test_owned_offline_runtime import bundle as bundle
from tests.test_owned_phase_session import READINESS
from tests.test_adapter_configuration import configured as configured
from tests.test_prepared_adapter_execution import adapters as adapters
from tests.test_owned_maintenance import plan
from tests.test_owned_pausable_demo import Clock
from app.demo.maintenance_plan import MaintenanceKind
from app.hardware.owned_application_execution import OwnedApplicationExecution
from app.hardware.prepared_adapter_device import PreparedAdapterDevice

NOW = datetime.now(UTC)
PREFIX = "/api/v1"


def definition(steps=None):
    return RecipeDefinition(
        name="Example recipe",
        sources={"B1": "Blue", "B2": "Purple", "S": "Water"},
        steps=steps
        or [
            {"kind": "ADD", "source": "S", "volume_ml": "2"},
            {"kind": "ADD", "source": "B2", "volume_ml": "1"},
            {"kind": "ADD", "source": "B2", "volume_ml": "1"},
            {"kind": "WAIT", "duration_seconds": "1"},
            {"kind": "WAIT", "duration_seconds": "2"},
            {"kind": "TRANSFER", "route": "REACTOR_TO_SF", "volume_ml": "4"},
            {"kind": "SF_MIX", "duration_seconds": "1"},
            {"kind": "SF_SETTLE", "duration_seconds": "1"},
            {"kind": "TRANSFER", "route": "SF_TO_COLUMN", "volume_ml": "4"},
            {"kind": "COLLECT", "fraction_count": 2, "fraction_duration_seconds": "1"},
        ],
    )


def readiness():
    return RecipeReadiness(
        operator="Fixture operator",
        evidence_note="Fresh fake-only statement",
        sources_match_recipe=True,
        reactor_sf_column_empty_clean=True,
        waste_capacity_available=True,
        collection_tubes_ready=True,
    )


def calibrations():
    ctx = context()
    return PumpCalibrationSet(p1=ctx.pumps[0].calibration, p2=ctx.pumps[1].calibration)


def save(client, value=None):
    response = client.post(
        PREFIX + "/recipes", json={"definition": (value or definition()).model_dump(mode="json")}
    )
    assert response.status_code == 200, response.text
    return response.json()


def execute(client, saved, run_id="recipe-run", declaration=None):
    return client.post(
        PREFIX + f"/recipes/{saved['recipe_id']}/execute",
        json={
            "run_id": run_id,
            "expected_revision": saved["revision"],
            "expected_content_digest": saved["content_digest"],
            "readiness": declaration or readiness().model_dump(mode="json"),
            **COMMAND,
        },
    )


@pytest.mark.parametrize(
    "step",
    [
        {"kind": "HEAT", "temperature": 40},
        {"kind": "ADD", "source": "B3", "volume_ml": 1},
        {"kind": "ADD", "source": "B1", "volume_ml": "NaN"},
        {"kind": "ADD", "source": "B1", "volume_ml": 0},
        {"kind": "WAIT", "duration_seconds": -1},
        {"kind": "SF_MIX", "duration_seconds": 1, "rpm": 300},
        {"kind": "TRANSFER", "route": "COLUMN_TO_WASTE", "volume_ml": 1},
        {"kind": "COLLECT", "fraction_count": True, "fraction_duration_seconds": 1},
        {"kind": "COLLECT", "fraction_count": 41, "fraction_duration_seconds": 1},
    ],
)
def test_reject_unknown_capabilities_values_and_motor_parameters(step):
    with pytest.raises(ValidationError):
        definition([step])


@pytest.mark.parametrize(
    "steps",
    [
        [{"kind": "TRANSFER", "route": "REACTOR_TO_SF", "volume_ml": 1}],
        [{"kind": "SF_MIX", "duration_seconds": 1}],
        [{"kind": "SF_SETTLE", "duration_seconds": 1}],
        [{"kind": "COLLECT", "fraction_count": 1, "fraction_duration_seconds": 1}],
    ],
)
def test_flow_requires_nominal_contents(steps):
    with pytest.raises(ValueError, match="Step 1"):
        validate_recipe_flow(definition(steps))


def test_library_revisions_reopen_and_stale_update(tmp_path):
    path = tmp_path / "recipes.db"
    with RecipeStore(path) as library:
        original = library.save(definition())
        updated = library.save(
            definition([{"kind": "WAIT", "duration_seconds": "2"}]),
            recipe_id=original.recipe_id,
            expected_revision=1,
        )
        assert updated.revision == 2
        with pytest.raises(RecipeConflict):
            library.save(definition(), recipe_id=original.recipe_id, expected_revision=1)
    with RecipeStore(path) as library:
        assert library.load(original.recipe_id) == updated
        assert library.list() == (updated,)
        assert (
            library.connection.execute("SELECT COUNT(*) FROM recipe_revisions").fetchone()[0] == 2
        )


def test_repeated_phase_advances_by_step_not_phase_identity():
    saved = SavedRecipe(recipe_id="saved", revision=1, definition=definition(),
                            content_digest=recipe_content_digest(definition()))
    run = lifecycle.create_recipe_run("run", saved, readiness(), NOW).run
    run = lifecycle.start_run(run, NOW).run
    for index, _ in enumerate(saved.definition.steps):
        assert run.recipe_step_index == index and run.status is RunStatus.RUNNING
        run = lifecycle.complete_current_phase(run, NOW).run
    assert run.recipe_step_index == 10 and run.status is RunStatus.COMPLETED
    assert run.recipe == saved


def test_preview_uses_existing_protected_sf_plan_and_exact_volume():
    plans = preview_recipe(definition(), calibrations(), READINESS)
    assert len(plans["steps"]) == 10 and plans["calibrations_checked"] is True
    protected = compile_step(definition().steps[8], calibrations(), READINESS)
    assert protected.operations[0].operation_kind.value == "PREPARE_SF_TO_COLUMN_TRANSFER"
    with pytest.raises(ValueError, match="whole steps"):
        preview_recipe(
            definition([{"kind": "ADD", "source": "B1", "volume_ml": "0.00001"}]), calibrations()
        )


def test_collection_must_be_last_because_volume_is_unknown():
    bad = definition().model_copy(update={"steps": definition().steps + (definition().steps[3],)})
    with pytest.raises(ValueError, match="final step"):
        validate_recipe_flow(bad)


def test_default_api_library_persists_but_never_enables_executor(tmp_path):
    path = tmp_path / "life.db"
    with ApiClient(create_app(path), lifespan="on") as client:
        saved = save(client)
        preview = client.post(
            PREFIX + "/recipes/preview", json=definition().model_dump(mode="json")
        )
        assert preview.status_code == 200 and preview.json()["calibrations_checked"] is False
        assert execute(client, saved).status_code == 503
    with ApiClient(create_app(path), lifespan="on") as client:
        assert client.get(PREFIX + "/recipes").json() == [saved]


def test_owned_recipe_complete_repeat_edit_snapshot_and_journal(assembly, bundle):
    app, _, devices, _ = assembly
    with ApiClient(app, lifespan="on") as client:
        saved = save(client)
        assert devices[0].calls == devices[0].sf_calls == []
        response = execute(client, saved)
        assert response.status_code == 202, response.text
        assert wait_idle(client)["error"] is None
        run = client.get(PREFIX + "/runs/recipe-run").json()
        assert run["status"] == "COMPLETED" and run["recipe_step_index"] == 10
        assert run["configuration"] is None and run["recipe"] == saved
        assert run["recipe_readiness"]["operator"] == "Fixture operator"
        changed = client.post(
            PREFIX + f"/recipes/{saved['recipe_id']}",
            json={
                "definition": definition([{"kind": "WAIT", "duration_seconds": "3"}]).model_dump(
                    mode="json"
                ),
                "expected_revision": 1,
            },
        )
        assert changed.status_code == 200 and changed.json()["revision"] == 2
        assert execute(client, saved, "stale-run").status_code == 409
        assert client.get(PREFIX + "/runs/recipe-run").json()["recipe"] == saved
        assert execute(client, changed.json(), "repeat-run").status_code == 202
        assert wait_idle(client)["error"] is None
        assert client.get(PREFIX + "/runs/repeat-run").json()["recipe_step_index"] == 1
    with sqlite3.connect(bundle.execution_path) as db:
        assert db.execute("SELECT COUNT(*) FROM prepared_command_plans").fetchone()[0] == 11


def test_readiness_and_invalid_preview_send_no_commands(assembly):
    app, _, devices, _ = assembly
    with ApiClient(app, lifespan="on") as client:
        saved = save(client)
        for field in readiness().model_dump():
            bad = readiness().model_dump()
            bad.pop(field)
            assert execute(client, saved, declaration=bad).status_code == 422
        invalid = save(client, definition([{"kind": "SF_MIX", "duration_seconds": 1}]))
        assert execute(client, invalid).status_code == 422
        assert devices[0].calls == devices[0].sf_calls == []


def test_recipe_stop_retains_ownership_flush_then_allows_new_run(assembly):
    app, _, devices, _ = assembly
    entered, release = Event(), Event()
    with ApiClient(app, lifespan="on") as client:
        saved = save(client)

        def before(*args):
            entered.set()
            assert release.wait(5)

        devices[0].before_send = before
        assert execute(client, saved).status_code == 202
        assert entered.wait(5)
        status = client.get(PREFIX + "/execution").json()
        response = client.post(
            PREFIX + f"/execution/{status['operation']['operation_id']}/stop", json=COMMAND
        )
        assert response.status_code == 200, response.text
        release.set()
        stopped = wait_idle(client)
        assert stopped["retained_owner_id"]
        run = client.get(PREFIX + "/runs/recipe-run").json()
        assert run["status"] == "ABORTED" and run["recipe_step_index"] == 0
        assert execute(client, saved, "blocked").status_code == 409
        devices[0].before_send = lambda _: None
        maintenance(client, "FLUSH", "recipe-run")
        assert wait_idle(client)["error"] is None
        assert execute(client, saved, "new").status_code == 202
        assert wait_idle(client)["error"] is None


def test_snapshot_and_progress_cannot_be_changed_in_persistence(assembly):
    app, execution, _, _ = assembly
    with ApiClient(app, lifespan="on"):
        saved = SavedRecipe(recipe_id="saved", revision=1, definition=definition(),
                            content_digest=recipe_content_digest(definition()))
        run = execution.create_recipe_run("unstarted", saved, readiness(), NOW)
        with execution.store(read_only=False) as store:
            transition = lifecycle.start_run(run, NOW)
            for forged in [
                transition.run.model_copy(
                    update={"recipe": saved.model_copy(update={"revision": 2})}
                ),
                transition.run.model_copy(
                    update={
                        "recipe_step_index": 1,
                        "phase": RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR,
                    }
                ),
            ]:
                with pytest.raises((PersistenceConflictError, ValidationError)):
                    store.persist_run_transition(forged, transition.events)
        with execution.store() as store:
            assert store.load_demo_run("unstarted").status is RunStatus.CREATED


def test_recipe_pause_resume_preserves_index_and_wait_owner(assembly):
    app, _, _, clock = assembly
    entered, release = Event(), Event()

    def hold():
        if not entered.is_set():
            entered.set()
            assert release.wait(10)

    clock.hook = hold
    with ApiClient(app, lifespan="on") as client:
        saved = save(
            client,
            definition(
                [{"kind": "WAIT", "duration_seconds": 3}, {"kind": "WAIT", "duration_seconds": 2}]
            ),
        )
        try:
            assert execute(client, saved).status_code == 202
            assert entered.wait(5)
            paused = client.post(PREFIX + "/runs/recipe-run/pause", json=COMMAND)
            assert paused.status_code == 200 and paused.json()["run"]["recipe_step_index"] == 0
            intent = paused.json()["machine"]["active_execution"]
            resumed = client.post(PREFIX + "/runs/recipe-run/resume", json=COMMAND)
            assert (
                resumed.status_code == 200
                and resumed.json()["machine"]["active_execution"] == intent
            )
        finally:
            release.set()
        assert wait_idle(client)["error"] is None
        assert client.get(PREFIX + "/runs/recipe-run").json()["recipe_step_index"] == 2


def test_recipe_fault_restart_recovery_flush_never_replays_snapshot(assembly, bundle):
    app, _, devices, _ = assembly
    with ApiClient(app, lifespan="on") as client:
        saved = save(client)

        def fail(_):
            raise RuntimeError("injected recipe transport failure")

        devices[0].before_send = fail
        assert execute(client, saved).status_code == 202
        assert wait_idle(client)["error"]
        assert client.get(PREFIX + "/runs/recipe-run").json()["recipe_step_index"] == 0
    previous = bundle.execution_path.read_bytes()
    devices = []
    with ApiClient(replacement(bundle, devices), lifespan="on") as client:
        assert devices[0].calls == devices[0].sf_calls == []
        assert bundle.execution_path.read_bytes() == previous
        run = client.get(PREFIX + "/runs/recipe-run").json()
        assert run["status"] == "FAULTED" and run["recipe"] == saved
        assert execute(client, saved, "blocked").status_code == 409
        for kind in ("RECOVERY", "FLUSH"):
            maintenance(client, kind, "recipe-run")
            assert wait_idle(client)["error"] is None
        assert execute(client, saved, "next").status_code == 202
        assert wait_idle(client)["error"] is None


def test_recipe_real_adapters_fake_transports_intent_before_bytes(bundle, adapters):
    arduino, sf, port, _ = adapters

    def factory():
        device = PreparedAdapterDevice(context(), arduino, sf)
        device.sf_mixer_running = False
        return device

    execution = OwnedApplicationExecution(
        bundle,
        factory,
        plan(MaintenanceKind.RECOVERY).calibrations,
        timer_factory=Clock().timer,
        column_readiness=READINESS,
    )
    checked = []

    def before(message):
        journal = execution._runtime._runner._journal.load(message["operation_command_id"])
        assert journal.state.value == "INTENT_PERSISTED"
        with execution.store() as store:
            run = store.load_demo_run("recipe-run")
            assert run.recipe is not None and run.status is RunStatus.RUNNING
            assert store.load_machine_snapshot().active_execution.start_committed_at is not None
        checked.append(message["command"])

    port.before_command = before
    with ApiClient(create_app(application_execution=execution), lifespan="on") as client:
        saved = save(client)
        assert execute(client, saved).status_code == 202
        assert wait_idle(client)["error"] is None
        assert client.get(PREFIX + "/runs/recipe-run").json()["status"] == "COMPLETED"
    assert "SF_MIXER_SET_STATE" in checked and "CAROUSEL_MOVE_TO_POSITION" in checked
    assert "PUMP_HOME" not in checked


def test_legacy_start_cannot_bypass_recipe_preconditions(assembly):
    app, execution, _, _ = assembly
    with ApiClient(app, lifespan="on") as client:
        saved = SavedRecipe(recipe_id="saved", revision=1, definition=definition(),
                            content_digest=recipe_content_digest(definition()))
        execution.create_recipe_run("created-recipe", saved, readiness(), NOW)
        assert client.post(PREFIX + "/runs/created-recipe/start", json=COMMAND).status_code == 409
        assert (
            client.post(
                PREFIX + "/runs/created-recipe/phases/current/complete", json=COMMAND
            ).status_code
            == 409
        )


def test_exact_inventory_does_not_round_away_overdraw():
    value = definition(
        [
            {"kind": "ADD", "source": "S", "volume_ml": "1"},
            {
                "kind": "TRANSFER",
                "route": "REACTOR_TO_SF",
                "volume_ml": "1.000000000000000000000000000001",
            },
        ]
    )
    with pytest.raises(ValueError, match="exceeds"):
        validate_recipe_flow(value)


@pytest.mark.parametrize("value", [False, 1, "true", None])
def test_operator_confirmation_is_exact_boolean(value):
    statement = readiness().model_dump()
    statement["sources_match_recipe"] = value
    with pytest.raises(ValidationError):
        RecipeReadiness.model_validate(statement)


def test_unknown_schema_is_rejected_without_rewriting_library(tmp_path):
    path = tmp_path / "recipes.db"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=99")
    before = path.read_bytes()
    with pytest.raises(RecipeConflict):
        RecipeStore(path)
    assert path.read_bytes() == before


def test_recipe_library_concurrent_initialization_and_revision_cas(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    path = tmp_path / "concurrent.db"

    def initialize():
        with RecipeStore(path) as library:
            assert library.list() == ()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: initialize(), range(2)))
    with RecipeStore(path) as library:
        saved = library.save(definition())

    def revise():
        with RecipeStore(path) as library:
            try:
                return library.save(
                    definition(), recipe_id=saved.recipe_id, expected_revision=1
                ).revision
            except RecipeConflict:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: revise(), range(2)))
    assert results.count(2) == results.count("conflict") == 1


def test_recipe_unknown_version_and_duplicate_payload_are_rejected(tmp_path):
    for version in (True, "1", 2):
        with pytest.raises(ValidationError):
            RecipeDefinition.model_validate(
                {**definition().model_dump(), "schema_version": version}
            )
    path = tmp_path / "corrupt.db"
    with RecipeStore(path) as library:
        saved = library.save(definition())
        library.connection.execute(
            "UPDATE recipe_revisions SET payload=? WHERE recipe_id=?",
            ('{"schema_version":1,"schema_version":2}', saved.recipe_id),
        )
        library.connection.commit()
        with pytest.raises(RecipeConflict, match="duplicate"):
            library.load(saved.recipe_id)


def test_unavailable_column_profile_blocks_before_any_send(assembly):
    app, execution, devices, _ = assembly
    execution._column_readiness = None
    with ApiClient(app, lifespan="on") as client:
        saved = save(client)
        preview = client.post(PREFIX + "/recipes/preview", json=saved["definition"]).json()
        assert preview["calibrations_checked"] is True
        assert preview["collection_readiness_status"] == "UNAVAILABLE"
        assert execute(client, saved).status_code == 409
        assert client.get(PREFIX + "/runs/recipe-run").status_code == 404
        assert devices[0].calls == devices[0].sf_calls == []


def test_transfer_home_boundary_is_rejected_without_rounding_or_movement():
    from app.demo.calibration_models import PumpCalibration

    calibrations = PumpCalibrationSet(
        **{
            key: PumpCalibration(
                pump_id=key.upper(),
                working_full_chamber_position_steps=0,
                working_empty_chamber_position_steps=20500,
                working_volume_ml="20",
            )
            for key in ("p1", "p2")
        }
    )
    with pytest.raises(ValueError, match="HOME is not a transfer"):
        preview_recipe(
            definition([{"kind": "ADD", "source": "S", "volume_ml": "20"}]), calibrations
        )


def test_recipe_cancelled_current_input_can_start_new_explicit_attempt(configured):
    from tests.test_operator_current_input import source, challenge, declare, AUTH

    build, ports, sessions, _, _, _ = configured
    current = source()
    execution = build(current_state_provider=current, context_clock=current.clock)
    with ApiClient(create_app(application_execution=execution), lifespan="on") as client:
        saved = save(client, definition([{"kind": "WAIT", "duration_seconds": 1}]))
        assert execute(client, saved).status_code == 202
        first = challenge(client)
        assert (
            client.post(
                PREFIX + "/execution/current-input/" + first["request_id"] + "/cancel", headers=AUTH
            ).status_code
            == 200
        )
        cancelled = wait_idle(client)
        assert cancelled["error"] and cancelled["retained_owner_id"] is None
        assert client.get(PREFIX + "/runs/recipe-run").json()["status"] == "CREATED"
        assert len(ports[0].writes) == 1 and sessions == []
        assert execute(client, saved, "fresh-recipe-attempt").status_code == 202
        second = challenge(client)
        assert second["request_id"] != first["request_id"]
        assert declare(client, first).status_code == 409
        assert declare(client, second).status_code == 200
        third = challenge(client)
        assert declare(client, third).status_code == 200
        assert wait_idle(client)["error"] is None
        assert client.get(PREFIX + "/runs/fresh-recipe-attempt").json()["status"] == "COMPLETED"
        assert client.get(PREFIX + "/runs/recipe-run").json()["status"] == "CREATED"



def test_configured_recipe_collect_uses_fresh_operator_references(configured):
    import json
    from tests.test_operator_current_input import source, challenge, declare

    build, ports, sessions, _, _, _ = configured
    current = source()
    execution = build(current_state_provider=current, context_clock=current.clock)
    assert execution._column_readiness is None
    with ApiClient(create_app(application_execution=execution), lifespan="on") as client:
        saved = save(client)
        preview = client.post(PREFIX + "/recipes/preview", json=saved["definition"])
        assert preview.status_code == 200
        assert preview.json()["calibrations_checked"] is True
        assert preview.json()["collection_readiness_status"] == "FRESH_INPUT_REQUIRED"
        assert preview.json()["content_digest"] == saved["content_digest"]
        assert execute(client, saved).status_code == 202
        initialization = challenge(client)
        assert len(ports[0].writes) == 1 and sessions == []
        assert declare(client, initialization).status_code == 200
        run_input = challenge(client)
        assert run_input["purpose"] == "RUN"
        assert run_input["request_id"] != initialization["request_id"]
        assert len(ports[0].writes) == 1 and sessions == []
        assert declare(client, run_input).status_code == 200
        assert wait_idle(client)["error"] is None
        run = client.get(PREFIX + "/runs/recipe-run").json()
        assert run["status"] == "COMPLETED" and run["recipe_step_index"] == 10
        assert run["recipe"] == saved
    commands = [message for value in ports[0].writes
                if (message := json.loads(value))["type"] == "COMMAND"]
    assert any(c["command"] == "CAROUSEL_MOVE_TO_POSITION" for c in commands)
    assert any(c["command"] == "COLUMN_BOTTOM_VALVE_SET_POSITION" for c in commands)
    assert sessions


@pytest.mark.parametrize("missing", ["column", "carousel", "both"])
def test_configured_recipe_missing_live_collection_references_dispatches_nothing(configured, missing):
    from tests.test_operator_current_input import source, challenge, declare, references, request, AUTH

    build, ports, sessions, _, _, _ = configured
    current = source()
    execution = build(current_state_provider=current, context_clock=current.clock)
    with ApiClient(create_app(application_execution=execution), lifespan="on") as client:
        saved = save(client)
        assert execute(client, saved).status_code == 202
        assert declare(client, challenge(client)).status_code == 200
        fresh = challenge(client)
        data = references(request()).model_dump(mode="json")
        if missing in ("column", "both"):
            data["column_position_degrees"] = None
        if missing in ("carousel", "both"):
            data["carousel_position"] = None
        assert client.post(PREFIX + "/execution/current-input/" + fresh["request_id"],
                           json=data, headers=AUTH).status_code == 200
        assert "complete independently established current references" in wait_idle(client)["error"]
        assert len(ports[0].writes) == 1 and sessions == []
        run = client.get(PREFIX + "/runs/recipe-run").json()
        assert run["status"] == "CREATED" and run["recipe_step_index"] == 0
        # The successful initialization receipt cannot replace the rejected RUN input.
        assert declare(client, fresh).status_code == 409
        assert len(ports[0].writes) == 1 and sessions == []


def test_library_content_mutation_fails_before_run_creation_or_dispatch(assembly, bundle):
    import json

    app, execution, devices, _ = assembly
    path = bundle.lifecycle_path.with_name(bundle.lifecycle_path.name + ".recipes.sqlite3")
    with ApiClient(app, lifespan="on") as client:
        saved = save(client)
        assert client.post(PREFIX + "/recipes/preview", json=saved["definition"]).status_code == 200
        changed = saved["definition"]
        changed["steps"][0]["volume_ml"] = "10"
        with sqlite3.connect(path) as db:
            db.execute("UPDATE recipe_revisions SET payload=? WHERE recipe_id=? AND revision=?",
                       (json.dumps(changed), saved["recipe_id"], saved["revision"]))
        before = path.read_bytes()
        assert client.get(PREFIX + "/recipes").status_code == 409
        assert client.get(PREFIX + f"/recipes/{saved['recipe_id']}").status_code == 409
        response = execute(client, saved)
        assert response.status_code == 409 and "content identity" in response.text
        assert client.get(PREFIX + "/runs/recipe-run").status_code == 404
        assert devices[0].calls == devices[0].sf_calls == []
        assert path.read_bytes() == before
        with execution.store() as store:
            assert store.load_demo_run("recipe-run") is None


def test_execute_requires_reviewed_digest_even_if_stored_identity_is_consistent(assembly, bundle):
    app, _, devices, _ = assembly
    path = bundle.lifecycle_path.with_name(bundle.lifecycle_path.name + ".recipes.sqlite3")
    with ApiClient(app, lifespan="on") as client:
        saved = save(client)
        changed = definition([{"kind": "WAIT", "duration_seconds": "3"}])
        # Simulate replacement by another source with a valid digest at the same revision.
        # The old browser review must still fail even though the row is self-consistent.
        with sqlite3.connect(path) as db:
            db.execute("UPDATE recipe_revisions SET payload=?, content_digest=? WHERE recipe_id=?",
                       (changed.model_dump_json(), recipe_content_digest(changed), saved["recipe_id"]))
        response = execute(client, saved)
        assert response.status_code == 409 and "content identity changed" in response.text
        assert client.get(PREFIX + "/runs/recipe-run").status_code == 404
        assert devices[0].calls == devices[0].sf_calls == []
        missing = client.post(PREFIX + f"/recipes/{saved['recipe_id']}/execute", json={
            "run_id": "no-identity", "expected_revision": 1,
            "readiness": readiness().model_dump(mode="json"), **COMMAND,
        })
        assert missing.status_code == 422


def test_prior_library_schema_is_rejected_without_migration_or_rewrite(tmp_path):
    path = tmp_path / "v1.db"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE recipe_revisions (recipe_id TEXT NOT NULL, revision INTEGER NOT NULL, "
                   "payload TEXT NOT NULL, PRIMARY KEY(recipe_id, revision))")
        db.execute("INSERT INTO recipe_revisions VALUES (?, ?, ?)",
                   ("old", 1, definition().model_dump_json()))
        db.execute("PRAGMA user_version=1")
    before = path.read_bytes()
    with pytest.raises(RecipeConflict, match="unsupported"):
        RecipeStore(path)
    assert path.read_bytes() == before


def test_snapshot_digest_validation_and_canonical_json_identity():
    import hashlib
    import json

    value = definition().model_copy(update={"name": "Čista procedura"})
    canonical = json.dumps(value.model_dump(mode="json"), sort_keys=True,
                           separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert recipe_content_digest(value) == digest
    saved = SavedRecipe(recipe_id="identity", revision=1, definition=value, content_digest=digest)
    data = saved.model_dump(mode="json")
    data["definition"]["steps"][0]["volume_ml"] = "10"
    with pytest.raises(ValidationError, match="content identity mismatch"):
        SavedRecipe.model_validate(data)
