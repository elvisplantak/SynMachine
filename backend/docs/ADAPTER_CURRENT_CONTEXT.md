# Adapter configuration and current-context preparation

Date: 2026-10-06. Scope: software preparation with fake Serial/DYNAMIXEL transports.
This is not production activation, physical commissioning or permission to move
hardware. The existing owned executor, worker, journals, owner and maintenance
policy remain the execution path. There is no new diagnostic endpoint/layer.

## Explicit configuration

`AdapterExecutionConfiguration` in `app/hardware/adapter_configuration.py` is a
strict, immutable, JSON-round-trippable input. It requires:

- a profile identity, evidence note and explicit `DEMO_NOMINAL` or
  `WORKING_VERIFIED` calibration scope;
- a positive finite `current_context_timeout_seconds`, without a default;
- every Arduino and SF adapter setting, including ports, communication timing,
  SF identity/positions/profile/tolerance; no adapter defaults fill missing fields;
- the P1/P2 calibration set and every existing symbolic route exactly once with
  an explicit switching order;
- existing recovery and flush plans with matching kinds and calibrations.

Blank/equal port names, invalid or missing timing, duplicate/missing routes,
out-of-travel calibrations, mismatched plans and unknown/nested discarded keys
are rejected before construction can access any transport. Distinct names do not
prove two paths resolve to distinct physical devices. An evidence note/scope is a
caller statement, not authenticated calibration or physical route approval.

Current pump/valve/Column/carousel positions, mixer states and controller session
identity are excluded from this configuration. Recovery alignment and rinse-start
position are declared plan inputs, not proof of currently aligned hardware.
The hypothetical fixtures under `tests/` must never become a filled live profile.

`build_configured_adapter_application_execution` delegates to the existing
`build_adapter_application_execution`. The preparation entry point requires
explicit transport factories and a current-state callback; it supplies no default
real transport factory or environment/production entry point. Construction opens
nothing. Startup still locks and validates the existing bundle before Serial
HELLO. No database is provisioned, migrated, cleared or repaired.

## Current input boundary

Startup creates unknown references rather than reconstructing them from a
configuration, historical log, old UI state or a controller boot identity.
Calibrations remain known inputs while pump positions are explicitly `None`.
No SF session, callback for current state or actuator command is part of startup.
Startup requires the existing controller capabilities for the complete configured
run/recovery/flush path. Persistent interruption reconciliation remains metadata
only and preserves the old command journal.

Before initial READY/new-run preparation, the runtime calls the current provider
on its single worker under the existing operation gate. The same hook obtains
fresh recovery input before compiling a recovery plan. A request contains:

- a new request ID and purpose (`RUN` for fresh initialization/start/standalone
  maintenance input, or `RECOVERY`);
- the connected boot, backend nonce and connection epoch;
- the start and configured deadline of this request in the supplied monotonic clock.

The callback receives correlation only, never an adapter. It must return a
`CurrentContextResponse` referencing that exact request and a validated
`CurrentDeviceState` with attributed current evidence obtained within the request
interval. Timestamp/identity checks reject cached, foreign, future or regressing
input and connection/capability changes. Responses arriving after the configured
deadline are rejected before planning/commands. The synchronous callback must bound
its own I/O and honor that deadline; this boundary does not forcibly interrupt a
blocked callback or claim hardware timing guarantees.
Old input is removed before acquisition;
callback failure cannot leave prior references available as a fallback. Callback
exceptions are never retried automatically and cannot send a physical command.

For a first run, both pumps must be at their explicitly configured working-empty
positions, all V1-V8 references must be supplied, Reactor/SF mixers stopped, SF
bottom valve closed, and Column/carousel references known. Missing data blocks
before a run becomes RUNNING or any command is sent. Column collection readiness
is derived from this state instead of supplied as unconditional true defaults.
Initial READY and first Start use separate fresh requests. Subsequent phases and
new runs after completion/flush use successful same-session owned command state;
the callback cannot overwrite that continuity with a new optimistic snapshot.

Recovery may begin with unknown pump/valve/Column/SF states. It still requires a
fresh stopped-Reactor statement and manual carousel alignment matching the
explicit recovery plan, plus all existing per-attempt maintenance readiness
statements. The existing recovery establishes references and pump empty positions
through its HOME/route/move command sequence. Ordinary aspiration/dispense and
flush planning reject unknown pump positions. This adds no automatic HOME or
recovery, and HOME remains a fluidic operation needing verified routes.

