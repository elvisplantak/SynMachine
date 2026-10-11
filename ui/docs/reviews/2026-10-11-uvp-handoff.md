# Consolidated UVP implementation review — 2026-10-11

Please respond to the user in Croatian/BHS. Review the complete connected UVP
software milestone independently. Treat recommendations as advisory, not already
accepted changes. Return concrete findings with severity, file/line, failure
scenario and suggested correction. Do not run hardware, upload firmware or enable
production; fake transports and localhost tests only. Never access firmware recovery/.

## Review refs

- Backend repo: https://github.com/elvisplantak/labforge-backend
  feature `codex/uvp-recipes`, commit e6260970b57c187c1bbe7ff0b09548f93ef9e5c0
  baseline 90e136cc3a8d26b6b212ad3b14a1f739caeb24fd.
- UI repo: https://github.com/elvisplantak/labforge-ui
  feature `codex/uvp-recipes`, use its published HEAD after this handoff commit;
  baseline 881e5bf. The implementation agent's final message supplies the exact HEAD.
- Firmware unchanged at 3cc2de2fe69ff4990dccc003f7baa2adb446ff7f; installed e2e9d3c.

Fetch both feature refs and inspect complete diffs from the baselines, including
all new files. The local worktrees are labforge-backend-multiphase and
labforge-ui-multiphase. No main merge or physical activation is part of this scope.

## User intent and resulting implementation

UVP means Unos vlastite procedure: chemist-facing ordered procedure entry in the
existing UI, durable saving and repeat execution. No free-text conversion, XDL,
new physical routes or animation. Future devices should be addable through
cohesive software extensions, without building a plugin framework now.

The UI adds UVP navigation, a recipe library, bottle descriptions, typed step
cards, reorder/duplicate/remove, immutable version saves and recipe copying.
Saving never executes. Review is backend-derived; edits invalidate review and
preparation. Explicit Start requires a saved current revision, a checked profile,
fresh recipe preparation and idle owned execution. The existing operator-reference
challenge remains separate. Status/Stop/Pause/Resume/recovery/flush reuse the
existing controls; navigation/reload do not replay commands.

A separate SQLite library appends immutable revisions with expected-revision CAS,
transactional initialization and schema/duplicate-key rejection. It does not alter
the strict lifecycle schema. A run stores its immutable reviewed recipe copy,
readiness statement and step index, without fake Guided Demo configuration.
Repeated identical phases advance by index, bound to the event sequence.

The recipe compiler returns existing operation plans. It preserves protected
SF aspiration/close, column close before carousel movement, timed waits and shared
ownership. The current-plan revalidator compares the complete source against the
current recipe step. Persistence rejects recipe/readiness replacement and progress
without completed-step events. Legacy Start/manual phase-completion endpoints
cannot execute recipes. Default app recipe execution returns 503 with no owned
composition, and startup has no new hardware activation.

After pre-command current-input cancellation, the original CREATED run stays in
history. A new explicit recipe attempt needs fresh preparation and fresh secured
reference challenges; no automatic retry or reuse of the old challenge. A fault
later in execution uses existing restart reconciliation, recovery and mandatory
flush before a new run.

## Validation and limits

- Full backend: 1895 passed; focused UVP: 37 passed.
- UI: 36 passed, including 15 real headless-browser cases; no skips.
- Ruff, UI lint, TypeScript/Vite build and whitespace/diff checks passed.
- Existing adapters were exercised with fake serial/SF transports and asserted
  durable intent before bytes. No real Serial port, motor, pump or valve opened.
- UVP cases cover balances, unsupported kinds/schema, quantization/HOME limits,
  version conflicts and concurrent initialization/CAS, persisted snapshots,
  repeated phases, Stop/Pause/Resume, failure/restart/recovery/flush, readiness,
  legacy bypass rejection and fresh operator input after cancellation.

Volumes/durations are configured, not measured. Nominal inventories assume empty
prepared reactor/SF/column; exact comparisons reject overdraw. Collection is timed
and must be last because its remaining volume is unknown. Normal completion does
not physically empty or clean vessels. Operator preparation is required for the
next procedure. No heater/reactor mixer/speed command or new route is inferred.

V1 displays latest library versions; older definitions remain in immutable rows
and run snapshots. Version-history browsing/export/import and animation are later
features. Unsaved drafts are not durable. Software limits: 100 steps, 1000 pump
cycles/transfer, existing carousel command positions 1..40; the latter does not
confirm physical tube availability. Non-integral pump positions and ordinary
absolute target zero are rejected. No substituted HOME or rounding.

Logical schema and hardware/profile compilation remain separate. Unknown future
kinds/versions are rejected until explicit support/migration exists. A new operation
can extend the typed schema and compiler plus existing executor support/tests.
No parallel recipe executor or plugin/module framework was introduced.

## Focus the independent review

1. Recipe snapshot immutability, repeated-phase progression and source matching.
2. Recipe revision races, atomic initialization and invalid/corrupt library behavior.
3. Integration with existing ownership, Stop, waits, fault/restart/recovery/flush.
4. Fresh preparation/current-reference semantics and pre-command cancellation.
5. UI review/save/execute separation, read failures and navigation persistence.
6. Default production gating, legacy snapshot compatibility and extension boundaries.

See UI docs/UVP_USER_GUIDE.md and backend docs/UVP_RECIPES_V1.md for the complete
contract. This checkpoint is software-complete and has not yet received independent
acceptance or physical wet validation.
