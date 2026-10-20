# Exclusive offline execution and interruption reconciliation

This checkpoint composes the accepted fake executor, lifecycle, command journals
and hardware ownership in `OwnedOfflineRuntime`. It adds explicit **software
interruption reconciliation**, not physical recovery or production startup.

## Exclusive lifetime

The runtime takes nonblocking advisory Linux `flock` locks on all three existing
bundle files, then validates their expected identities and bindings. Failed open
closes all acquired resources. The locks remain held across phase boundaries,
pauses and reconciliation, until close or process death. Partial bundle overlap
is blocked as well as an identical bundle. Missing files are not created.

Only the exact `SimulatedP1Device` is accepted. Runtime methods are bound to their
creating process/thread, and a non-reentrant operation gate prevents close or
reconciliation during execution. The current lifecycle SQLite connection is
thread-affine; this is not a concurrent API server or production control facade.

These locks coordinate **this explicit composition only**. Historical direct
assemblies, arbitrary database writers and the legacy production startup do not
participate. They must not operate concurrently on these offline files. Files must
not be replaced/unlinked while open. Production-wide exclusion remains a gate;
this checkpoint does not claim that an advisory file lock fences live hardware.

## Fresh execution

`start_fresh_run` accepts a caller's explicit configuration, settings, calibration
and independent fake readiness. It requires a bundle pristine at open and creates
the run within the same runtime lifetime. `execute_next` uses the existing
`OwnedPhaseSession` and its single durable command path. All ten demo phases can
complete in this composition; no second dispatcher or database is introduced.

A reopened run cannot be adopted, even if it died before the first command or
between two successfully completed phases. Failed initialization cannot be retried
in the same runtime. A previously completed bundle is also not recycled into a new
run; commissioning, flushing, fresh trust and reusable production startup remain
future integration work. No new physical facts or calibration defaults are assumed.

## Explicit interruption handling

Opening does not reconcile automatically. `reconcile_interruption(occurred_at)`:

1. Requires the exclusive runtime and no locally started execution session.
2. For a persisted BUSY machine, retains any existing unresolved owner unchanged.
   If none exists, atomically commits a new BLOCKED reservation first. It never
   returns or reconstructs a command lease.
3. Calls the existing transactional lifecycle reconciliation. Run and machine
   changes commit together, after ownership retention has committed separately.
4. Leaves command/wait journals and prepared plans untouched. It never sends a
   command, resumes a timer, closes a valve, performs cleanup or releases an owner.

A crash between ownership and lifecycle commits leaves the system blocked. A
lifecycle write failure rolls back the run/machine transaction while keeping the
owner. An explicit retry can finish the metadata reconciliation without creating
another owner. Once lifecycle reconciliation succeeded, repeating it does not
append events. A crash after that commit does not trigger repeat execution.

Claimed-but-not-started intents follow the existing RECOVERING policy. Started
intents retain the existing conservative RECOVERY_REQUIRED/unknown-outcome policy.
A gap without an active execution uses the existing active-run reconciliation.
ABORTING without a started unresolved action can become ABORTED; other interrupted
active runs become FAULTED according to the existing domain transitions.

### Lost paused process

The new composition explicitly opts into handling PAUSED runs only for supported
pausable wait phases with a durable started intent. Such a run becomes FAULTED,
with RECOVERY_REQUIRED and the conservative unknown-outcome marker; elapsed time
is never reconstructed. PAUSED with an unstarted intent is rejected without
lifecycle mutation. Legacy reconciliation defaults remain unchanged and reject
these paused cases unless deliberately opted in.

The return value is only a machine snapshot. READY, a missing machine or an already
reconciled snapshot does **not** authorize execution or free retained ownership.
Non-BUSY snapshots are returned without mutations, and the execution entry point
still rejects a runtime without a newly created process-local session. Use the
read-only inspection report for journal/owner observations, not as physical trust.

## Verification and remaining work

Tests cover a complete ten-phase fake demo, retained owners and inter-phase gaps,
unknown interruption evidence, reservation INSERT/UPDATE/COMMIT faults, lifecycle
first/second-write rollback, repeat reconciliation, unchanged journals, competing
processes, overlapping bundles, resource cleanup, reentrant close rejection,
missing files and default legacy isolation. Subprocess tests die while executing
a paused timer, between ownership/lifecycle commits, and after lifecycle commit.
Restart performs no send, Resume, cleanup or ownership release in each case.

Remaining gates: deliberate physical reconciliation and release policy, fresh
hardware/session trust and safe routes, live SF OPEN/Stop policy, production-wide
composition, transport/API/UI integration, commissioning and physical testing.
There is no schema migration, hardware execution, firmware/UI behavior change,
production activation or main merge in this checkpoint.

Final local verification: 30 new runtime/reconciliation tests pass; all 1608
backend tests pass (56.40 s), Ruff passes, and `git diff --check` passes. The
interrupted pre-final run also completed successfully (1606 tests); the final
run includes the two additional actual-process-death regressions. No independent
review of this new checkpoint has been requested yet.
