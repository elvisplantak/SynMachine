# Owned collection, timers and SF mixing — 2026-09-30

Accepted base: `771ad703d70fef9cde94e9fb2c00bea57c811665`.
Branch: `codex/owned-execution-slice`.
The preceding integrated transfer slice was independently accepted with zero
findings. This checkpoint extends that SAME runner, coordinator and ownership
composition. It adds no alternate command dispatch path.

## User decision and configuration

The user chose timed SF mixing, with seconds configurable before the run starts.
`DemoExecutionSettings.sf_mixing_duration_seconds` is an optional positive finite
Decimal. Omitted/None preserves old run snapshots but does NOT invent a duration:
preparing automatic SF_MIXING then fails before ownership or any command.
New runs can supply it in their existing execution-settings snapshot. No UI input
has been added yet, and this does not activate a physical execution endpoint.

SF mixing uses only the firmware's existing boolean START/STOP command and fixed
commissioned profile. It does not map `sf_mixing_command_percent` to pulse rate,
RPM or measured mixing intensity. Speed calibration remains deferred. SF settling
uses the existing configured non-negative duration; zero settles without sleep.
No mixing or settling time is evidence of actual phase separation.

## One execution path

The existing owned transfer runner now accepts:

- Column preparation, OPEN, interruptible timed collection, required CLOSE,
  carousel advancement, and the next fraction;
- SF_MIXING: START, interruptible timed wait, required STOP;
- SF_SETTLING: passive interruptible wait with no actuator command.

All actions use the same plan storage, PlanLifecycleCoordinator, HardwareOwnership,
OwnedHardware scopes and Arduino/SF journals as the accepted transfer path.
The fixture-only constructor remains enforced. Raw legacy adapters are not used
by this composition. Existing unwrapped application startup is unchanged.

Timed SF source plans regenerate from the current run settings before claim.
They are validated and stored through the existing immutable plan store, including
unknown-field rejection. `EXECUTION_INTENT_PHASES` adds mixing/settling to intent,
event, result and interrupted-execution validation. The legacy phase executor's
supported phases remain unchanged; it does not acquire a new execution route.
Legacy logical phase completion still works when there is no active intent, but
cannot bypass an active timed intent. Production-wide startup composition remains
a separate mandatory gate.

## Timer and completion evidence

`MonotonicExecutionTimer` uses monotonic nanoseconds and bounded sleeps (default
50 ms polling). It measures elapsed time, not a count of sleep calls. Stop is
checked before each deadline decision; zero duration needs no sleep. Invalid,
negative or regressing clock readings fail closed. Polling is cooperative and
is NOT a hard real-time or emergency-stop response guarantee. The default offline
runner still uses virtual fixture waits; the monotonic timer is explicitly injected.
Both were tested. No timer or elapsed state is restored on restart.

`execution_waits` is in the existing execution database. Intent is committed before
waiting, then COMPLETED/STOP_REQUESTED/OUTCOME_UNKNOWN is recorded. A separate
`operation_completed` bit becomes true ONLY after the primary operation and its
required CLOSE/STOP succeed. A finished wait alone is not a completed fraction or
successful mixer phase. Interrupted fractions are never counted completed.

Intent-write failure prevents waiting, while the surrounding protected operation
still attempts required cleanup. Result or completion-write failure blocks progress
and retains ownership. Error-write failure preserves the original exception and
adds a diagnostic note. The lifecycle intent remains unresolved on failure; no
new phase-outcome ledger is introduced.

## Ownership, cleanup and restart

Ownership spans START/OPEN, the entire wait, STOP/CLOSE, all inter-operation gaps,
and lifecycle result persistence. Service calls cannot intervene. Stop before
start sends nothing. Stop immediately after OPEN/START skips elapsed waiting but
still runs cleanup. Ordinary primary failure/unknown still attempts cleanup under
the same owner; both errors survive in ProtectedOperationError. Successful cleanup
does not resolve an unknown primary or release ownership.

Process death/abrupt interruption cannot guarantee cleanup. Reopening sends
nothing: no automatic CLOSE, STOP, resend, timer resume or owner release. The
existing explicit startup reconciliation now recognizes timed SF intents and
marks recovery required; it does not release hardware ownership. Cross-database
commits remain non-atomic and require deliberate reconciliation before activation.

## Carousel and current fixture trust

The current carousel fixture must match the plan's starting alignment. Position
projection is persisted in `execution_carousel_projection`, invalidated before
movement, and restored only after a completed Arduino result and projection write.
Failed movement/restore blocks the next fraction. If invalidation persistence
fails, no move is sent and the in-memory position is untrusted; retained ownership
prevents using any old stored projection as permission.

A controller session change invalidates current carousel/mixer fixture trust and
prevents stale-session cleanup commands. Timed SF phases additionally check the
SF session while waiting and require an independently stopped mixer at preflight.
A lost SF session during mixing still allows the required Arduino STOP if its
controller session remains valid, but leaves the phase unresolved.

These are test-fixture and software-result projections, NOT live hardware trust.
Each fixture is still consumed by one attempted phase. Live multi-phase trust,
physical readiness, route approval and sensor/position assurance remain deferred.

## Schema and rollout boundary

The execution schema adds wait and carousel evidence tables. Previous execution
files are deliberately rejected as incompatible; there is no automatic migration,
repair, replacement or restart provisioning. Original project databases were not
modified. A future migration/recovery decision must preserve unresolved evidence.
Ownership and lifecycle schemas are unchanged; existing run settings without the
new optional duration remain readable.

No API execution activation, Serial/Dynamixel integration, firmware changes,
physical testing or main merge occurred. Delay-between-additions and reaction-hold
Pause/Resume timers are not implemented by this checkpoint. Live Stop policy after
SF OPEN before aspiration, deliberate recovery, multi-phase trust and actual
production startup remain mandatory gates.

## Verification

New regressions cover complete collection/mixing/settling, Stop boundaries,
competing Services, manual completion refusal during active intents, controller/SF
session loss, carousel projection failures, wrong old schema, invalid/changed
mixing duration, unknown plan fields, and monotonic-clock semantics.

All six primary-ok/failed/unknown versus required-cleanup intent/result persistence
failure combinations are tested for both Column CLOSE and mixer STOP. Timer intent,
result, completion and error-persistence failures are covered. Actual subprocess
death during waits and lifecycle resolution is tested for all three new phases;
restart neither sends nor modifies the databases. Real short wall-time waiting and
Stop from a separate lifecycle database connection also run against fake hardware.

Final counts are recorded in the checkpoint handoff and canonical current state.
Review this combined collection/timer/mixer milestone as a whole.
