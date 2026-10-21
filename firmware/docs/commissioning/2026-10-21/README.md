# Supervised Reactor/SF wet-test preparation — 2026-10-21

Original software-preparation checkpoint (before the upload recorded below).
No real Serial port had been opened, firmware uploaded
or actuator commanded at this checkpoint. Existing live profile/state bindings,
credentials, journals, ownership and previously installed e2e9d3c remain unchanged.
Recovery artifacts are not accessed or modified.

## Owner request and current preparation

- One nominal full-stroke 20 mL from B1 colored water to Reactor.
- Reactor -> P2 -> SF; mix for20s at an explicitly approved600 pulses/s trial.
- SF bottom -> P2 -> Waste. Column and carousel are excluded.
- P1 priming: two 5 mL S -> P1 -> Waste cycles approved by the owner.
- B2 contains ordinary water, S is empty. Filling S or revising the preparation
  remains unresolved; an empty S source must not be treated as successful priming.
- Owner reports SF empty, mixing element free, Waste clear and USB connected;
  machine motor power OFF. Reactor-empty and full wet readiness need confirmation.

## Prepared implementation

The explicit PUMP_ASPIRATE_FULL_STROKE command accepts only pump P1/P2 and requires
trusted empty coordinate20500 with HOME inactive at preparation. It uses existing
bounded HOME-direction timing and confirmation, while rejecting stably early
HOME as PUMP_HOME_SWITCH_UNEXPECTED. At20500 pulses the existing motionless final
HOME wait/stability budget applies. Missing HOME fails without an extra pulse.
The operation completes at trusted zero, followed by a separate ordinary dispense
to20500; ordinary move-zero remains forbidden. This is not volume measurement.

The new capability is advertised in the unchanged464-byte HELLO buffer; the host
accepts up to10 capabilities. The452-byte worst HELLO fits the512-byte payload
contract. Older firmware cannot receive this command or cause implicit HOME
fallback. New firmware requires the updated host parser. Recipes' ordinary
zero-target planner and API behavior are unchanged; this checkpoint prepares
the explicit commissioning command, not a new UI raw-actuator recipe feature.

The SF interval is1667us (~599.88 pulses/s), rounded down in rate from the owner's
600 pulses/s request. Existing D6/D7, DIR=LOW,20us pulse width and5us direction
setup are unchanged. Start/Stop, retained ownership, required follow-up Stop,
protected SF Close, intent-before-bytes and no-retry semantics remain applicable.

## Checks and artifact

- Complete warning-enabled native suite:220 passed (previous211 plus9 new).
- Separate mixer-discovery native profile:6 passed.
- Complete backend suite before two new host regressions:1937 passed.
- Focused parser/Serial/full-stroke host suite including those new cases:131 passed.
- Backend Ruff and Git whitespace checks passed.
- Mega2560 compiled only:41570 flash bytes,3176 static SRAM bytes.
- Previous build:41056 flash bytes,3148 static SRAM bytes; delta+514/+28.
- New full-stroke tests cover strict schemas/preflight, both pump selections,
  STARTED ordering, no-motion duplicate replay, full out/back count, missing/early
  HOME, glitch resume, abort invalidation and HELLO size. Existing native tests
  retain coverage of late HOME timing, wraparound, session replacement and cache.
- Exact HEX identity and pending-upload state: [prepared-artifact.json](prepared-artifact.json).
- Previous installed HEX matched its original upload hash; a private rollback
  copy and an exact prepared upload copy are retained under /tmp, not published.

No physical capability or success is established by these tests. Main remains
unchanged; this software is on commissioning/full-stroke-wet-test.

## Next physical sequence to review

First obtain explicit firmware-upload authorization while motor power stays OFF.
After verified upload, obtain fresh powered readiness and inspect current state
without reusing old boot references. Establish only the route/pump references
needed for this test; Column bottom and carousel must remain uncommanded.
Pump initialization HOME requires the confirmed Waste air-gap route, followed by
emptying to20500. No pump HOME is substituted into a normal liquid transfer.

Before wet execution, finish S-water/Reactor-empty preparation and the exact
priming/transition review. P1 priming uses the approved two 5 mL cycles. The earlier
P2-priming concept returns liquid Reactor -> P2 -> Reactor twice, but no stroke
volume for that step was supplied for this test; do not silently invent it or
omit it when claiming all priming protocols completed. The wet runner/plan still
needs that concrete preparation. SF aspiration must retain a required Close,
and the20s mixer operation a required Stop. On failure or unknown result retain
ownership and evidence; no ad hoc retry, re-home, parking or state replacement.

The requested subsequent flushing test remains a separate future task. The live
profile's null recovery/flush plans must not be replaced to bypass maintenance.

## Authorized upload completed — 2026-10-21

