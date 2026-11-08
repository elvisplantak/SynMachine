"""Server-enforced identity/roles and durable attribution through real TLS RPCs."""

import asyncio
from datetime import UTC, datetime, timedelta
import json
import sqlite3
from unittest.mock import AsyncMock, Mock

import pytest

pytest.importorskip("sila")

import grpc.aio
from sila.server import DefinedExecutionError
from sila.framework.data_types import Structure
from sila.framework.protobuf import DecodeError

from app.sila2.access import AccessControl, AuditJournal, AuditUnavailable, Credential, METHODS, Policy, Role
from app.sila2.server import fake_server
from tests import test_sila2 as shared
from tests.test_api import ApiClient
from tests.test_owned_application_api import wait_idle
from tests.test_recipes import save

assembly = shared.assembly
base_assembly = shared.base_assembly
bundle = shared.bundle
tls = shared.tls
access = shared.access
STATUS_RPC = "/sila2.com.github.elvisplantak.synmachine.recipes.synmachinestatus.v1.SynMachineStatus/Get_Status"
START_RPC = "/sila2.com.github.elvisplantak.synmachine.recipes.synmachineexecution.v1.SynMachineExecution/StartRecipe"
STOP_RPC = "/sila2.com.github.elvisplantak.synmachine.recipes.synmachineexecution.v1.SynMachineExecution/Stop"


def rows(access):
    with sqlite3.connect(access.audit.path) as db:
        db.row_factory = sqlite3.Row
        return [dict(row) for row in db.execute("SELECT * FROM sila_access_events ORDER BY sequence")]


async def raw(server, cert, method=STATUS_RPC, metadata=(), payload=b""):
    async with grpc.aio.secure_channel(server.address,
                                      grpc.ssl_channel_credentials(cert.pem_certificate)) as channel:
        return await channel.unary_unary(method)(payload, metadata=metadata, timeout=3)


@pytest.fixture
def rpc_boundaries(access, monkeypatch):
    """Exercise a configured gRPC decoder as well as the SDK's own decoding.

    SDK 0.13.0 application handlers currently have request_deserializer=None;
    their command behavior decodes bytes later. Install a real SDK wire parser
    at the optional gRPC seam to prove admission precedes that seam too. Keep
    bytes as its output so the original SDK behavior retains its input contract.
    """
    observed = {}
    protect = access.protect
    message = Structure.create(name="AdmissionProbe", elements={})

    def decode_wire(payload):
        message.decode(payload)
        return payload

    def instrument(server, identity):
        observed["sdk_decode"] = AsyncMock(wraps=server.protobuf.decode)
        monkeypatch.setattr(server.protobuf, "decode", observed["sdk_decode"])
        for service, handlers in server.protobuf.services.items():
            for method, handler in tuple(handlers.items()):
                rpc = f"/{service}/{method}"
                if rpc in METHODS:
                    assert handler.request_deserializer is None
                    decode = Mock(wraps=decode_wire)
                    behavior = AsyncMock(wraps=handler.unary_unary)
                    handlers[method] = grpc.unary_unary_rpc_method_handler(
                        behavior, request_deserializer=decode,
                        response_serializer=handler.response_serializer,
                    )
                    observed[rpc] = (decode, behavior)
        protect(server, identity)

    monkeypatch.setattr(access, "protect", instrument)
    return observed


