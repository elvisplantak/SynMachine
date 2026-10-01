# Owned offline startup inspection

This is a read-only diagnostic step toward deliberate interruption reconciliation.
It is **not** a recovery executor, a production startup gate or permission to resume.
The accepted complete fake demo base is `3d9fab24f325f3a2da59d69215465e110acd3c33`;
independent review reported zero findings and requested no corrections.

`inspect_owned_startup(OfflineDatabaseBundle(...))` opens the three existing files
with SQLite `mode=ro`. All paths and expected identities must be provided by the
caller independently of the files being inspected. It checks ownership/execution
schemas, identity bindings, retained ownership consistency, stored plan hashes and
canonical derivation, and uses existing lifecycle schema/snapshot validation.
It never provisions, repairs, migrates or modifies a database.

The report includes the retained owner and state, ownership generation, machine
and run snapshots, paused run IDs, prepared phase IDs, journal totals and individual
non-successful record IDs/states. A completed timer whose encompassing operation
has not completed is reported separately. An ownerless bundle with unresolved
journal evidence remains visible; no absence is interpreted as permission to act.

Each database is read under its own transaction. These are not atomic snapshots
across all three databases and must not be used to decide owner release, declare
an operation successful, prove a process has died or authorize any command. In
particular, `ACTIVE` can still belong to a running process. The report is an
observation, not an exhaustive replay/consistency proof of all command arguments,
lifecycle events or hardware state. Missing/invalid bundles raise an error rather
than returning an empty/ready report. Even entirely successful history never
permits automatic resume or supplies fresh session/physical trust.

## Explicit diagnostic command

```sh
python -m app.hardware.owned_startup_inspection \
  --ownership-path /path/to/owner.db --ownership-id EXPECTED_OWNER_ID \
  --execution-path /path/to/execution.db --execution-id EXPECTED_EXECUTION_ID \
  --lifecycle-path /path/to/life.db --lifecycle-id EXPECTED_LIFECYCLE_ID
```

These are placeholders for a provisioned **offline** bundle, not production
project databases. The command prints JSON. Exit code 0 means inspection succeeded,
not that execution is safe; invalid bundles return exit code 2. No transport is
constructed and no recovery action, resend, Resume, CLOSE or owner release occurs.
`SimulationLifecycleStore(..., read_only=True)` supports this reader; its existing
read/write default is unchanged.

## Scope and continuation

The full fake demo and its runtime remain unchanged. No UI, API, firmware, live
transport or production startup activation is included. There is no new schema.
Interrupted PAUSED runs are reported intact, not converted to success or resumed.

The next software step is now implemented in `OwnedOfflineRuntime`; see
`OWNED_OFFLINE_RECONCILIATION.md` for its explicit composition, advisory-lock
boundary, cross-database failure handling and interrupted-pause policy. It retains
durable exclusion before lifecycle mutation and never reconstructs a lost lease. Physical recovery, fresh references, safe routes, flush
and permission for subsequent real execution remain separate work.

Verification covers full successful fake execution, inter-phase gaps, owner claim
before lifecycle claim, unknown SF outcomes, paused durable waits, incomplete
cleanup, unowned unresolved evidence, wrong/missing/empty/incompatible databases,
binding mismatches, corrupt plans, actual read-only write rejection and CLI output.
Tests compare file bytes and device call logs before and after inspection.
No new independent review is requested for this diagnostic substep; consolidate
with the larger reconciliation milestone, following the user's preference.

Verified locally: 26 new tests; 1578 full backend tests passed in 52.50 s;
146 focused integration tests passed before the final CLI additions; final full
suite includes those additions. Ruff and `git diff --check` passed.
