# LabForge Current Development State

- Checkpoint date: 2026-10-03
- Development phase: owned recovery, mandatory flush and durable new-run permission implemented under fake transports; production activation remains gated;
  V7/V8 repair and supervised dry production recommissioning complete
- Primary implementation agent: Codex
- Independent reviewer: ChatGPT

## Current checkpoint — owned recovery, mandatory flush and new runs

- Active persistent backend/UI worktrees remain `labforge-backend-multiphase`
  and `labforge-ui-multiphase`, now on `codex/owned-recovery-flush`.
  Backend HEAD: `a14c7beb77f7bd830a8368e1a400cf08be872b3b`, base `9245e9e`.
- The approved task is implemented. The same owned runner, immutable plan store,
  Arduino/SF journals and existing lifecycle connect recovery -> FLUSH_REQUIRED ->
  operator-triggered mandatory flush -> READY -> owner release -> a new run.
  No additional diagnostic layer, SQL schema, database or migration was added.
- Recovery explicitly homes references and selects supplied confirmed Waste routes
  before pump HOME/emptying. Successful recovery retains exclusion. A clean Stop
  can instead enter flush from retained command-confirmed state, including emptying
  pump contents toward Waste without unnecessary re-homing. Old runs never resume.
- Flush reuses protected SF aspiration/CLOSE and Column drain/CLOSE/carousel
  boundaries for two liquid cycles and final air passes. Volumes, calibration,
  switching order, drain duration, tube margin and manual alignment are supplied;
  no physical setting is inferred. Completion does not prove effective cleaning.
- Durable maintenance intent precedes commands. Stop (including the last command),
  ambiguity, write failure, changed sessions and process death retain ownership.
  Explicit maintenance interruption reconciliation sends nothing; restart requires
  deliberate recovery/flush. READY with unreleased ownership still blocks new runs.
- New-run entry consumes fresh/retained process-local state with ownership-generation
  checks and a new run identity. Normal completion also allows another run without
  mandatory flush. Historical unknown command evidence remains unchanged.
- `PreparedAdapterDevice` binds existing Serial/DYNAMIXEL adapters to the same
  executor. Fresh observations run under ownership; tests inject fake ports/sessions.
  Explicit monotonic timing is required. There is no environment startup/API/UI
  activation, real device connection, motion, firmware change or main merge.
- Final verification: 40 new focused tests passed (14.04 s); all 1710 backend tests
  passed (72.62 s), including 42 cases above the prior checkpoint; Ruff and both
  staged/working diff checks passed. Backend change: 21 files, +1829/-25 lines.
- Detail: backend `docs/OWNED_RECOVERY_FLUSH.md`. Consolidated review handoff:
  `docs/reviews/2026-10-03-owned-recovery-flush-handoff.md`.
  This release boundary warrants one consolidated review. Last independently
  accepted backend base remains `3d9fab24`; newer checkpoints, including this one,
  are implemented/verified but not independently accepted.
- Remaining gates: reviewed production composition, physically verified switching/
  wet routes, working margins/drain timing and commissioning. SF host scope remains
  correlation, not persistent physical trust; cross-database commits are non-atomic.
  Advisory locks protect this explicit composition only. Optional standalone flush
  from READY remains unintegrated. No physical/production authorization is implied.

## Previous session handoff — 2026-10-03 (superseded by current checkpoint)

- User requested a minimal clean stopping point, consolidated reviewer handoff and
  continuation in a new session. Do not start another implementation milestone
  while closing this session. Reviewer suggestions remain advisory; prefer fewer,
  substantial reviews and autonomous safe progress.
- Backend code is unchanged at `9245e9e3f66716eb5dde17aaa3bd3b432f058e99` on
  `codex/recovery-reference-checks`, confirmed equal to remote HEAD. Working tree
  was clean after the credit interruption; no implementation was lost.
- Last independently accepted base remains
  `3d9fab24f325f3a2da59d69215465e110acd3c33`. The four later checkpoints are now
  submitted together for review; do not describe them as independently accepted.
- Review handoff: `docs/reviews/2026-10-03-backend-handoff.md` in this UI worktree.
- Fresh verification on 2026-10-03: all 1668 backend tests passed (59.47 s),
  116 focused new tests passed (7.09 s), Ruff and diff checks passed. Backend
  code was not modified for the session handoff.
- Active persistent worktrees:
  `/home/elvis/Documents/labforge-backend-multiphase` and
  `/home/elvis/Documents/labforge-ui-multiphase`.
  Use these, not the older original checkout branches or historical `/tmp` worktrees.
- The last approved implementation task was **not implemented yet**: connect
  recovery, mandatory flush and durable owner release/new-run permission through
  the existing execution path; prepare real adapters using fake transports first.
  Only preliminary reads of application_service.py, machine_lifecycle.py and
  owned_hardware.py occurred before the interruption. There is no partial code
  requiring reconstruction and no new recovery/flush executor or release method.
- Next session: read the reviewer response if supplied and assess it independently,
  then continue that approved cohesive task. Reuse current lifecycle/ownership/
  durable command paths; do not create another separate diagnostic layer.
- Respect existing domain policy: interrupted run does not resume; recovery leads
  to FLUSH_REQUIRED, operator starts Flush system, and successful required flush
  precedes a new run. Reconcile older context with current HARDWARE_CONFIRMATIONS
  before selecting physical details. Unconfirmed safe routes/calibration must not
  be invented; no real execution/startup activation/main merge is authorized.
- Python tools: `/home/elvis/Documents/labforge-backend/.venv/bin/pytest` and
  `ruff`, working directory the persistent backend worktree. Prior `/tmp` test
  logs are ephemeral and are not the continuity source. Canonical documents,
  committed code and this handoff preserve state.

## Previous checkpoint — scoped recovery reference checks

- Backend/UI worktrees remain `labforge-backend-multiphase` and
  `labforge-ui-multiphase`, branch `codex/recovery-reference-checks`.
  Backend HEAD `9245e9e`, based on `d3274ef`.
- Verification: 26 new tests, 90 focused connected tests, all 1668 backend tests
  pass; Ruff and diff checks pass.
- Offline runtime now connects explicit interruption reconciliation and retained
  ownership to fresh Arduino/SF observations and process-local operator attestations.
  Entry requires RECOVERING/RECOVERY_REQUIRED, an interrupted run and no active intent.
- Checks have a new challenge bound to run, owner, boot, nonce and connection epoch.
  Each reference confirmation and report samples again under the runtime operation
  gate; restart, a new round, foreign/copied challenge, session/context changes and
  observation errors prevent reuse. Individual missing actuator/reference items remain visible.
- Snapshot comparisons plus SQLite data_version/total_changes detect relevant
  durable context changes, including journal detail changes with unchanged summaries.
- These are attributed operator statements, not sensor evidence or authenticated
  identities. No values are copied from stored plans, and no homing is performed.
  Even all recorded items do not release ownership or authorize a physical run.
- Detail: backend `docs/RECOVERY_REFERENCE_CHECKS.md`. Run/owner/journal data remain
  unchanged, no schema/API/UI/firmware activation or physical test occurs.
- Next: durable physical recovery/flush execution and release policy, approved
  routes, fresh usable references and production composition. Current software
  collects scoped evidence; it does not yet implement physical recovery.
- Keep reviews consolidated; no new handoff requested for this software substep.

## Previous checkpoint — fresh hardware observations

- Active backend/UI worktrees: `labforge-backend-multiphase` and
  `labforge-ui-multiphase`, branch `codex/fresh-hardware-observations`.
  Backend HEAD `d3274ef`, based on `d5d1843`.
- Verification: 34 new tests, 72 focused adapter tests, all 1642 backend tests pass;
  Ruff and diff checks pass.
- Added explicit observation through existing Arduino/SF adapters: fresh correlated
  trusted-IDLE Arduino status before and after a read-only SF sample, explicit
  capability requirements and a local connection generation to reject reconnects
  even if boot ID/nonce repeat. No Arduino auto-connect/reconnect is introduced.
- SF reads share its command lock, validate the device and configured endpoints,
  report position/torque without register writes, and close the temporary session.
  Ambiguous endpoint tolerance remains unknown; read/close faults prevent success.
- Results never authorize owner release. IDLE/TRUSTED is controller software
  evidence, not physical position, fluidic readiness or command reconciliation.
  SF's temporary connection does not establish persistent session trust.
- Caller-held production-wide ownership is still required before activation;
  probes are not connected to startup/API/runtime. Tests inject fake ports/sessions.
  No physical ports were opened, no actuator moved, no schema or firmware changed.
- Detail: backend `docs/FRESH_HARDWARE_OBSERVATIONS.md`, including remaining
  reference/calibration/route/recovery/flush/release requirements.
- Next: connect fresh observations and independently established references to a
  reviewed production composition, with durable recovery/release policy and live
  Stop handling. Do not treat this diagnostic result as permission to clear a block.
- Continue consolidated review at a substantial integration boundary; no new
  reviewer handoff requested for this diagnostic step.

## Previous checkpoint — exclusive offline interruption reconciliation

- Active backend/UI worktrees remain `labforge-backend-multiphase` and
  `labforge-ui-multiphase`, branch `codex/owned-startup-reconciliation`.
  Backend HEAD: `d5d1843` (accepted base `3d9fab24`, diagnostic step `0ee2b83`).
- `OwnedOfflineRuntime` composes the same accepted fake execution path with
  exclusive advisory locks on all three existing database files. It runs all ten
  phases from a fresh bundle and rejects adoption of a persisted run after restart.
- Explicit reconciliation commits retained ownership before transactional lifecycle
  changes. Existing owners remain unchanged; interrupted gaps gain a BLOCKED
  reservation. No lease reconstruction, resend, timer Resume, cleanup or release.
