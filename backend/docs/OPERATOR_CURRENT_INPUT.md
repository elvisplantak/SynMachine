# Fresh operator current input through the existing UI

Date: 2026-10-06. Software preparation only; tests use fake transports.

## Composition and attribution

`OperatorCurrentInput` implements the callback consumed by
`build_configured_adapter_application_execution`. Composition must explicitly
supply the operator identity, a randomly generated private ASCII credential of
at least 32 non-whitespace characters, and the same monotonic clock as the
configured provider. There is no default credential, live profile loader,
production entry point or automatic selection of a physical device.

The server stores a SHA-256 credential digest in process memory. A matching
Bearer credential attributes a declaration to the configured operator; the
client cannot choose the operator identity or observation timestamp. This is a
narrow declaration credential, not general API authentication, a user-management
system or proof that observations are true. Existing execution/Service endpoints
have not acquired a new authentication policy. Production network access and
credential provisioning remain a separate integration boundary.

The source performs no transport I/O. The existing owned worker asks it for
input, and GET `/api/v1/execution` exposes only the pending request ID, purpose,
operator, boot/connection epoch and remaining deadline. It exposes no credential
or handshake nonce. Reading, reloading or navigating cannot create a request.

## Explicit operator workflow

1. Deliberately request initialization, Start or recovery through existing controls.
2. The existing provider creates a fresh session-bound current-input request.
   The UI displays an initially blank panel even while initialization waits.
3. Supply current evidence, the access credential and explicit fresh-observation
   consent. Leave uncertain references unknown; stored logs, preview settings,
   visual estimates of raw coordinates and STATUS cannot fill them.
4. POST `/api/v1/execution/current-input/{request_id}` submits references to that
   request. The server stamps receipt time and identity. Its acknowledgement only
   means the declaration was received. The original action can continue if all
   existing backend eligibility, ownership, planning and dispatch checks pass.
5. Read actual backend machine/run/operation results. The UI cannot confirm
   phase completion, hardware movement, cleaning or durable ownership release.

For fresh READY/first Start, both pump raw positions must independently equal
their configured working-empty positions, every V1-V8 reference must be known,
Reactor/SF mixers stopped, SF bottom valve closed, and Column/carousel known.
Initial READY and first Start require separate requests. Missing references
block before RUNNING or actuator commands; acceptance of a partial declaration
does not waive this check. A failed Start leaves the CREATED run available for
an explicit fresh retry; no automatic retry or new run is created.

Recovery's panel asks only for current stopped Reactor and manual carousel
alignment matching its explicit plan, together with new evidence/consent. Other
actuator references stay unknown. The existing recovery sequence establishes
them using its HOME/route/move operations and still requires separately verified
routes, calibrated plan inputs and all existing per-attempt maintenance readiness.
There is no automatic recovery. Mandatory flushing retains the same owner until
durable READY/release. Successful same-session command continuity remains valid
for later phases/runs; operator declarations do not overwrite that continuity.

## Timeout, Stop, cancellation and restart

The source waits only until the configured monotonic deadline. Missing, old,
duplicate, foreign and late submissions cannot supply a fallback reference.
Wrong/missing credentials return 401 without consuming the request; an expired
or nonpending request returns 409. Strict input rejects client identity/time,
duplicate references, invalid positions and absent consent.

POST `/api/v1/execution/current-input/{request_id}/cancel` uses the same credential
to end that wait. Existing out-of-queue Stop also cancels pending run/maintenance
input. Closing the application closes the source and unblocks initialization
too. Stop/close can invalidate a submitted response before the worker consumes
it; normal atomic-operation Stop semantics remain unchanged after dispatch.

The UI clears its credential before awaiting either POST, including failures.
It keeps no credential in URLs, bodies, browser storage or logs. A new request ID
mounts a blank form with unchecked consent. Connection-read failure unmounts the
form, and restoration performs GETs only. There is no command/declaration replay.
Pending requests and input are process-local and never restored from a database.
The fake launcher rotates its credential on every process launch. A deployment
must separately choose its credential lifecycle; restart always requires a new
request regardless of whether the operator credential is rotated.

