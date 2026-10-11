# Focused independent review — commanded-flow animation

Please respond in Croatian/BHS. Review these pinned feature commits; this is a
new self-verified checkpoint, not an extension of the prior UVP acceptance.

| Repository | Branch | Code commit | Base |
| --- | --- | --- | --- |
| [backend](https://github.com/elvisplantak/labforge-backend) | codex/execution-flow-animation | [5c99e190e70c234507f3cf44abd66beca0354bd2](https://github.com/elvisplantak/labforge-backend/commit/5c99e190e70c234507f3cf44abd66beca0354bd2) | 8e22fd5d305d46d128f0aedc78bf2a0e36be8fa2 |
| [UI](https://github.com/elvisplantak/labforge-ui) | codex/execution-flow-animation | [5bc4aaf2c7664f8f38afe0cb5dc7a80c328ad03d](https://github.com/elvisplantak/labforge-ui/commit/5bc4aaf2c7664f8f38afe0cb5dc7a80c328ad03d) | 7edfed0c300218f589bdb108d6d4f1cdc8b2920e |

The user explicitly authorized command-driven traveling dashes after UVP, in
backend Guided Demo and Recipes, representing execution rather than sensor flow.
No wet check, real connection, motion, upload, production activation or main merge
was authorized or performed. Recipe definitions and current browser fixture state
were preserved, not reset or edited to obtain a successful test.

Backend adds optional/null `flow_activity` to existing GET `/execution`, from an
immutable ephemeral snapshot guarded by a separate short lock. Each pump action
uses its prepared kind and preceding symbolic SELECT_ROUTE; collection is only
the protected dwell after successful OPEN. Scope includes intent persistence,
dispatch and awaiting a result; it deliberately does NOT assert STARTED telemetry
or sensed fluid movement. The scope clears on every exit before follow-up.
Maintenance expansion, HOME, Service and non-transfer waits have no activity.
No protocol, command plan/journal schema, safety policy or ownership change.

UI extracts the existing schematic for reuse, preserves every coordinate,
selects direction per existing path and draws symbolic active valve links with
neutral inactive valves. It polls only GET status about every 200 ms, with 1 s
read deadline and 1.5 s freshness bound, rejects late/malformed/foreign responses,
and stays static for an older backend. Commands shorter than sampling may be
missed, never replayed for visual effect. Fill levels are schematic. Existing
frontend-only preview remains a preview. Reduced-motion preference is honored.

Evidence: full backend **1920 passed**, focused flow **17 passed**; UI **49 passed**,
including **23 actual headless browser cases**, zero skips. Ruff, UI lint,
TypeScript/Vite build and diff checks pass. JS335.10kB/gzip91.94, CSS53.04/gzip10.58.
A rendered fake-only Guided Demo screenshot was inspected. Local browser backend
was gracefully restarted only after idle/owner checks, using its same marked
state with existing --command-delay 1; recipe library compared exactly unchanged.

Review focus:

1. Does scoped display evidence preserve ownership, intent-before-bytes, atomic
   Stop, protected SF CLOSE/Column CLOSE, failure/restart and no-replay behavior?
   Backend: app/hardware/execution_flow.py, owned_transfer_runner.py,
   owned_application_execution.py; tests/test_execution_flow.py.
2. Are separate aspiration/dispense/collection routes and SVG directions correct,
   without phase-derived or history-derived movement/physical-state claims?
   UI: src/executionFlow.ts, FluidicScheme.tsx, ExecutionFlowView.tsx.
3. Do optional status parsing, freshness/timeout/late-response handling and
   read-only navigation fail static without enabling an actuator action?
   UI: src/guidedDemoApi.ts; tests/execution-flow.test.mjs and fixture.html.

Classify any findings by severity and identify the exact pinned source. Passing
software tests do not establish wet performance or physical authorization.

## Independent outcome and narrow UI follow-up

Review of the pinned commits above (plus documentation-only UI 0125ceb) reported
Critical 0, High 0, Medium 0, Low 1. Backend 5c99e190 is accepted for fake-only
observational scope; combined acceptance is pending one display-only correction.
Reported local test commands were not independently rerun by the reviewer.

The Low finding is valid: SF_BOTTOM_TO_P2 must use sf-v8 reverse because the
existing SVG path `M 650 -130 L 650 -105` begins at V8.k2 and ends toward the SF
outlet. The narrow follow-up changes only that mapping and focused tests. Unit
coverage checks the complete four-segment direction map; fake browser coverage
checks all four rendered segment attributes and computed CSS directions in both
Guided Demo and Recipes. No SVG geometry, other routes, backend, firmware,
ownership, journals or command behavior changed.

Follow-up evidence: focused flow unit tests 3 passed; full UI 49 passed including
23 actual headless-browser cases, zero skips; lint, TypeScript/Vite build and
`git diff --check` passed. JS335.10kB/gzip91.95, CSS53.04/gzip10.58.
The correction's pinned commit is supplied in the conversational handoff; these
notes belong to that same commit. This follow-up is self-verified, not yet
independently accepted. Please focus closure on the mapping and regression diff
against UI 0125ceb; the accepted backend requires no correction or rereview.
