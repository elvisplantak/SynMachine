# Consolidated owned application/UI review — 2026-10-03

Review the final connected software task. The user deferred independent review
while the reviewer was unavailable and authorized autonomous software integration.
Do not infer authorization for production activation, real ports/motion, database
migrations, firmware changes, main merges or firmware recovery artifacts.

## Pinned scope

- Backend repository: `elvisplantak/labforge-backend`, branch
  `codex/owned-application-execution`, commit
  `37d5b1611ae148c8ec52a5a66ecf7ffb266fc231`, base
  `e84ea97e177ff23be8d043e9b79be27a7a75e3a5`.
- UI repository: `elvisplantak/labforge-ui`, same branch. Review the implementation
  commit containing this file; it is based on
  `e72db554f427a67ff9e0d77665863051ca3526ac`. Use the full UI HEAD supplied with the
  checkpoint report, rather than an unrelated default branch.
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

Stop bypasses the worker queue, including early/between-phase requests. Stop
persistence failure blocks next primary work without suppressing required cleanup.
Pause/Resume use existing started wait intents. Domain-only completion requests
are blocked in this composition. Shutdown requests orderly Stop before joining.

Standalone flush and Service-fault recovery can have null run identity. Explicit
machine-only interruption metadata and new maintenance identities use existing
JSON payloads, with no SQL migration. Startup metadata reconciliation never
replays a command or frees retained ownership. Recovery success still requires
deliberate mandatory flushing before READY/release/new run.

The UI reads actual persisted phases/events, distinguishes acceptance/completion,
locks configuration while executing, and sends no automatic command retries.
SF mixing seconds, settling and fraction settings are explicit. Maintenance
readiness statements are refreshed per attempt. Existing frontend preview remains
separate; no global topology/layout redesign was performed.

## Evidence and review focus

- Backend: all 1758 tests pass (92.90 s), including 40 new cases; 349 focused
  connected cases pass (40.38 s). Ruff and staged/working diff checks pass.
  Change: 18 files, +1605/-51 lines.
- UI: 12 API contract tests, lint and build pass; JS 303.08 kB (83.59 kB gzip),
  CSS 49.57 kB (9.82 kB gzip). Browser visual/click testing was not available.
- Real Serial/DYNAMIXEL adapter implementations execute over fake ports/sessions
  in tests. Test-only routes/calibrations are not physical commissioning values.
- Main sources: backend `app/hardware/owned_application_execution.py`,
  `owned_offline_runtime.py`, `owned_phase_session.py`, `owned_maintenance.py`,
  `simulated_lifecycle.py`, `app/main.py`, `tests/test_owned_application_api.py`;
  UI `src/OwnedDemoControls.tsx`, `src/guidedDemoApi.ts`, their API tests and the
  narrow `src/App.tsx` integration. Backend technical detail:
  `docs/OWNED_APPLICATION_EXECUTION.md`.

Please focus on out-of-queue Stop races and persistence failures, shared Service
exclusion, teardown/restart without replay, null-run maintenance scope, mandatory
flush/release ordering, and UI acceptance/stale-read/error behavior. Assess findings
independently against this explicit candidate's boundaries.

Production wiring, authentication, persistent SF physical trust, real safe-route
verification, wet calibration and commissioning remain unfinished gated phases.
Supplied input is not proof of physical state. Cross-database commits remain
non-atomic. Advisory locks do not govern unwrapped adapters/arbitrary writers.
