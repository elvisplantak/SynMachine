# UVP recipes v1

UVP (Unos vlastite procedure) defines an ordered local recipe in the existing UI.
Saving, copying, editing and previewing a recipe send no actuator commands.
Execution is an explicit request to the existing owned application executor.
The default production app does not enable that executor: recipe execution returns
503 unless an explicit composition is injected. No hardware was used for this milestone.

## Logical recipe contract

`RecipeDefinition.schema_version = 1` contains a name, description, descriptive
labels for the configured B1/B2/S bottles, and an ordered list of typed steps:

| Kind | Parameters | Existing operation |
| --- | --- | --- |
| ADD | source B1/B2/S, positive volume_ml | P1 aspiration and dispense to reactor |
| WAIT | positive duration_seconds | Passive pausable reaction hold |
| TRANSFER | REACTOR_TO_SF or SF_TO_COLUMN, positive volume_ml | Existing P2 route and transfer plans |
| SF_MIX | positive duration_seconds | Fixed commissioned ON/OFF profile |
| SF_SETTLE | positive duration_seconds | Existing SF settling wait |
| COLLECT | fraction_count 1..40, positive fraction_duration_seconds | Protected timed collection and carousel advance |

Volumes and durations use Decimal JSON strings. No free-text parsing, XDL,
raw commands, motor parameters, heater control, reactor-mixer control or new
fluidic routes are included. Bottle labels do not alter hardware bindings.
40 is the existing command-position limit, not confirmation that 40 physical
collection tubes are installed. The operator must prepare the required tubes.
100 steps and 1000 pump cycles per transfer are software planning limits.

Nominal inventories start at zero in reactor, SF and column. Exact rational
comparisons reject overdraw. SF mixing/settling and collection require prior
configured contents in that vessel. Collection must be last: its duration does
not establish a delivered or remaining volume. Partial transfers can leave
configured contents behind. An operator must empty/prepare vessels before a
subsequent run; recipe completion does not claim physical cleaning.

Available profile calibrations are checked during preview and again at creation.
Non-integral step volumes and absolute target zero are rejected without rounding
or a substituted HOME command. A profile with full=0, empty=20500, volume=20 mL
therefore cannot execute an ordinary 20 mL cycle. This retains the existing
HOME/transfer boundary; no physical calibration or reserve has been invented.

## Library and API

The library is a separate SQLite database next to the lifecycle file:
`<lifecycle filename>.recipes.sqlite3`. `create_app(recipe_database_path=...)`
can supply a different explicit path. Back up the library alongside lifecycle,
execution and ownership evidence. Initialization is transactional; unknown schema
versions, unexpected columns and duplicate payload keys are rejected. No lifecycle
DB schema migration or changes to production activation are performed.

The recipe library now uses `PRAGMA user_version = 2`: each row stores
`content_digest` alongside id, revision and payload. `RecipeDefinition` remains
logical schema v1. The digest is SHA-256 over the validated definition serialized
as compact JSON with sorted keys, UTF-8 (`ensure_ascii=False`), including defaults
and Decimal strings. Decimal spelling is preserved, so 1 and 1.0 can have different
identities. JSON formatting/key order do not affect the identity. Every read
validates the recorded digest; a mismatch returns 409 without rewriting content.
This is integrity checking, not an authenticity signature.

Library schema v1 is explicitly unsupported and left unchanged. There is no
automatic migration, deletion or repair. Retain existing data; selecting a separate
new library or migrating old content requires an explicit later decision. Earlier
UVP run snapshots without the required digest also fail validation; they are not
silently upgraded. Legacy Guided Demo snapshots without recipes remain supported.

- GET `/api/v1/recipes`: latest revisions, including structurally valid drafts.
- POST `/api/v1/recipes`: save a new recipe (`definition`, expected_revision=0).
- GET `/api/v1/recipes/{recipe_id}`: latest revision.
- POST `/api/v1/recipes/{recipe_id}`: append immutable revision using expected_revision.
- POST `/api/v1/recipes/preview`: validate flow and compile supported steps where a
  profile is available. Preview is metadata-only and supplies no live references.
  `calibrations_checked` describes static compilation only; collection readiness
  is separate: `NOT_REQUIRED`, `STATIC_CONFIRMED`, `FRESH_INPUT_REQUIRED` or
  `UNAVAILABLE`. The UI explains pending fresh references and blocks unavailable
  collection, independently of calibrations.