- A supported PAUSED wait with durable start is marked FAULTED/RECOVERY_REQUIRED;
  time is not reconstructed. Legacy default reconciliation remains unchanged.
- Crash/write-failure tests cover both sides of the separate ownership/lifecycle
  commits and actual process death during paused execution. Repeated metadata
  reconciliation does not append events or mutate command evidence.
- Read-only inspection from `0ee2b83` remains diagnostic, not an authorization gate.
  The new advisory locks coordinate only the explicit offline composition, not
  legacy direct assemblies, arbitrary database writers or live hardware.
- Details: backend `docs/OWNED_OFFLINE_RECONCILIATION.md` and
  `docs/OWNED_STARTUP_INSPECTION.md`. No database migration, production activation,
  firmware/UI behavior change, physical execution or main merge occurred.
- The credit interruption preserved all changes. The previously started full suite
  completed with 1606 passing tests; two additional process-death regressions were
  then added and verified. Final result: 30 new tests, all 1608 backend tests
  passing; Ruff and diff checks pass.
- Next: prepare fresh hardware/session trust and the deliberate physical
  reconciliation/release boundary, then production transport/startup/API/UI
  composition. Software fault marking is not physical recovery or readiness.
- User requests substantially less frequent independent review. No new review
  requested for the interruption audit; consolidate the next review before moving
  from this offline composition toward production activation.

## Accepted full fake demo with pausable waits

- Backend branch `codex/owned-pausable-demo`, HEAD
  `3d9fab24f325f3a2da59d69215465e110acd3c33`; accepted base
  `dc9412bbf463ed95b71d16bd63e6bab94586d3f5` (independent review: all severities zero).
- All ten active phases now execute through one `OwnedPhaseSession`, including
  `DELAY_BETWEEN_ADDITIONS` and `REACTION_HOLD`. Full connected tests cover both
  reagent orders and Pause/Resume in both waits without fixture resets.
- New strict source plans compile to passive wait actions. Durations come from
  the run configuration; no heater, temperature feedback or reactor mixer control
  is implied. Runtime duration editing and UI controls remain unintegrated.
- An explicit monotonic timer is required for these phases. Intent is persisted
  before waiting. Pause/Resume uses durable domain events under a matching started
  wait intent; ownership remains held throughout pauses and blocks Service work.
- Control reads validate a consistent run/intent/event snapshot, replaying only
  valid Pause/Resume/Stop events. Monotonic accounting excludes paused time, read
  overhead and intervals containing control transitions, including a short complete
  Pause/Resume pair between polls. It may conservatively extend a wait; no exact
  real-time or chemical timing claim is made.
- Pause racing with lifecycle completion is deferred atomically without resolving
  the intent or releasing ownership. The same execution waits for Resume or Stop;
  no commands/intent are resent. Token and timestamp validation remain enforced.
  Stop during a pause or at the timer deadline aborts and retains ownership.
- Process death during a wait/pause cannot reconstruct or resume execution. Unknown,
  persistence or connection errors block continuity. Existing cross-database failure
  boundaries remain non-atomic and require deliberate reconciliation.
- The legacy execution coordinator explicitly rejects these new phases before
  preparation/claim. Broadening lifecycle intent support does not activate the
  legacy executor or any production API. No database schema or migration is added.
- Verification: 45 new regressions, 466 focused tests and all 1552 backend tests
  pass; Ruff and diff checks pass. Includes actual subprocess death while paused,
  another lifecycle connection issuing Pause/Resume, finalization races, zero
  durations, wrong-token deferral and injected persistence failures.
- Review document: backend `docs/OWNED_PAUSABLE_DEMO.md`. Independent review
  accepted `3d9fab24f325f3a2da59d69215465e110acd3c33` with all severities zero;
  no correction requested. Reviewer did not independently rerun the test suites. No Serial/Dynamixel, physical test, firmware/UI behavior
  change, production activation or main merge occurred.
- Next: deliberate recovery/reconciliation of retained ownership and separate
  lifecycle/execution databases. Then approved live routes, current physical/session
  trust and commissioning, explicit live SF OPEN/Stop policy, and production
  transport/startup/API/UI composition. Full fake execution is not physical readiness.
- Persistent worktrees, now on `codex/owned-pausable-demo`:
  `/home/elvis/Documents/labforge-backend-multiphase` and
  `/home/elvis/Documents/labforge-ui-multiphase`.
  Both interrupted sessions preserved work after moving out of `/tmp`.

## Accepted owned multiphase session — 2026-10-01

- Backend branch `codex/multiphase-session`, HEAD
  `dc9412bbf463ed95b71d16bd63e6bab94586d3f5`; accepted base
  `d3ad800f22642d0246db70cae6093ac9fae836f1` (independent review: all severities zero).
- `OwnedPhaseSession` connects existing source builders, stored plans, lifecycle,
  shared ownership and durable Arduino/SF execution through the same fake-only
  runner. No new database, schema or parallel transport path.
- The contiguous test executes Reactor → SF → mixing → settling → Column →
  fraction collection without resetting device state between phases. Initial
  entry at Reactor → SF is a test fixture, not proof of preceding physical work.
  P1 solvent → first reagent is also connected; execution stops at the unsupported
  inter-addition delay. Full end-to-end demo still requires pause-capable
  delay/reaction-hold timers in this composition.
- Initial positions/calibrations are independently supplied. Later state derives
  only from successful commands with persisted results, never optimistic plan
  projections. Handoff requires lifecycle resolution and owner release. Calibration
  mismatch is rejected before plan persistence. Source/run/session are rechecked.
- Existing ownership history supplies an interference generation, checked atomically
  during claim. Even completed Service work in another process invalidates the
  next phase. Same controller boot with a different fake connection nonce also
  invalidates continuity. These are fake-session observations, not live trust.
- Normal commands require both valid connections. Required STOP/CLOSE can use its
  surviving transport after the other connection fails. Cleanup never restores
  continuity. A final session check runs after lifecycle resolution before release.
- Stop, unknown, persistence faults and detected external changes block continuation.
  Restart cannot reconstruct this session, including death between successful
  phases. No resend, resume, automatic cleanup, owner release or database repair.
  Reconciliation, flush/new-run setup and physical reference recovery remain pending.
- Verification: 45 new regressions; 239 focused tests and all 1507 backend tests
  pass; Ruff and diff checks pass. Includes actual subprocess death, Service from
  another process, race before claim, concurrent entry and result-persistence faults.
- Review document: backend `docs/OWNED_MULTIPHASE_SESSION.md`.
  Independent review accepted HEAD `dc9412bbf463ed95b71d16bd63e6bab94586d3f5`
  with Critical/High/Medium/Low all zero; no correction requested. Reviewer confirmed
  remote HEAD but did not independently rerun tests through the GitHub connector;
  no GitHub status checks were present. Verification above is the local test result.
  No production API/startup activation, Serial/Dynamixel connection, firmware/UI
  behavior change, physical execution or main merge occurred.
- Next: integrate pause-capable delay/reaction-hold timers for one complete fake
  demo, then deliberate cross-database reconciliation. Backend-owned approved live
  routes, independently established physical/session trust and explicit live
  SF OPEN/Stop behavior remain gates before production activation.
- Persistent worktrees on `codex/multiphase-session`:
  `/home/elvis/Documents/labforge-backend-multiphase` and
  `/home/elvis/Documents/labforge-ui-multiphase`.
  After the interrupted session, former `/tmp` worktrees/logs were absent.
  Committed base/branches were intact; uncommitted work was reconstructed and
  verified again. Original checkouts and local databases were preserved.
  Historical `/tmp` paths below are no longer active workspaces.

## Accepted owned timed execution — 2026-09-30

- Backend branch `codex/owned-execution-slice`, HEAD
  `d3ad800f22642d0246db70cae6093ac9fae836f1`; accepted base
  `771ad703d70fef9cde94e9fb2c00bea57c811665` (independent review: all severities zero).
- The same owned runner/coordinator now executes Column collection with protected
  CLOSE, carousel moves, timed SF START/wait/required STOP, and passive SF settling.
  No alternate dispatch path. Default startup and fake-only assembly remain unchanged.
- User chose SF mixing duration in seconds, configured before starting a run.
  Added optional positive `sf_mixing_duration_seconds` to execution settings;
  missing duration blocks automatic mixing before claim, with no invented default.
  UI input is not added yet. Mixer uses only the existing fixed-profile boolean
  command; no percentage-to-speed conversion or speed calibration is claimed.
- Monotonic nanosecond timer with bounded cooperative polling is explicitly
  injectable; default fixture waits remain virtual. Wait intent precedes waiting,
  and operation completion is recorded only after successful required cleanup.
  Interrupted fractions are not counted complete. Ownership covers the entire
  wait and lifecycle resolution; Service commands stay blocked.
- Runtime carousel projection is invalidated before movement and restored only
  after completed command/persistence. Boot change invalidates fixture trust.
  SF mixing/settling require independently stopped mixer fixture state.
- Stop, unknown, persistence fault and process death retain ownership. Required
  STOP/CLOSE does not erase primary errors. Restart never resumes timers or sends
  START/STOP/CLOSE. Existing explicit startup reconciliation recognizes timed SF
  intents but does not release the shared owner. Full recovery remains deferred.
- Execution database gains wait/carousel evidence tables; previous schema is
  rejected without migration or repair. No original project database was changed.
  Lifecycle/ownership schemas remain unchanged. The broader intent-phase set does
  not activate new phases in the legacy executor or bypass active-intent guards.
- Verification: 87 new regressions, 194 focused and 1462 full backend tests pass;
  Ruff and diff checks pass. Includes actual process death, a real short timer,
  separate-connection Stop, and all six primary/cleanup journal-fault combinations
  for both Column CLOSE and mixer STOP.
