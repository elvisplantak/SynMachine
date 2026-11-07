"""Real SiLA protobuf/gRPC/TLS clients, existing application, fake devices only."""

import asyncio
import json
import os
import sqlite3
import subprocess
import sys
from threading import Event
from uuid import uuid4

import pytest

pytest.importorskip("sila", reason="install .[dev,sila2] for SiLA integration checks")
pytest.importorskip("cryptography")

from sila.client import Client, ClientConfig
from sila.server import DefinedExecutionError, create_certificate

from app.sila2.backend import BackendRejected, FakeBackend
from app.sila2.server import ORIGINATOR, fake_server
from tests import test_owned_application_api as owned_tests
from tests import test_owned_offline_runtime as runtime_tests
from tests.test_api import ApiClient
from tests.test_owned_application_api import wait_idle
from tests.test_recipes import definition, readiness, save

base_assembly = owned_tests.assembly
bundle = runtime_tests.bundle


@pytest.fixture
def assembly(base_assembly):
    # This fixture's device/timer factories are hardwired simulated objects.
    base_assembly[1]._transport_mode = "FAKE"
    return base_assembly


@pytest.fixture(scope="module")
def tls():
    identity = str(uuid4())
    return identity, create_certificate(identity, ip_addresses=["127.0.0.1"])


async def connect(server, certificate):
    client = Client(ClientConfig(
        hostname="127.0.0.1", port=int(server.address.rsplit(":", 1)[1]),
        tls=True, root_certificates=certificate.pem_certificate,
        default_timeout=5000, options={"grpc.enable_retries": False},
    ))
    await client.open()
    return client


def start_parameters(saved, run_id="sila-run"):
    return {"RecipeId": saved["recipe_id"], "RunId": run_id,
            "ExpectedRevision": saved["revision"], "ExpectedContentDigest": saved["content_digest"],
            "ReadinessJson": readiness().model_dump_json()}


def result(response):
    return json.loads(response.Result)


def test_tls_discovery_status_recipes_validation_and_no_device_commands(assembly, tls):
    app, _, devices, _ = assembly
    identity, cert = tls
    with ApiClient(app, lifespan="on") as api:
        saved = save(api)

        async def scenario():
            async with fake_server(app, server_uuid=identity,
                                   certificate=cert.pem_certificate, private_key=cert.pem_private_key) as server:
                client = await connect(server, cert)
                try:
                    assert await client.get_server_uuid() == identity
                    features = await client.get_implemented_features()
                    assert len(features) == 4
                    assert f"{ORIGINATOR}/recipes/SynMachineStatus/v1" in features
                    state = json.loads(await client.SynMachineStatus.Status.read())
                    assert state["health"] == {"status": "available"}
                    assert state["execution"]["transport_mode"] == "FAKE"
                    assert state["machine"] is None
                    assert json.loads(await client.SynMachineRecipes.Recipes.read()) == [saved]
                    assert result(await client.SynMachineRecipes.ReadRecipe(RecipeId=saved["recipe_id"])) == saved
                    preview = result(await client.SynMachineRecipes.ValidateRecipe(
                        DefinitionJson=definition().model_dump_json()))
                    assert preview["calibrations_checked"] is True
                    assert len(preview["steps"]) == 10
                    assert devices[0].calls == devices[0].sf_calls == []
                finally:
                    await client.close()

        asyncio.run(scenario())


@pytest.mark.parametrize("change,expected", [
    ({"ExpectedRevision": 2}, 409),
    ({"ExpectedContentDigest": "a" * 64}, 409),
    ({"ReadinessJson": "{}"}, 422),
    ({"ReadinessJson": "[]"}, 422),
    ({"ReadinessJson": "{invalid"}, 422),
    ({"ReadinessJson": '{"operator": NaN}'}, 422),
    ({"ReadinessJson": json.dumps({**readiness().model_dump(), "sources_match_recipe": "true"})}, 422),
    ({"RunId": "../machine/initialize"}, 422),
    ({"RecipeId": ".."}, 422),
    ({"RecipeId": "missing"}, 404),
])
def test_rejected_start_sends_no_commands(assembly, tls, change, expected):
    app, _, devices, _ = assembly
    identity, cert = tls
    with ApiClient(app, lifespan="on") as api:
        saved = save(api)

        async def scenario():
            async with fake_server(app, server_uuid=identity,
                                   certificate=cert.pem_certificate, private_key=cert.pem_private_key) as server:
                client = await connect(server, cert)
                try:
                    with pytest.raises(DefinedExecutionError) as caught:
                        await client.SynMachineExecution.StartRecipe(**(start_parameters(saved) | change))
                    assert json.loads(caught.value.message)["status"] == expected
                    assert devices[0].calls == devices[0].sf_calls == []
                finally:
                    await client.close()

        asyncio.run(scenario())