@pytest.mark.parametrize("payload", [b"\x80", b"\x0a\x80"], ids=["truncated-tag", "truncated-length"])
@pytest.mark.parametrize("method,token_file,status,event", [
    (START_RPC, None, grpc.StatusCode.UNAUTHENTICATED, "UNAUTHENTICATED"),
    (STATUS_RPC, None, grpc.StatusCode.UNAUTHENTICATED, "UNAUTHENTICATED"),
    (START_RPC, "reader.token", grpc.StatusCode.PERMISSION_DENIED, "FORBIDDEN"),
    (STOP_RPC, "reader.token", grpc.StatusCode.PERMISSION_DENIED, "FORBIDDEN"),
])
def test_wire_admission_precedes_native_deserialization(
    assembly, tls, access, rpc_boundaries, method, token_file, status, event, payload,
):
    app, _, devices, _ = assembly
    identity, cert = tls
    metadata = [] if token_file is None else [
        ("authorization", "Bearer " + (access.audit.path.parent / token_file).read_text())]
    with ApiClient(app, lifespan="on"):
        async def scenario():
            async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                   private_key=cert.pem_private_key, access=access) as server:
                with pytest.raises(grpc.aio.AioRpcError) as caught:
                    await raw(server, cert, method, metadata, payload)
                assert caught.value.code() is status
        asyncio.run(scenario())
        decode, behavior = rpc_boundaries[method]
        decode.assert_not_called()
        behavior.assert_not_called()
        rpc_boundaries["sdk_decode"].assert_not_called()
        # Prove these bytes are invalid for the actual pinned SDK parser.
        with pytest.raises(DecodeError):
            decode(payload)
        assert devices[0].calls == devices[0].sf_calls == []
    events = rows(access)
    assert [row["event"] for row in events] == [event]
    assert events[0]["client_id"] == (None if token_file is None else "fake-reader")


@pytest.mark.parametrize("payload", [b"\x80", b"\x0a\x80"], ids=["truncated-tag", "truncated-length"])
@pytest.mark.parametrize("method", [START_RPC, STOP_RPC, STATUS_RPC])
def test_authorized_invalid_wire_uses_native_decoder_without_dispatch(
    assembly, tls, access, rpc_boundaries, method, payload,
):
    app, _, devices, _ = assembly
    identity, cert = tls
    token = (access.audit.path.parent / "controller.token").read_text()
    with ApiClient(app, lifespan="on"):
        async def scenario():
            async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                   private_key=cert.pem_private_key, access=access) as server:
                with pytest.raises(grpc.aio.AioRpcError) as caught:
                    await raw(server, cert, method, [("authorization", f"Bearer {token}")], payload)
                # grpc.aio reports uncaught native protobuf DecodeError as UNKNOWN.
                assert caught.value.code() is grpc.StatusCode.UNKNOWN
        asyncio.run(scenario())
        decode, behavior = rpc_boundaries[method]
        decode.assert_called_once_with(payload)
        behavior.assert_not_called()
        rpc_boundaries["sdk_decode"].assert_not_called()
        assert devices[0].calls == devices[0].sf_calls == []
    assert [row["event"] for row in rows(access)] == ["AUTHORIZED", "RPC_FAILED"]


def test_configured_decoder_preserves_valid_sdk_call_and_response(assembly, tls, access, rpc_boundaries):
    app, _, devices, _ = assembly
    identity, cert = tls
    with ApiClient(app, lifespan="on"):
        async def scenario():
            async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                   private_key=cert.pem_private_key, access=access) as server:
                client = await shared.connect(server, cert, access, "reader.token")
                try:
                    state = json.loads(await client.SynMachineStatus.Status.read())
                    assert state["execution"]["transport_mode"] == "FAKE"
                finally:
                    await client.close()
        asyncio.run(scenario())
        decode, behavior = rpc_boundaries[STATUS_RPC]
        decode.assert_called_once_with(b"")
        assert behavior.await_args.args[0] == b""
        behavior.assert_awaited_once()
        assert devices[0].calls == devices[0].sf_calls == []
    assert [row["event"] for row in rows(access)] == ["AUTHORIZED", "DISPATCH", "RESULT"]