- Consolidated review document: backend `docs/OWNED_TIMED_EXECUTION.md`.
  No main merge, new execution API activation, Serial/Dynamixel connection,
  firmware change, UI behavior change or physical test occurred.
- Independent review accepted `d3ad800f22642d0246db70cae6093ac9fae836f1` with
  Critical/High/Medium/Low all zero; no correction requested.
- Next at that checkpoint: address fresh multi-phase state
  and deliberate cross-database recovery. Delay/reaction-hold Pause/Resume timers,
  live route approval, live SF OPEN/Stop semantics and production startup remain
  gates. Hardware trust must be independently re-established before live tests.
- Worktrees: `/tmp/labforge-p1-execution`, `/tmp/labforge-ui-p1-execution`, both on
  `codex/owned-execution-slice`. Prior physical checkpoint below is unchanged.

## Accepted integrated transfer checkpoint — 2026-09-30

- Backend branch `codex/owned-execution-slice`, HEAD
  `771ad703d70fef9cde94e9fb2c00bea57c811665`; accepted base
  `620e3fb4c9e741461f091df019e2743d9ca96481`. New branch, no main merge.
- One path now connects stored plans, the accepted lifecycle coordinator,
  shared ownership, durable Arduino/SF intent/results and fake transports for
  all five P1/P2 transfer phases. Service adapters share the same composition.
  There is no direct legacy send/fallback inside this candidate composition;
  historical simulator tests and default application startup remain unchanged.
- Execution database holds plans and both journals; ownership and lifecycle
  retain their accepted separate stores. No added simulation owner/phase ledger.
  UUID bindings and exact execution-schema validation reject wrong/missing/empty
  files without automatic creation, migration or repair on reopen.
- Ownership precedes lifecycle claim/start and remains through result persistence.
  Required CLOSE shares the gate and preserves primary/cleanup errors. Stop,
  unknown, crash and write failures retain the owner. Restart cannot resume,
  resend, auto-close or release. SF Service intent identifies its owning sequence.
- Verification: 38 new integration tests; 107 focused and 1375 full backend tests
  pass; Ruff and diff checks pass. Includes all six required SF CLOSE persistence
  fault combinations and actual subprocess death during Arduino/SF sends.
- Independent review accepted this HEAD with Critical/High/Medium/Low all zero.
  No corrections requested. Documentation: backend
  `docs/OWNED_TRANSFER_EXECUTION_SLICE.md`. Remaining gates were not accepted as
  completed, and review did not authorize hardware activation or main merge.
- Limits: fake-only construction and independent per-attempt fixture context;
  no generalized live trust or complete multi-phase demo. Collection/timers and
  continuous mixer ownership are not integrated in this new path. Live route
  switching, SF OPEN/Stop policy, current trust, deliberate recovery and actual
  production startup/API/transport activation remain gated. No physical action,
  firmware change or UI behavior change occurred.
- Next: evaluate consolidated review, then extend the same path to collection/
  timers and mixer ownership without parallel command execution paths. Establish
  fresh-state transitions and deliberate recovery before any live activation.
- Worktrees remain `/tmp/labforge-p1-execution` and
  `/tmp/labforge-ui-p1-execution`, now on `codex/owned-execution-slice`.

## Accepted shared ownership checkpoint — 2026-09-30

- Backend `codex/simulated-p1-execution` HEAD:
  `620e3fb4c9e741461f091df019e2743d9ca96481`.
  Accepted base: `9eed35297066ffbe47a4c4bd01a9ff586ed0991b` (zero findings).
- HardwareOwnership supplies a durable sequence owner across Arduino/SF and
  Service paths wired through OwnedHardware. Explicit new-file provisioning,
  existing-file/UUID/schema/history validation, process-local non-resumable leases,
  non-waiting operation gate and SQLite cross-process claim exclusion.
- Ownership remains across gaps and required CLOSE. Errors, unknown outcomes,
  Stop and crashes retain the owner. Failed retention writes preserve the primary
  exception and poison the local lease. Explicit completion releases only after
  caller-owned successful lifecycle resolution; no automatic recovery/release.
- create_app(owned_hardware=...) binds both Service paths and rejects mixing raw
  runtime/adapters. This injection is tested with fakes; environment startup is
  NOT changed, and legacy unwrapped paths are NOT claimed protected. The new
  Service wrapper rejects standalone continuous mixer START before send, pending
  retained START/STOP lifecycle integration. Existing unwrapped behavior unchanged.
- 38 new tests, 99 focused tests, 1337 full backend tests pass; Ruff and diff checks
  pass. Tests cover every Service endpoint, concurrency, required CLOSE, scoped
  access, process death, wrong databases and claim/block/release write failures.
- Independent review accepted HEAD `620e3fb4c9e741461f091df019e2743d9ca96481`
  with Critical/High/Medium/Low all zero; no corrections. Remaining production
  gates were explicitly not completed by that commit. No main merge or activation.
- Next: connect accepted lifecycle execution to the shared composition and SF
  durable action journal; retain ownership across mixer START/STOP; deliberate
  recovery. Live routes, current trust, SF OPEN/Stop semantics, timers and actual
  startup activation remain gated. No motor/Serial/Dynamixel action in this work.
- /tmp worktrees were removed across restart and restored from committed branches;
  backend /tmp/labforge-p1-execution and UI /tmp/labforge-ui-p1-execution are current.

## Accepted lifecycle checkpoint — 2026-09-29

- Backend `codex/simulated-p1-execution` HEAD:
  `9eed35297066ffbe47a4c4bd01a9ff586ed0991b`. Immediate base: collection milestone
  `76fca333e2a9807a6b9dafff71ad21fa3e4d1fa2`.
  Consolidated independent-review base: `f87a6c4f7612b7621e18ba1f3a5bc4aec68fcb00`.
- New offline coordinator binds stored plans to real SQLiteStore claim/start/Stop/
  result transitions for all six P1/P2/SF/Column source phases. It compares current
  run identity/sequence/phase, calibration and regenerated source operations before
  claiming. Explicit offline lifecycle database UUID also binds to simulation UUID.
  Missing/empty/wrong/incompatible files fail without provisioning or migration.
- Durable simulation ownership precedes lifecycle claim and remains held until
  result persistence succeeds. Stop racing with final resolution retains ownership.
  Cross-database commits are intentionally not claimed atomic: write failures or
  crashes can retain an active intent or an advanced run with a blocked owner.
  Exceptions propagate unchanged; no automatic resume, resend, CLOSE, repair or
  ownership release. Existing explicit startup reconciliation requires recovery.
- Verification: 31 new lifecycle tests, 186 focused tests and 1299 full backend
  tests pass. Ruff and diff checks pass. Includes actual subprocess death,
  competing coordinator, claim/start/result/release failures and Stop races.
- Independent review accepted the combined simulated Column collection and offline
  lifecycle checkpoint at HEAD `9eed35297066ffbe47a4c4bd01a9ff586ed0991b`: Critical 0,
  High 0, Medium 0, Low 0. No corrections requested; remote HEAD confirmed.
  The reviewer confirmed ownership, durable intents, Stop/required CLOSE, database
  identity, partial collection accounting and conservative cross-database recovery.
  Review grants no main merge or hardware activation. Technical boundaries remain
  in backend `docs/SIMULATED_COLLECTION_EXECUTION.md` and
  `docs/SIMULATED_LIFECYCLE_BINDING.md`.
- Next: production-wide Arduino/SF/Service sequence ownership and
  deliberate failure/recovery binding, under fake transport first. Approved live
  route switching, fresh hardware trust, live SF OPEN/Stop semantics, timers and
  API activation remain separate gates. No physical action occurred in this
  software milestone; production runtime configuration is unchanged.
- Worktrees: `/tmp/labforge-p1-execution`, `/tmp/labforge-ui-p1-execution`.

### Current physical-session state — V7/V8 dry recommissioning passed

- On 2026-09-29 the user identified an unconnected driver after repairing the
  damaged connection, reconnected it, observed successful motion, and declared
  the fault resolved. Prior no-motion attempts are not proof of a failed motor.
- Powered individual tests identify physical "old V7" as channel A STEP D34 /
  DIR D35: 266 pulses at DIR LOW moved approximately 60 degrees toward HOME,
  explicitly confirmed. Physical "old V8" is channel B STEP D36 / DIR D37:
  133 pulses at DIR LOW moved this motor. The user subsequently explicitly
  confirmed that this was toward HOME. Both motor directions are now confirmed.
- Manual switch tests confirmed V7 HOME D3 (HIGH for about 2.5 s), V8 HOME D2
  (HIGH for about 1.9 s), both released LOW. Transition evidence is saved in firmware
  `docs/commissioning/2026-09-29/home-switch-transitions.jsonl`.
- CURRENTLY INSTALLED: corrected production firmware, V7 D34/D35/HOME D3 and
  V8 D36/D37/HOME D2, both HOME direction LOW. Build/upload flash-verified:
  40806 flash bytes / 3140 SRAM bytes. Focused tests passed 12/12; full native
  warning-enabled suite passed 196/196. Other actuator bindings are unchanged.
- Boot 71: V7 HOME -> V7 90 degrees -> 10-second pause -> V8 HOME -> V8 90
  degrees completed through the durable production command path. All four results
  are COMPLETED, without retries. The user confirmed correct HOME stops, returns
  to 90 degrees, and successful tests. Repair and V7/V8 dry recommissioning are closed.
- Host Serial connection closed, no queued commands. Both valves were physically
  confirmed at 90 degrees. Motor supply was last ON; power-off requested but not
  confirmed. Reset loses volatile trust. Other route components were not exercised;
  full P2 route readiness and end-to-end/wet demo remain separate confirmations.
- For EVERY next physical test, tell the user to enable motor power and wait for
  a fresh explicit readiness confirmation. Two repeat attempts were mistakenly
  sent while power was off; exclude them from physical evidence.