def test_sila_execution_uses_same_run_snapshot_and_command_journal(assembly, bundle, tls):
    app, _, devices, _ = assembly
    identity, cert = tls
    with ApiClient(app, lifespan="on") as api:
        saved = save(api)

        async def scenario():
            async with fake_server(app, server_uuid=identity,
                                   certificate=cert.pem_certificate, private_key=cert.pem_private_key) as server:
                client = await connect(server, cert)
                try:
                    accepted = result(await client.SynMachineExecution.StartRecipe(**start_parameters(saved)))
                    assert accepted["action"] == "RUN" and accepted["run_id"] == "sila-run"
                    assert (await asyncio.to_thread(wait_idle, api))["error"] is None
                    run = result(await client.SynMachineExecution.GetProgress(RunId="sila-run"))
                    assert run == (await asyncio.to_thread(api.get, "/api/v1/runs/sila-run")).json()
                    assert run["status"] == "COMPLETED" and run["recipe_step_index"] == 10
                    assert run["recipe"] == saved
                    assert devices[0].calls
                    with pytest.raises(DefinedExecutionError) as caught:
                        await client.SynMachineExecution.StartRecipe(**start_parameters(saved))
                    assert json.loads(caught.value.message)["status"] == 409
                finally:
                    await client.close()

        asyncio.run(scenario())
    with sqlite3.connect(bundle.execution_path) as db:
        assert db.execute("SELECT COUNT(*) FROM prepared_command_plans").fetchone()[0] == 10


def test_concurrent_ui_start_stop_identity_and_retained_maintenance(assembly, tls):
    app, _, devices, _ = assembly
    identity, cert = tls
    entered, release = Event(), Event()
    with ApiClient(app, lifespan="on") as api:
        saved = save(api)

        def before(_):
            entered.set()
            assert release.wait(10)

        devices[0].before_send = before

        async def scenario():
            async with fake_server(app, server_uuid=identity,
                                   certificate=cert.pem_certificate, private_key=cert.pem_private_key) as server:
                client = await connect(server, cert)
                try:
                    await client.SynMachineExecution.StartRecipe(**start_parameters(saved))
                    assert await asyncio.to_thread(entered.wait, 5)
                    # A second SiLA client/UI uses the same backend exclusion.
                    from tests.test_recipes import execute
                    competing = await asyncio.to_thread(execute, api, saved, "ui-competing")
                    assert competing.status_code == 409
                    state = json.loads(await client.SynMachineStatus.Status.read())
                    operation_id = state["execution"]["operation"]["operation_id"]
                    with pytest.raises(DefinedExecutionError) as caught:
                        await client.SynMachineExecution.Stop(OperationId="stale-operation")
                    assert json.loads(caught.value.message)["status"] == 409
                    response = result(await client.SynMachineExecution.Stop(OperationId=operation_id))
                    assert response
                    release.set()
                    stopped = await asyncio.to_thread(wait_idle, api)
                    assert stopped["retained_owner_id"]
                    run = result(await client.SynMachineExecution.GetProgress(RunId="sila-run"))
                    assert run["status"] == "ABORTED" and run["recipe_step_index"] == 0
                    with pytest.raises(DefinedExecutionError):
                        await client.SynMachineExecution.StartRecipe(**start_parameters(saved, "blocked-run"))
                finally:
                    release.set()
                    await client.close()

        asyncio.run(scenario())


@pytest.mark.parametrize("mode", ["LIVE", "UNSPECIFIED"])
def test_non_fake_backend_rejected_before_listener(assembly, tls, mode):
    app, execution, devices, _ = assembly
    identity, cert = tls
    execution._transport_mode = mode
    with ApiClient(app, lifespan="on"):
        async def scenario():
            with pytest.raises(BackendRejected, match="explicitly FAKE"):
                async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                       private_key=cert.pem_private_key):
                    pytest.fail("listener must not start")
        asyncio.run(scenario())
        assert devices[0].calls == devices[0].sf_calls == []


