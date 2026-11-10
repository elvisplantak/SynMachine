# SynMachine current development state

- Checkpoint date: 2026-11-10
- Repository: `elvisplantak/SynMachine` (public consolidated repository)
- Primary checkout: `/home/elvis/Documents/SynMachine`
- Published main includes the initial XDL integration through PR #2 at
  `e0fd9590f711b924e42b94ba812c17f158138038`, from approved candidate
  `29a4674a48da91c361e8f11e1da2dd0591f7a1af` over main `d882030`.
- Preserved XDL feature: `feature/xdl2-recipe-interop`, worktree
  `/tmp/synmachine-xdl2`. Main documentation closure is isolated on
  `docs/xdl2-main-closure` in `/tmp/synmachine-xdl-main-docs`.
- The previous `/tmp/synmachine-sila2-main` checkout expired; the original primary
  checkout and its commissioning-derived source branch remain preserved.
- Initial SiLA integration merged to `main` through PR #1 at
  `bc775fae6e08c5768566536b16055099e67af683`, from approved candidate `18af175`
  over prior main `49b5beb`. The primary checkout remains on its preserved
  development branch; the integration and commissioning branches are retained.
- Preserved SiLA/CI source: `feature/sila2-ci` at
  `40d8a659c938fd3b14deb9b30f9fae24e427e9dc`.
- Separate commissioning branch: `commissioning/full-stroke-wet-test` at
  `1ea4e7a3d98d193ab3c8132aa0ebddf75cd380a6`.

## Initial XDL 2 recipe interchange — fake profiles only

The owner approved XDL integration and requested the newer generation. Direct
verification of the official public tag list found newest public release 2.1.0,
commit `6d60e8da7218a589b9c8715a239956601b17cd07`, marked as the last before
private development. That package still emits XML format version 2.0.0. The
implemented independent interchange profile follows that public interface;
the old 0.5 language and unknown later private versions are not claimed.

Recipes now has inspect/import/export HTTP routes plus UI file selection,
explicit reagent/bottle and vessel/role binding and a new-draft workflow. Liquid
Add, supported Transfer and passive Wait map to existing RecipeDefinition steps.
Unsupported steps/attributes are rejected; fixed-profile SF mixing, timed
collection, mass/temperature control, parameters, loops and blueprints are not
silently approximated. There is no new executor or XDL Start route. Save/review,
fresh readiness, immutable recipe versions, progress, exact Stop, ownership and
command journals remain on their existing paths.

All new interchange routes and UI controls require an explicitly FAKE executor.
XML limits, hardened defusedxml parsing, strict semantics and UTF-8 file checks
are documented in `backend/docs/XDL2.md`. The upstream Chemputer SDK is not a
runtime dependency; no upstream implementation/fixtures are vendored. The one
new dependency is PSF-licensed defusedxml 0.7.1. HTTP/UI authorization is unchanged.

The standalone `python -m tests.xdl_demo` completed import → explicit save/review/
Start → progress/COMPLETED → export/reimport with a new separate fake bundle,
closing its server and preserving evidence under
`/tmp/synmachine-xdl-demo-20261110-kvDQsl` (temporary). A new independent C# SiLA
scenario exercises an XDL-imported recipe through the same recipe library.
Prior SiLA acceptances remain separate from this parser/UI boundary. The initial
XDL main merge was explicitly approved; live device access, wet-state repair,
firmware and EEPROM actions remain outside that approval.

Local verification on November 10: **2094 complete backend tests passed**, zero
skipped, including **94 XDL cases** and **63 SiLA cases** (one new XDL-import →
independent C# SiLA execution scenario). All **55 UI tests passed**, zero skipped,
including four new browser cases. Backend Ruff 0.15.22, pip dependency/compilation,
UI lint/TypeScript/Vite build, locked C# restore/Release build (zero warnings/
errors), Actionlint 1.7.12 and whitespace checks passed. The exact CI report gate
accepted the full report and rejected a report with XDL coverage removed.
Existing execution/domain/protocol/SiLA implementations and the UI dependency
lock are unchanged; the new boundary is recipe interchange and its UI/tests.