@pytest.mark.parametrize("payload", [b"\x80", b"\x0a\x80"], ids=["truncated-tag", "truncated-length"])
@pytest.mark.parametrize("method", [START_RPC, STOP_RPC])
def test_native_sdk_decoding_keeps_its_error_semantics(assembly, tls, access, monkeypatch, method, payload):
    app, _, devices, _ = assembly
    identity, cert = tls
    token = (access.audit.path.parent / "controller.token").read_text()
    with ApiClient(app, lifespan="on"):
        async def scenario():
            async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                   private_key=cert.pem_private_key, access=access) as server:
                decode = AsyncMock(wraps=server.protobuf.decode)
                monkeypatch.setattr(server.protobuf, "decode", decode)
                with pytest.raises(grpc.aio.AioRpcError) as caught:
                    await raw(server, cert, method, [("authorization", f"Bearer {token}")], payload)
                assert caught.value.code() is grpc.StatusCode.ABORTED
                decode.assert_awaited_once()
                assert decode.await_args.args[1] == payload
        asyncio.run(scenario())
        assert devices[0].calls == devices[0].sf_calls == []
    assert [row["event"] for row in rows(access)] == ["AUTHORIZED", "RPC_FAILED"]


@pytest.mark.parametrize("kind", ["missing", "unknown", "malformed", "duplicate", "expired", "disabled", "revoked"])
def test_credentials_reject_before_backend(assembly, tls, access, kind):
    app, _, devices, _ = assembly
    identity, cert = tls
    token = (access.audit.path.parent / "controller.token").read_text()
    metadata = [("authorization", f"Bearer {token}")]
    if kind == "missing":
        metadata = [("x-client-id", "fake-controller")]
    elif kind == "unknown":
        metadata = [("authorization", "Bearer " + "z" * 43), ("x-client-id", "fake-controller")]
    elif kind == "malformed":
        metadata = [("authorization", "Bearer short")]
    elif kind == "duplicate":
        metadata *= 2
    elif kind == "revoked":
        access.policy.revoke("fake-controller")
    else:
        value = Credential.from_token(client_id="fake-controller", role=Role.CONTROL, token=token,
                                      expires_at=datetime.now(UTC) + timedelta(hours=1))
        update = {"expires_at": datetime.now(UTC) - timedelta(seconds=1)} if kind == "expired" else {"enabled": False}
        access.policy = Policy([value.model_copy(update=update)])
    with ApiClient(app, lifespan="on"):
        async def scenario():
            async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                   private_key=cert.pem_private_key, access=access) as server:
                with pytest.raises(grpc.aio.AioRpcError) as caught:
                    await raw(server, cert, START_RPC, metadata)
                assert caught.value.code() is grpc.StatusCode.UNAUTHENTICATED
                assert token not in caught.value.details()
        asyncio.run(scenario())
        assert devices[0].calls == devices[0].sf_calls == []
    assert rows(access)[-1]["event"] == "UNAUTHENTICATED"
    assert rows(access)[-1]["client_id"] is None
    assert token not in access.audit.path.read_bytes().decode("latin1")


@pytest.mark.parametrize("method", [START_RPC, STOP_RPC])
def test_reader_cannot_start_or_stop_with_default_payload(assembly, tls, access, method):
    app, _, devices, _ = assembly
    identity, cert = tls
    reader = (access.audit.path.parent / "reader.token").read_text()
    with ApiClient(app, lifespan="on"):
        async def scenario():
            async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                   private_key=cert.pem_private_key, access=access) as server:
                with pytest.raises(grpc.aio.AioRpcError) as caught:
                    await raw(server, cert, method, [("authorization", f"Bearer {reader}")])
                assert caught.value.code() is grpc.StatusCode.PERMISSION_DENIED
        asyncio.run(scenario())
        assert devices[0].calls == devices[0].sf_calls == []
    assert rows(access)[-1]["event"] == "FORBIDDEN" and rows(access)[-1]["client_id"] == "fake-reader"


