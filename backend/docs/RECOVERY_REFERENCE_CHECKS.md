# Recovery reference checks scoped to the current interruption

This checkpoint connects the existing fresh Arduino/SF observations to the
exclusive offline runtime and explicit operator attestations. It is not a
physical recovery executor and does not clear an owner or authorize a new run.
All tests use injected fake transports; no real port is opened during development.

## Entry and scope

Call `OwnedOfflineRuntime.begin_reference_checks(arduino, sf_valve,
required_commands=...)` only after explicit interruption reconciliation. The
machine must be RECOVERING or RECOVERY_REQUIRED with an interrupted run, no active
execution intent and a retained hardware owner. A live locally started execution
session cannot enter this workflow. All sampling holds the runtime operation gate
and existing process-level bundle locks. The normal production startup/API does
not call this method, and legacy writers do not participate in these advisory locks.

A new process-local challenge identifies the check round, interrupted run, retained
owner, controller boot ID, backend nonce and connection generation. The actual
challenge object is required on every confirmation and report. Copies, foreign
challenges, old rounds and old runtime instances are rejected. Starting another
round invalidates the previous round; restart does not reconstruct confirmations.

## Operator attestations versus observations

Each valve V1–V8 and each pump has a separate reference item. Additional items
cover the closed/referenced Column valve, manual carousel alignment, each stopped
mixer, each pump's safe recovery route and each pump's working calibration. No
position, route sequence, pulse count, volume or calibration value is invented.
An attestation requires an explicit operator string and explanatory evidence note.
The operator string is attribution supplied by the caller, not authenticated identity.

`confirm(challenge, item, operator=..., evidence_note=...)` records an **operator
statement in process memory**, not sensor evidence or a firmware reference command.
It does not home anything or populate command-planning assumptions. Individual
missing items remain visible in `report(challenge)`. Duplicate replacement is
rejected; correcting a statement requires a new round and new confirmations.

Every confirmation and report makes fresh Arduino/SF observations. The controller
must remain in the same connection/session and pass the existing trusted-IDLE and
capability checks. SF must be observed within its closed tolerance with torque
OFF. OPEN, unknown position, torque ON, communication/read errors and repeated
status request IDs invalidate the round. No corrective motion or torque write is
attempted. SF's short-lived samples still do not establish persistent SF session
trust, mechanical closure, fluidic sealing or unchanged physical state between reads.
Both bracketing STATUS request IDs are consumed by the round. Equal IDs within
one observation or reuse of either ID from any earlier observation permanently
invalidates the round and clears its confirmations, including when a queued
duplicate reply passes the Serial client's normal correlation checks.

## Database binding and invalidation

Before and after sampling, the workflow compares the current inspection snapshot
with its initial recovery context. SQLite data_version detects external commits,
and connection total_changes detects writes made through the runtime's own
connections. This also rejects real changes to journal details that leave the
inspection's counts/status summary unchanged. Rollback-related total_changes can
invalidate conservatively. No-op external SQL that changes no database bytes is
not a data change. These checks supplement the exclusive composition; they are not
an atomic snapshot against arbitrary uncoordinated database/hardware writers.

Any sampling/context failure permanently invalidates that check object and clears
its in-memory attestations. Closed/foreign runtime and occupied operation-gate
checks reject access. Invalid input is rejected without recording a statement.
Previously returned reports are historical snapshots, not reusable capabilities.

## Remaining boundary

Even with every item recorded, `may_release_owner` is always false. Run/machine
state, ownership, plans and command/wait journals remain unchanged. In particular:

- operator statements are not proof of homing or actual physical recovery;
- current observations cannot turn an old unknown command into success;
- this code does not reconstruct timers, resume the interrupted run or run cleanup;
- physical recovery/flush execution, its durable result, safe route approval,
  current references usable by command planning and a durable owner-release policy
  still need implementation/integration before a new physical run is possible;
- there is no UI/API activation, new database schema, migration, firmware change,
  physical test or merge to main.

The workflow is a concrete place to gather scoped confirmations and identify what
is missing. It must not be described as a completed production recovery system.

## Verification

Tests connect offline interruption reconciliation, real protocol/register adapter
code with fake ports, fresh observations and operator-check rounds. They cover all
items and single missing references, copied/old/restarted challenges, repeated
requests, same-ID reconnect, invalid/busy observations, SF position/torque changes,
missing operator/evidence, duplicate replacement, owner/journal changes including
unchanged summaries, changes during sampling and reentrant close exclusion.
Successful and failed checks do not send motion or mutate durable recovery evidence.

Local verification: 26 new tests; 90 focused connected tests and all 1668 backend
tests pass (53.89 s full suite). Ruff and `git diff --check` pass. No independent
review of this checkpoint has been requested yet.
