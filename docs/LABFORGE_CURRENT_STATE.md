# SynMachine current development state

- Checkpoint date: 2026-11-08
- Repository: `elvisplantak/SynMachine` (public consolidated repository)
- Local checkout: `/home/elvis/Documents/SynMachine`
- Active development branch: `feature/sila2-ci`, based on access-control review
  record `6670e8b`; main and commissioning remain separate.
- Handoff branch: `docs/sila2-session-handoff` (documentation only)
- Execution-code baseline: `commissioning/full-stroke-wet-test` at
  `1ea4e7a3d98d193ab3c8132aa0ebddf75cd380a6`.
- Last fetched public `main`: `49b5beb22945e9d55166c9c361a19d81809b5a28`.
  The owner-approved October 28 UI screenshot, demo MP4 and README links are
  published there. The commissioning code is on its separate pushed branch;
  these branches must not be treated as identical or merged implicitly.

## Backend and SiLA GitHub verification

The owner approved automatic GitHub checks after relevant pushes. The new
`.github/workflows/backend.yml` runs full backend pytest with the independent C#
client, Ruff and dependency/build checks on a hosted Ubuntu runner. Missing SiLA
modules, failed or skipped tests fail the check. Backend Markdown-only and
unrelated component changes do not trigger it; same-repository PRs reuse push
checks and newer branch/PR runs cancel older ones. Python 3.12, CI tool constraints
and .NET 10.0.403/global.json preserve the verified tooling baseline. No runtime
or device behavior changed. Workflow, usage and report limits: `backend/docs/CI.md`.
This automation does not extend any prior independent acceptance, authorize live
operation or merge the integration into main.

Local verification of the exact workflow shell steps on November 8: 2099 backend
tests, including 62 SiLA cases, passed with zero failures/skips; Ruff 0.15.22,
pip dependency checks, locked .NET restore and Release build passed (zero
warnings/errors). Actionlint 1.7.12 passed. The JUnit gate accepted a complete
report and rejected skipped, missing-SiLA, failed and empty reports.

