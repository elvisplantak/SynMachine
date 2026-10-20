# Offline lifecycle binding for stored command plans

Base: `76fca333e2a9807a6b9dafff71ad21fa3e4d1fa2`.
Accepted simulation review base: `f87a6c4f7612b7621e18ba1f3a5bc4aec68fcb00`.
Branch: `codex/simulated-p1-execution`.

## Scope

The stored-plan simulation now binds to the existing SQLiteStore lifecycle
claim, start-commit, Stop and result-resolution transitions. All six transfer /
collection source phases are covered. This is an explicitly constructed offline
coordinator using the exact SimulatedP1Runner / simulated device classes. It is
not imported or constructed by application startup, an API or a Service endpoint.
Arduino Serial, SF Dynamixel, firmware and UI behavior remain unchanged.

Preparation checks current run ID, phase, status and event sequence; supplied
calibrations must match stored assumptions. It regenerates operations using the
existing GuidedDemoPhaseExecutor builder and compares them with the stored source.
Stored route orders remain hypothetical test fixtures, not approved live routes.

## Ownership and persistence boundaries

1. The simulation claims its durable sequence owner before claiming the lifecycle.
2. Lifecycle claim and start permission are persisted before simulated actions.
3. Every Arduino/SF command keeps its previous durable intent-before-send behavior.
4. Stop is read from fresh lifecycle state at existing operation boundaries and
   during virtual collection waits; required follow-up retains existing semantics.
5. Successful lifecycle resolution must persist before simulation owner release.
   Stop accepted during final result resolution also prevents owner release.

The lifecycle and simulation stores are separate SQLite databases: this is NOT
an atomic distributed transaction. Cross-database failure is deliberately fail-closed.
A crash or write error before lifecycle resolution retains the active lifecycle
intent and simulation ownership. A crash after resolution but before owner release
may leave an advanced run with retained ownership. Neither case automatically
resumes, resends, closes, releases ownership or repairs the databases.

Failure exceptions, including definite command failures, propagate unchanged;
this slice does not invent failure-to-lifecycle outcome mappings. The lifecycle
intent stays unresolved. Existing startup reconciliation can classify interrupted
execution and require recovery, but does not release the simulation owner or send
commands. Explicit recovery/release remains future work.

## Database identity

`provision_lifecycle` creates a NEW offline lifecycle file exclusively, using the
normal lifecycle schema plus an offline-only UUID / simulation UUID binding table.
SimulationLifecycleStore opens only an existing file (`mode=rw`), validates both
expected identities, schema version and lifecycle table layout, and never invokes
normal initialize/migration behavior. The coordinator rejects a runner from another
simulation. A missing plan in a verified database is distinct from missing, empty,
wrong or incompatible databases. Identity records detect wrong-file use, not
malicious edits or cloned databases. Never use these fixture databases with normal
application startup: their additional table is deliberately incompatible.

## Verification

31 new tests cover all six success paths, Stop before start, Stop within protected
SF transfer / collection, Stop racing with final resolution, blocked competition,
claim/start/result/owner-write failures, stale run/plan/calibration, wrong/missing/
empty/incompatible lifecycle databases, explicit startup reconciliation and actual
subprocess death during simulated send. The 186-test focused suite passes.
The full backend suite passes 1299/1299 tests; Ruff and `git diff --check` pass.
Tests use fake devices and temporary fixture databases only.

## Remaining production gates

- Production-wide ownership across Arduino, SF and Service (NOT implemented here).
- Backend-owned approved live route-switching order.
- Independent current hardware/session trust; historical plans are not trust.
- Explicit live Stop semantics after SF OPEN and before aspiration.
- Deliberate resolution of failed/unknown attempts and cross-database gaps.
- Live timers and production lifecycle binding before API/hardware activation.

The prior collection milestone plus this lifecycle milestone form the next
consolidated independent-review checkpoint. Do not merge main or activate hardware
as part of this review.