- POST `/api/v1/recipes/{recipe_id}/execute`: require run_id, expected_revision,
  expected_content_digest, occurred_at and a fresh RecipeReadiness statement; returns existing RUN acceptance.

Preview returns `content_digest`; the UI verifies it matches the saved definition's
identity before presenting Start. Execute compares both expected revision and
expected reviewed digest before creating a run. Even a self-consistent replacement
row with a new valid digest at the same revision cannot satisfy an old review.
Concurrent stale updates and execution against an outdated revision return 409.
The UI library displays latest revisions. Older definitions remain in immutable
library rows and completed-run snapshots; history browsing/import/export are not
part of v1. A new run executes a copy of the reviewed saved recipe, never mutable
library data. Quantities are interpreted under the current configured profile;
the resulting command plans retain that execution's calibration assumptions.

## Execution, interruption and extension

The existing DemoRun snapshot has either Guided Demo configuration or an immutable
SavedRecipe, an operator preparation statement and a zero-based recipe_step_index.
The existing lifecycle advances by index, so repeated identical phases execute
independently. The persisted event sequence and full source-plan comparison bind
each phase to its current step. Persistence rejects recipe/readiness replacement
and progress changes without completed-step events. Legacy snapshots without
recipe fields and the fixed Guided Demo workflow remain supported.

Compilation returns existing validated operation-plan types. SF-to-column uses
its protected aspiration/follow-up-close plan; timed collection retains required
close before carousel movement. The existing phase session, journals, shared
owner, worker, Stop, Pause/Resume and recovery/flush machinery execute those plans.
Manual phase completion and ordinary legacy Start cannot execute a recipe.

RecipeReadiness is a fresh operator statement about bottle contents, empty/prepared
vessels, waste capacity and collection tubes. It is separate from the secured
current-reference input required by the adapter profile. Neither is sensor data.
The configured adapter builder supplies its typed current-context provider to
owned application composition. COLLECT creation can therefore reach the existing
fresh RUN input instead of requiring fabricated static readiness. Before any
COMMAND, the provider still requires known Column/carousel and all other RUN
references. OwnedPhaseSession derives collection readiness from that acquired
context, then retains the existing live owned continuity across phases. A static
composition with no readiness and no provider remains blocked. No stale receipt
or optimistic readiness substitutes for missing fresh references.
After cancellation before any command, the prior CREATED attempt is preserved.
The UI permits only another explicit reviewed recipe attempt with fresh preparation;
the adapter issues new current-input challenges. Old challenges cannot resume work.
Once execution is interrupted, retained ownership blocks a new run until existing
restart reconciliation, recovery and mandatory flush complete. No automatic replay.

Future operations belong in the logical schema/validation and step compiler,
with independent adapter/profile capabilities and tests. Saved recipes contain no
pins, directions, valve angles, raw pump steps or calibration. Unknown kinds and
versions fail closed until explicit support/migration is implemented. No plugin
architecture is introduced now, and no second executor is created.

## Verification scope

`tests/test_recipes.py` covers schema/capability rejection, exact balances, immutable
revisions and run snapshots, concurrent initialization/CAS, repeated phases,
quantization and HOME boundaries, whole owned execution, Stop, Pause/Resume,
transport failure/restart/recovery/flush, default-app gating, unavailable column
profile and fresh operator input after cancellation. Existing adapters are exercised
with fake serial and fake SF transports, asserting durable intent before bytes.
New regressions exercise a saved complete recipe including COLLECT through the
actual configured builder and secured fresh initialization/RUN inputs. Missing
Column, carousel or both send no COMMAND and leave the attempt CREATED. Additional
cases detect structurally valid same-revision payload changes before run creation,
reject a different reviewed digest even when storage is internally consistent,
preserve prior schema bytes, and validate snapshot content identities.
UI contract/browser tests intercept every API request. Firmware is unchanged;
this milestone does not establish wet performance or production readiness.
