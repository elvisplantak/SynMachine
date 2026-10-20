# Durable offline command plans

User-approved milestone, 2026-09-27: persist the complete source plan, prepared
commands, and initial assumptions; reject conflicting identities and test
restart without hardware. Base: `0ff0e3368ea93b046fea156765c0b93c35227944`.

## API and recorded identity

`SQLiteCommandPlanStore(database)` requires an explicit SQLite path. It is not
created by application startup and has no Serial, Dynamixel, execution, recovery,
or API hook. Tests use temporary databases; existing runtime databases are not
opened or migrated by this milestone.

`persist(PlanSource(...), CommandPlanningContext(...))` validates and lowers the
complete source before entering the write transaction. The version-1 payload
contains:

- run ID and run event sequence (caller-supplied provenance, not an execution claim);
- the full validated concrete operation plan, including source phase, topology,
  cycle metadata, reagent identity, or collection configuration;
- every prepared primary action, required follow-up, action ID, and projection;
- all initial assumptions, including calibration, positions, boot identity,
  route order, and stopped-mixer/valve/reference assumptions.

The phase execution ID is the table's primary key. Within `BEGIN IMMEDIATE`,
insert a new complete payload or compare the existing full canonical payload.
Identical repetition returns `created=False`; any different payload raises
`PlanIdentityConflictError` without changing the original. There is no update,
replace, delete, retry, or automatic execution operation. SQLite serializes
independent connections; a per-instance lock also protects cross-thread use.
Writes use `synchronous=FULL` and return only after COMMIT.

Source models are revalidated from raw field values before serialization, even
when assembled using `model_copy` or `model_construct`. This matters because
serialization can turn a bool masquerading as StrictInt into an integer. Unknown
nested fields may not silently disappear from the recorded provenance. The
source cycle capacity must match the corresponding planning calibration.

## Serialization and load semantics

Canonical JSON sorts object keys but preserves array order and Decimal spelling.
Decimal values are strings, not binary floating point. Semantically equivalent
but differently represented inputs can therefore conflict conservatively (for
example `2` versus `2.0` volume strings). The full payload is compared; SHA-256
is only an additional accidental-corruption check, not authentication against
someone able to rewrite the database.

`load(phase_execution_id)` returns the frozen `StoredCommandPlan`, or None when
absent. It checks version, checksum, row/payload identity, duplicate and unknown
fields, exact canonical round-trip, source model validity, and consistency of
stored prepared actions with the current offline compiler. Recompilation here is
validation only: different output fails closed with `PlanIntegrityError`; it
never replaces the saved commands. An unsupported future version or compiler
change needs a separate compatibility/migration decision, not silent rewriting.

Opening the store or loading a plan does not resume work, claim a run, mark any
command successful, or establish current physical position trust. A persisted
plan remains a preparation artifact even if a different process loads it.

## Verification

- 47 store tests; 94 combined store/planner tests pass.
- Complete backend suite: 1174 tests pass; Ruff and diff/whitespace checks pass.
- All transfer-source variants and Column collection round-trip across reopen.
- A fresh subprocess loads the committed plan without opening Serial or changing
  the database. Another subprocess exits with an uncommitted transaction; its
  row is absent on reopen and the existing committed plan remains intact.
- Independent connections and shared-store threads cannot overwrite identities.
- Changed source phase with identical prepared commands conflicts, as do changed
  run identity/version, volumes, fraction counts, initial assumptions, and route
  order even when the reordered route emits no actions.
- Invalid topology, source operation reordering/omissions/cycle metadata, forged
  bool boot IDs, and unknown nested fields cannot be stored.
- Altered commands/follow-ups, malformed or noncanonical data, invalid versions,
  inconsistent identity, checksum errors, and compiler drift fail closed without
  repair. Tests include recomputed checksums to exercise semantic validation.

## Remaining execution boundary and review

No automatic runner or physical authorization was added. A future milestone
must bind the stored run ID/event sequence to the actual durable lifecycle,
claim exclusive ownership across Arduino and SF paths (including Service,
follow-ups, Stop, and ambiguous-outcome queries), persist each command intent,
and resolve outcomes without automatic resending. Current boot/session references
must be established independently of loaded assumptions. Runtime route policy
must be backend-owned and approved; stored offline route order is not permission.

Fault tests for partial physical execution, restart between OPEN and CLOSE,
required-close unknown/failure, and carousel trust loss still belong to that
runner milestone. This checkpoint tests persistence/restart, not those physical
execution semantics. V8/P2 Waste-route restrictions remain unchanged.

Independent review focus: complete source provenance despite lossy lowering,
canonical identity comparison and raw-value validation, SQLite atomicity/races,
load-time corruption/compatibility rejection, and the separation between loaded
preparations and permission to execute. No UI/firmware code changed.


## Independent-review follow-up — 2026-09-27

Review base: `92b5dc8712a19b5c032500e8361aacc7a93c7f0a`.
Both findings were reproduced/confirmed from the implementation and accepted.

- `PlanSource` and the offline `PlanningModel` boundary now use wrap validators
  to compare recursively the incoming mapping/model keys with validated fields.
  Unknown keys discarded by nested domain models raise validation errors during
  ordinary construction or JSON validation, before persistence. The helper in
  `app/hardware/provenance.py` is limited to these boundaries; unrelated domain
  model behavior is unchanged. Existing model-copy revalidation remains active.
- Raw external provenance must enter these boundaries before any lossy domain
  conversion. No validator can recover fields already discarded by a caller's
  earlier independent domain-model construction. Internally generated typed
  domain plans remain supported.
- Store opening validates the ordered table columns, declared types, NOT NULL,
  and primary-key flags, rejecting incompatible layouts with `PlanIntegrityError`.
  Missing row-column errors also normalize to that error. No migration or repair
  is attempted. This is a layout check, not authentication of arbitrary SQLite
  schema objects or protection against an external writer changing the database.
- Six regression cases cover unknown plan/operation/calibration fields using
  normal raw mappings and JSON. A seventh verifies incompatible table rejection
  with existing rows and byte-for-byte unchanged database contents.

Future runtime gates additionally include distinguishing absent plans from a
wrong/missing database path or a newly created empty database. Recovery must not
silently create an empty store and interpret it as evidence that no work exists.
Required-follow-up tests must explicitly cover primary definitive failure and
unknown outcome, Stop during CollectionWait, CLOSE failure and unknown outcome,
restart between OPEN/CLOSE, and carousel failure/unknown with lost position trust.
These are documented requirements only; no runtime integration is introduced.

Focused review questions: does the raw envelope reject discarded nested keys
for both mappings and JSON without broad domain changes, and does incompatible
schema rejection leave existing storage untouched?
