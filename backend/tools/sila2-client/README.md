# Independent SiLA 2 client example

This console application uses **SiLA2.Client.Dynamic 10.3.3**, the official
[C# implementation](https://gitlab.com/SiLA2/sila_csharp), against SynMachine's
Python `unitelabs-sila` server. It runs as a separate process and reads Feature
Definitions over TLS, using the C# SDK's FDL parser, dynamic message generation,
protobuf/gRPC calls and standard SiLA error decoder. It does not use a Python
client, backend HTTP, Serial or backend databases.

Selection checked on November 7, 2026: [SiLA2.Client release history](https://www.nuget.org/packages/SiLA2.Client)
shows 10.3.3 released October 6, 2026. The downloaded Dynamic package metadata
identifies MIT licensing and source commit
`262066bd97c9e93e0746582dd2f403efdfaa2857`. Its maintained implementation is
independent of UniteLabs. Version 10.3.3 is pinned, with all 25 resolved packages
and integrity hashes in `packages.lock.json`. Restore uses the explicit nuget.org
source in `NuGet.Config`; no package source or binary is vendored. Inspected
dependency license metadata is MIT, BSD-3-Clause or Apache-2.0, including the
CommandLineParser package's MIT `License.md`. Preserve those licenses when
distributing a built environment. .NET is needed for this example, not for the
normal Python backend.

## Build

Requires .NET SDK 10.0.403 (selected by `backend/global.json`) and the backend's
`.[dev,sila2]` Python extra. From
`backend/` (substitute your development Python environment where appropriate):

```bash
dotnet restore tools/sila2-client/SynMachine.SilaClient.csproj \
  --configfile tools/sila2-client/NuGet.Config --locked-mode
dotnet build tools/sila2-client/SynMachine.SilaClient.csproj -c Release --no-restore
```

The implementation session used .NET SDK 10.0.403 installed only in
`/tmp/synmachine-dotnet` and NuGet/CLI caches under `/tmp`. No global .NET install
or shell configuration was changed. In that environment replace `dotnet` with
`/tmp/synmachine-dotnet/dotnet`; the installation is temporary.

## One-command fake demonstration

After building, run from `backend/`:

```bash
env -u LABFORGE_ARDUINO_PORT -u LABFORGE_SF_BOTTOM_VALVE_PORT \
  .venv/bin/python -m tests.sila2_external_demo \
  --dotnet /absolute/path/to/dotnet --state-dir /tmp/synmachine-independent-demo
```

The demo creates a **new empty fake state directory**, starts the existing
hardwired fake Serial/DYNAMIXEL composition, prepares two clearly labeled fixture
recipes through the existing save API and runs the separate C# client for every
SiLA request. It prints the outcomes of discovery/status/library access, a short
completed recipe, progress and an exact-operation Stop. The test-only readiness
statement is explicit fixture data, not physical evidence. The client never
synthesizes readiness; it accepts an explicit file.
The current demo also proves that READ_ONLY can read but cannot Start/Stop, while
CONTROL can execute and stop. Request attribution remains in `sila-access.sqlite3`
beside the fake bundle; client tokens are temporary and never copied to this audit.

The second run ends ABORTED and retains the fake maintenance owner. All processes
and listeners close; databases remain for inspection. The demo refuses any
nonempty existing state directory, including a previously completed demo, and
does not repair/reset it. An independent scenario needs its own new directory;
do not replace a retained bundle to conceal its outcome. The existing live wet
state is never accessed. Importing the demo is inert, and live-port settings are
rejected before importing `app.main` or creating state.

## Use the client manually

Start the existing `python -m tests.sila2_check` launcher as described in
[SILA2.md](../../docs/SILA2.md#run-with-fake-devices). Use its printed TLS port,
public certificate and UUID. For example, replace the sample certificate and UUID:

```bash
dotnet tools/sila2-client/bin/Release/net10.0/SynMachine.SilaClient.dll status \
  --port 50052 --certificate /tmp/printed-path/certificate.pem \
  --token-file /tmp/printed-path/reader.token \
  --server-uuid 00000000-0000-0000-0000-000000000000
```

Every action uses the same connection options and a client token file. The
launcher prints separate READ_ONLY (`reader.token`) and CONTROL (`controller.token`)
file paths. Use CONTROL for Start/Stop; READ_ONLY can list/read/validate recipes,
read status and track progress. Missing credentials or insufficient rights are
rejected by the server before application dispatch. `help` lists the actions:

| Action | Additional options | Result |
| --- | --- | --- |
| `discover` | none | Server UUID and implemented Feature identifiers |
| `status` | none | Backend status/machine/activity JSON |
| `recipes` | none | Saved recipe array |
| `read` | `--recipe-id ID` | Saved recipe; save stdout as your reviewed snapshot |
| `validate` | `--definition FILE` | Backend recipe preview |
| `start` | `--recipe FILE --readiness FILE --run-id ID` | Backend acceptance, not completion |
| `progress` | `--run-id ID` | Persisted run |
| `watch` | `--run-id ID`, optional `--watch-seconds N` | JSON lines until terminal status or timeout |
| `stop` | `--operation-id ID` | Orderly Stop for the exact ID from Status |

Create/save recipes in the existing UI. For Start, pass the **saved recipe object**
from `read`, including its reviewed revision and content digest, plus a separate
explicit `RecipeReadiness` JSON object as documented in the backend schema. The
client supplies no readiness defaults, new run ID or substitute operation ID.
It reads the token from `--token-file` and sends a Bearer authorization header
over its pinned TLS connection. It never prints the token. Launcher tokens expire
in one hour, have mode 0600 and are removed on shutdown; restart requires its new
token files. Program identity is separate from the human readiness statement.

Connections are fixed to `127.0.0.1` with TLS. The presented certificate must
match the explicitly supplied certificate's SHA-256, be time-valid and match the
endpoint name; the returned UUID must also match. The initial status must report
FAKE before any requested recipe/control call. No multicast discovery or proxy is
used. This is local development certificate pinning with client token/role checks,
not production identity or certificate provisioning. A server restart requires its
new public certificate. See [the access-control contract](../../docs/SILA2.md#client-access-control-and-request-attribution--2026-11-07)
for policy, request audit and HTTP/UI scope limits.

Exit codes: 0 means the requested read/acceptance/watch completed; inspect the
returned run status to distinguish COMPLETED, ABORTED and FAULTED. Code 2 means
validation/connection/request failure before a Start attempt. Code 3 means Start
was attempted and failed to return success; stderr includes the same run ID and
decodes a defined backend error when available. There is no automatic Start retry.
An unknown response outcome requires `progress` and `status` using the **same**
run ID, even after starting a fresh client process. A failed watch or closed client
does not stop a backend run. Stop remains explicit and never clears maintenance.

## Cross-implementation regression checks

GitHub now runs these scenarios as part of the complete backend suite for
relevant pushes/fork pull requests, with no skipped tests permitted. See
[CI.md](../../docs/CI.md) for triggers, tool versions, reports and scope.

From `backend/`, after the locked restore/build:

```bash
SYNMACHINE_SILA_DOTNET=/absolute/path/to/dotnet \
SYNMACHINE_SILA_CLIENT_DLL="$PWD/tools/sila2-client/bin/Release/net10.0/SynMachine.SilaClient.dll" \
  .venv/bin/python -m pytest -q tests/test_sila2.py tests/test_sila2_access.py tests/test_sila2_external_client.py
```

These tests do not download/build the client. They skip the five .NET scenarios
with an explicit message when either setting is absent; explicitly configured
missing files fail. Two Python launcher-environment checks need no .NET runtime.
The scenarios cover discovery/FDL, status/recipes/preview, full execution and
duplicate IDs, stale revisions/readiness, Stop identity and retained ownership,
wrong certificate/UUID/non-fake status, and a literal client process/socket loss
after backend acceptance but before delivery of the Start response. A new C#
process reads the same run, with one Start invocation and unchanged completed
command counts. The server remains running during that reconnect test; it does
not claim recovery from a backend crash or exactly-once transport.

November 7 interoperability verification at `039b70c`: 2063 complete backend tests, zero skipped with the .NET
settings supplied; 26 focused SiLA cases. Release build (SDK 10.0.403) had zero
warnings/errors. Locked restore, .NET format verification, full Ruff 0.15.22,
Python compilation, pip dependency and whitespace checks passed. The standalone
demo passed, and a second invocation refused reused state without changing any
existing fake-file hash.

The subsequent access-control checkpoint passes 2080 complete backend tests and
43 focused SiLA cases with .NET enabled, including the independent client's reader
denials and attributed control requests. The updated demo and launcher smoke test
passed token permissions, rotation/cleanup and audit preservation. C# Release
build and .NET format verification passed with unchanged locked dependencies.

This is evidence for the tested SDK/version and Draft JSON Feature contract, not
full SiLA conformance certification or support for arbitrary clients. The server
implementation accepted at `222e9e5` was unchanged in the `039b70c` interoperability
slice. Its independent review does not cover later client/example or access-control
changes. Production/live
operation, firmware, wet-state repair, XDL and main merge remain outside scope.