- Canonical repair evidence and remaining gates: firmware
  `HARDWARE_CONFIRMATIONS.md`, current 2026-09-29 section. Successful powered
  single-valve logs: firmware `docs/commissioning/2026-09-29/`.
- Production regression events and durable journal SQL export are saved in firmware
  `docs/commissioning/2026-09-29/`. Next: backend lifecycle/shared ownership work
  under fake transport; later dry demo requires fresh hardware and route readiness.

## Previous P2/SF checkpoint — 2026-09-28

- Backend `codex/simulated-p1-execution` is at
  `eca8fbd4a9d8a9a7d165b35109234522beca8ae1`; immediate base `2495d1f`,
  consolidated review base `7ee5000` (accepted durable-plan checkpoint).
- The user authorized continued offline work with fewer consolidated reviews.
  All P1 variants plus P2 Reactor-to-SF and SF-to-Column now execute through the
  explicit simulated device. Historical P1 class names remain compatible;
  `SimulatedTransferRunner`/`SimulatedTransferDevice` aliases expose the broader
  scope in `app/hardware/simulated_p1_runner.py`.
- SF commands have their own durable intent/outcome table and independently
  checked simulated session. Arduino and SF share the simulation sequence owner.
  Required CLOSE runs after ordinary primary failure, preserves both errors when
  both fail, and never turns an unknown primary outcome into success. Stop waits
  until the protected operation ends. No later route/dispense begins after error.
- Restart after process death between OPEN and CLOSE neither resumes nor sends
  automatic CLOSE. The durable owner remains blocked. Missing/wrong database
  identity is not treated as an absent plan. Old simulation databases without
  the new SF table are rejected without migration; use a new explicit test store.
- Verification: 59 simulation cases (21 new SF/P2 cases), 165 combined focused
  tests, 1233 complete backend tests; Ruff and diff/whitespace checks pass.
  Fault coverage includes all nine primary/CLOSE result combinations, SF write
  failures, OPEN failure, initial SF failure with required Column CLOSE, session
  changes, competing runner during CLOSE, and subprocess death after OPEN.
- This is the consolidated independent-review gate after P1 and P2/SF work.
  Provide a copy-paste handoff; focus and boundaries are in backend
  `docs/SIMULATED_TRANSFER_EXECUTION.md`. Review `7ee5000..eca8fbd`.
- Next: simulated Column collection wait/Stop/CLOSE and carousel trust-loss
  handling, followed by actual lifecycle and shared production ownership binding.
  The current owner covers only simulation, not production Service/SF/API paths.
  Collection is still rejected. No physical safety or route approval is inferred.
- Worktrees remain `/tmp/labforge-p1-execution` and `/tmp/labforge-ui-p1-execution`.
  Original databases/checkouts are preserved. No Serial/Dynamixel session,
  firmware upload or physical test occurred. V8 repair, motor-off D2 test and
  P2 Waste-route restrictions remain pending.

## Previous P1 checkpoint — 2026-09-28

- The user approved one P1 transfer phase through simulated devices, including
  durable command intents/results and interruption tests. Backend branch
  `codex/simulated-p1-execution` is at
  `2495d1fdfde4f306407cd4723a174acc39be36af`, based on
  `7ee5000f08238e7e7def2a681545b7a96eff88c7`. The prior persistence milestone
  and its two focused corrections were accepted by the independent reviewer
  with no remaining findings.
- `app/hardware/simulated_p1_runner.py` executes complete stored P1
  solvent/B1/B2-to-Reactor phases, using the existing durable Arduino command executor
  with an explicitly simulated device. It preserves prepared identities/order,
  journals intent before send, and stops at operation boundaries.
- Durable simulation ownership prevents interleaving or replay. Every incomplete
  attempt retains ownership, including Stop and process exit. Restart only
  inspects state; it never resumes or resends. Opening requires an existing,
  explicitly provisioned simulation database with matching independently held
  UUID, distinguishing an absent plan from a wrong/missing/empty database.
- Current simulation assumptions are supplied separately and consumed by one
  attempt. Boot identity is checked before and after commands. No stored plan
  becomes real hardware trust. Caller run/event matching is not yet integrated
  with the actual application lifecycle.
- Verification: 40 simulation tests; 146 combined runner/store/planner/durable-command
  tests; all 1214 backend tests pass. Ruff and diff/whitespace checks pass.
  Fault coverage includes command rejection/failure/ambiguity, intent/result
  write failure, independent runners, abrupt subprocess exit, and session change
  during the final command as well as earlier commands. Additional tests inject
  failure/ambiguity at every P1 action slot and Stop during aspiration/dispense.
- Important boundary: ownership currently covers this isolated simulation only.
  Production Service, SF, recovery and API paths are unchanged and not connected
  to this runner. Required follow-ups, P2 and collection phases are
  rejected; no Serial session, upload or physical test occurred.
- Next: continue simulated execution and bind actual lifecycle/shared ownership
  before any live activation. Review will be consolidated after larger progress,
  per the user's 2026-09-28 instruction; provide a copy-paste handoff then. P2/SF
  and collection require protected CLOSE, Stop and ambiguous-outcome tests.
  Approved runtime route order and fresh hardware trust remain prerequisites.
- Reviewer scope/approval/evidence and concrete questions are in backend
  `docs/SIMULATED_P1_EXECUTION.md`; current cumulative base is `7ee5000`, HEAD `2495d1f`.
  No additional reviewer request is made for this P1 reagent extension.
- Worktrees: `/tmp/labforge-p1-execution` (backend) and
  `/tmp/labforge-ui-p1-execution` (documentation), both on the new branch.
  Original checkouts and runtime databases are preserved. V8 wiring repair,
  motor-off D2 testing and P2 Waste-route restrictions remain unchanged.

## Previous persistence checkpoint — 2026-09-27

- The user approved durable offline plan storage after the command-planner
  review. Backend branch `codex/durable-command-plans` is at
  `92b5dc8712a19b5c032500e8361aacc7a93c7f0a`, based on
  `0ff0e3368ea93b046fea156765c0b93c35227944`. That base includes the independently
  evaluated reviewer follow-up: the planner conservatively rejects the maximum
  boot ID without claiming that current firmware cannot emit it.
- `app/hardware/command_plan_store.py` stores the complete source plan, run/event
  identity, prepared actions, and planning assumptions in an explicitly selected
  SQLite database. Atomic insert-or-compare accepts an identical repeat and
  rejects changed content under the same phase identity. It preserves source
  metadata even when different sources compile to identical commands.
- Loading validates schema, checksum, full source content, and compatibility
  with the pure compiler. Corrupt or incompatible records fail closed, without
  replacement or automatic execution. Persisted assumptions are historical
  input, not renewed physical-position trust or permission to execute.
- Verification: 40 new store tests, 87 combined store/compiler tests, and all
  1167 backend tests pass. Ruff and diff/whitespace checks pass. Tests cover
  independent-process restart, interrupted transaction rollback, concurrent
  writers, source/assumption conflicts, malformed data, and compiler drift.
- No API/startup integration, command dispatch, runtime ownership, physical
  operation, or migration of existing runtime databases was introduced. UI and
  firmware code are unchanged; no builds of those applications were required.
- Next software milestone: a separately scoped runner with exclusive ownership
  across Arduino, SF, and Service operations; durable per-command intent/results;
  current-session validation; Stop and required-close handling; and explicit
  unknown-outcome/restart tests using fake transports before API activation.
  Bind the stored run/event identity to the actual lifecycle at that boundary.
- This is an independent-review checkpoint for durable identity and restart
  semantics. Review backend `92b5dc8` against `0ff0e33`; focused scope, approval,
  verification, limitations, and questions are in `docs/DURABLE_COMMAND_PLANS.md`.
- V8 wiring repair and the motor-off D2 input test remain pending. V8 movement
  and P2 Waste-route homing remain blocked. No physical authorization is implied.
- Active worktrees: backend `/tmp/labforge-review-20260927` and documentation
  `/tmp/labforge-ui-durable-20260927`, both on `codex/durable-command-plans`.
  Original checkouts and their untracked runtime databases are preserved.
  Older worktree paths below are historical and may no longer exist.

## Previous offline checkpoint — 2026-09-26

- The user resumed development and authorized the backend bridge from existing
  Guided Demo plans to Arduino commands, using tests without motors. No Serial
  session, firmware upload, or physical test was performed or authorized.
- Backend branch `codex/offline-command-planning`, commit
  `0cc073b9e86e99767c81ab33c63c5649bf2a5e84` (base `668d7cd`), implements the
  first offline command-preparation milestone in
  `app/hardware/command_planning.py`. It translates existing P1/P2 transfer and
  Column fraction-collection operations into immutable command specifications,
  separate host SF actions, and Stop-aware collection waits. Protected required
  closes and scheduler boundaries are preserved.
- Preparation requires explicit positions/references, nominal calibration,
  expected boot identity, and proposed route switching order. Route final targets
  are derived from approved topology, not certified as physically safe. It rejects
  unknown required state, mismatched pump/routes, fractional-step volumes,
  out-of-range targets, and target zero; it never substitutes HOME for transfer.
  It skips already-reached valve targets and maps carousel fractions from an
  explicit tube reference, including 40-to-1 wrap.
- Verification: 46 focused tests and 1126 complete backend tests pass; Ruff and
  diff/whitespace checks pass. Only backend code and continuity documentation
  changed; no UI build or firmware build was required.
- Next software milestone: persist the whole immutable prepared plan, integrate
  command/result execution under exclusive ownership, and test Stop, required
  close failures, unknown outcomes, and restart handling before API activation.
  Per-command IDs alone do not protect changed order/omissions; no actual runtime
  adapter or API endpoint was enabled by this checkpoint. Full-span 20 ml transfer
  and volume quantization require an explicit policy compatible with `1..20500`.
