"""Cross-implementation checks: separate .NET process vs Python SiLA server.

Build the client first, then set SYNMACHINE_SILA_DOTNET and
SYNMACHINE_SILA_CLIENT_DLL. No SDK download/build occurs during pytest.
"""

import asyncio
import base64
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from threading import Event

import pytest

pytest.importorskip("sila", reason="install .[dev,sila2] for external SiLA checks")

from sila.framework import SiLAError

from app.sila2.backend import FakeBackend
from app.recipes.models import RecipeDefinition
from app.sila2.server import fake_server
from tests import test_sila2 as shared
from tests.test_api import ApiClient
from tests.test_owned_application_api import wait_idle
from tests.test_recipes import definition, readiness, save

assembly = shared.assembly
base_assembly = shared.base_assembly
bundle = shared.bundle
tls = shared.tls
access = shared.access


@pytest.fixture
def external_client(tmp_path):
    dotnet = os.environ.get("SYNMACHINE_SILA_DOTNET")
    dll = os.environ.get("SYNMACHINE_SILA_CLIENT_DLL")
    if not dotnet or not dll:
        pytest.skip("set SYNMACHINE_SILA_DOTNET and SYNMACHINE_SILA_CLIENT_DLL for .NET interoperability")
    assert Path(dotnet).is_file() and Path(dll).is_file(), "explicit .NET executable/client DLL missing"
    return ExternalClient(Path(dotnet), Path(dll), tmp_path)


class ExternalClient:
    def __init__(self, dotnet, dll, directory):
        self.dotnet, self.dll, self.directory = dotnet, dll, directory

    async def launch(self, server, tls, action, *arguments, uuid=None, certificate=None, token_file="controller.token"):
        identity, cert = tls
        path = self.directory / "public-certificate.pem"
        path.write_bytes(certificate or cert.pem_certificate)
        auth = [] if token_file is None else ["--token-file", str(self.directory / token_file)]
        return await asyncio.create_subprocess_exec(
            str(self.dotnet), str(self.dll), action,
            "--port", server.address.rsplit(":", 1)[1], "--certificate", str(path),
            "--server-uuid", uuid or identity, *auth, *arguments,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            env={**os.environ, "DOTNET_CLI_TELEMETRY_OPTOUT": "1"},
        )

    async def call(self, server, tls, action, *arguments, **options):
        process = await self.launch(server, tls, action, *arguments, **options)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 20)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        return process.returncode, stdout.decode(), stderr.decode()

    def start_arguments(self, saved, run_id="external-run"):
        snapshot = self.directory / "reviewed-recipe.json"
        declaration = self.directory / "readiness.json"
        snapshot.write_text(json.dumps(saved))
        declaration.write_text(readiness().model_dump_json())
        return ("--recipe", str(snapshot), "--readiness", str(declaration), "--run-id", run_id)


def success(response):
    code, stdout, stderr = response
    assert code == 0, (code, stdout, stderr)
    return json.loads(stdout)


def rejection(response, expected, *, attempted=False):
    code, stdout, stderr = response
    assert code == (3 if attempted else 2), (code, stdout, stderr)
    error = json.loads(stderr.splitlines()[0])
    assert error["start_attempted"] is attempted
    assert error["error"] == "Aborted", error
    assert error["backend"]["status"] == expected
    decoded = SiLAError.decode(base64.b64decode(error["detail"]))
    assert json.loads(decoded.message)["status"] == expected


