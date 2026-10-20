# Owned transfer execution slice — 2026-09-30

This historical checkpoint is accepted with zero independent-review findings.
The next extension is documented in [OWNED_TIMED_EXECUTION.md](OWNED_TIMED_EXECUTION.md).

Accepted base: `620e3fb4c9e741461f091df019e2743d9ca96481`.
Branch: `codex/owned-execution-slice`.
The previous shared-ownership checkpoint was independently accepted with zero
findings. This document records the accepted transfer-only integration checkpoint.

## Concrete result

One offline composition now connects stored plans, real lifecycle persistence,
shared Arduino/SF/Service ownership, durable command intent/result, and explicit
fake transports. It executes the five existing P1/P2 transfer phases, including
SF-to-Column protected aspiration and existing Column CLOSE actions. It does not
execute collection, waits or continuous mixer operation.

`PlanLifecycleCoordinator` reuses the accepted lifecycle validation and commits;
its old `SimulatedLifecycleCoordinator` name remains compatible. It chooses one
runner. With `OwnedTransferRunner`, all prepared hardware actions go through
`OwnedHardware`, as do the exposed Service adapters. There is no direct legacy
send/fallback inside this composition. The historical simulator remains available
for its existing tests; default application startup remains unchanged.

Execution order:

1. Load and revalidate the stored plan against run identity, event sequence,
   phase, calibration and regenerated source operations.
2. Check the independent fixture context and sessions; refuse previously used
   fixtures or existing command evidence. No stored assumption creates trust.
3. Claim `HardwareOwnership`, then repeat preflight under the owner to catch
   intervening Service work on the fixture.
4. Commit lifecycle claim/start before hardware actions.
5. Execute each operation through the owner gate. Arduino uses the existing
   `DurableArduinoCommandExecutor`; SF uses `DurableSfExecutor`. Both persist
   intent before fake send. Required CLOSE has a separate command scope under
   the same gate, including after an ordinary primary failure.
6. Resolve lifecycle before releasing ownership. Stop, unresolved outcomes and
   persistence failures retain ownership. A successful CLOSE cannot erase an
   unknown primary outcome.

The SF Service adapter also uses the SF journal. Its phase identity is the
owning Service sequence identity; each action has a fresh command ID. The new
`journaled_sf=True` composition option selects that path explicitly. Existing
unwrapped SF adapters and default startup are unchanged.

## Persistence and recovery boundary

There are three explicitly provisioned fixture files: the existing ownership
schema, the existing offline lifecycle schema, and an execution database holding
plans plus Arduino and SF command journals. This slice adds no simulated owner,
simulated phase or projection ledger. The execution database binds its UUID to
the ownership UUID; lifecycle binds to the execution UUID. Opening is mode=rw;
missing/empty/wrong/incompatible execution databases fail before opening the
legacy auto-create journal/plan stores. The compiled schema, including unexpected
triggers/views/indexes, is checked. No migration or repair occurs.

SF rows are INTENT_PERSISTED, COMPLETED or OUTCOME_UNKNOWN. There is no accepted
SF negative-acknowledgment contract, so transport exceptions are conservatively
unknown. Intent-write failure prevents send. Result-write failure leaves durable
intent unresolved. Error-write failure preserves the original transport exception
and adds a diagnostic note. Duplicate IDs never resend, even after completion.

Separate files do not provide an atomic multi-database transaction. Crashes can
leave ownership without lifecycle start, unresolved lifecycle with command intent,
or advanced lifecycle with ownership retained. Reopen does not reconstruct leases,
release owners, resume, resend or automatically CLOSE. Tests compare database
bytes around rejected restart attempts. Deliberate cross-database reconciliation
and an operator recovery policy are still required.

## Exact limits

This is a candidate orchestration path with a deliberately fake-only constructor,
not production-ready startup. It still uses `SimulatedP1Device` for independent
context/session fixtures and the existing offline lifecycle store. Each fixture
is consumed by one phase attempt. Service calls on that fixture invalidate its
initial assumptions. These checks are NOT a general live trust provider and do
not prove current physical state across real processes/devices or successive
phases. Fresh live trust, session binding and invalidation remain mandatory.

The planner's fixture route ordering is not approved live route switching.
Stop retains the accepted offline operation-boundary behavior: a protected
OPEN/aspiration/CLOSE operation finishes its required follow-up before observing
Stop at the next operation boundary. In particular this does not settle the
live policy for Stop after SF OPEN but before aspiration. No emergency-stop or
interrupt-in-flight guarantee is claimed.

Still deferred: continuous mixer START/STOP ownership, collection/timers in the
new composition, full multi-phase fresh-state integration, deliberate recovery,
live route approval, live trust, live Stop policy, actual transport/startup/API
activation, UI/firmware changes and physical tests. No main merge.

## Verification

- 38 new integration regressions; 107 focused tests pass (new slice plus accepted
  lifecycle and shared-ownership suites).
- Full backend: 1375 passed.
- Ruff and git diff --check pass.
- Tests assert lifecycle start, shared ownership and committed command intent
  from inside fake send hooks; competing Arduino/SF Services cannot send.
- All five transfer phases complete through the same composition.
- Stop before start, during protected transfer and racing final resolution.
- All six required SF CLOSE persistence combinations: primary ok/failed/unknown
  versus CLOSE intent/result write failure; primary errors are preserved.
- Successful CLOSE after unknown primary still requires reconciliation.
- Lifecycle claim/start/result and ownership release failures retain ownership.
- Actual subprocess death during Arduino send and SF OPEN leaves durable intent;
  restart sends nothing, performs no cleanup and does not alter the databases.
- Wrong database/schema/binding, absent plans, changed calibration/run/context/
  sessions, duplicate SF intent, failed error persistence, and Service work
  between preflight and claim are covered.

No hardware connection, firmware upload, physical action or production activation
was performed. Review this whole slice together rather than its mechanical edits.
