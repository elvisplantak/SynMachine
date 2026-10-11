# UVP focused review follow-up — 2026-10-11

## Independent review closure — accepted

The user's supplied focused follow-up review independently accepted the complete
UVP milestone for its declared fake-only software scope, closed both former Medium
findings, and reported Critical 0, High 0, Medium 0, Low 0. No further software
correction was requested. Codex checked that the response names the implemented
fixes and these exact reviewed checkpoints:

- Backend: `8e22fd5d305d46d128f0aedc78bf2a0e36be8fa2`.
- UI: `bf986cbb983b4d664070c6474627a62074d9584a`.
- Both feature branches: `codex/uvp-recipes`.

The reviewer inspected the focused diffs, integration code and regressions.
Implementation-reported verification (1903 backend, 45 focused UVP, 41 UI with
18 browser cases and zero skips, Ruff/lint/build/diff checks) was not independently
rerun through the GitHub connector; no combined GitHub checks were present.
This closure is documentation-only and does not create another accepted code HEAD.

Acceptance does not authorize real-device/Serial activation, physical movement,
HOME/Recovery/Flush, wet testing, firmware changes/upload, production activation
or merging to main. Firmware recovery/ remains prohibited. The next integration
or physical/profile boundary retains the existing approval requirements.

## Original submitted follow-up packet

The packet below records its status at submission; its pending acceptance wording
is superseded by the closure above. Its UI target is now pinned to
`bf986cbb983b4d664070c6474627a62074d9584a`.

Please respond in Croatian/BHS. Independently review only the two targeted
corrections from the consolidated review (Critical 0, High 0, Medium 2, Low 0).
The reviewed UVP milestone is NOT YET ACCEPTED; implementation verification does
not imply independent acceptance. Recommendations remain advisory.

## Pinned scope

- Backend: https://github.com/elvisplantak/labforge-backend
  branch `codex/uvp-recipes`, follow-up HEAD
  `8e22fd5d305d46d128f0aedc78bf2a0e36be8fa2`, reviewed base
  `e6260970b57c187c1bbe7ff0b09548f93ef9e5c0`.
- UI: https://github.com/elvisplantak/labforge-ui
  branch `codex/uvp-recipes`, reviewed base
  `6a880de7fb554f7d0653793a2fb60b9c74762120`.
  Follow-up target is the commit containing this packet; the implementation
  agent's final report supplies its exact full HEAD. Pin that HEAD after fetching.
- Original milestone baselines: backend
  `90e136cc3a8d26b6b212ad3b14a1f739caeb24fd`, UI
  `881e5bf77c7a5d3a425719a69e4d10160fcd78be`.
- Firmware unchanged `3cc2de2fe69ff4990dccc003f7baa2adb446ff7f`; installed e2e9d3c.
  No production activation, hardware execution, firmware upload or main merge.
  Never access firmware recovery/. All tests use fake transports/API only.

## Medium 1 — configured COLLECT path

`build_adapter_application_execution` now passes its validated typed
AdapterCurrentContextProvider into OwnedApplicationExecution. Recipe creation
permits pending live readiness when this configured source exists, rather than
rejecting solely because static column_readiness is None. No hardcoded readiness
is supplied. Existing acquire(RUN) still requires complete known fresh references
before COMMAND; OwnedPhaseSession derives collection readiness from that context.
A static composition with neither readiness nor live source remains blocked.

Preview separates calibration checks from collection readiness: NOT_REQUIRED,
STATIC_CONFIRMED, FRESH_INPUT_REQUIRED or UNAVAILABLE. The UI explains pending
live references and blocks UNAVAILABLE regardless of calibration status.

The regression uses the actual configured builder, fake serial/SF transports and
secured operator input: save complete 10-step recipe ending COLLECT -> preview ->
execute -> fresh initialization input -> distinct fresh RUN input -> all phases
including existing protected SF/column collection -> COMPLETED. Before either
input, serial has HELLO only and SF has no sessions. Missing Column, carousel or
both after successful initialization sends zero COMMAND, leaves recipe CREATED
at index zero and rejects replay of the consumed challenge. Existing static-source
rejection, cancellation, Stop and fault/recovery tests remain passing.

## Medium 2 — immutable content identity

SavedRecipe carries required content_digest, validated against the definition.
The library stores it durably per row. SHA-256 input is the validated definition's
compact sorted-key UTF-8 JSON (ensure_ascii=False), including defaults and Decimal
strings. Decimal spelling is preserved; this is content integrity, not a signature.
Read/list fail closed on payload/digest/schema mismatch without content repair.
Preview returns identity; UI verifies it against SavedRecipe before showing review.
Execute checks expected_revision AND required expected_content_digest before
creating a run. Thus even replacement with a valid new digest at the same revision
cannot execute under a previously reviewed identity.

Library PRAGMA user_version is explicitly 2; logical recipe schema remains 1.
Prior v1 library structure is rejected with unchanged bytes, no migration/deletion.
Earlier UVP run snapshots missing digest also fail validation, with no silent
upgrade; legacy Guided Demo snapshots remain supported. Existing UVP data must be
preserved for a separately approved transition. No existing user database was
rewritten or cleared by this work.

Tests mutate valid same-revision payload and prove 409 before run creation/dispatch,
reject an internally consistent different digest under an old review, reject a
missing execute digest, validate canonical identity and snapshot mismatch, and
retain unchanged loads, revision append/CAS, duplicate/schema checks and library-
independent run snapshots. Browser/API regressions cover mismatched preview identity,
exact execute identity, fresh-reference explanation and unavailable collection.

## Verification and review questions

- Focused UVP: 45 passed. Full backend: 1903 passed in 127.86 seconds.
- UI/API/browser: 41 passed, 18 real headless-browser cases, zero skipped.
- Ruff, UI lint, TypeScript/Vite build, complete diff self-review and whitespace
  checks passed. Backend: 8 files, +262/-29. UI exact diff-stat is in its commit.
- Build assets: JS 330.35 kB (gzip 91.23 kB), CSS 52.32 kB (gzip 10.42 kB).
- No second executor, new kinds/routes, XDL, parser, plugin framework or animation.

Please verify:
1. Configured COLLECT reaches fresh RUN input and completes through the existing
   protected owned collection path without fabricated/static/stale readiness;
   missing references and unsupported static composition remain fail closed.
2. Stored revision and explicit review/execute identity are content-bound;
   valid same-revision mutation fails before run creation/dispatch, with append-
   only/CAS/snapshot guarantees intact and no automatic old-data migration.

Return findings with severity, file/line and concrete scenario, and an explicit
follow-up acceptance verdict. Prior milestone scope is in
`docs/reviews/2026-10-11-uvp-handoff.md`; current contract is in backend
`docs/UVP_RECIPES_V1.md` and UI `docs/UVP_USER_GUIDE.md`.
