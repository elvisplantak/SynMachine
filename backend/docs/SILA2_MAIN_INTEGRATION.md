# Initial SiLA 2 integration on the main baseline

The owner approved preparing the initial fake/local SiLA software integration
for main on November 8, 2026. This is a selective port on a separate integration
branch, not a merge of commissioning history or an activation of live devices.

## Provenance and retained boundaries

| Role | Pinned revision |
| --- | --- |
| Main base | `49b5beb22945e9d55166c9c361a19d81809b5a28` |
| SiLA/CI source, preserved on `feature/sila2-ci` | `40d8a659c938fd3b14deb9b30f9fae24e427e9dc` |
| Pre-SiLA handoff used to select the delta | `ae8c78f062a5fa4fe38049bee82c40597f1606db` |
| Separate commissioning code, preserved | `1ea4e7a3d98d193ab3c8132aa0ebddf75cd380a6` |

The selected backend/workflow delta comprises 23 paths: `app/sila2/`, the three
SiLA test modules and their launchers/credential/demo helpers, the independent
C# client and lock, optional Python dependencies, CI workflow/tool configuration
and related backend documentation. Each transferred path matches its source blob
exactly. System context/current-state documents are updated for this main-based
port while retaining the old main publication/migration history and links to the
separate detailed commissioning checkpoint.

No existing backend domain/HTTP/recipe/hardware or protocol implementation is
modified. Commissioning's expanded capability count, pump-HOME status fields,
wet-test runner and startup reconciliation are not dependencies of the SiLA
adapter and are excluded. Their original branch remains preserved. Main's UI,
root README screenshot/video links and media are preserved. Firmware directories
are outside the sparse worktree and were not accessed for this task.

The source adapter/client APIs, TLS, explicit FAKE restriction, per-request
roles/revocation, pre-decoding admission, audit-before-dispatch and unknown-outcome
semantics remain the same. No extra execution path, state migration or repair is
introduced. The current live owner stays blocked; live credentials, databases,
Serial/DYNAMIXEL devices and EEPROM are not accessed.

## Review and verification scope

Original independent acceptances of exact `222e9e5` and `a10a068` remain historical
records for their declared scopes in [SILA2.md](SILA2.md). Their source blobs are
retained, but the port has a different backend/protocol base, so acceptance is not
automatically relabeled or extended. Tests and hosted CI for this integration are
reported separately. Its expected complete count differs from the earlier 2099
because commissioning-only tests are intentionally not imported; all 62 SiLA
cases must still run, including the independent .NET client, without skips.

Local verification on November 8, from the integration component directories:

- **1999 complete backend tests passed**, zero skipped: 1937 existing main cases
  and all 62 SiLA cases, with the independent C# client enabled. The identical CI
  JUnit gate accepted the report with zero failures/skips.
- All **51 UI tests passed**, including the browser cases, zero skipped. UI lint,
  TypeScript and Vite production build passed on the unchanged main UI.
- Backend Ruff 0.15.22, pip dependency check and Python compilation passed.
  Actionlint 1.7.12 and diff/whitespace checks passed.
- Locked NuGet restore and C# Release build with SDK 10.0.403 passed with zero
  warnings/errors. The main-based standalone demo passed discovery, roles,
  completion/progress and exact Stop with retained fake ownership. All clients,
  listeners and temporary credentials closed; the separate fake result bundle
  is `/tmp/synmachine-sila-main-demo-20261108-K6zMkl` (temporary evidence).

Hosted verification also **succeeded** for exact implementation commit
`e598d58f89df609368c949f39814e0d79bdcf930`:
[GitHub run 42481909369](https://github.com/elvisplantak/SynMachine/actions/runs/42481909369).
All 1999 backend tests passed in 163.70 seconds; the JUnit gate confirmed 62 SiLA
cases, zero failures and zero skips. Lint, locked restore, C# Release build
(zero warnings/errors), report upload and cache cleanup all passed. The hosted
run took about 3.5 minutes including setup. Later documentation-only records do
not change the verified implementation.

The owner explicitly approved [PR #1](https://github.com/elvisplantak/SynMachine/pull/1)
on November 8; approved candidate `18af175fa3e427916969077d5bb52ac67501a80c`
was merged to main as `bc775fae6e08c5768566536b16055099e67af683`.
No source branch was deleted or shared history rewritten. The merge preserves
the approved candidate's backend/UI/documentation content exactly; the
commissioning implementation remains separate. GitHub generated the merge
commit's account metadata; local repository Git identity remains Elvis and the
configured owner noreply address, without global setting changes.

The automatic post-merge [main run 42483128655](https://github.com/elvisplantak/SynMachine/actions/runs/42483128655)
**succeeded** for exact merge commit `bc775fae6e08c5768566536b16055099e67af683`.
It passed all 1999 backend tests in 165.50 seconds, with all 62 SiLA cases and no
failures/skips. Lint/dependency checks, C# Release build (zero warnings/errors),
report upload and cache cleanup also passed. Existing main UI/media and backend
implementation checks remain valid because the approved candidate's contents
were preserved. The initial fake/local software integration is complete on main;
this final record changes only documentation.

The existing main UI lock also produced four high-severity npm audit package
alerts: Vite, nanoid, PostCSS and source-map-js. They are development/build
dependencies already present in the unchanged lock. This port does not update
them; dependency remediation is a separate maintenance follow-up. Advisory
examples: [Vite](https://github.com/advisories/GHSA-9jrq-w75r-8gcw),
[nanoid](https://github.com/advisories/GHSA-2v37-7h3g-55p8),
[PostCSS](https://github.com/advisories/GHSA-fxqj-rqcc-2cmp),
[source-map-js](https://github.com/advisories/GHSA-68fv-2mgg-jv7q).

The final integration is reviewed against the pinned main base. Owner approval
covered this initial main merge under the development governance. Production
authentication/provisioning/exposure, live composition, wet-state reconciliation,
firmware, physical tests and XDL remain outside this port.
