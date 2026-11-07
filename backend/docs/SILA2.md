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

Example read-only client (substitute the printed certificate path):

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
        print(json.loads(await client.SynMachineStatus.Status.read()))
        print(json.loads(await client.SynMachineRecipes.Recipes.read()))
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

## Before any live integration

This development listener offers local fake control without application-level
authentication. Production authentication/authorization, certificate provisioning,
deployment exposure and supported external clients must be deliberately selected
and independently reviewed before introducing a live composition. This milestone
does not claim full SiLA conformance certification or interoperability with
untested clients. The existing blocked wet-test owner remains untouched.
