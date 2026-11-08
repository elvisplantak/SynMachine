# SiLA 2 development adapter

## Scope and implementation choice — 2026-11-07

The first slice exposes status/discovery, saved recipe reads, recipe preview,
explicit execution, persisted progress and orderly Stop. It runs only with an
explicitly `FAKE` owned application. XDL is deferred. No firmware, physical
configuration, live database or operator credential is used or changed.

Branch `feature/sila2-backend-adapter` starts at the documentation handoff
`ae8c78f`, whose execution baseline is commissioning `1ea4e7a`. Public main
`49b5beb` has different execution code. Neither existing branch is merged or
rewritten by this work.

Selected SDK: **unitelabs-sila 0.13.0**, released October 21, 2026, MIT licensed,
supporting Python >=3.10, with client/server support and built-in SiLAService.
The downloaded wheel's license was inspected. It is pinned because this is a
beta API. Its bound-address field is wrapped in one local property.

Selection evidence:

- [Old sila2 project status](https://sila2.gitlab.io/sila_python/) explicitly says
  unmaintained and directs users to UniteLabs. Do not select `sila2`/`sila2lib`.
- [Selected release](https://pypi.org/project/unitelabs-sila/0.13.0/) documents
  license, release, Python support and client/server API.
- [Maintainer repository](https://gitlab.com/unitelabs/sila2/sila-python) and
  [CDK overview](https://docs.unitelabs.io/connector-development/getting-started/overview/)
  identify the library underneath the larger CDK. Only the library is needed;
  no cloud service, account or CDK device lifecycle is introduced.

The optional `sila2` extra also installs HTTPX (BSD-3-Clause) and cryptography
(Apache-2.0 OR BSD-3-Clause). Installed SDK dependency metadata reports Apache-2.0
for grpcio and MIT for jsonschema/xmlschema and their schema dependencies. HTTPX's
certifi dependency carries MPL-2.0; it is installed unmodified. No dependency
source or wheel is vendored. Preserve dependency licenses when distributing a
packaged environment. Normal backend installation does not require this extra.

## Composition and contract

`app/sila2/backend.py` calls the **same FastAPI routes** as the UI using HTTPX's
in-process ASGI transport. There is no outbound HTTP connection, second executor,
Serial owner, recipe store implementation or lifecycle startup. The enclosing
application owns lifespan exactly once. Existing validation, immutable recipe
snapshots, ownership, maintenance gates and durable command journals remain the
authority. Every adapter operation rechecks `transport_mode == FAKE`.

The SDK provides `org.silastandard/core/SiLAService/v1`, including server identity,
implemented Features and XML Feature Definitions. The three vendor Features are
**Draft**, version 1.0, under `com.github.elvisplantak.synmachine/recipes/`:

| Feature | Property / command | Existing backend operation |
| --- | --- | --- |
| `SynMachineStatus/v1` | `Status` property | `/health`, `/api/v1/execution`, `/api/v1/machine` |
| `SynMachineRecipes/v1` | `Recipes` property | GET `/api/v1/recipes` |
| | `ReadRecipe(RecipeId)` | GET `/api/v1/recipes/{id}` |
| | `ValidateRecipe(DefinitionJson)` | POST `/api/v1/recipes/preview` |
| `SynMachineExecution/v1` | `StartRecipe(RecipeId, RunId, ExpectedRevision, ExpectedContentDigest, ReadinessJson)` | POST `/api/v1/recipes/{id}/execute` |
| | `GetProgress(RunId)` | GET `/api/v1/runs/{id}` |
| | `Stop(OperationId)` | POST `/api/v1/execution/{id}/stop` |

Commands are unobservable, short API requests. `StartRecipe` returns acceptance
only; it does not represent a completed recipe. Poll `GetProgress` for persisted
run status, phase, recipe snapshot and completed `recipe_step_index`. Poll `Status`
for current activity, owner and exact `operation_id`. Its three snapshots are
separate reads and can straddle a transition; they are not an atomic machine
observation. Machine `null` means not initialized. Availability does not establish
physical readiness, and step progress does not measure liquid or elapsed time.

Command responses contain a SiLA String named `Result` holding the existing JSON
response. Properties are JSON Strings. `ExpectedRevision` is a SiLA Integer;
other parameters are Strings. `DefinitionJson` and `ReadinessJson` are JSON objects
validated by existing backend models, without adapter-provided confirmations.
Decimal recipe values retain backend string representation. IDs are single ASCII
path segments of 1..128 letters/digits/`_.:-`, excluding `.` and `..`.

This draft JSON contract deliberately follows the existing schema v1. It is not
a standardized chemical procedure model. Typed cross-vendor recipe exchange and
observable-command subscriptions remain future work.

`BackendRejected` is a defined SiLA execution error containing JSON `status` and
`detail`: missing resources 404, conflicts/maintenance/stale identity 409, validation
422 and unavailable backend/non-fake composition 503. Unexpected HTTP 5xx details
are redacted. Normal SiLA wire/type errors retain SDK errors. No adapter request
is automatically retried. A lost response can leave an accepted run: inspect the
caller-owned `RunId` and status before any deliberate retry. Never generate a new
run ID to conceal an unknown outcome. Duplicate run IDs retain backend conflict
semantics; this is not a new idempotency cache.

Stop targets the **exact** backend operation ID, rejecting a stale ID. It requests
an orderly stop and does not clear retained ownership or mandatory maintenance.
Continue reading progress/status after acceptance. There are no SiLA maintenance,
service actuator, operator-input, resume, repair or recipe-write commands.

## Run with fake devices

From `backend/`, install into a development virtualenv:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,sila2]'
env -u LABFORGE_ARDUINO_PORT -u LABFORGE_SF_BOTTOM_VALVE_PORT \
  .venv/bin/python -m tests.sila2_check \
  --state-dir /tmp/synmachine-sila2-fake --http-port 8000 --sila-port 50052
```

The launcher reuses `tests.browser_check`'s hardwired fake Serial/DYNAMIXEL
factories and bundle checks. It rejects live-port environment settings **before**
importing `app.main` or creating state. Unknown/nonempty state directories and
incomplete bundles are not reset. Reuse the same fake directory for restart
checks. Use a new directory for an independent scenario, never to bypass a
retained owner. Recipes created by the UI and SiLA run records share this bundle.

Both listeners bind only `127.0.0.1`. HTTP uses the existing development UI API;
SiLA requires TLS. The launcher prints the SiLA endpoint, stable fake-bundle UUID
and temporary **public certificate** path for client trust. Its ephemeral private
key stays in memory. A restart issues a new certificate with the same UUID;
clients must trust the new certificate. Ctrl+C closes SiLA then the owned app.
No mDNS advertisement or network-wide discovery is enabled; clients connect to
the printed address and use SiLAService feature discovery.

Example anonymous core-discovery client (substitute the printed certificate path).
Application status/recipes now require a client token; use the authenticated C#
example linked below for those requests:

```python
import asyncio
import json
from pathlib import Path
from sila.client import Client, ClientConfig

async def main():
    client = Client(ClientConfig(
        hostname="127.0.0.1", port=50052, tls=True,
        root_certificates=Path("/tmp/printed-path/certificate.pem").read_bytes(),
        default_timeout=5000, options={"grpc.enable_retries": False},
    ))
    await client.open()
    try:
        print(await client.get_implemented_features())
    finally:
        await client.close()

asyncio.run(main())
```

Run checks with `.venv/bin/python -m pytest -q` and `ruff check .` from `backend/`.
SiLA tests require the extra; otherwise that test module is explicitly skipped.
The integration check uses TLS/protobuf/gRPC, shared UI execution exclusion,
backend revision/digest/readiness validation, command journaling, retained Stop
ownership, fake adapter transports and restart without replay. The baseline lint
version is Ruff 0.15.22; newer 0.17.4 enables additional rules that report existing
repository style issues, outside this integration's scope.

November 7 verification: 2057 complete backend tests (20 SiLA cases), full Ruff
0.15.22, pip dependency check and Python compilation passed in an isolated `/tmp`
virtualenv. A separate subprocess smoke check exercised launcher HTTP health,
TLS SiLA discovery/status and orderly shutdown with public-certificate cleanup.

## Independent review acceptance — 2026-11-07

The owner supplied the completed independent review for repository
`elvisplantak/SynMachine`, branch `feature/sila2-backend-adapter`:

- Reviewed implementation: `222e9e5c163576a706bc32455ad60b8066c946c8`
  (`Add fake-only SiLA 2 adapter over existing backend execution`).
- Review base: `ae8c78f062a5fa4fe38049bee82c40597f1606db`.
- Verdict: **ACCEPTED for the declared fake-only SiLA 2 software integration**.
- Findings: Critical 0, High 0, Medium 0, Low 0.
- Requested software corrections: none.

The review covered the complete base-to-HEAD diff, adapter, tests, fake launcher,
this contract, existing recipe execution API, owned execution and fake browser
composition, together with repository/backend rules and governance/context.
It accepted the shared lifecycle/owner/journals, per-operation fake-mode boundary,
existing revision/content/readiness validation, conservative lost-response and
duplicate-ID semantics, exact-operation Stop, retained maintenance ownership,
status/progress semantics, error handling and TLS/listener lifecycle.

Evidence limits remain explicit: the 2057 backend tests (20 SiLA cases), Ruff
0.15.22, dependency/compilation/whitespace checks and launcher smoke results were
reported by the implementation session. The reviewer did not independently rerun
these commands through the GitHub connector and reported no published GitHub
combined status checks on the reviewed HEAD. No literal network failure was
injected between backend acceptance and delivery of the gRPC Start response.
The reviewer accepted the documented caller-owned RunId, durable backend state,
conflict semantics and diagnostic workflow without exactly-once claims; this
testing limit was not a finding.

Acceptance applies to the exact implementation commit above. This later
documentation-only record is not an independently reviewed runtime change. It
does not authorize production exposure/authentication, real-device execution,
state repair, physical testing, firmware work, XDL or merging into main. Recipe
writes, maintenance/Service/operator-input commands, observable subscriptions,
typed cross-vendor exchange, conformance certification and interoperability with
untested clients remain outside the accepted slice. Define the next SiLA phase
separately before introducing any production/live composition; the existing
blocked wet-test state remains deferred.

## Independent client interoperability — 2026-11-07

After acceptance of the server checkpoint, the owner approved a separate local
fake-only client interoperability phase. Branch `feature/sila2-client-interop`
starts at documentation commit `a6467e6`, retaining accepted server implementation
`222e9e5` unchanged.

The new [standalone C# client and instructions](../tools/sila2-client/README.md)
use the independently implemented `SiLA2.Client.Dynamic==10.3.3` SDK (MIT).
The client discovers FDL over TLS and exercises the existing Draft JSON Features
in a separate process. It pins the explicitly supplied public certificate,
requires the expected server UUID and FAKE status, and never retries Start.
It exposes no backend HTTP, Serial, maintenance, repair or recipe-write path.
All .NET dependencies and integrity hashes are locked separately from Python.

`python -m tests.sila2_external_demo` prepares explicit fixture recipes in a new
empty fake bundle, then drives discovery/status/library, completion/progress and
exact-operation Stop through that C# executable. It preserves the resulting fake
databases and retained maintenance owner. Existing live state remains untouched.

Twenty-six focused SiLA cases pass, including six new cases for the external
client/demo. Cross-implementation checks cover full execution, revision/readiness
rejection, duplicate IDs, exact Stop and retained ownership, standard error
decoding, certificate/UUID/non-fake rejection and a literal client process/socket
loss after backend acceptance but before delivery of its Start response. A new
C# process reads the same durable RunId without another Start or command replay.
This adds fault-injection evidence beyond the earlier review's reported limits;
it does not retroactively change what that reviewer tested or accepted.

November 7 verification: 2063 complete backend tests passed with the .NET cases
enabled and zero skipped; all 26 focused SiLA cases passed. C# Release build had
zero warnings/errors; locked NuGet restore, .NET format verification, full Ruff
0.15.22, pip dependency check, Python compilation and whitespace checks passed.
The standalone fake demo passed completion/Stop and refused reused state with
all existing fake-file hashes unchanged. SDK 10.0.403 and its CLI/NuGet caches
were installed only under `/tmp`; no global .NET configuration was changed.

The original independent acceptance remains scoped to `222e9e5`. This later
client/example work is not independently accepted by that review, does not claim
full SiLA certification, and demonstrates only the tested SDK/version and Feature
contract. Production/live composition, authentication/provisioning, firmware,
wet-state repair, XDL and main merge remain outside this phase.

## Client access control and request attribution — 2026-11-07

The owner approved local client authentication, separate read/control rights and
request attribution, still with fake devices only. Branch
`feature/sila2-access-control` starts at `039b70c`; earlier independent acceptance
of `222e9e5` does not cover these later admission changes.

`fake_server()` now requires an explicit `AccessControl(Policy(...), AuditJournal(...))`.
There is no anonymous application-mode fallback. Each configured `Credential`
binds a unique client ID to a role, SHA-256 of a secret token, enabled flag and
mandatory timezone-aware expiry. Token possession identifies the configured
program, not a human operator. Policy is in memory; its `revoke(client_id)` applies
to subsequent requests even on an existing TLS connection. It does not cancel
already admitted work or stop a run. No credential-management endpoint is exposed.

The transport uses `authorization: Bearer <token>` over TLS, following
[gRPC's credential/metadata mechanism](https://grpc.io/docs/guides/auth/).
This is a local application policy, not an implementation of the optional SiLA
AuthenticationService, AuthorizationService or AuditTrailService Features.
Those standard Features are described in the
[SiLA Features Index](https://sila-standard.com/wp-content/uploads/2022/03/SiLA-2-Part-C-Standard-Features-Index-v1.0.pdf).
No conformance certification or production identity/provisioning claim is made.

| Role | Allowed application operations |
| --- | --- |
| `READ_ONLY` | Status, Recipes, ReadRecipe, ValidateRecipe, GetProgress |
| `CONTROL` | All read operations, plus StartRecipe and exact-operation Stop |

The server checks the token and role **before request deserialization, SDK
parameter decoding or backend dispatch**, independently of client UI behavior.
Its application unary RPC handlers receive raw bytes (`request_deserializer=None`).
After admission and durable AUTHORIZED audit, the wrapper calls the original
request deserializer if configured, then the original SDK behavior with the same
context. The original response serializer remains registered. Decoder exceptions
and cancellation propagate through the existing audit cleanup to gRPC; no custom
protobuf parser, SiLA error translation or background executor is introduced.
Every application RPC must have an explicit mapping; a missing mapping refuses
startup. Unused SDK BinaryUpload/BinaryDownload services are removed from this
adapter: none of its Features has a Binary parameter/response. SiLAService core
discovery, identity, Feature Definitions and the SDK's ephemeral display-name
commands remain public; they do not invoke backend execution or change recipes.
All application status/recipe/control calls are protected.

Missing, malformed, duplicate, unknown, expired, disabled and revoked credentials
receive gRPC UNAUTHENTICATED. A reader's Start/Stop receives PERMISSION_DENIED.
Caller-supplied client names are ignored. Existing backend revision/digest,
readiness, ownership, lifecycle and Stop-ID checks still run after admission.
A CONTROL client may stop any exact current operation; per-run client ownership
is not introduced. The human readiness statement is preserved separately from
the authenticated program identity and is never synthesized from its token.

`sila-access.sqlite3` is a separate append-only request-event API, linked to the
existing execution records by run/operation IDs. It records generated request ID,
server UUID, UTC time, authenticated client ID/role, RPC method and selected
run/operation/recipe/revision/digest fields. It does not copy Authorization headers,
token files, recipe/readiness bodies or error detail. Existing command journals
remain the execution evidence; this file is not a second executor, domain journal,
or a tamper-proof/regulatory audit ledger.

Events distinguish AUTHORIZED, FORBIDDEN, UNAUTHENTICATED, DISPATCH, RESULT and
BACKEND_REJECTED. RPC_FAILED/CLIENT_DISCONNECTED can occur when no final result
is available; disconnected work may still later append RESULT. Authorization is
not backend acceptance, and Start's RESULT still means acceptance only.
The authenticated request context propagates into SDK background tasks.
DISPATCH commits with SQLite synchronous FULL **before** the backend call. An
audit failure before dispatch blocks the request, including Stop in this fake
slice. If logging fails after backend acceptance, the outcome can be unknown to
the client: inspect the same RunId, never auto-retry or clear ownership. Unknown
audit files/schema, extra objects and altered definitions are rejected without
migration/repair. Existing lifecycle/ownership/execution stores are unchanged.

The manual launcher prints file paths for separate generated `reader.token` and
`controller.token` credentials, not their values. Token files have mode 0600 in
a temporary private directory and expire after one hour; policy stores hashes.
Shutdown removes these temporary credentials. Restart issues fresh credentials
and reopens the same recognized request audit alongside the retained fake bundle.
It does not repair the bundle or clear maintenance. Supply the selected file to
the C# client with `--token-file`; the Python SDK test shim composes gRPC SSL and
access-token credentials on the pinned SDK's channel after public discovery.

This policy protects the **SiLA listener**. Existing localhost HTTP/UI routes keep
their current authorization behavior; SiLA roles do not isolate a local process
that can access those routes or read another client's credential files. Both
listeners and all device compositions remain local/fake. Production-wide access
control, credential provisioning/rotation, storage availability/retention and
emergency-stop policy require a separate phase before any live deployment.

Verification on November 7: 2080 complete backend tests passed, zero skipped with
the independent .NET client enabled; 43 focused SiLA cases. Added 16 policy/audit
cases plus a C# role/attribution case cover denial before application dispatch,
expiry/disable/revocation, reader monitoring without control, exact Stop and
retained ownership, request/run/operation linkage, secret omission, audit failure
before/after acceptance, strict schema preservation and unclassified-RPC refusal.
The prior response-loss/reconnect tests still pass under authenticated access.
Full Ruff 0.15.22, pip dependency/Python compilation, C# Release build (zero
warnings/errors), .NET format verification and whitespace checks passed. The
updated demo passed role denials and accepted control; a separate launcher smoke
check verified private token files, no secret values in logs, shutdown cleanup
and reopening the same fake bundle with new credentials and a retained audit.
Existing backend HTTP/domain/hardware/recipe code and dependency inputs are
unchanged; production/live activation and independent acceptance remain separate.

## Access-control review and admission correction — 2026-11-08

The owner supplied an independent review of exact HEAD
`30a7ee3397c29eea3a5d7506e1a974c1e2fabf46` on
`feature/sila2-access-control`, against base
`039b70c2bfa26dd62123d889a731c198d8bcc7bc`. Findings: Critical 0, High 0,
Medium 1, Low 0. **That checkpoint is not independently accepted.**
The requested correction is limited to admission before gRPC request
deserialization and associated regressions/documentation. The reviewer accepted
the remaining declared policy, attribution, audit-failure, exact Stop and retained
ownership behavior. Reported local checks were not independently rerun through
the GitHub connector; no combined GitHub status checks were published.

The finding identifies a real omission in the generic handler wrapper: forwarding
`handler.request_deserializer` to gRPC allows a configured decoder to run before
the wrapped behavior's authentication. Inspection of the pinned SDK also establishes
an important limit: its current application handlers register **no** gRPC request
deserializer. Commands decode inside the SDK behavior; status properties do not
decode their empty request. The prior implementation therefore protected the
current SDK's parameter decoding, but did not enforce admission ahead of an
optional gRPC deserializer. Empty `b""` regression payloads did not prove that
stronger boundary. The raw admission wrapper described above now enforces both.

New TLS regressions use genuinely invalid protobuf bytes (`80` and `0a 80`, hex).
At the optional gRPC seam, tests explicitly install the pinned SDK's wire parser
as a validation/deserialization probe that preserves bytes for the original
handler. Spies observe that probe, native SDK behavior and SDK parameter decoding:
anonymous Start/Status and reader Start/Stop return UNAUTHENTICATED/FORBIDDEN
audit respectively, with gRPC UNAUTHENTICATED/PERMISSION_DENIED, without calling
any of those boundaries or dispatching to the backend. All eight denial cases
fail on the original wrapper and pass after correction. Authorized malformed
requests reach the configured decoder once, retain gRPC's native UNKNOWN failure
and append RPC_FAILED without dispatch. A valid authenticated status round trip
preserves the original response. Separate tests without an injected decoder
retain the pinned SDK's ABORTED errors for malformed Start/Stop parameters.

Public core RPCs, removed binary services, exact method mapping, TLS, per-request
revocation, audit-before-dispatch, backend validation, exact-operation Stop and
retained ownership keep their existing contracts. The focused follow-up review
accepted the exact correction commit as recorded below; the original `30a7ee3`
checkpoint keeps its historical unaccepted verdict.

Verification on November 8: **2099 complete backend tests passed**, zero skipped
with the independent .NET client enabled; **62 focused SiLA cases** passed,
including 19 new decoding-boundary cases. Full Ruff 0.15.22, pip dependency check,
Python compilation and whitespace checks passed. The unchanged C# client restored
its locked dependencies and rebuilt with SDK 10.0.403 with zero warnings/errors.
The existing response-loss/no-replay, revocation, audit-failure, retained-owner
and independent-client regressions all passed. No SDK/dependency, backend domain,
HTTP/UI, hardware or firmware changes were made; the previous demo/launcher smoke
results above remain historical and were not rerun for this narrow correction.

## Independent admission-correction acceptance — 2026-11-08

The owner supplied the completed independent follow-up review for repository
`elvisplantak/SynMachine`, branch `feature/sila2-access-control`, exact HEAD
`a10a068806697e0125caab90e252b0187fb838db` against base
`30a7ee3397c29eea3a5d7506e1a974c1e2fabf46`.
**Accepted for the declared narrow fake/local SiLA admission correction.**
Findings: Blocker 0, High 0, Medium 0, Low 0, Documentation-only 0.
The previous Medium finding is resolved; no additional software correction was
requested for it.

The review covered `app/sila2/access.py`, `tests/test_sila2_access.py` and this
contract, including admission before the optional original gRPC deserializer,
malformed-wire regressions, native SDK errors/cancellation, audit semantics and
existing backend authority, exact Stop and retained ownership. It accepted the
raw-bytes admission boundary, preserved original handler/context/response
serializer, denied-request exclusion from decoding/dispatch, authorized decoder
failure as UNKNOWN and the pinned SDK's separate native ABORTED behavior.

Evidence recorded for the reviewed HEAD was 2099 complete backend tests,
62 focused SiLA cases, passing Ruff and a C# Release build with zero warnings or
errors. The reviewer did not independently rerun those local commands; the
reviewed GitHub commit had no published combined CI status checks/workflow runs.

Acceptance applies only to the exact commit and narrow follow-up scope above.
It does not independently accept this later documentation record or expand to
the entire earlier access-control/client integration. HTTP/UI authorization,
production deployment/exposure or credential provisioning, live device execution,
state repair/reconciliation, firmware changes/upload, XDL and merging into main
remain outside acceptance and authorization. No executable changes were made
to record this result; runtime tests/build were not rerun for this documentation-only
update. Documentation diff/whitespace/status checks were performed.

## Before any live integration

This development listener now authenticates local fake SiLA clients and separates
read/control roles. Production-wide authentication/authorization, certificate and
credential provisioning, deployment exposure and supported external clients must
be deliberately selected and independently reviewed before introducing a live
composition. This milestone
does not claim full SiLA conformance certification or interoperability with
untested clients. The existing blocked wet-test owner remains untouched.