def test_backend_mode_rechecked_and_invalid_recipe_uses_same_validator(assembly):
    app, execution, devices, _ = assembly
    with ApiClient(app, lifespan="on"):
        async def scenario():
            backend = FakeBackend(app)
            try:
                with pytest.raises(BackendRejected) as caught:
                    await backend.validate_recipe(definition([
                        {"kind": "SF_MIX", "duration_seconds": "1"}]).model_dump_json())
                assert caught.value.status == 422
                execution._transport_mode = "LIVE"
                with pytest.raises(BackendRejected, match="explicitly FAKE"):
                    await backend.recipes()
            finally:
                await backend.close()
        asyncio.run(scenario())
        assert devices[0].calls == devices[0].sf_calls == []


def test_fake_adapter_transports_and_restart_do_not_replay(assembly, tmp_path, tls):
    import httpx

    from tests.browser_check import build_profile

    identity, cert = tls
    directory = tmp_path / "sila-fake"

    async def scenario():
        application, execution = build_profile(directory, command_delay=0)
        async with application.router.lifespan_context(application):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(application),
                                        base_url="http://test", trust_env=False) as api:
                response = await api.post("/api/v1/recipes", json={"definition": definition([
                    {"kind": "ADD", "source": "S", "volume_ml": "1"}]).model_dump(mode="json")})
                assert response.status_code == 200
                saved = response.json()
                async with fake_server(application, server_uuid=identity,
                                       certificate=cert.pem_certificate, private_key=cert.pem_private_key) as server:
                    client = await connect(server, cert)
                    try:
                        await client.SynMachineExecution.StartRecipe(**start_parameters(saved))
                        async with asyncio.timeout(10):
                            while (await api.get("/api/v1/execution")).json()["busy"]:
                                await asyncio.sleep(0.01)
                        run = result(await client.SynMachineExecution.GetProgress(RunId="sila-run"))
                        assert run["status"] == "COMPLETED"
                    finally:
                        await client.close()
        with sqlite3.connect(execution.bundle.execution_path) as db:
            rows = db.execute("SELECT * FROM arduino_command_journal").fetchall()
            assert rows
            assert set(db.execute("SELECT state FROM arduino_command_journal").fetchall()) == {("COMPLETED",)}
        # Same fake bundle, not a replacement/reset. Reopen does not replay commands.
        reopened, _ = build_profile(directory, command_delay=0)
        async with reopened.router.lifespan_context(reopened):
            async with fake_server(reopened, server_uuid=identity,
                                   certificate=cert.pem_certificate, private_key=cert.pem_private_key) as server:
                client = await connect(server, cert)
                try:
                    assert result(await client.SynMachineExecution.GetProgress(RunId="sila-run")) == run
                    assert json.loads(await client.SynMachineStatus.Status.read())["execution"]["busy"] is False
                    with sqlite3.connect(execution.bundle.execution_path) as db:
                        assert db.execute("SELECT * FROM arduino_command_journal").fetchall() == rows
                finally:
                    await client.close()

    asyncio.run(scenario())


def test_plaintext_connection_cannot_use_tls_server(assembly, tls):
    import grpc.aio

    app, _, devices, _ = assembly
    identity, cert = tls
    with ApiClient(app, lifespan="on"):
        async def scenario():
            async with fake_server(app, server_uuid=identity,
                                   certificate=cert.pem_certificate, private_key=cert.pem_private_key) as server:
                async with grpc.aio.insecure_channel(server.address) as channel:
                    call = channel.unary_unary(
                        "/sila2.org.silastandard.core.silaservice.v1.SiLAService/Get_ServerUUID")
                    with pytest.raises(grpc.aio.AioRpcError):
                        await call(b"", timeout=0.5)
                assert devices[0].calls == devices[0].sf_calls == []
        asyncio.run(scenario())


@pytest.mark.parametrize("name", ["LABFORGE_ARDUINO_PORT", "LABFORGE_SF_BOTTOM_VALVE_PORT"])
def test_launcher_rejects_live_environment_before_import_or_state(tmp_path, name):
    environment = {**os.environ, name: "forbidden-test-port"}
    imported = subprocess.run(
        [sys.executable, "-c", "import sys; import tests.sila2_check; assert 'app.main' not in sys.modules"],
        env=environment, capture_output=True, text=True, timeout=10,
    )
    assert imported.returncode == 0, imported.stderr
    launched = subprocess.run(
        [sys.executable, "-m", "tests.sila2_check", "--state-dir", str(tmp_path / "state")],
        env=environment, capture_output=True, text=True, timeout=10,
    )
    assert launched.returncode == 2 and "unset LABFORGE_ARDUINO_PORT" in launched.stderr
    assert not (tmp_path / "state").exists()
