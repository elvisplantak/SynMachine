# Fresh operator current-input integration — independent review

Date: 2026-10-06. Independent review accepted the exact implementation HEADs
below for the declared fake-only software scope. Critical: 0; High: 0;
Medium: 0; Low: 0. Codex checked the key conclusions against source and agrees;
no software correction is needed. The original review scope/questions are
retained below; the closure records the returned outcome.

## Exact pinned scope

- Branch in both repositories: `codex/operator-current-input`.
- Backend: https://github.com/elvisplantak/labforge-backend
- Backend review HEAD: `1c0e906ac2ad440ea741032192c29a67ab771739`
- Backend accepted base: `36d6046a10361bf7bdb5db7f440075573e9d2b41`
- Backend comparison: https://github.com/elvisplantak/labforge-backend/compare/36d6046a10361bf7bdb5db7f440075573e9d2b41...1c0e906ac2ad440ea741032192c29a67ab771739
- UI: https://github.com/elvisplantak/labforge-ui
- UI implementation review HEAD: `7e36cf7b6518c08c514aa2e151b18f31ac888cb3`
- UI base: `b2f00dfe8bf3a9a92ef09f71b174a14392576a70`
- UI comparison: https://github.com/elvisplantak/labforge-ui/compare/b2f00dfe8bf3a9a92ef09f71b174a14392576a70...7e36cf7b6518c08c514aa2e151b18f31ac888cb3
- Subsequent UI checkpoint commit adds documentation only. Review the pinned
  implementation commits above; do not substitute another branch or old HEAD.

## Authorization, result and limits

The user approved concrete operator current input through the existing UI and
preparation of a physical profile without guessing missing facts. The user also
explicitly reapproved additional UI regression/final checks after an accidental
workspace-write rejection. No real devices/ports, physical tests, production,
EEPROM, firmware upload or main merge were authorized/performed; animation deferred.

The bounded callback, existing owned worker/owner/journals and configured session
provider remain the path. GET execution status exposes a pending request; two
explicit POSTs submit/cancel it. The server authenticates a configured operator
credential, stamps identity/time, and preserves exact request/session/deadline
checks. Credentials attribute declarations only; they do not authenticate general
execution/Service APIs or physical truth. There is no production entry point,
default live credential, new diagnostic layer, dependency or SQL schema migration.

Initial READY and first Start need separate fresh requests. Unknown/partial RUN
input blocks before RUNNING/commands; explicit retry keeps CREATED identity.
Recovery needs fresh stopped Reactor/manual carousel and existing per-attempt
readiness while other references may remain unknown. Mandatory flush retains
ownership through durable READY/release. Old/foreign/late/duplicate input cannot
fall back to prior references. Stop/Cancel/timeout/shutdown unblock the callback.
Restart retains journals/owner but drops requests; old fake credentials are rejected.

UI form defaults/consent are empty per request, secrets are cleared before sends,
and restoration is GET-only. Historical receipt metadata stays in plan assumptions
without secrets; it cannot grant current readiness. Existing canonical schema-1
records remain readable without migration/rewrite or weakened digest/derivation checks.
The JSON physical worksheet remains non-activatable. HOME 0/max 20500 and nominal
1025 steps/ml plus dated dry Waste setups are retained; working margins explicitly
"jos nije potvrdjeno" and full route-transition confirmation remains missing.

## Verification and focus

- Backend: **1858 passed in 111.43 s**, Ruff/diff checks pass. Delta 16 files +1100/-25.
- UI: **26 passed**, 15 API +11 isolated fake-API browser, zero skipped; lint/build/diff
  checks pass. Application delta six files +316/-3. JS 313.51 kB /86.31 kB gzip,
  CSS 50.08 kB /9.94 kB gzip. No firmware change/resource impact.
- New source/HTTP tests cover authentication, one-use binding, Stop/close races,
  late/partial input, original-run retry, initialization shutdown and restart/
  retained owner/recovery/mandatory flush/new run. Compatibility tests preserve
  old canonical bytes and reject noncanonical modified records.
- UI tests cover actual forms, credential clearing, request remount/consent,
  unknown recovery input, expiration/cancellation, RUN retry and no automatic replay.
- Optional browser launcher uses real adapters over hardwired fake transports;
  manual user verification of this new panel is pending. No live calibration approval.

Inspect `operator_current_input.py`, its integration diffs, prepared-plan optional
attribution, `OperatorCurrentInput.tsx`, API/control diffs and focused tests.

1. Can any timeout/Stop/close/restart/race consume stale input or send commands
   before existing readiness/session/owner checks, including initialization?
2. Can input receipt or restoration promote historical references, release
   ownership early, bypass mandatory flush or automatically resend work?
3. Are credential scope, server attribution, UI clearing and strict payload
   validation accurate without claiming general authentication or physical proof?
4. Is canonical legacy plan compatibility preserved with full integrity, and are
   known physical records versus missing live inputs represented accurately?

Report findings by severity with source/trigger and requested correction, or
accept the exact pinned implementations for this declared fake-only software scope.


## Review closure — 2026-10-06

The independently accepted implementation checkpoints are:

- Backend: `1c0e906ac2ad440ea741032192c29a67ab771739`.
- UI: `7e36cf7b6518c08c514aa2e151b18f31ac888cb3`.

Critical/High/Medium/Low findings are all zero. The reviewer accepted fresh
request/session/deadline binding, rejection of stale input, explicit CREATED-run
retry, bounded cancellation including response-before-consumption races,
restart invalidation, retained ownership through Recovery and mandatory Flush,
historical-only attribution, canonical legacy-plan compatibility and fresh UI
forms without automatic replay. Codex independently checked the key conclusions
against the implementation and agrees; no code correction is required.

The declaration credential authenticates only `OperatorCurrentInput`. It does
not authenticate `MaintenanceReadiness` or general execution/Service APIs.
Complete operator/network/API authentication and credential provisioning remain
separate production integration decisions; this is not a defect in this scope.

The 1858 backend and 26 UI passing-test results and other checks above were
reported by the implementation session. The reviewer did not independently rerun
commands through the GitHub connector; no GitHub combined status checks were
present on the reviewed HEADs. Documentation-only closure does not change the
accepted implementation or its verification evidence.

The physical worksheet remains incomplete and non-activatable. The next
substantive boundary is a physically approved configuration/profile and a
concrete method for acquiring real current references. Manual fake-browser
verification of the new operator panel remains pending. Acceptance does not
authorize live ports/devices, physical HOME/Recovery/Flush, liquid testing,
production activation, firmware upload, EEPROM operations or merging to main.
