# Owned pausable demo — fake-only end-to-end execution

Branch: `codex/owned-pausable-demo`.
Accepted base: `dc9412bbf463ed95b71d16bd63e6bab94586d3f5` (all review severities zero).

## Result and scope

Both `DELAY_BETWEEN_ADDITIONS` and `REACTION_HOLD` now execute through the same
stored-plan → lifecycle → shared ownership → durable wait path as the other
owned phases. One process-local session can execute all ten active Guided Demo
phases, from solvent transfer through the last collected fraction, without
resetting fake device state. Tests cover both reagent addition orders and a full
run with Pause/Resume in both waits. No alternate command dispatcher is added.

These two phases are passive waits. Their durations come from the immutable run
configuration (`delay_between_additions_seconds`, `reaction_duration_seconds`).
They do not imply heater control, temperature feedback, reactor mixer activation
or a mapping of percentage commands to physical speed. Runtime duration editing
and its UI remain future integration work. Zero duration is legal and still
requires durable intent and lifecycle resolution.

## Preparation and lifecycle

- New strict `PausableWaitPlan` / `PausableWaitOperation` models compile to a
  `PausableWait` action; source and prepared plan are durably stored and revalidated.
- The broader lifecycle intent set now admits the two waits. The legacy
  `GuidedDemoExecutionCoordinator` explicitly rejects them before preparation,
  claim or execution. The historical simulator also cannot execute these plans.
- This candidate requires an explicitly injected `MonotonicExecutionTimer` for
  these phases. Missing timer blocks the bound session before plan persistence.
  Other accepted single-phase fixtures retain their existing virtual waits.
- Ownership claim precedes lifecycle claim/start, and wait intent is persisted
  before the timer starts. The same owner and intent survive every Pause/Resume.
  Service remains blocked throughout the wait and pause.
- `SimulationLifecycleStore.set_wait_paused()` is an explicit offline control
  method, not a production endpoint. In a write transaction it checks the matching
  started execution ID, BUSY machine, active run and supported wait phase, then
  uses the existing domain Pause/Resume transitions. Wrong tokens, pre-start,
  other phases and already resolved execution are rejected without mutation.
- Timer control reads run, intent and events from one consistent transaction.
  It accepts only valid replayed Pause/Resume/Stop transitions from the original
  phase run and compares the entire resulting run snapshot. Unrelated source or
  configuration changes cannot hide behind an updated status/event sequence.
  Replaying control history validates a currently executing phase; it does not
  restore an interrupted execution after restart.

## Time and completion races

The timer charges monotonic elapsed nanoseconds only between readings with the
same durable control event sequence and RUNNING state. PAUSED time is excluded.
If Pause and Resume both happen between polls, their changed sequence prevents
charging that ambiguous interval. Clock readings bracket control reads so the
read overhead is also excluded. This deliberately errs toward a longer wait,
not an early completion; it is not a hard real-time or exact chemical-duration
claim. Poll sleep is bounded (default 50 ms), but DB/scheduling overhead is not.
Wall-clock event timestamps do not drive elapsed-time calculation.

Stop wins when observed at the timer deadline and also works while paused.
Clock regression, malformed control state and read/sleep errors fail closed.

Pause can win after the duration elapsed but before lifecycle resolution. The
explicit `defer_paused_wait=True` option on result resolution checks that race
inside the lifecycle write transaction. It validates the token/start/timestamps
using the existing resolver against a temporary RUNNING view of the paused run;
that view and its hypothetical result are never written. For a valid COMPLETED
wait result it returns `None` while PAUSED. The coordinator retains ownership
and the same unresolved intent, waits for Resume or Stop with zero remaining
budget, and attempts only lifecycle resolution again. No commands or wait intent
are resent. A wrong token or invalid timestamp still fails; default resolution
behavior is unchanged. Deferral is limited to these wait phases and COMPLETED
results.

If duration evidence was already persisted as COMPLETED before that late Pause
or Stop, it stays evidence of the elapsed budget; it is not proof that the phase
advanced. The lifecycle outcome remains authoritative. A late Stop resolves the
run as ABORTED and retains hardware ownership, even when wait evidence is complete.

## Failure and restart boundaries

Wait result, Pause/Resume, lifecycle resolution and ownership release failures
cannot publish permission for the next phase. Separate databases remain
non-atomic: an already persisted elapsed duration or advanced lifecycle does not
undo an unresolved owner. Existing session/fixture checks still run before owner
release. Session changes during a pause invalidate continuation.

Actual subprocess death while waiting or paused leaves the owner and durable
intent. New session construction rejects that history; there is no automatic
resume, timer reconstruction, resend, cleanup, owner release or database repair.
The offline control method itself changes only run metadata and cannot acquire
or reconstruct a lost execution lease. Deliberate recovery remains unimplemented.

## Verification and remaining gates

45 new regressions; 466 focused execution/lifecycle/ownership tests pass.
All 1552 full backend tests pass (50.14 seconds). Ruff and `git diff --check`
pass. Tests include a complete run, both addition orders, both
paused waits in one run, another lifecycle connection issuing controls, deadline
Pause/Stop races, wrong-token deferral, zero durations, hidden configuration
changes, connection loss, persistence faults and real process death while paused.

No schema, migration, production API/startup, Serial/Dynamixel transport, UI
behavior, firmware or physical test was activated. Original checkout databases
remain untouched. Full fake lifecycle execution is now covered; physical demo
readiness still requires deliberate cross-database reconciliation, approved live
routes, independent current hardware/session trust, commissioning/calibration,
live SF OPEN/Stop policy and explicit production/API/UI integration.

Review focus: timer accounting under rapid Pause/Resume, transaction-bound Pause
versus completion, preserved intent/owner across pauses, strict source/control
history validation, isolation from legacy execution, and crash/no-resume behavior.