Accepted operator input carries a historical receipt into the existing prepared
plan assumptions: request ID/purpose, configured operator, evidence note,
server monotonic receipt time and `OPERATOR_CREDENTIAL` attribution method.
No secret is stored. Receipt time belongs to that process clock, not a portable
wall-clock timestamp. This receipt is history, never current readiness or a
resume permit. Startup ignores it. Old canonical schema-1 plan records without
the optional receipt remain readable byte-for-byte without migration/rewrite;
strict canonical comparison, derivation and SHA-256 checks remain enforced.

## Physical profile still incomplete

`ADAPTER_PHYSICAL_PROFILE.draft.json` is a non-activatable worksheet, deliberately
rejected by `AdapterExecutionConfiguration`. Unknown working margins, ordered
valve transitions, adapter timing/identity and recovery/flush plan inputs remain
null. It is not a loader or a runnable profile. Never fill it from test fixtures.

Firmware `HARDWARE_CONFIRMATIONS.md` owns physical facts. Existing nominal
1025 steps/ml applies only to the supervised demo, not precise wet calibration
or working endpoint selection. Existing tubing/final target sets do not establish
safe transition order. Raw current pump references also need an independent
method; the current firmware does not report all actuator positions. Real startup,
HOME, recovery and flushing still need separate physical authorization and fresh
motor-power readiness.

See `ADAPTER_CURRENT_CONTEXT.md` for the physical confirmation matrix and
`BROWSER_CHECK.md` for the optional fake-only browser procedure. No firmware,
dependencies, production activation, real serial/SDK access or flow animation
is added by this milestone.


## Existing physical records and remaining inputs

Pump positions are absolute stepper coordinates, not millimetres or revolutions.
The hardware record already accepts HOME coordinate 0 and maximum coordinate
20500 for P1/P2, plus the demo-only nominal 1025 steps/ml mapping. These facts
are retained in the worksheet's reference section, separate from current state.
Working full/empty margins remain explicitly `jos nije potvrdjeno`; candidate
coordinates/working volume remain null. Volume units are ml. No new measurement
is inferred from an old dry movement or the accepted maximum coordinate.

Confirmed dry Waste HOME routes are P1 with V1=180/V2=180 and P2 with
V3=180/V7=90/V8=90/V5=180. On 2026-08-08 the recorded dry setup homed/set
V1 then V2 before P1 HOME, and V3 then V7 then V8 then V5 before P2 HOME.
Those are existing confirmed setups, not missing tubing facts. Complete safe
switching between all run/flush routes, including transient connections from
each applicable previous route, remains unconfirmed. Test fixture orders must
not substitute for that physical confirmation. Later V7/V8 repair evidence
overrides obsolete pin/fault records, but creates no wet-transition approval.

## Software checkpoint and verification

Active branch in both worktrees: `codex/operator-current-input`. Backend base:
`36d6046a10361bf7bdb5db7f440075573e9d2b41`; UI base:
`b2f00dfe8bf3a9a92ef09f71b174a14392576a70`. This new cohesive checkpoint
needs independent consolidated review; the previously accepted base remains
accepted only for its declared scope. Pinned HEADs are recorded in the UI
`LABFORGE_CURRENT_STATE.md` and review handoff after finalization.

Full backend verification: 1858 tests passed in 111.43 s, Ruff and diff checks
passed. New coverage comprises 28 operator-source/HTTP tests, two optional fake
browser-profile tests and two canonical-plan compatibility tests. The complete
UI suite passed 26 tests (15 API, 11 isolated fake-API browser; zero skipped),
lint and build. The additional RUN-form/retry regression verifies original
CREATED identity, blank references/consent and exactly one explicit Start plus
one declaration, without automatic command replay. JS: 313.51 kB / 86.31 kB gzip;
CSS: 50.08 kB / 9.94 kB gzip. All transports and intercepted API responses are
fake. The draft JSON parses and its candidate is strictly rejected as incomplete.
No dependency, SQL schema, firmware, real device or production activation change
occurred. Manual browser verification of the new panel is still pending.