Published implementation commit `6ac42df9c8aeddbb85f373a813541f3d7bc05e72` also
passed hosted GitHub CI:
[run 42812048926](https://github.com/elvisplantak/SynMachine/actions/runs/42812048926).
All 2094 backend tests passed in 179.93 seconds; the report gate confirmed 94 XDL
and 63 SiLA cases, zero failures/skips. Ruff, dependency checks, locked C# build
(zero warnings/errors), report upload and cleanup succeeded. The hosted run took
about four minutes. UI verification remains the separate local 55-test run.
Later documentation-only commits record this evidence without changing the
verified implementation. The separate main-merge evidence is recorded below.

Independent review **accepted exact HEAD
`ab7af954ce74ca2572122f9fda808c8465ea4bb1`** against base `d882030`, for the
declared bounded FAKE/local XDL 2 recipe-interchange scope, with zero findings
at every severity and no requested correction. The review verified the hosted
CI evidence and retained the local UI evidence distinction. The following project
instruction change and this acceptance record do not alter executable behavior
or extend acceptance to other commits/scopes. See `backend/docs/XDL2.md`.
Full XDL, main merge, live/production activation and physical/state/firmware work
remain outside this acceptance.

After explicit owner approval, [PR #2](https://github.com/elvisplantak/SynMachine/pull/2)
was merged on November 10 as `e0fd9590f711b924e42b94ba812c17f158138038`.
The merge parents are prior main `d882030` and exact approved candidate `29a4674`;
its root tree is identical to the candidate. The merge author and committer are
Elvis with the configured GitHub noreply address. Development/commissioning
branches and unrelated local work remain preserved. No commissioning execution
delta, live-device action or existing-state change is included.

Exact candidate `29a4674` also passed
[CI 42818100137](https://github.com/elvisplantak/SynMachine/actions/runs/42818100137):
2094 backend tests in 174.69 seconds, 94 XDL and 63 SiLA cases, zero failures/skips;
Ruff/dependency/report checks and C# Release build passed with zero warnings/errors.
Executable files match the accepted checkpoint; local UI evidence remains the
separate 55-test result. The merge does not broaden independent acceptance.

Automatic post-merge **main CI also passed** on exact merge `e0fd959`:
[run 42819905886](https://github.com/elvisplantak/SynMachine/actions/runs/42819905886).
All 2094 backend tests passed in 175.96 seconds; the report gate confirmed 94 XDL
and 63 SiLA cases, zero failures/skips. Ruff, dependency checks, C# Release build
(zero warnings/errors), report upload and cleanup passed. The hosted run took
about four minutes. This later closure changes documentation only; whitespace/
status checks passed. Initial FAKE/local XDL software and SiLA are published on
main, with their exact independent-review scopes retained. No further runtime
change, live device access or physical authorization is part of this closure.

## Initial SiLA 2 software integration on the main baseline

The owner explicitly approved merging PR #1 on November 8. The initial fake/local
SiLA integration is now on main at `bc775fa`.
Only the SiLA adapter, client, fake tests, optional dependency extra, CI and
related documentation were transferred from the preserved source branch.
Existing main backend domain/HTTP/recipe/hardware and protocol code, UI, README
screenshot/video and firmware are not part of this transfer. Commissioning's
full-stroke capability/status changes and wet-test/reconciliation runner remain
on their original branch. The source branches and historical review records
remain intact. See `backend/docs/SILA2_MAIN_INTEGRATION.md` for exact provenance
and verification. This approval covers the initial software merge only.

The adapter uses optional `unitelabs-sila==0.13.0` and exposes TLS/loopback-only
status, recipe read/preview, explicit Start, progress and exact-operation Stop
through the existing backend. Only FAKE execution is allowed. READ_ONLY/CONTROL
client credentials and selected-field request attribution protect SiLA requests
before decoding/dispatch; HTTP/UI authorization is unchanged. The independent
C# client uses `SiLA2.Client.Dynamic` 10.3.3 with locked dependencies.
Contract: `backend/docs/SILA2.md`; use/demo: `backend/tools/sila2-client/README.md`;
GitHub checks: `backend/docs/CI.md`.

Original independent acceptance applies only to exact server commit `222e9e5`
and exact narrow admission-correction commit `a10a068`, within their recorded
fake/local scopes. It is not relabeled as acceptance of this port, the whole
access-control phase or production/live operation. Tests on this main baseline
must be reported separately from the earlier commissioning-based 2099-test run.

Verification on this main base: **1999 backend tests passed**, including all
**62 SiLA cases**, zero skipped. All **51 UI tests** passed, zero skipped; UI
lint/TypeScript/Vite build, backend Ruff/pip/compilation, Actionlint, locked NuGet
restore and C# Release build passed (zero compiler warnings/errors). The same CI
report gate passed. The standalone main-based fake demo also passed completion,
progress, reader denials and exact Stop with retained fake ownership. Main's
README/media, UI and existing backend implementation match the pinned main base;
all 23 transferred backend/workflow paths match the preserved source blobs.
Hosted CI **also passed** on exact implementation commit
`e598d58f89df609368c949f39814e0d79bdcf930`:
[run 42481909369](https://github.com/elvisplantak/SynMachine/actions/runs/42481909369),
1999 tests in 163.70 seconds, 62 SiLA cases, zero failures/skips and a C# build
without warnings/errors. [PR #1](https://github.com/elvisplantak/SynMachine/pull/1)
was merged after the owner's explicit approval, preserving its development
branches. Later documentation-only records do not change this verified code.

Post-merge **main CI also succeeded** on exact merge commit
`bc775fae6e08c5768566536b16055099e67af683`:
[run 42483128655](https://github.com/elvisplantak/SynMachine/actions/runs/42483128655).
All 1999 tests passed in 165.50 seconds; the report gate confirmed 62 SiLA cases,
zero failures/skips. Ruff, dependency checks, C# Release build (zero warnings/
errors), report upload and cache cleanup passed. Total hosted run time was about
3.5 minutes. The initial fake/local SiLA software integration and CI are now
published on main. This closure only updates documentation; diff/whitespace/status
checks passed, with no further runtime change or physical authorization.

The unchanged UI lock reports four high-severity npm audit package alerts in
existing build/development dependencies. They are recorded with advisory links
in `backend/docs/SILA2_MAIN_INTEGRATION.md` as separate maintenance work.

## Live state and preserved work

The existing live owner remains BLOCKED after the October wet startup failure.
Its state reconciliation, physical readiness and flushing are deferred; this
software task never opens live databases, reads operator credentials, connects
Serial/DYNAMIXEL devices, moves actuators, uploads firmware or changes EEPROM.
The owner later reported standalone sketch uploads; the currently installed
firmware, fluid contents and present references are unverified. Earlier installed-
firmware statements below are dated history, not current readiness.

Detailed commissioning/failure and prior software evidence remains in the
[preserved development checkpoint](https://github.com/elvisplantak/SynMachine/blob/40d8a659c938fd3b14deb9b30f9fae24e427e9dc/docs/LABFORGE_CURRENT_STATE.md).
Protected firmware recovery artifacts require exact action-specific authorization
and were excluded from this worktree/review. The primary checkout retains the
unrelated untracked commissioning observation file. No state repair, production
exposure or physical test is included in these software integrations.

## Historical publication/migration record through 2026-10-20

The following records retain their original context and verification scope.

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

Installed firmware remains the previously recorded e2e9d3c artifact. Physical
readiness and current references need fresh explicit operator confirmation before
any future real-device action. The next liquid test remains deferred until the
user explicitly resumes it.

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
