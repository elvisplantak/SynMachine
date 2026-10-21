# Supervised Reactor/SF wet-test preparation — 2026-10-21

Software preparation only. No real Serial port has been opened, firmware uploaded
or actuator commanded at this checkpoint. Existing live profile/state bindings,
credentials, journals, ownership and previously installed e2e9d3c remain unchanged.
Recovery artifacts are not accessed or modified.

## Owner request and current preparation

- One nominal full-stroke 20 mL from B1 colored water to Reactor.
- Reactor -> P2 -> SF; mix for20s at an explicitly approved600 pulses/s trial.
- SF bottom -> P2 -> Waste. Column and carousel are excluded.
- P1 priming: two5mL S -> P1 -> Waste cycles approved by the owner.
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
priming/transition review. P1 priming uses the approved two5mL cycles. The earlier
P2-priming concept returns liquid Reactor -> P2 -> Reactor twice, but no stroke
volume for that step was supplied for this test; do not silently invent it or
omit it when claiming all priming protocols completed. The wet runner/plan still
needs that concrete preparation. SF aspiration must retain a required Close,
and the20s mixer operation a required Stop. On failure or unknown result retain
ownership and evidence; no ad hoc retry, re-home, parking or state replacement.

The requested subsequent flushing test remains a separate future task. The live
profile's null recovery/flush plans must not be replaced to bypass maintenance.