The owner explicitly approved uploading prepared commit
`dc7a53fcdd93315965bf82ba143bf4def17688e7` with motor power OFF. The exact
prepared HEX above was written through avrdude to the confirmed Arduino by-id
port; device signature was `0x1e9801`, and all 41570 flash bytes were verified
(exit 0). This replaces the previously installed e2e9d3c image.

No application Serial monitor, HOME, actuator command, wet run, EEPROM
provisioning or fuse write was performed. Motor power remains last reported OFF.
Full-stroke aspiration and the 600 pulses/s mixing trial are not physically
verified by this upload. The original preparation JSON remains a historical
pre-upload snapshot. Current upload evidence is
[upload-verification.json](upload-verification.json) and [upload.log.txt](upload.log.txt).

Next: finish the wet plan and resolve S-water/Reactor-empty readiness and P2
priming volume. Obtain fresh powered readiness before execution; keep motor
power OFF during preparation. Use the updated backend source for the 10-capability
HELLO; do not reuse old boot references or silently fall back to HOME.

## Wet plan finalized after operator clarification

The owner confirmed S filled/intake submerged and Reactor empty, and approved
two 5 mL Reactor-to-P2-to-Reactor priming cycles after filling. See the
[exact wet-test plan](WET_TEST_PLAN.md) for the fixed supervised runner,
required Close/Stop, existing-bundle exclusion and remaining powered readiness.
These updates supersede the unresolved preparation items above; physical
execution has not started.

Verification of the finalized runner: 71 focused and 2010 complete backend
tests passed, zero skipped; full backend Ruff passed. Firmware source and
uploaded HEX are unchanged. No real port opened during this preparation.

## First attempt halted during startup — boot 111

The owner freshly approved the full test and powered readiness. P1 ordinary
startup HOME failed with PUMP_MOTION_TIMEOUT before priming or liquid transfer.
No automatic continuation/retry occurred and existing ownership remains BLOCKED.
[Result and journal snapshot](wet-01-result.json), [events](wet-01-events.jsonl).
The operator subsequently corrected the HOME-pressed report to possibly only
near HOME. Read-only input diagnostics are being prepared; no new firmware
upload, hardware connection or owner release has followed the failure.

## Read-only pump HOME diagnostic firmware prepared

QUERY_STATUS now optionally samples P1/P2 HOME inputs through their existing
IO read methods. This changes no pin, polarity, motion limit/timing, trust or
command execution. A sample does not establish a pump zero. The input may be
false if the mechanism is merely near the switch; the operator's corrected
observation supersedes the earlier pressed-HOME claim.

Verification: 224 complete native tests (8 focused), 6 mixer-profile tests, 2025
complete backend tests (112 focused STATUS/Serial), Ruff and Mega passed.
Mega 42062 flash/3184 static SRAM (+492/+8 versus installed); STATUS scratch
stack buffer grows 66 bytes. Warning-enabled native build has no warnings; Mega
reports 4 unused-parameter warnings in upstream Arduino new.cpp, none in project
source. Exact pending image: [artifact](pump-home-diagnostics-artifact.json).
The installed artifact remains dc7a53f; no new real port has been opened.

Proposed authorized observation: [five read-only samples](observe-pump-home.py.txt).
It locks the existing bundle, requires the exact retained BLOCKED owner, sends
only HELLO/QUERY_STATUS, closes the port and verifies the bundle observation
unchanged. It never obtains a motion lease, changes journals, releases the owner
or creates a position reference. Upload and real observation each need explicit
authorization; motor power must be OFF. No full-cycle resumption is implied.

## Authorized diagnostic upload and five observations

Motor power OFF was freshly confirmed. Firmware 5d09cb8 flash verified 42062
bytes. Boot 113 reads P1 HOME=true and P2 HOME=false in five samples; no
actuator commands or state repair. The blocked owner is unchanged.
[Upload verification](pump-home-diagnostics-upload-verification.json),
[upload log](pump-home-diagnostics-upload.log.txt),
[raw observations](pump-home-observation.json). These supersede pending-upload
status above. The timeout cause is not inferred from a later raw-input level.

## Narrow continuation prepared

The extra startup-reconciliation entry accepts only the original recorded
pre-liquid failure, requires current active P1 HOME twice and retains the
original owner until the later flushing test even on wet-cycle success.
See [the continuation plan](WET_TEST_PLAN.md#explicit-continuation-after-the-recorded-startup-failure).
It never clears the old FAILED command, moves with an inactive initial P1
HOME input or selects a replacement state bundle. No new motion has occurred.

Continuation verification: 12 new fake cases and all 2037 complete backend
tests passed, Ruff and whitespace checks passed. Installed firmware/HEX is
unchanged since the verified diagnostic upload. Fresh powered readiness and
explicit continuation approval remain pending.