- Independent review gate: inspect backend commit `0cc073b` against `668d7cd`,
  focusing on route target derivation versus unverified switching order, pump
  direction/endpoints, protected-action grouping, and identity/persistence
  boundaries. Scope, approval, limitations, and evidence are in backend
  `docs/OFFLINE_COMMAND_PLANNING.md`. Review is requested before runtime binding;
  physical authorization is separate.
- The user confirmed melted insulation at the V8 motor cable connection; repair
  awaits replacement wiring. Heating/contact root cause is not proven. A reduced
  current setting was recommended but neither application nor physical performance
  is confirmed. Firmware documentation commit `01d2c11` on the matching branch
  records this. V8 motion and P2 Waste-route homing remain blocked; the D2 manual
  input test with motor power off remains pending.
- Work is isolated in `/tmp/labforge-command-plan`,
  `/tmp/labforge-ui-command-plan`, and `/tmp/labforge-firmware` worktrees. Original
  checkouts and the two untracked backend runtime databases are preserved.

## Previous physical checkpoint — 2026-08-16

- Backend branch `codex/sf-mixer-service-integration` is at `668d7cd`. It now
  consumes a correlated Column HOME diagnostic `STATUS` that arrives after the
  command's `COMPLETED` lifecycle instead of leaving that response to poison
  the following command. Ruff and the full backend suite pass (`1080/1080`). A
  supervised production regression subsequently completed Column HOME followed
  immediately by CLOSED at 4 degrees, confirming the observed race is fixed.
- Firmware branch `codex/sf-mixer-service-integration` is at `0443837`. A pump
  HOME search may now confirm an active HOME signal produced by the final
  allowed 20,500th pulse without emitting a 20,501st pulse; a signal that drops
  before the 30 ms stability interval still times out without overtravel. The
  warning-enabled native suite passes `195/195`; the Mega build uses
  `40,806 / 253,952` flash bytes and `3,140 / 8,192` static SRAM. This production
  firmware is uploaded and flash-verified. The exact full-span physical
  boundary regression remains pending because the later V8 fault stopped the
  end-to-end run before pump transfers began.
- Do not command V8 until its physical drive is diagnosed. During the latest
  end-to-end attempt, V1-V7 homed normally, but V8 only oscillated/made an
  abnormal sound in its confirmed HOME direction and timed out. A temporary
  bounded diagnostic then observed D2 continuously LOW while HOME motion was
  attempted. Twenty slow pulses in the direction away from HOME moved normally;
  a five-times-slower HOME attempt still only oscillated and never reached the
  switch. This is a physical V8 direction/load/coupling/phase fault, not evidence
  that the backend retried a command. The temporary diagnostic firmware was
  removed afterward.
- Final safe state: production firmware `0443837` restored and flash-verified;
  motor power physically off; backend and Serial monitor off. Firmware restart
  makes all Arduino position trust volatile/untrusted. V1-V7 last had
  controller-completed HOME targets, Column remained physically CLOSED at 4
  degrees, P1 and P2 remained physically at HOME, carousel remained physically
  aligned at tube 1, SF mixer remained stopped, and the Dynamixel SF bottom
  valve remained CLOSED.
  V8 physical position is not trusted. The requested V1-V8 = 90 degrees and
  P1/P2 = 2,000-step parking was intentionally not performed because the P2
  Waste route depends on confirmed V8 = 90 degrees.
- The user intentionally paused LabForge work until September 2026 and will
  manually position any actuators needed for storage; no software parking is
  pending. On resumption, keep V8 motion prohibited and first test its D2 HOME
  signal without motor power by observing released `LOW` and manually pressed
  `HIGH`. That test must precede any further V8 mechanical/driver diagnosis or
  motion. No separate session handoff is required beyond this document,
  firmware `HARDWARE_CONFIRMATIONS.md`, and the pushed repository history.

## Repository checkpoints

### UI

- SF mixer Service control is implemented on branch
  `codex/sf-mixer-service-integration` at commits `db7b607` and `f25ce04`.
  The card exposes only fixed-profile Start/Stop, reports commanded rather than
  sensed state, keeps Stop available after an uncertain UI session, and blocks
  other Arduino Service controls while the mixer is known running. A CSS
  follow-up makes enabled Service buttons visually distinct from disabled
  buttons. The production UI build passes. The supervised production-path test
  completed STOP -> START -> STOP, and the user physically confirmed rotation
  and stopping. A final regression completed three additional Start -> Stop
  cycles without an error; the user confirmed both physical behavior and the
  corrected enabled/disabled button appearance.
- Production Column integration is physically validated through the backend/UI
  Service path with the reassembled calibration (`CLOSED=889`, `OPEN=24,739`
  pulses from HOME). The supervised sequence CLOSED -> HOME -> CLOSED -> OPEN ->
  HOME -> CLOSED completed at the correct physical positions; every request
  returned HTTP 200, UI controls were disabled only while commands ran, and the
  user reported normal direction, movement, stops, and sound. The valve is
  parked at confirmed CLOSED and motor power is physically off.
- A final supervised regression on the production firmware after the cumulative
  HOME-search accounting correction confirmed the restart boundary and motion
  path. Four pre-HOME OPEN requests in controller boot session `58` failed
  closed as `INVALID_FIELD` with `execution_started=false`; after HOME, the
  `HOME -> OPEN -> CLOSED` sequence completed and the user physically confirmed
  the test passed. The final production firmware is therefore physically
  validated, including its mandatory fresh-HOME behavior after session change.
- Powered D10 remains electrically noisy while the HOME lever is pressed. The
  Column-only bounded filter accumulates active evidence for HOME confirmation,
  fails unresolved mixed input after 250 ms, and never bypasses the interlock.
  Movement away from trusted HOME ignores raw D10 transitions only for the
  confirmed 889-pulse DIR HIGH release zone; STEP then remains inactive until
  D10 is continuously LOW for 30 ms. This removed the observed 30-60 second
  HOME-to-CLOSED delay while preserving a hard no-motion-beyond-CLOSED boundary
  when release is not confirmed.
- OPEN-to-HOME diagnostics exposed that rejected false HOME candidates reset the
  former per-stage pulse counter. Firmware now maintains and reports a separate
  cumulative HOME-search count, so the command times out at exactly 80,000 total
  pulses across all candidate pauses. Warning-enabled native tests pass
  `183/183`; the final Mega build uses `39,394 / 253,952` flash bytes and
  `3,079 / 8,192` static SRAM and is uploaded and flash-verified. No physical
  motion was performed after this accounting-only safety correction.
- A supervised V1 regression smoke test after the host concurrency correction
  completed HOME and 90-degree positioning. A following Column HOME attempt is
  not a valid mechanical test because the shaft/coupling pin had been removed
  pending replacement; the backend timed out and durably recorded
  `OUTCOME_UNKNOWN`. The command was not retried, UI/backend were stopped, and
  the user confirmed motor power was switched off. The Column test is deferred
  until reassembly and must restart with a new controller session, fresh
  identity, and HOME before CLOSED/OPEN. The user has since installed the new
  shaft/coupling pin; the supervised post-reassembly test is still pending.
  Five accidental SF UI requests failed
  closed with HTTP 503 because U2D2 was not configured, so no SF hardware
  command occurred.
- All Arduino-backed Service controls now share a synchronous global command
  guard. The guard closes same-tick and cross-card click races before React's
  next render, notifies every mounted Arduino control, and disables pumps,
  V1-V8, the Column bottom valve, and carousel controls while one Arduino
  request is active. Backend serialization remains the authoritative boundary.
  UI lint and the production build pass.
- Independent-review follow-up makes every Arduino guard owner enter an
  exception-safe `try/finally` immediately after successful acquisition, so
  even synchronous command-ID or preparation failure releases the guard. V1-V8
  and Column UI wording now reports only controller-completed targets rather
  than independent physical position confirmation; HOME `0 degrees` remains
  explicitly distinct from Column CLOSED `4 degrees`.
- Carousel now has a dedicated Service section for operator-confirmed manual
  reference and logical-forward movement to tube positions `1..40`. Reference
  and movement use separate inline confirmations, fresh caller-owned command
  identities, pending-control locking, and no automatic retry. The UI reports
  only the last completed command rather than claiming durable trusted
  position, because controller session replacement invalidates the volatile
  carousel reference. UI lint and the production build pass. A subsequent
  supervised production-path test established a no-motion manual reference at
  tube 1, then physically completed and aligned `1 -> 2 -> 10 -> 40 -> 1`.
  Every accepted move returned HTTP 200 and was durably `COMPLETED`; the final
  40-to-1 wrap moved one adjacent 250-pulse / 9-degree position as designed.
  The carousel is parked at position 1 and motor power is physically off.
- Carousel UI familiarization also exposed an operator-error case: setting a
  new manual reference at 2 while the mechanism physically remained at 1 made
  later move-to-2 requests correctly reject as `INVALID_FIELD` with
  `execution_started=false`, because the controller considered logical 2
  already reached. Correcting the no-motion reference to physical tube 1
  restored the intended mapping. Manual reference is an absolute declaration
  of the currently aligned tube, not a relative offset.
- The Carousel Service UI follow-up separates manual reference and movement
  into numbered control blocks with independent reference and target inputs.
  A completed reference locks its block and enables movement; changing it now
  requires an explicit `Change manual reference` step followed by the existing
  physical-alignment confirmation. Reference changes clear any previous Column
  CLOSED checkbox, movement stays disabled until the new reference completes,
  and the UI explains that an incorrect absolute declaration shifts all later
  tube mapping. UI lint and the production build pass; this UI-only correction
  initially issued no hardware command. A subsequent supervised regression
  through the hardened UI completed the no-motion reference at 1 followed by
  `1 -> 2 -> 20 -> 40 -> 10 -> 1`; every command returned HTTP 200 and was
  durably `COMPLETED`, and the user physically confirmed the complete test
  passed. The carousel is at position 1 and motor power is physically off.