The first automatic GitHub push run **succeeded** for exact workflow commit
`1da6f3e4c9375fb667eb89e225074b7cb50fc915` on `feature/sila2-ci`:
[run 42479023480](https://github.com/elvisplantak/SynMachine/actions/runs/42479023480).
Hosted Python 3.12.16, Ruff 0.15.22 and .NET SDK 10.0.403: all 2099 tests passed
in 148.52 seconds; the report gate confirmed 62 SiLA cases, zero failures and
zero skips. Release build had zero warnings/errors. Setup, lint, locked restore,
test/report upload and cache cleanup all succeeded. Total run time was about
3 minutes (12:10:53–12:13:55 UTC). The JUnit report is retained for seven days;
the implementation and acceptance boundaries remain unchanged. This later
documentation-only record does not need another backend run.

## SiLA 2 client access control — fake devices only

The owner approved local client authentication, separate read/control rights and
attribution. `backend/app/sila2/access.py` now enforces explicit per-client tokens
over TLS before application RPC deserialization/decoding/dispatch, with READ_ONLY
and CONTROL roles, mandatory expiry, enabled flag and in-process revocation on
subsequent requests. `fake_server()` requires explicit policy/audit configuration and has no
anonymous application fallback. Token hashes are kept in policy; caller-supplied
identity names are ignored. Existing readiness/lifecycle/owner/command-journal
paths remain authoritative. Credential possession identifies the client program,
separately from the human readiness statement.

The fake launchers issue one-hour reader/controller tokens in private temporary
files, print paths only and retain `sila-access.sqlite3` alongside the fake bundle.
The C# client accepts `--token-file`. A selected-field request event precedes each
backend dispatch and links authenticated client/role/request ID to existing
run/operation/recipe identities. Tokens, bodies and error detail are not copied.
Audit failure blocks pre-dispatch requests; a failure after acceptance preserves
the existing run and unknown-outcome/no-retry semantics. Unknown audit schemas
are rejected without repair. This is attribution, not a second execution journal
or a tamper-proof compliance ledger.

Core SiLAService discovery/identity/FDL/display-name metadata remains public;
application status/recipes/control require authorization. Unused SDK binary
transfer RPCs are not exposed. This protects the SiLA listener, not the existing
HTTP/UI routes or local users with access to token files. Stop also requires
available audit storage in this fake scope. Production-wide identity/provisioning,
storage/Stop availability and external exposure remain a separate phase.

Verification on November 7: **2080 complete backend tests passed**, zero skipped
with .NET enabled; all 43 focused SiLA cases passed, including 16 new policy/audit
cases and an additional independent C# role/attribution case. Full Ruff 0.15.22,
pip dependency/compilation and whitespace checks passed. C# Release build and
format verification passed with SDK 10.0.403, zero compiler warnings/errors and
unchanged locked dependencies. The fake demo showed READ_ONLY Start/Stop rejected,
CONTROL completion/Stop accepted, retained maintenance and request attribution.
A launcher smoke test passed authenticated TLS, anonymous denial, mode-0600 token
files, no token values in logs, cleanup and same-bundle restart with rotated
credentials. No live state, hardware, firmware, XDL or main merge.
Contract and scope: `backend/docs/SILA2.md`; client usage:
`backend/tools/sila2-client/README.md`. Earlier acceptance of `222e9e5` does not
cover this phase's changes.

Independent review of exact access-control HEAD
`30a7ee3397c29eea3a5d7506e1a974c1e2fabf46` against `039b70c` returned
Critical 0, High 0, Medium 1, Low 0: **not independently accepted**. The wrapper
forwarded an optional request deserializer to gRPC, allowing it to run ahead of
authentication. The pinned SDK's current application handlers have no such
deserializer and decode parameters inside their behavior; nevertheless, the
stronger boundary needed explicit enforcement and nonempty malformed-wire tests.
The narrow correction now receives raw bytes, authenticates/authorizes and commits
AUTHORIZED before invoking any configured original decoder and SDK behavior.
Original response serialization, SDK errors/cancellation and all backend authority
remain in place. New regressions cover both configured and native SDK decoding;
the eight malformed-wire denial cases fail on the original wrapper.

The independent follow-up review **accepted exact correction commit
`a10a068806697e0125caab90e252b0187fb838db`**, against base `30a7ee3`,
for the narrow fake/local admission correction only. Findings: Blocker 0, High 0,
Medium 0, Low 0, Documentation-only 0. The previous Medium finding is resolved;
no additional correction was requested. This does not independently accept the
entire preceding integration, this later documentation record or production/live
operation. Full review scope and evidence limits:
`backend/docs/SILA2.md#independent-admission-correction-acceptance--2026-11-08`.
The reviewer did not rerun the local checks and found no published combined CI
status checks/workflow runs. No runtime tests/build were rerun for this
documentation-only acceptance record; diff/whitespace/status checks passed.

Correction verification on November 8: **2099 complete backend tests passed**,
zero skipped with the independent .NET client enabled; **62 focused SiLA cases**
passed, including 19 new decoding-boundary cases. Full Ruff 0.15.22, pip dependency
check, Python compilation and whitespace checks passed. The unchanged C# client
was restored in locked mode and rebuilt with SDK 10.0.403: zero warnings/errors,
unchanged dependency inputs. Only the SiLA wrapper, tests and documentation changed;
existing HTTP/UI/domain execution and physical/live state remain untouched.

## Independent SiLA 2 client interoperability — prior checkpoint

After the server review, the owner approved the proposed software-only phase:
connect an independent program on the same computer, test against fake devices,
and provide a runnable example. Added `backend/tools/sila2-client/`, a separate
C# CLI using official `SiLA2.Client.Dynamic` 10.3.3 (MIT), with a locked dependency
graph. No Python server/application/dependency code was changed.

The client uses TLS/loopback, explicit certificate pinning, expected server UUID
and FAKE status. It supports discovery/status, recipe list/read/validation,
reviewed recipe Start, progress/watch and exact-operation Stop; no automatic Start
retry or synthesized readiness. The client communicates only through SiLA.
`python -m tests.sila2_external_demo` prepares fixture recipes in a new empty fake
bundle and demonstrates completion and Stop using separate C# client processes.
It preserves the resulting databases/retained fake maintenance owner and rejects
live-port settings before application import. User/build instructions and SDK
selection/license evidence: `backend/tools/sila2-client/README.md`.

Verification on November 7: **2063 complete backend tests passed**, with .NET
scenarios enabled and zero skipped. All 26 focused SiLA tests passed, including six new external-client/demo
cases. A C# process is killed after backend acceptance but before the Start reply;
a fresh C# process reads the same run without replay. Wrong TLS certificate/UUID
and non-fake status reject before Start. The standalone demo passed with real
adapters over hardwired fake Serial/DYNAMIXEL transports. C# Release build and
format verification passed with .NET SDK 10.0.403, zero compiler warnings/errors.
Locked NuGet restore, full Ruff 0.15.22, pip dependency check, Python compilation
and whitespace checks passed. Reusing the demo directory was rejected with all
existing fake-file hashes unchanged.
Runtime/CLI/NuGet caches are isolated under `/tmp`; no global install was made.

This new client checkpoint does not inherit the earlier server's independent
acceptance. Next production/live composition, authentication, certificate
provisioning and external exposure require a separately defined phase. The wet
block remains deferred; XDL, firmware, device access, state repair and main merge
remain outside scope.

## SiLA 2 integration — accepted fake-device server slice

Implemented an optional `unitelabs-sila==0.13.0` (MIT) adapter in `backend/app/sila2/`.
It exposes the SDK's SiLAService discovery plus Draft vendor Features for backend
status, saved recipe list/read, existing recipe preview validation, explicit
StartRecipe, persisted progress and exact-operation Stop. Requests call the same
FastAPI routes in-process; there is no second lifecycle, executor or serial owner.
Existing revision/digest/readiness checks, command journals and retained maintenance
ownership remain authoritative. API acceptance is not recipe completion.

This first listener is TLS/127.0.0.1 only and rejects LIVE/UNSPECIFIED executors on
startup and every adapter operation. `python -m tests.sila2_check` shares the
existing hardwired fake browser composition with the UI and separate fake state;
it rejects live-port environment settings before importing the application.
No production activation, operator-credential access, live-state repair, device
connection, firmware change or main merge occurred. XDL remains unimplemented.
SDK selection evidence, complete Feature contract and launch/client instructions:
`backend/docs/SILA2.md`.

Verification on November 7: **2057 backend tests passed**, including 20 new SiLA
tests for TLS discovery/client calls,
shared UI exclusion, stale identity/readiness rejection without commands, exact
Stop and retained ownership, real adapters with fake transports, restart without
replay and launcher environment guards. Full backend Ruff 0.15.22, pip dependency
check, Python compilation and whitespace checks passed. A separate launcher smoke
check passed HTTP health, TLS SiLA discovery/status and orderly Ctrl+C shutdown.
Checks ran from `backend/` in an isolated `/tmp` virtualenv with temporary fake
state. Ruff 0.17.4 reports pre-existing repository style issues under its expanded
rules; no unrelated style rewrite was made. UI/firmware were unchanged and their
November 3 verification below remains historical.

Independent review accepted the exact implementation commit
`222e9e5c163576a706bc32455ad60b8066c946c8` on
`feature/sila2-backend-adapter`, against base
`ae8c78f062a5fa4fe38049bee82c40597f1606db`, for this fake-only SiLA 2 scope.
Findings: Critical 0, High 0, Medium 0, Low 0; no software correction requested.
The owner supplied the completed review; detailed acceptance and evidence limits
are recorded in [the SiLA review record](../backend/docs/SILA2.md#independent-review-acceptance--2026-11-07).
The reviewer inspected code but did not independently rerun the reported local
checks. This acceptance does not extend to this later documentation commit or
authorize production/live operation, firmware work, state repair, physical tests,
XDL or a main merge.

The later owner-approved independent-client phase is recorded above; its results
do not broaden this review's accepted scope. Production authentication/authorization,
certificate provisioning and exposure require a separate design before live
composition is introduced. The blocked wet-test state remains deferred.

## November 7 starting handoff: SiLA 2, then XDL

The owner chose SiLA 2 integration as the next task in a new session, with XDL
reserved for a later phase. Neither integration was implemented at `ae8c78f`.
That starting handoff changed documentation only, not execution behavior or
authorization; the new fake-only implementation is recorded above.

Proposed direction: add a SiLA 2 adapter to the existing Python backend, sharing
recipe validation, command journals, lifecycle and ownership with the UI.
Begin with status/feature discovery; then consider saved recipe access,
explicit recipe execution, progress and Stop using existing application paths.
Exact Features, authentication, SDK, supported clients and first implementation
scope still need design. Do not introduce a separate serial owner or bypass
maintenance, readiness or existing command identities. Inspect current maintained
SDKs and their licenses before selecting a dependency; the previously consulted
`sila2` reference documentation labels that implementation unmaintained.

Read root/component AGENTS, development governance and system context first.
Select the integration branch/base deliberately: public main and the commissioning
branch contain different execution code. Preserve both; a new task is not
approval to merge commissioning into main. Start software verification with
fake devices and separate temporary state. XDL and real-device execution are
outside this initial handoff; physical access still needs explicit approval.

## Known live state and preserved local work

- On November 3, read-only inspection found the existing live owner
  `wet-reactor-sf-1b559875-a2df-44b4-831c-21151320acda` still `BLOCKED` in
  `/home/elvis/.local/state/labforge/recipes-live-v1/owner.sqlite3`.
  Ownership, execution, lifecycle and recipe databases passed SQLite quick_check.
  This is local backend state, not a GitHub or Arduino-resident lock.
- The owner explicitly deferred unblocking and physical commissioning. The live
  profile has no configured automatic Recovery/Flush. Do not clear databases,
  replace the bundle, release ownership or replay the wet runner for SiLA work.
  Never read or expose the private `operator.key`.
- After the original startup timeout, the explicitly approved continuation
  stopped on P1 full-stroke aspiration with PUMP_MOTION_TIMEOUT before Reactor
  delivery. The owner subsequently reported P1 full of red liquid. That expanded
  journal is not the pristine/original-13-command state accepted by the narrow
  startup reconciliation mode. Do not reuse that mode as an unblock shortcut.
- The owner later self-uploaded standalone Arduino sketches and reported
  successful P1 dispense and a P2 Reactor-to-SF transfer. These observations do
  not repair backend journals or establish current references. The currently
  installed firmware and present fluid contents are unverified; older installed-
  firmware/power/reference statements below are historical, not current readiness.
- Six standalone sketch/test packages remain untracked under the legacy
  `/home/elvis/Documents/labforge-firmware/tools/`: `p1_b1_reactor`,
  `p1_dispense_once`, `p2_reactor_sf`, `p2_sf_mix`, `reactor_sf_once`,
  `reactor_sf_simple`. Preserve them; they are not published in SynMachine.
- The active monorepo also retains the unrelated untracked file
  `firmware/docs/commissioning/2026-10-21/observe-pump-home-powered.py.txt`.
- The November 3 check found neither localhost UI nor backend running. Recheck
  availability when needed; this historical observation does not authorize a
  real-device connection. Protected `firmware/recovery/` and legacy `recovery/`
  remain excluded from access without exact action-specific authorization.

## Last complete software check: 2026-11-03

On execution baseline 1ea4e7a: 2037 backend tests; 51 UI tests, zero skipped;
224 native firmware plus 6 mixer-profile cases; 155 standalone fake-GPIO cases
and one fake DYNAMIXEL host-tool test passed. Backend Ruff/pip dependency checks,
UI lint/TypeScript/Vite build and Mega 2560 build passed. No tracked source changes
were found; local commissioning HEAD matched its GitHub branch. No device access,
upload, physical motion, state repair or main merge occurred.

Mega: 42062 flash / 3184 static SRAM bytes. Rebuilt HEX SHA256 matched the prior
artifact: `d8478b434439bff45cd05a26e1e9e0628c8c4e4cd1cd7851528cb7a7648538c6`.
This establishes a reproducible software build, not the image currently on Arduino.
Those tests were not rerun for this documentation-only November 7 handoff.
Temporary check logs may have expired; retain this dated result as historical
verification and run relevant checks for future executable changes.

## Historical development record through 2026-10-21

The following records preserve their original checkpoint context. Current scope,
installed-firmware uncertainty and live-state limitations are described above.

## Repository consolidation

The user explicitly authorized one repository and corrected historical commit
authorship. All 318 source-history commits were imported and verified against
original file trees, dates, messages, parent graph and branch targets. Author
metadata now uses Elvis and the owner's GitHub noreply address. The original
repositories/remotes/worktrees remain untouched and private. Verified full bundles
are retained locally outside the new repo. See MIGRATION.md and docs/history/.

The root README and component instructions describe the agreed colored-liquid
mechatronic scope, existing silicone/medical-plastic parts and planned PTFE/glass
upgrades. Runtime code, SVG geometry, tests, dependency/build inputs and bound live
profile JSON are unchanged. The protected recovery artifacts were copied and
verified unchanged under the migration authorization; future access remains gated.

## Existing software and physical boundaries

Recipes, command-driven flow animation and explicit live Recipes preparation
retain their original independently reviewed scopes. The original review records
remain under ui/docs/reviews/; resolve their original IDs using docs/history maps.
Migration validation does not extend those reviews to new execution behavior.

The existing live profile remains nominal, with no configured automatic Recovery/
Flush. Stop/fault can retain mandatory maintenance and block a subsequent run.
Existing state/credentials are outside this checkout and are neither copied nor
reprovisioned. The migration does not connect to devices, start or stop an old
server, initialize references, issue motion, upload firmware or change EEPROM.
Old UI snapshots contain historical session IDs and are not live-state evidence.

Installed firmware is now the verified dc7a53f artifact recorded below. Physical
readiness and current references need fresh explicit operator confirmation before
any future real-device action. The liquid test has been requested; execution
awaits completion of the wet plan and fresh operator readiness.

## Verification and next steps

Migration checks passed: 1937 backend, 51 UI (24 browser), 211 native firmware,
6 mixer-profile and 1 host-tool unit test; lint/build passed. Mega uses 41056 flash
and 3148 static SRAM bytes, unchanged. Details: MIGRATION_VERIFICATION.md.

On 2026-10-20 the owner selected Apache-2.0, approved the English README and
provided a prototype photograph. LICENSE, NOTICE, README/photo and dependency
license/publication verification records are integrated into main. The owner
confirmed ownership of the old code. GitHub description/topics are configured;
GitHub Markdown rendering, image identity, local links, ignore rules and redacted
secret scans passed within the documented scope. No new recovery access was
performed: the owner requested a separate discussion; prior full-audit and
unchanged-import evidence remain applicable.

Follow-up on 2026-10-20: the owner decided to retain the recovery archive for
public access and approved a README acknowledgment of Professor Lee Cronin and
the Cronin Group at the University of Glasgow. The acknowledgment links to the
official group site and describes SynMachine as independent. The recovery
publication question is resolved without new recovery access or modification.

Only documentation/licensing/image/presentation changed; runtime behavior and
physical state are unchanged. On 2026-10-20 the owner explicitly authorized public
visibility; `elvisplantak/SynMachine` is now public. Anonymous repository/API and
README/LICENSE/photo access were verified, including exact raw-file contents.
The original component repositories remain private and unchanged. Publication is
complete; no further publication approval is pending. Future physical/liquid tests
still require fresh operator readiness and authorization. See PUBLICATION.md and
PUBLICATION_VERIFICATION.md.

## Supervised wet test preparation — 2026-10-21

The owner requested B1 colored water -> Reactor (one nominal full-stroke 20 mL)
-> SF -> 20 s mixing -> P2 -> Waste, excluding Column/carousel and deferring
flushing. B2 is ordinary water. The owner now confirms S filled, intake submerged
and Reactor empty, and approves two 5 mL Reactor-to-P2-to-Reactor priming cycles
after filling, alongside the two approved 5 mL S-to-P1-to-Waste cycles. SF empty, mixer
free, Waste clear and USB connected were reported; motor power is OFF.

On this feature branch, firmware adds explicit PUMP_ASPIRATE_FULL_STROKE only
from trusted empty20500, with stable HOME, bounded20500 pulse count and early-HOME
failure. Ordinary move-zero remains invalid; Recipes' ordinary planner remains
unchanged. SF interval is prepared at1667us (~600 pulses/s), explicitly approved
as a trial. Host capability limit is10 to accept the updated HELLO, without
implicit command fallback on older firmware. No live profile/state binding,
existing journal, installed firmware, device connection or physical motion is
changed by preparation. Verification:220 native +6 mixer-profile tests,1937
complete backend tests plus two additional host cases (131 focused), Ruff and
Mega build passed. Mega41570 flash/3176 SRAM (+514/+28); prepared HEX SHA256
61feb4425fddee73799191faf5a1bf98bb684db601a598712b30a7fe8a1c0d45.
Previous installed HEX matched its recorded hash and is preserved separately.
Upload completed with explicit owner approval and motor power OFF: exact
dc7a53fcdd93315965bf82ba143bf4def17688e7 HEX, signature 0x1e9801, all 41570 flash
bytes verified, exit 0. No actuator command, application Serial monitor, EEPROM
provisioning or wet test. New stroke/speed remain physically unverified.
The fixed supervised runner is prepared at backend/app/wet_reactor_sf.py with
71 fake regressions and unchanged existing live profile/bundle binding. It uses
a single retained owner and the existing Arduino/SF/wait journals; no Column
reference is invented. Exact plan, bootstrap, follow-ups and single-use boundary:
firmware/docs/commissioning/2026-10-21/WET_TEST_PLAN.md. Verification: all 2010
backend tests passed (71 new), full Ruff check and whitespace checks passed.
Firmware source/HEX is unchanged since the approved upload. Next: fresh powered readiness, Waste air-gap/free-mixer checks
and explicit execution approval for this concrete plan. No new application
connection or actuator command has occurred. Preparation/flash verification
are not physical test acceptance. Evidence:
firmware/docs/commissioning/2026-10-21/README.md.

## Wet startup failed; read-only diagnostic preparation

The explicitly approved first attempt in boot 111 stopped on ordinary P1
PUMP_HOME with PUMP_MOTION_TIMEOUT, execution_started=true: 12 Arduino commands
completed, 1 failed, SF CLOSE completed. No priming, liquid transfer, P2 motion
or mixer START occurred. Both ports closed; existing live owner remains
BLOCKED at generation 1. No retry, re-home, owner release or reprovisioning.

Operator correction: P1 may only be near HOME, replacing the earlier pressed
assertion. Motor power last confirmed ON; OFF was requested, not confirmed.
Do not continue the fixed runner or manufacture a trusted pump zero. Exact
evidence: firmware/docs/commissioning/2026-10-21/wet-01-result.json.

Read-only QUERY_STATUS fields p1_home_active/p2_home_active are prepared to
distinguish input level from a physical proximity guess. They do not change
motion limits/timing, HOME semantics or reference trust. Diagnostic firmware
is not installed; dc7a53f remains installed. Verification passed: 224 native,
6 mixer-profile, 2025 complete backend (112 focused), Ruff and Mega. Image:
42062 flash/3184 static SRAM; metadata in commissioning pump-home-diagnostics-artifact.json.
Mega warnings are 4 upstream Arduino unused parameters, zero project warnings.
Next: explicit upload approval with motor power OFF and
permission for read-only observation are required before any new real access.
A subsequent full cycle still needs deliberate reconciliation of the retained
owner, confirmed HOME/reference and fresh powered readiness; never clear its
history or select a new bundle to bypass this failed attempt.

## Diagnostic upload and observation completed

Fresh approval with motor power OFF covered 5d09cb8 upload and five read-only
queries. All42062 flash bytes verified, exit 0, HEX d8478b434439bff45cd05a26e1e9e0628c8c4e4cd1cd7851528cb7a7648538c6.
In boot 113 all five samples report p1_home_active=true and p2_home_active=false.
No actuator command, reference establishment, owner release or journal repair.
Existing bundle observation stayed unchanged; port closed. Motor power is OFF.
This is current input evidence, not a diagnosis of the preceding timeout.
The full wet cycle remains outstanding; prepare a narrowly validated startup
reconciliation against the exact retained failure, then obtain fresh powered
readiness. Do not treat the old pristine-only runner as a resume mechanism.

## Explicit startup reconciliation prepared

backend/app/wet_reactor_sf.py now has a separately armed startup reconciliation
mode, matching the exact original 13 Arduino/1 SF rows before connection and
retaining the same owner under bundle locks. A separately fsync'd approved plan
precedes begin_maintenance and a new phase; no old lease, journal or bundle is
reset. Fresh P1 HOME=true is required at preflight and immediately before HOME.
The unchanged wet plan then runs; its owner stays BLOCKED afterward until the
separate flushing test. Default pristine-only entry remains unchanged.
12 new fake cases and all 2037 complete backend tests passed; full Ruff passed. Current
installed firmware remains 5d09cb8. Fresh powered readiness/continuation approval
is still required; no new device connection or motion occurred during preparation.