def test_reader_reads_but_cannot_interrupt_controller_and_audit_links_existing_run(assembly, bundle, tls, access):
    from threading import Event

    app, _, devices, _ = assembly
    identity, cert = tls
    entered, release = Event(), Event()
    with ApiClient(app, lifespan="on") as api:
        saved = save(api)

        async def scenario():
            async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                   private_key=cert.pem_private_key, access=access) as server:
                controller = await shared.connect(server, cert, access)
                reader = await shared.connect(server, cert, access, "reader.token")
                try:
                    assert json.loads(await reader.SynMachineRecipes.Recipes.read()) == [saved]

                    def hold(_):
                        entered.set()
                        assert release.wait(20)
                    devices[0].before_send = hold
                    accepted = shared.result(await controller.SynMachineExecution.StartRecipe(**shared.start_parameters(saved)))
                    assert await asyncio.to_thread(entered.wait, 5)
                    progress = shared.result(await reader.SynMachineExecution.GetProgress(RunId="sila-run"))
                    assert progress["status"] == "RUNNING"
                    reader_token = (access.audit.path.parent / "reader.token").read_text()
                    with pytest.raises(grpc.aio.AioRpcError) as caught:
                        await raw(server, cert, STOP_RPC, [("authorization", f"Bearer {reader_token}")])
                    assert caught.value.code() is grpc.StatusCode.PERMISSION_DENIED
                    assert (await asyncio.to_thread(api.get, "/api/v1/execution")).json()["busy"]
                    await controller.SynMachineExecution.Stop(OperationId=accepted["operation_id"])
                    release.set()
                    assert (await asyncio.to_thread(wait_idle, api))["retained_owner_id"]
                finally:
                    release.set()
                    await controller.close()
                    await reader.close()
        asyncio.run(scenario())
    events = rows(access)
    start = [r for r in events if r["rpc_method"] == START_RPC]
    assert [r["event"] for r in start] == ["AUTHORIZED", "DISPATCH", "RESULT"]
    assert len({r["request_id"] for r in start}) == 1
    assert start[-1]["client_id"] == "fake-controller" and start[-1]["run_id"] == "sila-run"
    assert start[-1]["operation_id"] == accepted_operation(events)
    assert start[1]["expected_content_digest"] == saved["content_digest"]
    assert start[1]["recipe_id"] == saved["recipe_id"] and start[1]["expected_revision"] == saved["revision"]
    assert any(r["client_id"] == "fake-reader" and r["event"] == "RESULT"
               and r["rpc_method"].endswith("/GetProgress") for r in events)
    with sqlite3.connect(bundle.execution_path) as db:
        assert db.execute("SELECT COUNT(*) FROM prepared_command_plans").fetchone()[0] == 1
    for name in ("reader.token", "controller.token"):
        assert (access.audit.path.parent / name).read_text() not in access.audit.path.read_bytes().decode("latin1")
    reopened = AuditJournal(access.audit.path)
    assert rows(AccessControl(access.policy, reopened)) == events


def accepted_operation(events):
    return next(row["operation_id"] for row in events if row["rpc_method"] == STOP_RPC and row["event"] == "DISPATCH")


@pytest.mark.parametrize("failure_at", ["AUTHORIZED", "DISPATCH", "RESULT"])
def test_audit_failure_blocks_dispatch_or_preserves_unknown_accepted_outcome(
    assembly, tls, access, monkeypatch, failure_at,
):
    app, _, devices, _ = assembly
    identity, cert = tls
    original = access.audit.append

    def fail(request, event, **kwargs):
        if request.rpc_method == START_RPC and event == failure_at:
            raise AuditUnavailable()
        return original(request, event, **kwargs)

    monkeypatch.setattr(access.audit, "append", fail)
    with ApiClient(app, lifespan="on") as api:
        saved = save(api)

        async def scenario():
            async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                   private_key=cert.pem_private_key, access=access) as server:
                client = await shared.connect(server, cert, access)
                try:
                    if failure_at == "AUTHORIZED":
                        token = (access.audit.path.parent / "controller.token").read_text()
                        with pytest.raises(grpc.aio.AioRpcError) as caught:
                            await raw(server, cert, START_RPC, [("authorization", f"Bearer {token}")])
                        assert caught.value.code() is grpc.StatusCode.UNAVAILABLE
                    else:
                        with pytest.raises(DefinedExecutionError) as caught:
                            await client.SynMachineExecution.StartRecipe(**shared.start_parameters(saved))
                        assert json.loads(caught.value.message)["status"] == 503
                    if failure_at != "RESULT":
                        assert devices[0].calls == devices[0].sf_calls == []
                        assert (await asyncio.to_thread(api.get, "/api/v1/runs/sila-run")).status_code == 404
                    else:
                        assert (await asyncio.to_thread(wait_idle, api))["error"] is None
                        progress = shared.result(await client.SynMachineExecution.GetProgress(RunId="sila-run"))
                        assert progress["status"] == "COMPLETED"
                        assert any(r["event"] == "DISPATCH" and r["run_id"] == "sila-run" for r in rows(access))
                finally:
                    await client.close()
        asyncio.run(scenario())


