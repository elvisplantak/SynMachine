# XDL 2 linear recipe interchange

The owner approved XDL integration on November 10, 2026, preferring the newer
language generation. This first slice provides import/export in Recipes, a
browser workflow, bounded validation and a runnable fake-device example. It is
a defined subset of XDL 2, not a general Chemputer executor or full XDL compiler.

## Version and implementation decision

The official [tag list](https://gitlab.com/croningroup/chemputer/xdl/-/tags), also
checked directly through the GitLab API on November 10, lists **2.1.0** at commit
`6d60e8da7218a589b9c8715a239956601b17cd07` as its newest public tag. Its tag message
describes it as the last release before the project became private. Public
documentation separately describes the old 0.5 and newer 2.0 standards. This
does not establish the version or availability of later private development.

The reference package version and XML format declaration are different: tag
2.1.0 still defines `XDL_VERSION = "2.0.0"` in `xdl/constants.py` and emits
`<?xdl version="2.0.0"?>`. This adapter emits that declaration, not an invented
2.1.0 declaration. Accepted wrapped documents without a declaration are parsed
under the explicitly selected local XDL 2 profile, not auto-detected as a version.
An explicit older/unknown version is rejected. A bare `Synthesis` is accepted
only with the explicit 2.0.0 declaration, following the documented compatibility
shape. [File structure](https://croningroup.gitlab.io/chemputer/xdl/standard/xdl_file_structure.html)
and [steps specification](https://croningroup.gitlab.io/chemputer/xdl/standard/full_steps_specification.html)
are the public interface references; the pinned source resolves details such as
`Component type`, default false flags and format declaration.

SynMachine implements this bounded reader/writer independently. The public SDK's
`setup.cfg` declares AGPL-3.0, classifiers through Python 3.10, older pinned
Socket.IO/WebSocket dependencies and separate Chemputer-provider extras. It is
not added as a dependency or executor; no upstream code or fixtures are vendored.
The new runtime dependency is [defusedxml 0.7.1](https://pypi.org/project/defusedxml/),
which declares the Python Software Foundation license. Existing project LICENSE
and NOTICE remain unchanged. This is a dependency/implementation record, not
a new license grant or a claim of upstream certification.

## Supported profile

API profile identifier: `synmachine-xdl2-linear-v1` (v1 is the local profile
revision, not the old XDL language generation).

| XDL | Existing RecipeDefinition step | Required explicit binding |
| --- | --- | --- |
| Liquid `Add` with `volume` | `ADD` | Reagent to B1/B2/S, target to REACTOR |
| `Transfer` with `volume` | `TRANSFER` | REACTOR→SF or SF→COLUMN |
| Passive `Wait` with `time` | `WAIT` | No device binding for the wait |

The file must have one Synthesis, Hardware, Reagents and a linear Procedure;
Metadata is optional and supports `description`. Synthesis `id` supplies the
suggested recipe name, which the caller can replace explicitly. Component IDs
and reagent names must be unique. Bottle and vessel bindings must refer to
declared values and be one-to-one. REACTOR accepts reactor/ChemputerReactor,
SF accepts separator/ChemputerSeparator and COLUMN accepts column. These are
logical bindings for review, not a hardware graph or physical readiness evidence.

Add permits only vessel/reagent/volume and optional explicitly false
stir/dropwise/viscous flags. Transfer permits only source/target/volume and false
solid/viscous flags. Reagents permit name and false solid/stir flags. Unknown
attributes are rejected, including requested speeds, transfer times, masses,
equivalents, rinsing, temperatures or reagent handling conditions. No instruction
is silently skipped or approximated.

Stir/heating/filtration/RunColumn, continuous operations, nested/sectioned
procedures, Repeat, Async, Parameters, Variables, Blueprints, compiled execution
records and graph bindings are outside this profile. In particular, the existing
fixed SF mixing profile has no confirmed RPM conversion; it is not exported as
an arbitrary XDL Stir. SF_SETTLE and timed fraction COLLECT also have no exact
mapping in this slice. Export rejects these steps rather than dropping them.

Accepted quantities use plain positive decimals, with explicit units: volume
`mL`, `ml`, `L`, `l`, `uL`, `µL`, `μL`; time `s`, `sec`, `seconds`, `min`, `mins`,
`h`. Numeric text is limited to 40 characters and normalized values to
`(0, 1000000]` mL/seconds. Decimal conversion is exact, without binary floats,
expressions, exponent notation or rounding. Native export bounds coefficient
length/exponent before expanding Decimal strings. Existing inventory/calibration,
whole-step and planning limits still apply and may reject a value in that range.
These are software interchange bounds, not physical capacities.

Export emits all three bottle labels as distinct reagent names and standard
REACTOR/SF/COLUMN component IDs. Blank/ambiguous labels are rejected. The response
includes explicit bindings for reimport and the source recipe content digest.
The XML contains no saved recipe ID/revision, run ID, credentials or readiness.
Unit normalization may change decimal spelling and therefore content digest;
import is a new draft requiring save/review, not restoration of a saved version.

## API and UI

New routes require an explicitly FAKE owned executor. LIVE, UNSPECIFIED and
absent executors are rejected. The routes perform no save, Start, maintenance,
device query or state repair. HTTP/UI authorization remains its existing policy;
SiLA client roles are not extended to these HTTP calls.

- `POST /api/v1/recipes/xdl/inspect`: `{ "xml": "..." }` returns supported
  declarations, step count and suggested name. No bindings are guessed.
- `POST /api/v1/recipes/xdl/import`: `{ "xml": "...", "name": "optional name",
  "reagents": { "S": "coloured_water" }, "vessels": { "REACTOR": "reaction_vessel" } }`
  returns a validated draft definition plus the existing preview. `name` may be
  omitted. Missing/ambiguous/unsupported bindings fail; execution fields are not
  accepted. No recipe store or command journal is written.
- `POST /api/v1/recipes/xdl/export`: `{ "definition": { ... } }` validates the
  existing definition/preview and returns XML, profile, digest and bindings.

In Recipes, open **XDL 2 import / export**, choose a UTF-8 file, review its declared
reagents/vessels, assign the bindings and select **Import as new draft**. Save it
using the existing versioned recipe action, review it and supply fresh readiness
before a separate Start. Selecting/importing a file clears prior execution
readiness; failure preserves the previous draft. Export downloads
`synmachine-recipe.xdl`. The file controls are disabled outside a FAKE profile.

Existing revision/digest/readiness checks, lifecycle, run snapshots, ownership,
command journals, progress and exact-operation Stop remain authoritative. There
is no XDL Start route, alternate executor, implicit recovery or new actuator step.

## Input boundaries and checks

The server enforces a 128 KiB UTF-8 XML limit, at most 512 elements, depth 8 and
1..100 steps. defusedxml forbids DTDs, entities and external resources. Unknown
processing instructions, namespaces, text instructions, duplicate sections and
executable extensions are rejected. Only one version instruction in the prolog
is allowed. The browser rejects oversize and malformed UTF-8 files before upload;
the server independently checks XML size/structure/semantics.

The backend suite includes hostile-input, precision, unsupported-feature,
binding, flow, calibration, fake-only and existing-save/execute regressions.
Browser fixtures cover mapping, new-draft identity, download, separate explicit
Start, rejected import/readiness invalidation, UTF-8 failure before upload and
disabled live controls. All browser fetches are fake fixtures, not a live API.
GitHub backend CI now requires both the existing SiLA modules and test_xdl,
with zero failures/skips. The UI suite is validated locally from `ui/`.

Local verification on November 10, 2026 passed 2094 complete backend tests,
including 94 XDL cases and 63 SiLA cases, with zero skips. The additional C# SiLA
scenario lists and explicitly executes an XDL-imported/saved recipe through the
unchanged SiLA adapter and backend. All 55 UI tests passed. Backend Ruff,
dependency/compilation checks, UI lint/TypeScript/Vite build, locked NuGet
restore/C# Release build (zero warnings/errors) and Actionlint passed. The exact
CI report gate accepted the full report and rejected missing XDL coverage.

Hosted [GitHub run 42812048926](https://github.com/elvisplantak/SynMachine/actions/runs/42812048926)
also passed on implementation commit `6ac42df9c8aeddbb85f373a813541f3d7bc05e72`:
2094 backend tests in 179.93 seconds, including 94 XDL and 63 SiLA cases,
zero failures/skips, with successful Ruff/dependency checks and a C# build
without warnings/errors. UI checks above are local, not a new hosted UI job.

## Runnable fake demonstration

From `backend/`, after installing `.[dev]` in a development environment:

```bash
env -u LABFORGE_ARDUINO_PORT -u LABFORGE_SF_BOTTOM_VALVE_PORT \
  .venv/bin/python -m tests.xdl_demo --state-dir /tmp/synmachine-xdl-demo
```

The example [coloured-water.xdl](../examples/xdl2/coloured-water.xdl) imports with
explicit fixture bindings, saves/previews through the existing API, explicitly
starts with a clearly fake readiness statement, observes progress/completion
and exports/reimports the same recipe. It creates a new empty isolated fake
bundle, closes all resources and preserves the resulting databases/XML. It
refuses reused state and live-port environment settings before application import.
Temporary evidence is not a substitute for physical readiness or state repair.

## Independent review

Independent review accepted exact HEAD
`ab7af954ce74ca2572122f9fda808c8465ea4bb1` against base
`d8820309971e50ccbbe12ca412252e3609369b84` for the declared narrow FAKE/local
XDL 2 recipe-interchange scope. The implementation is
`6ac42df9c8aeddbb85f373a813541f3d7bc05e72`; the reviewed HEAD only adds its CI
documentation record. Findings: zero Blocker, High, Medium, Low and
documentation-only findings. No software correction was requested.

The review confirmed bounded fail-closed parsing/export, explicit bindings,
deterministic Add/Transfer/Wait translation, the existing validation/execution
authority, new-draft/save/review/fresh-readiness/Start separation and server-side
FAKE admission. It verified hosted run 42812048926 and the distinction between
hosted backend evidence and the separately recorded local UI verification.

Acceptance applies only to that exact reviewed commit and scope. Later project
instructions and documentation records do not extend the acceptance. Full XDL,
live execution, physical/wet testing, inferred hardware topology, existing-state
repair/migration, firmware/EEPROM, production exposure and main merge remain
outside it. Earlier SiLA acceptances remain separate.

## Main integration

[PR #2](https://github.com/elvisplantak/SynMachine/pull/2) was merged after explicit
owner approval on November 10, 2026, as
`e0fd9590f711b924e42b94ba812c17f158138038`. Its parents are prior main
`d8820309971e50ccbbe12ca412252e3609369b84` and approved candidate
`29a4674a48da91c361e8f11e1da2dd0591f7a1af`; the merge tree exactly matches that
candidate. The existing source/commissioning branches are retained.

Exact candidate [CI 42818100137](https://github.com/elvisplantak/SynMachine/actions/runs/42818100137)
passed 2094 backend tests in 174.69 seconds, including 94 XDL and 63 SiLA cases,
zero failures/skips; Ruff, dependency/report checks and the locked C# Release
build passed with zero warnings/errors. Its executable files match the accepted
XDL checkpoint. The local 55-test UI verification remains separate.

Automatic post-merge [main CI 42819905886](https://github.com/elvisplantak/SynMachine/actions/runs/42819905886)
also passed on exact merge `e0fd9590f711b924e42b94ba812c17f158138038`: all 2094
backend tests in 175.96 seconds, 94 XDL and 63 SiLA cases, zero failures/skips.
Ruff, dependency checks and the locked C# Release build passed with zero warnings/
errors. This subsequent documentation-only closure preserves that verified code.

The software merge does not extend independent acceptance or authorize live,
production, physical/wet, state-repair or firmware/EEPROM work.
