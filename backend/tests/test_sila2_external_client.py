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
from app.sila2.server import fake_server
from tests import test_sila2 as shared
from tests.test_api import ApiClient
from tests.test_owned_application_api import wait_idle
from tests.test_recipes import definition, readiness, save

assembly = shared.assembly
base_assembly = shared.base_assembly
bundle = shared.bundle
tls = shared.tls


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

    async def launch(self, server, tls, action, *arguments, uuid=None, certificate=None):
        identity, cert = tls
        path = self.directory / "public-certificate.pem"
        path.write_bytes(certificate or cert.pem_certificate)
        return await asyncio.create_subprocess_exec(
            str(self.dotnet), str(self.dll), action,
            "--port", server.address.rsplit(":", 1)[1], "--certificate", str(path),
            "--server-uuid", uuid or identity, *arguments,
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


def test_external_discovery_complete_recipe_and_duplicate(assembly, bundle, tls, external_client):
    app, _, devices, _ = assembly
    identity, cert = tls
    with ApiClient(app, lifespan="on") as api:
        saved = save(api)

        async def scenario():
            async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                   private_key=cert.pem_private_key) as server:
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


def test_external_validation_stop_and_retained_owner(assembly, tls, external_client):
    app, _, devices, _ = assembly
    identity, cert = tls
    entered, release = Event(), Event()
    with ApiClient(app, lifespan="on") as api:
        saved = save(api)

        async def scenario():
            async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                   private_key=cert.pem_private_key) as server:
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
    assembly, bundle, tls, external_client, monkeypatch,
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
                                   private_key=cert.pem_private_key) as server:
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


def test_external_identity_tls_and_non_fake_status_reject_before_start(assembly, tls, external_client, monkeypatch):
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
                                   private_key=cert.pem_private_key) as server:
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