def test_external_discovery_complete_recipe_and_duplicate(assembly, bundle, tls, external_client, access):
    app, _, devices, _ = assembly
    identity, cert = tls
    with ApiClient(app, lifespan="on") as api:
        saved = save(api)

        async def scenario():
            async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                   private_key=cert.pem_private_key, access=access) as server:
                discovered = success(await external_client.call(server, tls, "discover"))
                assert discovered["server_uuid"] == identity and len(discovered["features"]) == 4
                status = success(await external_client.call(server, tls, "status"))
                assert status["execution"]["transport_mode"] == "FAKE"
                assert success(await external_client.call(server, tls, "recipes")) == [saved]
                assert success(await external_client.call(server, tls, "read", "--recipe-id", saved["recipe_id"])) == saved
                preview_path = external_client.directory / "definition.json"
                preview_path.write_text(definition().model_dump_json())
                preview = success(await external_client.call(server, tls, "validate", "--definition", str(preview_path)))
                assert preview["calibrations_checked"] is True and len(preview["steps"]) == 10
                args = external_client.start_arguments(saved)
                accepted = success(await external_client.call(server, tls, "start", *args))
                assert accepted["run_id"] == "external-run" and accepted["action"] == "RUN"
                assert (await asyncio.to_thread(wait_idle, api))["error"] is None
                run = success(await external_client.call(server, tls, "progress", "--run-id", "external-run"))
                assert run["status"] == "COMPLETED" and run["recipe_step_index"] == 10
                assert run["recipe"] == saved
                assert success(await external_client.call(server, tls, "watch", "--run-id", "external-run")) == run
                rejection(await external_client.call(server, tls, "start", *args), 409, attempted=True)
                assert devices[0].calls
        asyncio.run(scenario())
    with sqlite3.connect(bundle.execution_path) as db:
        assert db.execute("SELECT COUNT(*) FROM prepared_command_plans").fetchone()[0] == 10


@pytest.mark.parametrize("name", ["LABFORGE_ARDUINO_PORT", "LABFORGE_SF_BOTTOM_VALVE_PORT"])
def test_external_demo_rejects_live_environment_before_state(tmp_path, name):
    directory = tmp_path / "demo-state"
    environment = {**os.environ, name: "forbidden-test-port"}
    inert = subprocess.run(
        [sys.executable, "-c", "import sys; import tests.sila2_external_demo; assert 'app.main' not in sys.modules"],
        env=environment, capture_output=True, text=True, timeout=10,
    )
    assert inert.returncode == 0, inert.stderr
    launched = subprocess.run(
        [sys.executable, "-m", "tests.sila2_external_demo", "--state-dir", str(directory),
         "--dotnet", str(tmp_path / "not-used")],
        env=environment, capture_output=True, text=True, timeout=10,
    )
    assert launched.returncode == 2 and "unset LABFORGE_ARDUINO_PORT" in launched.stderr
    assert not directory.exists()


def test_external_validation_stop_and_retained_owner(assembly, tls, external_client, access):
    app, _, devices, _ = assembly
    identity, cert = tls
    entered, release = Event(), Event()
    with ApiClient(app, lifespan="on") as api:
        saved = save(api)

        async def scenario():
            async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                   private_key=cert.pem_private_key, access=access) as server:
                invalid = dict(saved, revision=saved["revision"] + 1)
                rejection(await external_client.call(server, tls, "start", *external_client.start_arguments(invalid)),
                          409, attempted=True)
                args = external_client.start_arguments(saved)
                (external_client.directory / "readiness.json").write_text("{}")
                rejection(await external_client.call(server, tls, "start", *args), 422, attempted=True)
                assert devices[0].calls == devices[0].sf_calls == []

                def hold(_):
                    entered.set()
                    assert release.wait(30)
                devices[0].before_send = hold
                try:
                    success(await external_client.call(server, tls, "start", *external_client.start_arguments(saved)))
                    assert await asyncio.to_thread(entered.wait, 5)
                    status = success(await external_client.call(server, tls, "status"))
                    operation = status["execution"]["operation"]["operation_id"]
                    rejection(await external_client.call(server, tls, "stop", "--operation-id", "stale-id"), 409)
                    success(await external_client.call(server, tls, "stop", "--operation-id", operation))
                finally:
                    release.set()
                stopped = await asyncio.to_thread(wait_idle, api)
                assert stopped["retained_owner_id"]
                run = success(await external_client.call(server, tls, "progress", "--run-id", "external-run"))
                assert run["status"] == "ABORTED" and run["recipe_step_index"] == 0
                rejection(await external_client.call(server, tls, "start",
                          *external_client.start_arguments(saved, "blocked-run")), 409, attempted=True)
        asyncio.run(scenario())


