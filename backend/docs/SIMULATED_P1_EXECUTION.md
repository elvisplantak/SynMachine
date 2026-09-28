# Simulated P1 sequence execution

Historical P1 checkpoint. The current P2/SF continuation and cumulative review
scope are in [SIMULATED_TRANSFER_EXECUTION.md](SIMULATED_TRANSFER_EXECUTION.md).

Approved on 2026-09-28: execute one stored P1 solvent-to-Reactor phase through
simulated devices, with exclusive sequence ownership, durable per-command intent
and outcomes, Stop boundaries, and interruption tests. Base:
`7ee5000f08238e7e7def2a681545b7a96eff88c7` (`codex/durable-command-plans`).
That persistence checkpoint was independently accepted with no remaining findings.

## Exact scope

`app/hardware/simulated_p1_runner.py` is an explicitly offline harness. It accepts
only `SimulatedP1Device`, not a live transport or Serial client. Nothing constructs
it at application startup, and no API, Service, firmware or hardware path changes.
It loads the whole validated stored plan and accepts only
`P1SolventToReactorOperationPlan` and `P1ReagentToReactorOperationPlan`; P2, SF, collection and required-followup
operations are rejected before acquiring ownership. No implicit HOME is added.

The harness uses the existing `DurableArduinoCommandExecutor` and
`SQLiteArduinoCommandJournal`, retaining the original prepared action identities,
arguments, terminal outcomes and persist-before-send behavior. It does not create
a second command lifecycle or reinterpret a command failure as completion.
The simulation transport returns successful terminal results without claiming
physical movement or delivered volume. Its hook permits deterministic test faults.

## Database identity and sequence ownership

`provision_simulation(Path(...))` explicitly creates a new, dedicated simulation
SQLite database and returns its UUID. It refuses an existing path. Persist the
source plan with `SQLiteCommandPlanStore` in that database before execution.
`SimulatedP1Runner(path, expected_database_id, device)` uses SQLite `mode=rw` and
checks the database UUID and required tables. A missing/wrong/empty database is
not interpreted as an absent plan; opening never provisions it automatically.
The expected identity must be retained independently of the database path.

A `BEGIN IMMEDIATE` transaction claims the singleton sequence owner and records
an immutable attempt identity before any command. Existing phase attempts or
command intents cannot be replayed. Separate connections cannot interleave phases.
Progress counts only fully completed prepared operations, including no-op ones.
Only full completion releases ownership. Stop, failure, unknown outcome and an
abrupt process exit retain it. There is intentionally no unlock, auto-resume,
auto-resend, query recovery or operator override API in this milestone.

A RUNNING row observed after restart is evidence of an unresolved attempt, not
permission to continue. Commands completed just before a progress-write failure
are also never reissued. Loading/status inspection alone transmits nothing.

This owner governs only participants in this simulation database. Existing
production Arduino Service, SF, recovery and API paths do not share it yet.
Cross-path ownership must be integrated and tested before any live runner exists.

## Source identity, assumptions and Stop

The caller supplies run ID/event sequence, checked against stored provenance.
This is a simulation assertion, not binding to the real application lifecycle.
The simulated current-state fixture is supplied independently of the loaded plan,
validated for exact agreement with its assumptions, and consumed by one attempt.
The controller boot ID is checked before the attempt and before/after each command. No loaded
assumption becomes real hardware trust and no physical route order is approved.

Stop is checked before each prepared operation. A multi-command route operation
finishes before Stop is observed; no mid-operation pump interruption is introduced.
A stop callback error is conservatively unresolved. Definitive command failures
record FAILED at phase level; other exceptions record OUTCOME_UNKNOWN. If even the
phase outcome cannot be persisted, the durable RUNNING owner still blocks replay.

## Verification and remaining gates

- 40 simulation tests; 146 combined runner/store/planner/durable-command tests.
- Full backend suite: 1214 tests pass; Ruff and whitespace checks pass.
- Tests assert exact command order/arguments and committed intent visibility from
  another connection before sending, normal completion, no replay after completion,
  Stop before first action and after an atomic multi-action route, rejection/failure,
  transport ambiguity, unexpected exceptions, and reboot between commands.
- Tests inject intent/result write failures and abrupt subprocess exit immediately
  after command intent. Reopening never sends again. Separate runners cannot
  interleave; an unresolved owner also blocks a different phase identity.
- Wrong/missing/empty database, absent plan, mismatched lifecycle/assumptions,
  unsupported phases and live transport objects fail without sending.
- Tests use temporary databases; existing runtime databases remain untouched.

Before production integration: bind actual lifecycle state and event version;
establish backend-owned approved switching policy and fresh hardware trust;
share ownership across Arduino, SF, Service, required follow-ups and recovery;
implement explicit query-only ambiguity handling and recovery policy. Extend the
runner to P2/SF/collection with primary failure/unknown, Stop during collection,
required CLOSE failure/unknown, restart between OPEN/CLOSE, and carousel trust-loss
tests. UI activation and physical authorization remain separate milestones.

## Independent review focus

Review the pinned commit against the base above on `codex/simulated-p1-execution`.
Check that no send precedes durable intent, a restarted or previously attempted
phase cannot resend or continue, independent runners cannot interleave, Stop
respects operation boundaries, and invalid database identity cannot become an
empty-history recovery decision. Also check that simulation guarantees are not
mistaken for production-wide ownership or hardware readiness.


## P1 reagent extension and review cadence — 2026-09-28

The user requested continued autonomous software work and less frequent,
consolidated independent reviews. The P1 harness now accepts the existing B1/B2
reagent plans as well as solvent, without changing calibration, route targets,
command identities or the execution/journaling algorithm. All three P1 source
variants pass exact-order and durable-intent tests. A fault matrix exercises
both definitive failure and ambiguous outcome at every action slot, verifying
the completed-operation prefix, absence of later intents, and no resend on reopen.
Stop tests cover aspiration and dispense for all three variants; a Stop arriving
in the final operation yields a fully completed phase after that operation ends.

This is a continuation of the same simulated P1 boundary, not a new independent
review request. Consolidate review with a larger sequence/follow-up milestone.
When review is warranted, supply the user a copy-paste handoff with pinned base
and HEAD. Production lifecycle/shared ownership and SF/required-close integration
remain unimplemented gates, as described above.