- Column bottom valve Service card now calls the durable Arduino backend path
  for separate `HOME`, `CLOSED`, and `OPEN` actions. The UI truthfully keeps
  `HOME reference = 0 degrees` distinct from the confirmed operating positions
  `CLOSED = 4 degrees` and `OPEN = 94 degrees`, creates fresh caller-owned
  identities, locks controls while pending, never retries automatically, and
  records a controller-completed target only after terminal `COMPLETED`. UI
  lint and the production build pass; no physical execution was performed in
  this phase.
- V1-V8 Service cards now call the durable Arduino backend command API for
  explicit `HOME` and canonical `SET_POSITION` actions at `0`, `90`, or `180`
  degrees. Each command creates fresh caller-owned phase/operation identities,
  locks its card while pending, never retries automatically, and records a
  controller-completed UI target only after the backend returns terminal
  `COMPLETED`.
- The UI maps the confirmed semantics as `0 degrees = closed`,
  `90 degrees = k1 <-> k3`, and `180 degrees = k1 <-> k2`. This software
  checkpoint has passed lint and the production build; no physical execution
  was performed during the software implementation phase. A subsequent
  supervised dry end-to-end Service UI test completed 38 commands across
  V1-V8: every valve completed HOME, 90 degrees, and 180 degrees; 0 degrees
  completed for V1-V4 and V6-V8. The user physically confirmed that all eight
  valves operated as planned. One additional V6 180-degree request was
  terminally rejected as `INVALID_FIELD` before execution; another V6
  180-degree command had already completed, no outcome remained unknown, and
  no automatic retry occurred. Final journaled positions were V1, V2, and
  V4-V8 at 90 degrees and V3 at 180 degrees. Follow-up V6 and V8 180-to-90
  retests completed successfully. A second accidental V8 90-degree request was
  also rejected as `INVALID_FIELD` before execution; this led to the shared
  backend Serial concurrency correction recorded below.
- Branch: `codex/pump-service-ui`
- P1 and P2 Service cards now call the durable Arduino backend command API for
  explicit `HOME` and raw `MOVE_ABSOLUTE_STEPS` actions in the canonical
  `1..20500` range.
- Each action creates a fresh caller-owned phase/operation identity, requires
  an inline physical safe-route checkbox, locks its controls while pending,
  and reports only the terminal lifecycle result returned by the backend.
- Pump Service commands do not use browser confirmation popups and do not
  automatically retry unknown or failed outcomes.
- Volume, speed, relative-motion, calibration, and priming actions remain
  intentionally disabled pending their separate contracts and calibration.
- The user subsequently accepted a demo-only linear P1/P2 nominal mapping of
  raw `0 = 20 ml`, raw `20500 = 0 ml`, and `1025 steps/ml`. This preserves the
  confirmed physical direction: aspiration moves toward lower raw positions
  and dispense toward higher positions. Precise real-machine calibration,
  measured-volume claims, dead-volume compensation, and production working
  margins remain deferred. No volume command or hardware execution was added
  by this documentation checkpoint.
- The complete P1/P2 Service path was physically validated in a supervised dry
  test using the actual UI controls through backend intent handling,
  LABFORGE/1 Serial, production firmware, and Arduino GPIO: both pumps
  completed HOME followed by an absolute move to 2,000 steps on their manually
  confirmed Waste routes, all four UI operations reported success, and no
  impact, slipping, binding, or abnormal sound was observed. Machine motor
  power was then switched off explicitly.
- Minor deferred UI issue: after the safe-route checkbox enables a pump action,
  the enabled button does not change to a sufficiently distinct visual color.
  This did not prevent execution and is not part of the confirmed hardware
  behavior.
- SF bottom valve Service control calls the confirmed backend API with explicit
  `OPEN` and `CLOSED` actions, disables controls while motion is pending, and
  shows only backend-confirmed positions as confirmed.
- The live buttons execute directly without a browser popup, remain disabled
  while motion is pending, and other actuator controls remain disabled at this
  checkpoint.
- The Vite development server proxies `/api` to the local backend on
  `127.0.0.1:8000`.
- The live UI path was physically validated in supervised operation: `Open`
  moved the valve to its confirmed open position, `Close` returned it to the
  physically confirmed closed position without a browser popup, and the UI
  displayed the corresponding backend-confirmed state after each command.
- Active-route SVG rendering was optimized on branch
  `codex/ui-svg-render-performance` at commit
  `54152b83ece5b037122d9d0c307df4fe0a734df4`: the animated dash path no longer
  carries the expensive `drop-shadow`; a separate static glow path preserves
  the visual appearance without repeatedly repainting the filter.
- The user compared the optimized UI on the actual workstation and confirmed
  that opening it no longer increases the processor-fan speed. Closing the UI
  did not reduce the existing fan speed either, so the optimized screen was not
  producing a perceptible additional CPU/fan load during that observation.

### Backend

- The strict `/api/v1/service/sf-mixer/command` endpoint is implemented on
  branch `codex/sf-mixer-service-integration` at commit `c4a585e`. It maps only
  literal `START` / `STOP` to the exact durable
  `SF_MIXER_SET_STATE {"running":boolean}` contract, preserves identity and
  transport failures, and never retries an ambiguous physical command. The
  complete backend suite passes `1079/1079`. The supervised production-path
  test durably completed STOP -> START -> STOP without an error.
- The production Arduino command timeout is now `180 seconds`. A supervised
  assembled Column HOME reached and held the physical HOME switch but exceeded
  the intermediate `90-second` host deadline, producing `OUTCOME_UNKNOWN`.
  A follow-up test with motor power off and the HOME switch held active returned
  HTTP 200 and durably recorded `COMPLETED`, confirming D10 sensing and terminal
  lifecycle delivery. The firmware's 80,000 pulses at a minimum 1 ms interval
  imply at least 80 seconds rather than an 80-second upper bound, so the host
  now retains conservative wall-clock margin for the supervised demo. A
  regression test preserves that configured margin; focused tests passed
  `22/22`, the complete backend suite passed `1074` tests, and Ruff is clean.
- The production `DurableArduinoCommandExecutor` now owns a global nonblocking
  command/recovery lock around the complete journal/Serial/lifecycle
  transaction. A concurrent request fails with known `CONTROLLER_BUSY` before
  creating an intent or sending Serial bytes, preventing FastAPI worker threads
  from interleaving writes or lifecycle reads on the shared Serial client. A
  deterministic concurrency regression test holds the first fake Serial
  command active and proves the second performs no Serial call and creates no
  journal row. Focused Service/concurrency tests passed `36/36`, the complete
  backend suite passed `1073` tests, and Ruff is clean.
- Carousel Arduino Service integration is implemented on branch
  `codex/v1-v8-service-backend-ui`: the strict
  `/api/v1/service/carousel/command` boundary accepts caller-owned identities,
  positions `1..40`, and exactly `SET_REFERENCE` with literal manual-alignment
  confirmation or `MOVE_TO_POSITION` with literal Column-bottom-valve CLOSED
  confirmation. Only canonical `position` is sent to firmware. The existing
  firmware trusted-reference and trusted `CLOSED = 4 degrees` interlock remains
  authoritative, and unknown outcomes are never retried. Focused Service
  regression tests passed `24/24`, the complete backend suite passed `1072`
  tests, and Ruff is clean. No physical execution was performed in this phase.
- Column bottom valve Arduino Service integration is implemented on branch
  `codex/v1-v8-service-backend-ui`: the strict
  `/api/v1/service/column-bottom-valve/command` boundary accepts caller-owned
  identities and exactly `HOME` or `SET_POSITION` at `4` or `94` degrees; maps
  these to the canonical LABFORGE/1 column contracts with an empty HOME
  argument object; uses the existing durable command journal/Serial executor;
  preserves HTTP 409 identity conflicts and HTTP 503 unavailable/unknown
  outcomes; and never retries a physical command. Focused Service regression
  tests passed `17/17`, the complete backend suite passed `1065` tests, and
  Ruff is clean. No physical execution was performed in this phase.
- V1-V8 Arduino Service integration is implemented on branch
  `codex/v1-v8-service-backend-ui`: the strict
  `/api/v1/service/valves/command` boundary accepts caller-owned identities,
  `V1` through `V8`, and exactly `HOME` or `SET_POSITION` at `0`, `90`, or
  `180` degrees; maps them to the canonical LABFORGE/1 valve contracts; uses
  the existing durable command journal/Serial executor; preserves HTTP 409
  identity conflicts and HTTP 503 unavailable/unknown outcomes; and never
  retries a physical command. Focused tests passed `12/12`, the complete
  backend suite passed `1060` tests, and Ruff is clean. No physical execution
  was performed in this phase.
- Arduino Service integration checkpoint:
  - branch: `codex/arduino-serial-backend-integration`;
  - commits: `a2c78187e0741deb2971f830fd67dc8431071967`,
    `94a2c46` (`Wait for Mega reset before serial handshake`), and `8456841`
    (`Make Arduino journal thread safe`);
  - an explicitly configured production Serial runtime owns the Arduino
    session and a separate SQLite durable-command journal;
  - `/api/v1/service/pumps/command` accepts caller-owned command identities,
    P1/P2 `HOME` or absolute targets in `1..20500`, and a literal
    `safe_route_confirmed:true` boundary;
  - durable intent is persisted before first Serial transmission, identity
    conflicts fail with HTTP 409, unavailable/failed Serial execution fails
    with HTTP 503, and commands are never automatically retried; and
  - the runtime waits for the Mega USB-reset settling interval before HELLO,
    and the SQLite journal serializes access across FastAPI worker threads;
  - focused regression verification passed and the complete suite passed
    `1055` tests, with Ruff clean; and
  - P1 HOME/2,000 and P2 HOME/2,000 were physically completed through this
    backend path in supervised dry operation.

