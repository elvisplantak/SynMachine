"""Explicit local SiLA client policy and durable request attribution; fake scope only."""

from contextvars import ContextVar
from contextlib import contextmanager
import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from hmac import compare_digest
import os
from pathlib import Path
import re
import sqlite3
from threading import RLock
from uuid import uuid4

import grpc
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Role(StrEnum):
    READ_ONLY = "READ_ONLY"
    CONTROL = "CONTROL"


class Credential(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    client_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")
    role: Role
    token_sha256: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    enabled: bool = Field(default=True, strict=True)
    expires_at: datetime

    @field_validator("expires_at")
    @classmethod
    def aware_expiry(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("credential expiry must be timezone-aware")
        return value

    @classmethod
    def from_token(cls, *, client_id, role, token, expires_at):
        if type(token) is not str or re.fullmatch(r"[A-Za-z0-9_-]{32,128}", token) is None:
            raise ValueError("explicit 32..128 character URL-safe client token required")
        return cls(client_id=client_id, role=role, token_sha256=sha256(token.encode()).hexdigest(),
                   expires_at=expires_at)


class Policy:
    def __init__(self, credentials):
        values = tuple(Credential.model_validate(item) for item in credentials)
        if not 1 <= len(values) <= 64:
            raise ValueError("explicit policy requires 1..64 client credentials")
        if len({v.client_id for v in values}) != len(values) or len({v.token_sha256 for v in values}) != len(values):
            raise ValueError("client identities and token hashes must be unique")
        self._credentials = values
        self._revoked = set()
        self._lock = RLock()

    def revoke(self, client_id):
        with self._lock:
            self._revoked.add(client_id)

    def authenticate(self, metadata):
        headers = [value for key, value in metadata if key == "authorization"]
        if len(headers) != 1 or type(headers[0]) is not str:
            return None
        match = re.fullmatch(r"Bearer ([A-Za-z0-9_-]{32,128})", headers[0])
        if match is None:
            return None
        digest = sha256(match[1].encode()).hexdigest()
        now = datetime.now(UTC)
        found = None
        with self._lock:
            for value in self._credentials:
                matches = compare_digest(value.token_sha256, digest)
                if (matches and value.enabled and now < value.expires_at
                    and value.client_id not in self._revoked):
                    found = value
        return found


class AuditUnavailable(Exception):
    def __init__(self):
        super().__init__("SiLA request audit unavailable; inspect backend state before retrying")


SCHEMA = """CREATE TABLE sila_access_events (
    sequence INTEGER PRIMARY KEY, request_id TEXT NOT NULL, server_uuid TEXT NOT NULL,
    occurred_at TEXT NOT NULL, client_id TEXT, role TEXT, rpc_method TEXT NOT NULL,
    event TEXT NOT NULL, run_id TEXT, operation_id TEXT, recipe_id TEXT,
    expected_revision INTEGER, expected_content_digest TEXT, backend_status INTEGER
)"""


class AuditJournal:
    """Separate append-only API. No token, request body or error detail is recorded.

    This is request attribution linked to existing run/operation IDs, not a second
    execution journal or a tamper-proof compliance ledger. Unknown files are never
    migrated or repaired. The application owns existing lifecycle/command stores.
    """

    def __init__(self, path):
        self.path = Path(path).absolute()
        self._lock = RLock()
        if self.path.is_symlink():
            raise ValueError("audit path must not be a symlink")
        if not self.path.exists():
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            with self._connection() as connection:
                connection.execute(SCHEMA)
                connection.execute("PRAGMA user_version=1")
        with self._connection() as connection:
            objects = connection.execute(
                "SELECT name,type,sql FROM sqlite_master WHERE name NOT GLOB 'sqlite_*'"
            ).fetchall()
            if (objects != [("sila_access_events", "table", SCHEMA)]
                or connection.execute("PRAGMA user_version").fetchone()[0] != 1):
                raise ValueError("unsupported SiLA audit schema; existing file preserved")

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=0.2)
        try:
            connection.execute("PRAGMA synchronous=FULL")
            with connection:
                yield connection
        finally:
            connection.close()

    def append(self, request, event, *, backend_status=None):
        try:
            with self._lock:
                with self._connection() as connection:
                    connection.execute("INSERT INTO sila_access_events VALUES (NULL,?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                        request.request_id, request.server_uuid, datetime.now(UTC).isoformat(),
                        None if request.credential is None else request.credential.client_id,
                        None if request.credential is None else request.credential.role.value,
                        request.rpc_method, event, request.run_id, request.operation_id, request.recipe_id,
                        request.expected_revision, request.expected_content_digest, backend_status,
                    ))
        except (OSError, sqlite3.Error):
            raise AuditUnavailable() from None


@dataclass
class RequestIdentity:
    access: "AccessControl" = field(repr=False)
    server_uuid: str
    rpc_method: str
    credential: Credential | None = field(repr=False)
    request_id: str = field(default_factory=lambda: str(uuid4()))
    run_id: str | None = None
    operation_id: str | None = None
    recipe_id: str | None = None
    expected_revision: int | None = None
    expected_content_digest: str | None = None
    settled: bool = False


