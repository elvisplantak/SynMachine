# Shared hardware sequence ownership (explicit composition)

Base: `9eed35297066ffbe47a4c4bd01a9ff586ed0991b`, accepted independent review.
Branch: `codex/simulated-p1-execution`. Date: 2026-09-30.

## Implemented boundary

`HardwareOwnership` supplies one durable sequence owner for Arduino, SF and
Service calls routed through one `OwnedHardware` composition. The same file and
expected database UUID must be used by every participating process. A sequence
holds ownership across operations and stationary gaps. Operation execution is
serialized without waiting on another in-process operation. SQLite BEGIN IMMEDIATE
makes claims exclusive across connections/processes.

The database is created only through explicit `provision_ownership` with exclusive
file creation. Reopening uses mode=rw, exact expected table definitions, UUID and
owner/history consistency checks. It does not create, migrate, repair or release
anything. No TTL or process-start cleanup exists. Leases are process-local object
identities: a copied lease or the same sequence ID in a new process cannot resume.
Identity checks are not protection against an adversary editing/cloning databases.

Normal command exceptions, unknown/incomplete Arduino results, Stop at a boundary,
and BaseException interruptions retain ownership. Persistence failure retains the
original exception and marks the local lease unusable even if the BLOCKED write
fails. The durable ACTIVE owner still blocks restart. Explicit `complete` is the
only success release; it is forbidden during another active operation. A caller
must persist successful lifecycle resolution before invoking it. No automatic
recovery/release API is provided.

## Arduino, SF and required follow-up

`OwnedHardware.run_operation` gives a callback temporary, thread-confined command
access. Arduino phase identity must match its lease. Access expires when the callback
returns. Swallowing an adapter error cannot permit later commands or false success.
An optional required-followup callback runs through the existing protected-operation
helper under the same owner and operation gate. This permits required CLOSE after
an ordinary primary error without exposing the hardware to a competing Service
request. Both errors remain available in ProtectedOperationError. Successful CLOSE
never erases an unknown primary result or releases sequence ownership. Abrupt process
death does not promise CLOSE, and restart does not send it.

The callbacks are trusted backend code, not user-supplied scripts or route approval.
The underlying adapters must remain private; calling an unwrapped adapter bypasses
this composition. Existing Arduino durable intent-before-send is preserved and
verified with the real durable executor plus a fake transport. This ownership store
is not an SF command journal and does not establish hardware position/session trust.
SF durable action-intent integration remains required before live activation.

## Service wiring and compatibility

`create_app(owned_hardware=...)` explicitly binds BOTH Service paths. Mixing it with
raw arduino_commands, sf_bottom_valve or arduino_runtime arguments is rejected.
Tests use this injection with fakes; environment builders and default application
construction do NOT enable it. Legacy unwrapped startup remains unchanged and is
not claimed to have shared ownership.

An Arduino Service request owns a single-operation sequence keyed by operation ID,
while preserving the caller's phase ID in its durable command. Different operations
can share a phase ID. Repeating an attempted operation ID is blocked rather than
resent. SF Service creates a fresh sequence ID for each synchronous request.
Only successful bounded commands release their Service owner.

The new Arduino Service wrapper rejects SF mixer START before send: command
completion starts continuous rotation and cannot authorize owner release. Supporting
START/STOP as a retained sequence requires deliberate lifecycle integration. The
existing unwrapped SF mixer endpoint behavior is unchanged. A Stop command cannot
bypass another sequence owner; live Stop/recovery semantics remain a separate gate.

## Verification and remaining work

38 new tests cover all Arduino/SF Service endpoints, simultaneous channels, same-lease
competition, ownership during required CLOSE, swallowed errors, wrong phase, escaped
scopes, wrong/missing/empty/incompatible databases, claim/block/release write faults,
second-process contention and actual process death. 99 focused tests and all
1337 backend tests pass; Ruff and `git diff --check` pass.

This stage changes no firmware, UI behavior, hardware state or automatic startup
configuration. No main merge or physical tests. Before live activation:

- connect the accepted lifecycle runner to this production-capable composition;
- bind SF durable action intents and result persistence;
- preserve sequence ownership across mixer START/STOP;
- define deliberate recovery of retained owners and cross-database states;
- approve backend-owned live route order and independently establish current trust;
- implement explicit live Stop after SF OPEN, live timers and startup composition.

Do not infer that legacy Service callers or an independently constructed runtime
are protected merely because this module exists.