- SF bottom valve Dynamixel backend checkpoint:
  - branch: `codex/sf-bottom-valve-dynamixel-backend`;
  - commits: `9de415565eb9e8137c7bf7d885104f4f9c1ecb5f` and
    `e9b6144d390294030593508f28a1e101885dcb9d`;
  - confirmed XL430-W250-T/U2D2 adapter uses ID `2`, baud `57600`, Protocol
    `2.0`, `CLOSED=2559`, `OPEN=3697`, velocity `20`, acceleration `1`, and
    disables torque after every terminal outcome;
  - the runtime is enabled only by an explicit stable U2D2 path and exposes a
    narrow Service API for `OPEN`/`CLOSED` with confirmed-position success;
  - overlapping actuator commands are rejected; and
  - the production backend path was physically validated through
    `CLOSED -> OPEN -> CLOSED`, with all responses `200 OK` and the user
    confirming orderly movement and the final physically closed position.

- Branch: `codex/labforge-v1-message-models-parser-contract-fixes`
- HEAD: `7f8697c6b3ea02f1ff9450faa2d55149ace2f180`
- Working tree was clean when governance alignment started.
- LABFORGE/1 message models and parser contract fixes are pushed at this
  checkpoint.

### Firmware

- SF mixer production control is implemented on branch
  `codex/sf-mixer-service-integration` at commits `7de696f` and `da8f031`.
  Confirmed pins are STEP D6 and DIR D7; fixed DIR low produces clockwise
  rotation when viewed from the motor front. The sensorless demo profile is
  500 pulses/s with 20 us STEP HIGH, no catch-up bursts, explicit Start/Stop,
  and a firmware interlock against other Arduino actuator commands while
  running. Session replacement does not silently alter mixer output. The
  warning-clean native suite passes `193/193`; the Mega build uses
  `40,768 / 253,952` flash bytes and `3,140 / 8,192` static SRAM. Production
  firmware was uploaded and flash-verified, and the user physically confirmed
  the UI-to-hardware STOP -> START -> STOP test. Final mixer state is commanded
  stopped; RPM, mixing performance, and the required final impeller direction
  remain uncalibrated.
- Current V1-V8 software-integration checkpoint:
  - branch: `codex/v1-v8-production-runtime`
  - base reviewed commit: `e0644d5c2ec503ebb706723b04e0b7454a03a8ef`
    (`Integrate V1-V8 valve runtime`)
  - `VALVE_HOME` and `VALVE_SET_POSITION` are integrated for V1-V8 with
    confirmed STEP, DIR, HOME, polarity, direction, and 0/90/180-degree
    coordinate semantics from `HARDWARE_CONFIRMATIONS.md`;
  - every valve retains independent position trust, while P1, P2, and V1-V8
    share one global physical-command lifecycle owner;
  - HOME transitions use a 30 ms continuous-stability policy with STEP held
    inactive during resolution, bounded 20 us STEP HIGH pulses, and no
    catch-up pulse bursts;
  - request rejection and post-STARTED execution failures remain distinct;
  - the corrected checkpoint passes `144/144` native tests and the Mega build
    uses `34,210 / 253,952` flash bytes and `2,676 / 8,192` static SRAM bytes;
  - follow-up review corrections cover HOME candidate bounce, explicit valve
    failure behavior, and exact contract rejection behavior;
  - the no-LTO AVR stack analysis removed simultaneous double parsing and
    places the worst credible project path at approximately `3.8 KB`, leaving
    approximately `1.7 KB` after static data before interrupt/runtime margin;
  - firmware commit `c6a523440f4c187f092926db242d7b9e317d94a3` was uploaded
    and flash-verified on the Arduino Mega;
  - the production Serial/lifecycle path was physically validated first with
    V1 HOME and then with the complete V1-V8 cascade: each valve homed and
    moved to nominal 90 degrees, with a two-second dwell between valves;
  - every command completed with `ACCEPTED -> STARTED -> COMPLETED`, and the
    user confirmed correct HOME behavior, released switches at final 90-degree
    positions, and no impact, slipping, or abnormal sound; and
  - the 1,600-pulse missing-HOME software timeout is not established as
    mechanical protection. The user explicitly accepts missing-HOME overtravel
    only as a supervised-demo risk with the operator at the power switch;
    unattended and production operation remain out of scope.

- Current P2 software-integration checkpoint:
  - branch: `codex/p1-motion-safety-hardening`
  - commit: `e01d9084227d7180209c12d60ca4743db4465588`
    (`Integrate P2 pump runtime`)
  - the exact pump contracts now accept P1 and P2 while preserving the
    `1..20500` absolute target range;
  - P2 uses the confirmed D48 STEP, D49 DIR, and D44 HOME pins through an
    independent Arduino adapter and controller state;
  - P1 and P2 share the reviewed motion/lifecycle implementation but retain
    independent position trust;
  - only one pump command may execute globally at a time;
  - focused P2 contract/cache/runtime tests: `42/42 passed`;
  - complete warning-clean native suite: `123/123 passed`;
  - Mega 2560 build: successful;
  - flash: `31,300 / 253,952 bytes` (`12.3%`);
  - static RAM: `2,288 / 8,192 bytes` (`27.9%`);
  - verified firmware upload to the Arduino Mega completed successfully;
  - supervised `PUMP_HOME` physically confirmed correct movement and HOME stop;
  - HOME -> 5,000 steps -> two-second dwell -> HOME completed smoothly;
  - final HOME -> 2,000-step parking move completed smoothly; and
  - no impact, slipping, binding, leakage, abnormal noise, or other unusual
    event was observed before machine power was switched off.

- Current P1 runtime checkpoint:
  - branch: `codex/p1-motion-safety-hardening`
  - commit: `430f7534b4d554c81af39338280f5aa95835727a`
    (`Bound P1 step pulses and serial output`)
  - production Mega build connects the confirmed P1 STEP/DIR/HOME pins, the
    nonblocking controller, bounded Serial servicing, lifecycle output, and
    volatile command-status recovery;
  - each STEP pulse uses the confirmed bounded 20 us HIGH primitive and returns
    LOW before controller update returns;
  - Serial output is cooperatively handed to the AVR transport in fixed chunks,
    with motion servicing between chunks;
  - a complete `STARTED` frame must be handed to Serial before motion starts or
    the cache advances to `STARTED`;
  - reconnect preserves active motion, suppresses lifecycle frames tied to the
    replaced nonce, reports `BUSY`, and permits recovery through
    `QUERY_COMMAND`;
  - identity-untrusted physical commands fail closed;
  - focused P1 motion/runtime/transport tests: `36/36 passed`;
  - complete warning-clean native suite: `118/118 passed`;
  - warning-clean Mega 2560 build: successful;
  - flash: `30,816 / 253,952 bytes` (`12%`);
  - static RAM: `2,241 / 8,192 bytes` (`27%`);
  - refreshed no-LTO AVR stack analysis places the worst credible integrated
    parser/dispatch path at approximately `5.0 KB`, leaving approximately
    `0.9 KB` before interrupt/runtime margin; and
  - P1 was subsequently uploaded and physically validated through the
    production Serial/lifecycle path as recorded in
    `HARDWARE_CONFIRMATIONS.md`.

- Completed and pushed EEPROM bootstrap:
  - branch: `codex/labforge-v1-arduino-eeprom-identity-bootstrap`
  - commit: `cde95cae8860f8ef0b417d95b0b1ee3d1848031e`
- Completed and pushed handshake/session foundation:
  - branch: `codex/labforge-v1-handshake-session-foundation`
  - commit: `1a4f72668045bb63cb8411b6a12249fdd9aa6320`
- Completed and pushed status-query foundation:
  - branch: `codex/labforge-v1-status-query-foundation`
  - commit: `81bc8037c35edbfc6576a32daf93f8a753f62b49`
- Completed and pushed protocol-error/dispatch foundation:
  - branch: `codex/labforge-v1-protocol-error-dispatch-foundation`
  - commit: `2d793369ba4a91bb9fbbbcaf48de963fbc650af2`
- Completed and pushed command-status cache foundation:
  - branch: `codex/labforge-v1-command-status-cache-foundation`
  - commit: `ab6c1747f70ed99885fa2bcb38f4ee425cc7ac82`
- Completed and pushed command-lifecycle integrity foundation:
  - branch: `codex/labforge-v1-command-lifecycle-integrity-foundation`
  - commit: `99101b93f2d44c4e2e5722398653d665c9b031c1`
- Completed and pushed P1 absolute-step command contract:
  - branch: `codex/labforge-v1-p1-absolute-command-contract`
  - commit: `d0f295005f77da673cc4c0b8376f6b003cce08e5`
- Completed and pushed P1 command-boundary hardening:
  - branch: `codex/labforge-v1-p1-command-boundary-hardening`
  - commit: `52fa9188f91bc1e08036bb8d1f769e634b156f29`

The milestone sections below preserve the state recorded when each checkpoint
was completed. They are historical; the current firmware state is the P1
runtime checkpoint above.

## Handshake/session milestone

Implemented and pushed:

- trusted and untrusted deterministic `HELLO_OK` serialization;
- fixed-capacity volatile session state;
- nullable inbound `controller_boot_id` representation;
- stale-session and boot-ID validation foundation; and
- valid `HELLO` to `HELLO_OK` Serial integration without motion.

Latest verified results:

- focused handshake/session/writer and parser tests: `16/16 passed`;
- focused boot-identity tests: `12/12 passed`;
- complete native suite: `41/41 passed`;
- warning-enabled native suite: `41/41 passed`;
- Mega 2560 build: successful;
- flash: `17,302 / 253,952 bytes`;
- static RAM: `1,231 / 8,192 bytes`; and
- `git diff --check`: passed.

