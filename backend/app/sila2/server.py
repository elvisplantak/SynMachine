"""Draft vendor Features over the existing backend API, loopback/TLS/fake only."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sila.server import (
    DefinedExecutionError,
    Element,
    Feature,
    Integer,
    Server,
    ServerConfig,
    String,
    UnobservableCommand,
    UnobservableProperty,
)

from app.sila2.backend import BackendRejected, FakeBackend
from app.sila2.access import AccessControl, AuditUnavailable

ORIGINATOR = "com.github.elvisplantak.synmachine"


class SynMachineServer(Server):
    @property
    def address(self) -> str:
        # The pinned SDK exposes the dynamically bound endpoint only here.
        return self._address


def _feature(identifier, display_name, description):
    return Feature(originator=ORIGINATOR, category="recipes", identifier=identifier,
                   display_name=display_name, description=description, version="1.0")


def _handler(function, access):
    # Each Feature owns its error type; SDK registration associates the type with its FQI.
    rejected = DefinedExecutionError.create(
        "BackendRejected", "Backend Rejected",
        "JSON containing the backend HTTP status and detail. No retry or repair is performed.",
    )

    async def invoke(*, metadata, **parameters):
        del metadata
        try:
            access.dispatch(parameters)
            value = await function(**parameters)
            access.result(value)
        except BackendRejected as error:
            try:
                access.rejected(error.status)
            except AuditUnavailable:
                raise rejected('{"status":503,"detail":"SiLA request audit unavailable; inspect backend state"}') from None
            raise rejected(str(error)) from None
        except AuditUnavailable:
            raise rejected('{"status":503,"detail":"SiLA request audit unavailable; inspect backend state"}') from None
        return {"Result": json.dumps(value, ensure_ascii=False, allow_nan=False)}

    return invoke, {rejected.identifier: rejected}


def _command(feature, identifier, display_name, description, function, access, parameters=()):
    invoke, errors = _handler(function, access)
    UnobservableCommand(
        identifier=identifier, display_name=display_name, description=description,
        parameters={name: Element(identifier=label, display_name=title, data_type=kind,
                                  description=help_text)
                    for name, label, title, kind, help_text in parameters},
        responses={"Result": Element(identifier="Result", display_name="Result", data_type=String,
                                     description="Existing backend response encoded as JSON.")},
        function=invoke, errors=errors, feature=feature,
    )


def _property(feature, identifier, display_name, description, function, access):
    invoke, errors = _handler(function, access)

    async def read(*, metadata):
        return {identifier: (await invoke(metadata=metadata))["Result"]}

    UnobservableProperty(identifier=identifier, display_name=display_name, description=description,
                         data_type=String, function=read, errors=errors, feature=feature)


def register_features(server: Server, backend: FakeBackend, access: AccessControl):
    status = _feature("SynMachineStatus", "SynMachine Status",
                      "Backend availability, lifecycle and execution snapshots. Fake devices only.")
    _property(status, "Status", "Status",
              "JSON with health, execution and nullable machine snapshots; no device query.",
              backend.status, access)
    server.register_feature(status)

    recipes = _feature("SynMachineRecipes", "SynMachine Recipes",
                       "Read and validate existing logical recipe schema v1. No recipe writes or XDL.")
    _property(recipes, "Recipes", "Recipes", "JSON array of saved recipes, revisions and digests.",
              backend.recipes, access)
    _command(recipes, "ReadRecipe", "Read Recipe", "Read the latest saved recipe revision.",
             backend.read_recipe, access, (
                 ("recipe_id", "RecipeId", "Recipe Id", String, "Existing saved recipe ID."),))
    _command(recipes, "ValidateRecipe", "Validate Recipe",
             "Preview using backend schema, flow and configured calibration validation; no save.",
             backend.validate_recipe, access, (
                 ("definition_json", "DefinitionJson", "Definition Json", String,
                  "JSON object matching RecipeDefinition schema v1; Decimal values use strings."),))
    server.register_feature(recipes)

    execution = _feature("SynMachineExecution", "SynMachine Execution",
                         "Explicit fake recipe acceptance, authoritative progress and orderly Stop.")
    _command(execution, "StartRecipe", "Start Recipe",
             "Returns backend acceptance, not completion. Reuse run ID for diagnosis; never auto-retry.",
             backend.start_recipe, access, (
                 ("recipe_id", "RecipeId", "Recipe Id", String, "Reviewed saved recipe ID."),
                 ("run_id", "RunId", "Run Id", String, "Caller-owned unique run ID; 1..128 ASCII _.:-."),
                 ("expected_revision", "ExpectedRevision", "Expected Revision", Integer,
                  "Reviewed saved recipe revision."),
                 ("expected_content_digest", "ExpectedContentDigest", "Expected Content Digest", String,
                  "Reviewed saved recipe SHA-256 digest."),
                 ("readiness_json", "ReadinessJson", "Readiness Json", String,
                  "Fresh explicit RecipeReadiness JSON; no confirmations are supplied by the adapter."),
             ))
    _command(execution, "GetProgress", "Get Progress",
             "Read persisted run including status, phase, immutable recipe and completed step index.",
             backend.progress, access, (
                 ("run_id", "RunId", "Run Id", String, "Exact backend run ID."),))
    _command(execution, "Stop", "Stop",
             "Request orderly Stop for the exact operation ID from Status. Inspect progress afterward; "
             "acceptance is not proof of physical stopping or permission to clear maintenance.",
             backend.stop, access, (
                 ("operation_id", "OperationId", "Operation Id", String,
                  "Exact backend execution operation ID; no current-operation substitution."),))
    server.register_feature(execution)


@asynccontextmanager
async def fake_server(application: FastAPI, *, server_uuid: str, certificate: bytes,
                      private_key: bytes, access: AccessControl,
                      port: int = 0) -> AsyncIterator[SynMachineServer]:
    """Attach to an already-started fake app; caller retains application lifecycle.

    TLS and loopback are fixed. No listener, state directory or device is selected
    by ambient environment. SDK's built-in SiLAService supplies discovery/FDL.
    """
    if not certificate or not private_key:
        raise ValueError("explicit TLS certificate and private key are required")
    if type(access) is not AccessControl:
        raise ValueError("explicit SiLA client access policy and audit are required")
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("port must be in 0..65535")
    backend = FakeBackend(application)
    server = None
    try:
        await backend.execution()
        server = SynMachineServer(ServerConfig(
            hostname="127.0.0.1", port=port, tls=True,
            certificate_chain=certificate, private_key=private_key, uuid=server_uuid,
            name="SynMachine Fake", type="SynMachine", version="0.1.0",
            description="Development adapter using fake devices and isolated state only.",
            vendor_url="https://github.com/elvisplantak/SynMachine",
            options={"grpc.so_reuseport": False},
        ))
        register_features(server, backend, access)
        access.protect(server, server_uuid)
        await server.start()
        yield server
    finally:
        try:
            if server is not None:
                await server.stop(grace=5000)
        finally:
            await backend.close()