def test_external_client_disconnect_after_acceptance_reconnects_without_replay(
    assembly, bundle, tls, external_client, monkeypatch, access,
):
    app, _, devices, _ = assembly
    identity, cert = tls
    entered, release_device = Event(), Event()
    with ApiClient(app, lifespan="on") as api:
        saved = save(api)

        def hold(_):
            entered.set()
            assert release_device.wait(30)
        devices[0].before_send = hold

        async def scenario():
            accepted, release_response = asyncio.Event(), asyncio.Event()
            original = FakeBackend.start_recipe
            calls = []

            async def lose_response(self, *args, **kwargs):
                result = await original(self, *args, **kwargs)
                calls.append(result)
                accepted.set()
                await release_response.wait()
                return result

            monkeypatch.setattr(FakeBackend, "start_recipe", lose_response)
            async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                   private_key=cert.pem_private_key, access=access) as server:
                process = await external_client.launch(server, tls, "start", *external_client.start_arguments(saved))
                try:
                    await asyncio.wait_for(accepted.wait(), 15)
                    assert await asyncio.to_thread(entered.wait, 5)
                    # Actual process/socket loss after durable acceptance, before any Start response.
                    process.kill()
                    stdout, _ = await process.communicate()
                    assert stdout == b"" and len(calls) == 1
                    release_response.set()
                    run = success(await external_client.call(server, tls, "progress", "--run-id", "external-run"))
                    assert run["status"] == "RUNNING" and run["recipe"] == saved
                    release_device.set()
                    assert (await asyncio.to_thread(wait_idle, api))["error"] is None
                    before = tuple(devices[0].calls)
                    run = success(await external_client.call(server, tls, "progress", "--run-id", "external-run"))
                    assert run["status"] == "COMPLETED" and tuple(devices[0].calls) == before
                    assert len(calls) == 1
                finally:
                    release_device.set()
                    release_response.set()
                    if process.returncode is None:
                        process.kill()
                        await process.wait()
        asyncio.run(scenario())
    with sqlite3.connect(bundle.execution_path) as db:
        assert db.execute("SELECT COUNT(*) FROM prepared_command_plans").fetchone()[0] == 10


def test_external_identity_tls_and_non_fake_status_reject_before_start(assembly, tls, external_client, monkeypatch, access):
    from uuid import uuid4

    from sila.server import create_certificate

    app, _, devices, _ = assembly
    identity, cert = tls
    original = FakeBackend.status

    async def live_marker(self):
        snapshot = await original(self)
        snapshot["execution"]["transport_mode"] = "LIVE"
        return snapshot

    # Feature handlers bind the method during server registration.
    monkeypatch.setattr(FakeBackend, "status", live_marker)
    with ApiClient(app, lifespan="on") as api:
        saved = save(api)

        async def scenario():
            async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                   private_key=cert.pem_private_key, access=access) as server:
                args = external_client.start_arguments(saved)
                wrong_id = await external_client.call(server, tls, "start", *args, uuid=str(uuid4()))
                assert wrong_id[0] == 2 and "server UUID differs" in wrong_id[2]
                other = create_certificate(str(uuid4()), ip_addresses=["127.0.0.1"])
                wrong_tls = await external_client.call(server, tls, "start", *args, certificate=other.pem_certificate)
                assert wrong_tls[0] == 2 and '"start_attempted":false' in wrong_tls[2]
                non_fake = await external_client.call(server, tls, "start", *args)
                assert non_fake[0] == 2 and "requires an explicitly FAKE server" in non_fake[2]
                assert devices[0].calls == devices[0].sf_calls == []
        asyncio.run(scenario())


