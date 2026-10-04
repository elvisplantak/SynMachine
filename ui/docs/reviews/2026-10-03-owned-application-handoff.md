# Consolidated owned application/UI review — 2026-10-03

Review the final connected software task. The user deferred independent review
while the reviewer was unavailable and authorized autonomous software integration.
Do not infer authorization for production activation, real ports/motion, database
migrations, firmware changes, main merges or firmware recovery artifacts.

## Pinned scope

- Backend repository: `elvisplantak/labforge-backend`, branch
  `codex/browser-check-profile`, commit
  `e47d2acf777a96a09fde763c4d8cb5f6c8fa5139`, base
  `e84ea97e177ff23be8d043e9b79be27a7a75e3a5`.
- UI repository: `elvisplantak/labforge-ui`, same branch. UI implementation commit
  `a68c0a79e61ec4992a20eb11c5995633374e9e15`, including status/request message
  clarification and guidance for repeating recovery after restart. The connected
  UI implementation is based on
  `e72db554f427a67ff9e0d77665863051ca3526ac`. Use the full UI HEAD supplied with the
  checkpoint report, rather than an unrelated default branch. Adapter-resource
  backend delta is `37d5b16..3d4298f`; browser profile delta is
  `3d4298f..e47d2ac`. The full review includes all three slices.
- Last independently accepted backend base remains `3d9fab24`. Prior integration
  and targeted STATUS freshness correction are not newly marked accepted here.
  Prior packets are `2026-10-03-owned-recovery-flush-handoff.md` and
  `2026-10-03-status-request-freshness-followup.md` in this directory.

## Result and boundaries

`OwnedApplicationExecution` connects explicit FastAPI injection and the Guided
Demo UI to the existing runtime, runner, shared owner, plan store and journals.
One worker owns execution and writable handles. Service calls share the same
hardware exclusion. Run/maintenance acceptance is asynchronous. Separate validated
read-only handles provide snapshots/events. No new diagnostic or transport layer
is introduced; default environment startup remains unactivated for this candidate.

The subsequent explicit `build_adapter_application_execution` composes adapter
resource lifetime. Construction opens nothing. Deferred factory invocation follows
bundle lock/schema/identity checks, so a second runtime cannot open its transport.
Explicit startup establishes only a Serial handshake before obtaining independent
current-context input. Failure and shutdown close the connection on the worker;
shutdown requests Stop and waits before adapter teardown. No implicit actuator
command or release occurs. Existing caller-owned fixture lifetime remains supported.

Stop bypasses the worker queue, including early/between-phase requests. Stop
persistence failure blocks next primary work without suppressing required cleanup.
Pause/Resume use existing started wait intents. Domain-only completion requests
are blocked in this composition. Shutdown requests orderly Stop before joining.

Standalone flush and Service-fault recovery can have null run identity. Explicit
machine-only interruption metadata and new maintenance identities use existing
JSON payloads, with no SQL migration. Startup metadata reconciliation never
replays a command or frees retained ownership. Recovery success still requires
deliberate mandatory flushing before READY/release/new run.

Restart between recovery and flushing deliberately invalidates execution session
continuity, even when persisted FLUSH_REQUIRED/ownership remain. Fresh recovery
is required in the new process before flush; no historical diagnostic snapshot
is promoted into device trust. READY/release/new-run permission after successful
flush remain durable. The browser-profile regression now covers both restarts,
rejecting a flush without fresh continuity before any new command is journaled.

The UI reads actual persisted phases/events, distinguishes acceptance/completion,
locks configuration while executing, and sends no automatic command retries.
SF mixing seconds, settling and fraction settings are explicit. Maintenance
readiness statements are refreshed per attempt. Existing frontend preview remains
separate; no global topology/layout redesign was performed.

## Evidence and review focus

- Backend: all 1782 tests pass (100.39 s), including 64 cases above the full-review
  base. Browser-profile delta adds 10 cases; 47 focused browser/maintenance cases
  pass (19.97 s), including extended recovery/release restart coverage.
  Adapter-resource delta adds 14 cases; 80 focused connected cases pass
  (27.67 s). Prior application slice passed 349 focused cases (40.38 s).
  Ruff and staged/working diff checks pass. Application slice: 18 files,
  +1605/-51 lines; adapter-resource delta: 5 files, +406/-12 lines;
  browser-profile delta: 3 files, +416 lines. Latest browser-results/regression
  checkpoint: 2 files, +55/-4; UI text delta: 1 file, +6/-2.
- UI: 12 API contract tests, lint and build pass; JS 303.36 kB (83.67 kB gzip),
  CSS 49.57 kB (9.82 kB gzip). Request responses are now labeled as historical
  requests, the initial reading message clears on connection, and recovery-before-
  flush after restart is explained. Button policy/backend safety are unchanged.
- Real Serial/DYNAMIXEL adapter implementations execute over fake ports/sessions
  in tests. Test-only routes/calibrations are not physical commissioning values.
- Development-only `tests/browser_check.py` exposes the same existing HTTP
  execution path for user-led browser checks. It hardwires fake transports,
  refuses live-port environment settings before import and retains a marked
  temporary bundle across restarts without resetting evidence. Real wall-clock
  waits and optional fake transport failure support control/recovery scenarios.
  Actual CLI startup, HTTP snapshot and orderly shutdown passed. User-led browser
  checks on 2026-10-04 confirmed initialization, run Pause/Resume/completion,
  clean Stop/flush, injected failure, recovery after restart, repeat recovery
  after a restart before flushing, and a completed new run after flush/release
  and another restart. Same temporary bundle throughout; screenshots and read-only
  HTTP state corroborate the results. Backend `docs/BROWSER_CHECK.md` records
  settings and boundaries. Hard process death, Service contention, Stop during
  flushing and page reload were not manually tested in this session. The final
  small UI text delta passed lint/build; user screenshots preceded that delta.
- Main sources: backend `app/hardware/owned_application_execution.py`,
  `app/hardware/adapter_application.py`, `tests/test_adapter_application.py`,
  `owned_offline_runtime.py`, `owned_phase_session.py`, `owned_maintenance.py`,
  `simulated_lifecycle.py`, `app/main.py`, `tests/test_owned_application_api.py`;
  UI `src/OwnedDemoControls.tsx`, `src/guidedDemoApi.ts`, their API tests and the
  narrow `src/App.tsx` integration. Backend technical detail:
  `docs/OWNED_APPLICATION_EXECUTION.md`.

Please focus on out-of-queue Stop races and persistence failures, shared Service
exclusion, teardown/restart without replay, null-run maintenance scope, mandatory
flush/release ordering, device-factory ordering/resource failure cleanup, context
binding without inferred trust, and UI acceptance/stale-read/error behavior. Assess findings
independently against this explicit candidate's boundaries.

Production activation/configuration, authentication, persistent SF physical trust, real safe-route
verification, wet calibration and commissioning remain unfinished gated phases.
Supplied input is not proof of physical state. Cross-database commits remain
non-atomic. Advisory locks do not govern unwrapped adapters/arbitrary writers.