def test_policy_requires_unique_expiring_explicit_credentials_and_unknown_audit_is_preserved(tmp_path):
    token = "a" * 43
    value = Credential.from_token(client_id="client", role=Role.READ_ONLY, token=token,
                                  expires_at=datetime.now(UTC) + timedelta(hours=1))
    with pytest.raises(ValueError, match="unique"):
        Policy([value, value])
    with pytest.raises(ValueError):
        Credential.from_token(client_id="client", role=Role.CONTROL, token="short",
                              expires_at=datetime.now(UTC))
    with pytest.raises(ValueError):
        Credential.from_token(client_id="client", role=Role.CONTROL, token=token,
                              expires_at=datetime.now())
    path = tmp_path / "foreign.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE foreign_state (value TEXT)")
    connection.commit()
    connection.close()
    before = path.read_bytes()
    with pytest.raises(ValueError, match="unsupported"):
        AuditJournal(path)
    assert path.read_bytes() == before
    own_path = tmp_path / "audit.sqlite3"
    AuditJournal(own_path)
    connection = sqlite3.connect(own_path)
    connection.execute("CREATE TABLE sqliteXunrecognized (value TEXT)")
    connection.commit()
    connection.close()
    before = own_path.read_bytes()
    with pytest.raises(ValueError, match="unsupported"):
        AuditJournal(own_path)
    assert own_path.read_bytes() == before


def test_revocation_is_checked_again_on_same_tls_connection(assembly, tls, access):
    app, _, devices, _ = assembly
    identity, cert = tls
    token = (access.audit.path.parent / "controller.token").read_text()
    with ApiClient(app, lifespan="on"):
        async def scenario():
            async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                   private_key=cert.pem_private_key, access=access) as server:
                async with grpc.aio.secure_channel(server.address, grpc.ssl_channel_credentials(cert.pem_certificate)) as channel:
                    call = channel.unary_unary(STATUS_RPC)
                    assert await call(b"", metadata=[("authorization", f"Bearer {token}")])
                    access.policy.revoke("fake-controller")
                    with pytest.raises(grpc.aio.AioRpcError) as caught:
                        await call(b"", metadata=[("authorization", f"Bearer {token}")])
                    assert caught.value.code() is grpc.StatusCode.UNAUTHENTICATED
        asyncio.run(scenario())
        assert devices[0].calls == devices[0].sf_calls == []


def test_rpc_mapping_fails_closed_and_binary_upload_is_not_exposed(assembly, tls, access):
    from sila.server import Server

    app, _, devices, _ = assembly
    identity, cert = tls
    server = Server()
    server.protobuf.services["unclassified.Service"] = {
        "Action": grpc.unary_unary_rpc_method_handler(lambda *_: b"")}
    with pytest.raises(ValueError, match="missing an explicit"):
        access.protect(server, identity)
    with ApiClient(app, lifespan="on"):
        async def scenario():
            async with fake_server(app, server_uuid=identity, certificate=cert.pem_certificate,
                                   private_key=cert.pem_private_key, access=access) as secured:
                with pytest.raises(grpc.aio.AioRpcError) as caught:
                    await raw(secured, cert, "/sila2.org.silastandard.BinaryUpload/CreateBinary")
                assert caught.value.code() is grpc.StatusCode.UNIMPLEMENTED
        asyncio.run(scenario())
        assert devices[0].calls == devices[0].sf_calls == []