CURRENT_REQUEST = ContextVar("sila_client_request", default=None)
PREFIX = "sila2.com.github.elvisplantak.synmachine.recipes."
METHODS = {
    f"/{PREFIX}synmachinestatus.v1.SynMachineStatus/Get_Status": Role.READ_ONLY,
    f"/{PREFIX}synmachinerecipes.v1.SynMachineRecipes/Get_Recipes": Role.READ_ONLY,
    f"/{PREFIX}synmachinerecipes.v1.SynMachineRecipes/ReadRecipe": Role.READ_ONLY,
    f"/{PREFIX}synmachinerecipes.v1.SynMachineRecipes/ValidateRecipe": Role.READ_ONLY,
    f"/{PREFIX}synmachineexecution.v1.SynMachineExecution/GetProgress": Role.READ_ONLY,
    f"/{PREFIX}synmachineexecution.v1.SynMachineExecution/StartRecipe": Role.CONTROL,
    f"/{PREFIX}synmachineexecution.v1.SynMachineExecution/Stop": Role.CONTROL,
}
CORE_SERVICE = "sila2.org.silastandard.core.silaservice.v1.SiLAService"
UNUSED_BINARY_SERVICES = {"sila2.org.silastandard.BinaryUpload", "sila2.org.silastandard.BinaryDownload"}


class AccessControl:
    def __init__(self, policy: Policy, audit: AuditJournal):
        if type(policy) is not Policy or type(audit) is not AuditJournal:
            raise TypeError("explicit client policy and audit journal required")
        self.policy, self.audit = policy, audit

    def _current(self):
        request = CURRENT_REQUEST.get()
        if request is None or request.access is not self:
            raise AuditUnavailable()
        return request

    def dispatch(self, parameters):
        request = self._current()
        for key in ("run_id", "operation_id", "recipe_id"):
            value = parameters.get(key)
            if type(value) is str and value not in (".", "..") and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value):
                setattr(request, key, value)
        revision = parameters.get("expected_revision")
        if type(revision) is int and 1 <= revision <= 2**63 - 1:
            request.expected_revision = revision
        digest = parameters.get("expected_content_digest")
        if type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest):
            request.expected_content_digest = digest
        self.audit.append(request, "DISPATCH")

    def result(self, value):
        request = self._current()
        if type(value) is dict:
            for key in ("run_id", "operation_id"):
                item = value.get(key)
                if type(item) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", item):
                    setattr(request, key, item)
        self.audit.append(request, "RESULT")
        request.settled = True

    def rejected(self, status):
        request = self._current()
        self.audit.append(request, "BACKEND_REJECTED", backend_status=status)
        request.settled = True

    def protect(self, server, server_uuid):
        # Wrap SDK-native unary handlers before start. Preserve its protobuf,
        # metadata, decoding, cancellation and command-background-task behavior.
        for service, handlers in tuple(server.protobuf.services.items()):
            if service in UNUSED_BINARY_SERVICES:
                # No Feature exposes Binary in this slice. Do not leave an
                # unauthenticated SDK upload/download surface alongside it.
                del server.protobuf.services[service]
                continue
            if service == CORE_SERVICE:
                continue  # Core discovery/display metadata never controls backend execution.
            for method, handler in tuple(handlers.items()):
                rpc_method = f"/{service}/{method}"
                if handler.unary_unary is None or rpc_method not in METHODS:
                    raise ValueError("SiLA application RPC is missing an explicit access policy")
                handlers[method] = grpc.unary_unary_rpc_method_handler(
                    self._wrap(handler.unary_unary, rpc_method, server_uuid),
                    request_deserializer=handler.request_deserializer,
                    response_serializer=handler.response_serializer,
                )

    def _wrap(self, function, method, server_uuid):
        async def call(payload, context):
            credential = self.policy.authenticate(context.invocation_metadata())
            request = RequestIdentity(self, server_uuid, method, credential)
            try:
                if credential is None:
                    self.audit.append(request, "UNAUTHENTICATED")
                    await context.abort(grpc.StatusCode.UNAUTHENTICATED, "Client authorization required")
                if METHODS[method] is Role.CONTROL and credential.role is not Role.CONTROL:
                    self.audit.append(request, "FORBIDDEN")
                    await context.abort(grpc.StatusCode.PERMISSION_DENIED, "Client permission denied")
                self.audit.append(request, "AUTHORIZED")
            except AuditUnavailable:
                await context.abort(grpc.StatusCode.UNAVAILABLE, "SiLA request audit unavailable")
            token = CURRENT_REQUEST.set(request)
            try:
                return await function(payload, context)
            except BaseException as error:
                if not request.settled:
                    event = "CLIENT_DISCONNECTED" if isinstance(error, asyncio.CancelledError) else "RPC_FAILED"
                    try:
                        self.audit.append(request, event)
                    except AuditUnavailable:
                        pass  # A prior durable DISPATCH remains an unknown outcome, never a retry.
                raise
            finally:
                CURRENT_REQUEST.reset(token)
        return call
