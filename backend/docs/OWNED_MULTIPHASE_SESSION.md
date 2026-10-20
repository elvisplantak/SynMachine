# Owned multiphase session — fake transports only

Accepted base: `d3ad800f22642d0246db70cae6093ac9fae836f1`.
Branch: `codex/multiphase-session`.
The previous owned timed-execution checkpoint was independently accepted with
Critical/High/Medium/Low all zero. This document describes the next checkpoint.

## Result

`OwnedPhaseSession.execute_next()` prepares and executes the current supported
phase through the existing `PlanLifecycleCoordinator` and `OwnedTransferRunner`.
It reuses the same fake device, journals and exclusive hardware owner across
successive phases. It adds no transport, dispatch path, database or schema.

The contiguous integration test executes Reactor → SF, SF mixing, SF settling,
SF → Column and Column fraction collection through normal lifecycle transitions,
without resetting the fixture or clearing command history between phases. Its
initial late-phase run is an explicit test fixture; earlier phases are not
claimed as physically executed. A separate P1 solvent → first-reagent test stops
at the unsupported inter-addition delay. This is not yet the full Guided Demo.

## State and ownership boundaries

- Construction requires an unused fake runner, empty execution evidence and
  empty ownership history, a running run without an active execution intent,
  independently supplied initial positions/calibrations and a stopped mixer.
  Mismatched calibration is rejected before a plan is persisted.
- The initial context remains immutable. A private candidate state advances only
  after successful command results and durable result persistence, using the
  actual executed command's target. It is never copied from a prepared plan's
  optimistic final state. Candidate updates are not continuation permission.
- Each new plan receives a fresh phase execution ID. Its source is rebuilt from
  the current bound run and settings; the accepted coordinator independently
  revalidates source, phase, event sequence and calibration.
- The existing ownership history acts as an interference generation. Its count
  is read in one consistent idle transaction. The next claim compares the
  expected count inside `BEGIN IMMEDIATE`, before inserting a claim. Completed
  or failed Service work, including other connections/processes and the race
  between preflight and claim, cannot silently preserve session continuity.
  The history is append-only through the ownership API, not tamper-proof against
  external database edits or replacement. No new persisted counter is introduced.
- Preflight is repeated under ownership. Same controller boot alone is
  insufficient: the fake Arduino connection nonce and SF session must also match.
  Current fixture projections and command-call counts detect local interference.
  These are test observations, not live handshake or physical sensor evidence.
- Normal actions require both connections to remain valid. Required cleanup
  checks its own transport: a valid Arduino can still STOP the mixer after SF
  connection loss, and a valid SF can CLOSE after Arduino connection loss.
  Successful cleanup never restores an invalid session or erases the primary
  error. No commands are retried or rerouted through another adapter.
- Ownership covers lifecycle resolution and a final session/state check. Only
  successful execution, persisted lifecycle resolution and successful ownership
  release permit the next handoff. The session increments its generation by
  exactly its own claim; it never adopts a later observed generation.
- Stop, unknown outcomes, persistence faults and detected session/interference
  changes permanently invalidate this process-local session. There is no reset,
  rebind or resume method. An already-claimed phase retains ownership on failure;
  rejection before claim does not invent a retained owner.
- Separate database commits remain non-atomic. Failure after lifecycle commit
  may leave an advanced run and retained owner. Failure/interference detected
  after a completed release blocks this session's next phase; it does not undo
  an already committed successful phase or claim that release did not happen.

## Restart and explicit limits

A restarted process cannot construct a new session over prior ownership or
execution history, including a crash in the idle gap after a successful phase.
No automatic resend, resume, CLOSE, STOP, timer restart, provisioning or database
repair occurs. Completed evidence cannot substitute for a new live hardware
reference. Deliberate reconciliation and new-run reinitialization are deferred.

`execute_next()` is an explicit synchronous call, not an auto-run background
worker. It returns `None` at an unsupported delay/reaction-hold phase without
changing the run, sending commands or skipping that phase. External manual phase
advancement invalidates continuity. Delay/reaction-hold Pause/Resume timers still
need integration before the full demo can run on this composition.

Construction remains restricted to the exact fake transport/coordinator types.
No production startup, API, UI, firmware, Serial/Dynamixel integration or physical
action is activated. Live routes, physical/session trust, live SF OPEN/Stop policy,
recovery/flush and commissioning remain gates. Hypothetical fixture route orders
and calibrations are not approved live settings. Existing standalone phase tests
and the default legacy application composition remain unchanged.

## Verification and review focus

45 new session regressions; 239 focused execution/ownership/lifecycle tests pass.
All 1507 full backend tests pass (45.78 seconds); Ruff and `git diff --check`
pass. Tests include actual subprocess death in Arduino/SF send and between
phases, another process's completed ownership claim, concurrent session entry,
Service races, Stop, reconnect with unchanged boot, result-persistence faults,
required cleanup on the surviving connection and failure after lifecycle commit.

Review the handoff's command-confirmed state provenance, generation claim race,
cleanup after connection loss, retained owner on finalization failures and restart
rejection. Production activation and main merge are outside this checkpoint.

## Workspace continuity

After the interrupted work session, the temporary `/tmp` worktrees and test logs
were absent. Committed base and branches were intact. The uncommitted change was
reconstructed and all tests rerun. Active worktrees now live in persistent paths:
`/home/elvis/Documents/labforge-backend-multiphase` and
`/home/elvis/Documents/labforge-ui-multiphase`. Original checkouts and databases
were preserved. Do not use historical `/tmp` paths as the active workspace.