def test_external_reader_permissions_and_authenticated_attribution(assembly, tls, external_client, access):
    app, _, devices, _ = assembly
    identity, cert = tls
    entered, release = Event(), Event()
    with ApiClient(app, lifespan="on") as api:
        saved = save(api)

        async def scenario():
            async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                   private_key=cert.pem_private_key, access=access) as server:
                missing = await external_client.call(server, tls, "status", token_file=None)
                assert missing[0] == 2 and json.loads(missing[2].splitlines()[0])["error"] == "Unauthenticated"
                assert success(await external_client.call(server, tls, "recipes", token_file="reader.token")) == [saved]
                args = external_client.start_arguments(saved)
                denied = await external_client.call(server, tls, "start", *args, token_file="reader.token")
                assert denied[0] == 3 and json.loads(denied[2].splitlines()[0])["error"] == "PermissionDenied"
                assert devices[0].calls == devices[0].sf_calls == []

                def hold(_):
                    entered.set()
                    assert release.wait(30)
                devices[0].before_send = hold
                try:
                    accepted = success(await external_client.call(server, tls, "start", *args))
                    assert await asyncio.to_thread(entered.wait, 5)
                    denied_stop = await external_client.call(server, tls, "stop", "--operation-id",
                                                           accepted["operation_id"], token_file="reader.token")
                    assert denied_stop[0] == 2 and "PermissionDenied" in denied_stop[2]
                    assert (await asyncio.to_thread(api.get, "/api/v1/execution")).json()["busy"]
                    success(await external_client.call(server, tls, "stop", "--operation-id", accepted["operation_id"]))
                finally:
                    release.set()
                assert (await asyncio.to_thread(wait_idle, api))["retained_owner_id"]
        asyncio.run(scenario())
    with sqlite3.connect(access.audit.path) as db:
        assert db.execute("SELECT client_id,role,run_id FROM sila_access_events WHERE event='RESULT' AND rpc_method LIKE '%/StartRecipe'").fetchall() == [
            ("fake-controller", "CONTROL", "external-run")]
        assert db.execute("SELECT COUNT(*) FROM sila_access_events WHERE event='FORBIDDEN' AND client_id='fake-reader'").fetchone()[0] == 2


def test_external_client_executes_xdl_import_through_the_shared_recipe_library(assembly, tls, external_client, access):
    app, _, devices, _ = assembly
    identity, cert = tls
    xml = (Path(__file__).parents[1] / 'examples/xdl2/coloured-water.xdl').read_text()
    with ApiClient(app, lifespan='on') as api:
        imported = api.post('/api/v1/recipes/xdl/import', json={
            'xml': xml, 'reagents': {'S':'coloured_water'},
            'vessels': {'REACTOR':'reaction_vessel'}})
        assert imported.status_code == 200, imported.text
        value = imported.json()['definition']
        assert api.get('/api/v1/recipes').json() == []
        assert devices[0].calls == devices[0].sf_calls == []
        saved = save(api, RecipeDefinition.model_validate(value))

        async def scenario():
            async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                   private_key=cert.pem_private_key, access=access) as server:
                assert success(await external_client.call(server, tls, 'recipes', token_file='reader.token')) == [saved]
                success(await external_client.call(server, tls, 'start', *external_client.start_arguments(saved, 'xdl-external-run')))
                code, output, error = await external_client.call(server, tls, 'watch', '--run-id', 'xdl-external-run')
                assert code == 0, error
                completed = json.loads(output.splitlines()[-1])
                assert completed['status'] == 'COMPLETED' and completed['recipe_step_index'] == 2
                assert completed['recipe']['content_digest'] == saved['content_digest']
        asyncio.run(scenario())
    with sqlite3.connect(access.audit.path) as db:
        assert db.execute("SELECT client_id,run_id FROM sila_access_events WHERE event='RESULT' AND rpc_method LIKE '%/StartRecipe'").fetchall() == [
            ('fake-controller', 'xdl-external-run')]
