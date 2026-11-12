# UI GitHub verification

[UI (fake API)](https://github.com/elvisplantak/SynMachine/actions/workflows/ui.yml)
runs on GitHub-hosted Ubuntu 24.04 for UI code/fixture/configuration or UI workflow
changes, on branch pushes and pull requests. UI Markdown-only changes do not
trigger a push run. Pull requests are filtered by their complete proposed diff,
so a later documentation commit can still trigger a PR verification. The latest
run for the same source repository/branch supersedes an older in-progress run;
different fork repositories have separate concurrency groups.

Push checks use the source branch; PR checks use GitHub's proposed merge. A new
PR can supersede an in-progress push check. `workflow_dispatch` is also declared;
GitHub requires the workflow to be on the default branch before offering its
manual trigger. This feature does not merge itself or configure branch protection.

## What runs

The job has read-only repository permissions, disables persisted checkout
credentials and sparsely checks out only `ui/` and `.github/`. There are no
deployment steps, application credentials or self-hosted/device runners.

The workflow pins action commits and Node.js 24.18.0, matching the existing local
verification baseline. `npm ci` uses the unchanged package-lock.json and caches
only npm downloads, not node_modules. The hosted image supplies Chrome; the job
requires an executable `/usr/bin/google-chrome` and records its version before
tests. It does not silently replace missing browser tests with unit-only success.

It runs the existing `npm run lint`, `npm run build` and complete Node test suite.
The test command preserves `npm test`'s file selection and isolation option,
adding native spec and JUnit reporters:

```bash
node --test --test-isolation=none \
  --test-reporter=spec --test-reporter-destination=stdout \
  --test-reporter=junit --test-reporter-destination="$RUNNER_TEMP/ui-tests.xml" \
  tests/*.test.mjs
```

Run from `ui/`. For a local report, set RUNNER_TEMP to an existing temporary
directory. Ordinary `npm test` retains its previous behavior, including explicit
browser skips when no browser is installed. Hosted CI additionally requires at
least the current 55 test cases, including 28 browser cases and all four existing
test modules, with zero skipped, failed or errored cases.
Missing/malformed reports also fail the check. Intentional future suite reductions
must update this explicit floor; adding cases needs no floor change.

The JUnit report is uploaded even after a failed test step, retained for seven
days, and summarized in the Actions job. The job timeout is ten minutes. A
cancelled/superseded run does not claim successful verification.

## Scope

Tests use existing in-memory fake API fixtures and isolated headless browser
profiles. The localhost Vite middleware blocks API fallthrough. No actual backend,
live state, credentials, Serial device, firmware or physical operation is used.
Browser fixtures exercise UI/contract behavior; backend tests remain authoritative
for execution policy, durable state and command ownership.

This workflow automates the existing UI checks. Application code, test scenarios,
dependencies/lockfile, backend CI and hardware behavior are unchanged. The four
previously recorded UI development-dependency audit alerts remain separate
maintenance; this workflow does not claim an audit result or dependency update.

## Verification record

On November 12, 2026, local Node 24.18.0/Chrome 148 passed 55 tests (28 browser)
in 15.06 seconds, zero failures/skips, plus lint/build and Actionlint 1.7.12.
The exact report gate rejected skipped/failed/errored cases, missing browser-module
coverage, and empty/missing/malformed reports.

Hosted [run 43212406428](https://github.com/elvisplantak/SynMachine/actions/runs/43212406428)
passed on implementation `fb4387ad4890380b943803fc514db5520c1a82c4` for
[PR #3](https://github.com/elvisplantak/SynMachine/pull/3): 55 tests in 59.48 seconds,
28 browser cases, zero failures/skips, Node 24.18.0/Chrome 156.0.8078.79.
Lint/build, report verification/upload and cache cleanup passed. The latest
candidate's check is tracked on that PR; later documentation-only records do not
change the verified workflow or application/test code. Main merge remains pending.