Recovery retains ownership and FLUSH_REQUIRED. Only the existing successful
mandatory flush commits READY and releases ownership. Restart never promotes a
callback response, command projection or old reference report into current trust.
Fresh recovery is still required after restart between recovery and flush.
Service/connection changes still invalidate command continuity.

## What the current firmware can establish

The canonical firmware document is `docs/LABFORGE_SERIAL_PROTOCOL_V1.md`.
STATUS reports software state/trust, active-command identity and limited Column
diagnostics; it does not report trusted P1/P2/V1-V8/carousel positions or SF mixer
rotation. HELLO/boot/IDLE are correlation/software evidence, not physical readiness.
The SF adapter's current register inspection can report proximity and torque, not
leak-tightness or effective cleaning. Existing fresh bracketing observations remain
the non-actuating preflight under the shared owner; this provider does not duplicate
them or extend the firmware protocol.

The typed callback is the boundary for an independently established current-input
source. It does not implement a concrete live operator workflow, acquire missing
actuator references, or authenticate evidence. A caller that relabels old values
with a new request/time can lie; no software envelope proves physical truth.
Real input acquisition and authorization must be defined before live activation.

## Physical confirmation matrix

Source: firmware `HARDWARE_CONFIRMATIONS.md`, especially the current 2026-09-29
V7/V8 checkpoint and the dated component sections. Historical observations are
not current references; the current checkpoint overrides older V7/V8 fault/mapping.

| Input | Existing confirmed level | Still required for live configuration/use |
| --- | --- | --- |
| Tubing and valve targets | Physical tubing graph and nominal valve semantics documented | Physically verified routes, leak-tightness and safe switching sequence for each applicable path; static targets alone do not provide that sequence |
| V7/V8 | Repair and supervised dry HOME/90-degree production-path regression closed | New current-session references; historical boot-71 positions cannot be reused |
| P1/P2 | Common orientation, separate aspiration/dispense, supervised dry Service paths; nominal demo mapping accepted | Working full/empty margins, precise wet calibration where required, and verified route readiness before HOME/movement |
| Pump nominal mapping | 1025 steps/ml accepted for the supervised colored-liquid demo | It is not measured volume, dead-volume compensation or a working-margin decision; do not silently label it WORKING_VERIFIED |
| SF bottom valve | XL430/U2D2 identity, commissioned raw positions and fixed profile documented | Current register observation, unchanged coupling/calibration, leak/route verification and physical authorization |
| Column bottom valve | Reassembled HOME/CLOSED/OPEN control path documented | Current reference, fluidic behavior, suitable measured drain duration and relevant remaining thermal confirmation |
| Carousel | 40 positions, manual reference, supervised dry movement confirmed; no HOME sensor | Fresh manual alignment for the exact recovery/rinse/collection position; no absolute reference inferred after reset |
| Mixers | SF fixed ON/OFF path tested; Reactor mixer documented as unconnected | Current stopped states; no percentage/RPM mapping or sensor-confirmed rotation inferred |
| Flush | Software volumes/drain/tube margin are explicit plan inputs | Verified rinse volumes, safe tube margin, drain timing and actual cleaning assessment; software completion does not prove cleaning |
| Live adapter ports/timeouts | Existing adapters and prior commissioned interfaces documented | Confirm installed device identity and explicit timing/profile settings; do not automatically select/open a port or reuse a historical connection |

These missing physical facts do not prevent software preparation. No unconfirmed
value is filled by this milestone. Before every powered physical test, the current
hardware instructions require a new user confirmation of motor-power readiness.

## Verification and next boundary

Tests use existing adapters over fake transports only. They cover configuration
round trips/strict refusal, unknown startup, request freshness/worker identity,
partial state, connection/capability changes, complete runs with retained continuity,
unknown-state recovery, failed recovery input, transport fault/restart with preserved
journal and owner, mandatory flush, and a new completed run.

The next decision is how to acquire and attribute real current references and
which demo/working configuration is physically approved. This preparation does
not authorize live startup, EEPROM changes, firmware upload, physical recovery,
physical flushing, unattended execution or a main merge. Flow animation remains
deferred by the user.
