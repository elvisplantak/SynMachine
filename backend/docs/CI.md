# Backend and SiLA continuous integration

The owner approved automatic software verification on GitHub on November 8,
2026. [The workflow](../../.github/workflows/backend.yml) runs the complete backend
suite, including the independent C# SiLA client, on a GitHub-hosted Ubuntu 24.04
runner. It uses test fixtures, loopback TLS and separate temporary fake state.
It does not deploy or connect to physical devices.

## When it runs

- Pushing changes under `backend/`, except Markdown-only changes, or changing
  `.github/workflows/backend.yml` starts verification on that branch.
- Local commits do not start GitHub jobs until pushed. UI-only, firmware-only
  and project-documentation-only changes do not start this backend workflow.
- Fork pull requests receive the same verification. Same-repository pull requests
  use the push check instead of running the suite twice.
- A newer run for the same branch or fork pull request cancels the older one.
  Each job has a 15-minute timeout.

Results are visible under
[Actions → Backend and SiLA (fake devices)](https://github.com/elvisplantak/SynMachine/actions/workflows/backend.yml)
and as checks on the tested commit. Existing runs can be rerun from Actions.
`workflow_dispatch` is also declared, but GitHub requires the workflow to exist
on the default branch before offering that manual trigger. Adding this workflow
to a feature branch does not merge it into main or configure required branch checks.

## What it verifies

1. Install `.[dev,sila2]` with the CI tool constraints, check dependencies and run
   backend Ruff. Python is 3.12; `ci-constraints.txt` pins pytest 9.2.0 and Ruff
   0.15.22 to the verified baseline. Python application dependencies retain their
   existing declared version ranges; this is not a full Python dependency lock.
2. Select .NET SDK 10.0.403 from `backend/global.json`, restore the independent
   client using its existing NuGet lock and build Release with warnings as errors.
3. Supply the built client and actual dotnet executable explicitly, then run
   `python -m pytest -q -ra` once for the entire backend. The SiLA cases are part
   of that suite; the focused subset is not run a second time in CI.
4. Check the JUnit report: all three SiLA test modules must be represented, with
   no skipped or failed tests. Missing optional SDKs or a silently skipped
   independent-client fixture cannot produce a successful check.

The suite covers shared recipe validation/execution, authorization before
decoding, client roles and attribution, exact-operation Stop and retained
ownership, audit failures and response loss without replay. Passing CI records
software verification; independent review and physical readiness retain their
existing separate scopes.

## Runner and report boundaries

The job checks out `backend/` and `.github/` only (plus Git's root files), using
sparse checkout. Firmware directories are not checked out. It uses no repository
secrets, grants only `contents: read` and does not persist checkout credentials.
GitHub actions are pinned to exact commits. Pip downloads and locked NuGet
packages are cached; fake databases, token files and TLS keys are not cached.

Only the JUnit XML report is uploaded, retained for seven days, with captured
test stdout/stderr omitted. No fake runtime directory, certificate or credential
file is uploaded. Failure tracebacks and test results remain available in job
logs/report. A failed install/build still fails the job; missing reports do not
override earlier failures.

Configuration references: [GitHub workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax),
[checkout sparse patterns](https://github.com/actions/checkout#fetch-only-the-root-files-and-github-and-src-folder),
[setup-python cache](https://github.com/actions/setup-python#caching-packages-dependencies),
[setup-dotnet SDK selection and cache](https://github.com/actions/setup-dotnet).