Independent review identified unnecessary AVR SRAM use in the writer format
strings. The final implementation stores those constant strings in flash and
retains:

- global `helloOkFrame`: `256` bytes;
- `SessionState`: `38` bytes.

The optimization reduced static RAM from `1,609` to `1,231` bytes (`378` bytes
recovered) without changing flash usage or byte-exact `HELLO_OK` output.

## Status-query milestone

The status-query foundation now implements:

- session and boot-ID validation for `QUERY_STATUS`;
- byte-exact trusted and untrusted `STATUS` serialization;
- echoed session nonce and request ID;
- `PROTOCOL_ONLY` or `IDENTITY_UNTRUSTED` software state;
- `active_operation_command_id:null`; and
- no command dispatch, pin access, or physical behavior.

Latest verified results:

- focused status-query tests: `3/3 passed`;
- complete native suite: `44/44 passed`;
- warning-enabled native suite: `44/44 passed`;
- Mega 2560 build: successful;
- flash: `17,984 / 253,952 bytes`;
- static RAM: `1,295 / 8,192 bytes`; and
- `git diff --check`: passed.

## Protocol-error/dispatch milestone

The protocol-error/dispatch foundation now implements:

- a small testable no-motion dispatch path from parsed frame to one response or
  intentional no response;
- bounded deterministic `PROTOCOL_ERROR` serialization;
- safe query or command correlation for recoverable schema errors;
- uncorrelated malformed and oversized errors;
- correlated `QUERY_STATUS` session and boot-identity errors;
- transactional writer failure with no partial Serial output; and
- at most one selected response per received frame.

Latest verified results:

- focused protocol-error/dispatch tests: `7/7 passed`;
- complete native suite: `51/51 passed`;
- warning-enabled native suite: `51/51 passed`;
- Mega 2560 build: successful;
- flash: `20,682 / 253,952 bytes`;
- static RAM: `1,359 / 8,192 bytes`; and
- `git diff --check`: passed.

An AVR `-fstack-usage` analysis without LTO estimated the deepest current
parser/dispatch path at approximately `3.3–3.6 KB`, including parser, JSON
document, and validator calls. This is acceptable for the current no-motion
shell but must be reassessed before command-cache growth and actuator work.

## Command-status cache milestone

The command-status cache foundation now implements:

- valid session-bound `QUERY_COMMAND` / `COMMAND_STATUS` responses;
- a two-entry volatile per-boot cache with at most one non-terminal entry;
- deterministic oldest-terminal eviction;
- read-only query behavior and `UNKNOWN` for absent or evicted IDs;
- mandatory serialization for all six command states, without optional message
  or result payloads; and
- no incoming `COMMAND` acceptance, lifecycle progression, duplicate-command
  identity comparison, dispatch, or physical behavior.

Latest verified results:

- focused command-status and protocol-error/dispatch tests: `16/16 passed`;
- complete native suite: `60/60 passed`;
- warning-enabled native suite: `60/60 passed`;
- Mega 2560 build: successful;
- flash: `22,286 / 253,952 bytes`;
- static RAM: `1,665 / 8,192 bytes`; and
- `git diff --check`: passed.

AVR memory details:

- `CommandStatusEntry`: `111` bytes;
- `CommandStatusCache`: `226` bytes;
- shared output buffer: `464` bytes;
- maximum implemented mandatory `COMMAND_STATUS`: `443` bytes including LF;
- deepest estimated parser/dispatch stack path: approximately `3.3–3.6 KB`;
- command-status writer path: approximately `1.7 KB`; and
- nominal SRAM remaining after static use plus the conservative deepest stack
  estimate: approximately `2.9 KB` before interrupt/runtime margin.

## Command-lifecycle integrity milestone

The command-lifecycle integrity foundation now adds:

- strict `ACCEPTED -> STARTED -> COMPLETED` lifecycle ordering;
- idempotent exact replay without insertion-sequence changes;
- immutable terminal states and phase identity;
- canonical lowercase UUID and safe phase-ID validation;
- rejection of invalid enum values and invalid cached identifiers; and
- structural recognition of both valid `FAILED` boundaries, while actual
  `FAILED` storage remains blocked until execution-failure error codes are
  explicitly defined and reviewed.

At this historical checkpoint the production runtime did not yet call
`CommandStatusCache::store()`. The current P1 runtime now stores lifecycle
states, and deliberate post-`STARTED` abort uses the distinct
`COMMAND_ABORTED` execution-failure code.

Latest verified results:

- focused command-lifecycle tests: `11/11 passed`;
- complete native suite: `63/63 passed`;
- warning-enabled native suite: `63/63 passed`;
- Mega 2560 build: successful;
- flash: `22,286 / 253,952 bytes`;
- static RAM: `1,665 / 8,192 bytes`; and
- `git diff --check`: passed.

The memory measurements and conservative stack estimate from the preceding
command-status checkpoint are unchanged. The next step is independent review
of this checkpoint before selecting the first actual command contract or any
Service-layer actuator boundary. Incoming `COMMAND` handling, duplicate-command
identity comparison, dispatch, and physical behavior remain unimplemented.

## P1 absolute-step contract milestone

The first approved Service-mode contract is now implemented as a no-motion
foundation:

- exact `PUMP_MOVE_ABSOLUTE_STEPS` schema, restricted to `P1`;
- exactly `pump:"P1"` and integer `target_steps` in `1..20500`;
- compact exact semantic duplicate identity without hash-only comparison;
- testable `ACCEPTED -> STARTED -> COMPLETED/FAILED` Service lifecycle using a
  fake executor; and
- precise `PUMP_MOTION_TIMEOUT` and `PUMP_HOME_SWITCH_UNEXPECTED` execution
  failure codes.

Production `main.cpp` and `NoMotionDispatcher` remain unchanged. The Service
is not connected to Serial, pins, a motor driver, or physical behavior, and the
real `QUERY_COMMAND` path can still return only `UNKNOWN`.

Latest verified results:

- focused P1 contract tests: `5/5 passed`;
- complete native suite: `68/68 passed`;
- warning-enabled native suite: `68/68 passed`;
- Mega 2560 build: successful;
- flash: `22,358 / 253,952 bytes`;
- static RAM: `1,675 / 8,192 bytes`; and
- `git diff --check`: passed.

Compared with the preceding checkpoint, this adds 72 bytes of flash and 10
bytes of static RAM. The next boundary is independent review, followed by
confirmation of P1 pins, home-switch electrical semantics, tested pulse timing,
`ENA` behavior, initial trusted-position policy, and the safe manually prepared
fluidic route before any production adapter, upload, or physical test.

The user explicitly approved `PUMP_MOVE_ABSOLUTE_STEPS` as the first no-motion
Service-mode contract before this implementation was created. That approval
does not authorize production Serial integration, an actuator adapter, upload,
or physical execution.

## Latest firmware milestone

The no-motion P1 command boundary is now hardened with:

- disjoint request-rejection and execution-failure error categories;
- detailed cache-store outcomes so only a real non-terminal conflict maps to
  `CONTROLLER_BUSY`;
- side-effect-free preflight before `ACCEPTED` and `STARTED`;
- explicit handling of every declared executor outcome and fail-closed handling
  of an invalid outcome without inventing a physical cause;
- `PUMP_HOME_SWITCH_UNEXPECTED` restricted to unexpected activation after the
  physical execution boundary; and
- `0..20500` documented as a representable coordinate envelope, not a validated
  safe physical working range.

Latest verified results:

- focused cache and P1 boundary tests: `20/20 passed`;
- complete native suite: `72/72 passed`;
- warning-enabled native suite: `72/72 passed`;
- Mega 2560 build: successful;
- flash: `22,358 / 253,952 bytes`;
- static RAM: `1,675 / 8,192 bytes`; and
- `git diff --check`: passed.

Flash, SRAM, cache sizes, output capacity, and the production stack path are
unchanged from the preceding contract checkpoint. Production `main.cpp` and
`NoMotionDispatcher` remain unchanged and disconnected from the Service.

## Approved phase and next phase boundary

The user approved the focused P1 Arduino GPIO and production Serial/lifecycle
software integration. That checkpoint is implemented and reviewed in software.
No firmware upload, Serial Monitor use, physical P1 execution, PR, or merge to
`main` is authorized by that approval. The next boundary is an explicit
physical integration/test authorization or a separately scoped software
checkpoint for another actuator.

The later supervised-demo checkpoints supersede that historical boundary:
P1/P2, V1-V8, the column-bottom valve, the carousel, SF mixer, and the separate
SF-bottom DYNAMIXEL path have production software checkpoints, with the
physically executed confirmations recorded above and in firmware
`HARDWARE_CONFIRMATIONS.md`. The immediate next phase is the supervised dry
demo sequence and its remaining orchestration/UI integration. Wet-route
testing, precise pump-volume calibration, SF mixer RPM/performance calibration,
and full Guided Demo orchestration remain later phases.

## Current limitations and unresolved physical decisions

- P1/P2, V1-V8, Column bottom valve, carousel, and SF mixer are integrated in
  the production Mega runtime. Reactor mixer is not connected or integrated.
- SF mixer control has no speed input or rotation feedback. The fixed
  500-pulse/s dry-demo profile and clockwise observed direction are not a
  calibrated RPM or validated final mixing direction.
- EEPROM fail-closed recovery/provisioning remains unresolved.
- Unconfirmed pin, polarity, direction, angle, step, calibration, homing, and
  safe-route decisions must be obtained from the user and canonical hardware
  documentation.

## Governance alignment work

Governance alignment is pushed on `codex/align-development-governance` in the
UI, backend, and firmware repositories. No PR or merge has been performed.
