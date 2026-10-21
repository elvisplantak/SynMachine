# First supervised Reactor/SF wet test — 2026-10-21

Prepared execution only; no wet test or new device connection has occurred.
Installed firmware is the flash-verified dc7a53f artifact. This test uses the
explicit full-stroke command and fixed ~600 pulses/s mixer trial; nominal mL
are commanded step accounting, not measured delivered liquid.

## Operator inputs

- B1: colored water. B2: ordinary water, unused in this test.
- S was initially empty; the owner now confirms ordinary water and submerged intake.
- Reactor and SF are empty; SF mixing element is free.
- P1 priming approved: two cycles of 5 mL, S -> P1 -> Waste.
- P2 priming approved: two cycles of 5 mL, Reactor -> P2 -> Reactor, after filling.
- Motor power remains last confirmed OFF. Fresh powered readiness is pending.
- Before execution, freshly confirm open/nonsealed Waste with both discharge
  paths above the liquid, enough capacity for the test, B1 intake submerged,
  free SF element in the accepted DIR=LOW direction, and Reactor mixer stopped.
  Include the separately powered SF servo in powered readiness.

## Exact sequence

1. Fresh HELLO/status and read-only SF inspection under exclusive bundle locks;
   require trusted idle controller, advertised full-stroke capability and SF
   CLOSED with torque disabled. No assumed pump/valve/Column/carousel references.
2. Command mixer STOP and SF CLOSE. HOME V5 and select 180 (Waste) first,
   isolating the Column inlet; then HOME V1,V2,V4,V6,V3,V7,V8 with pumps stationary.
3. Select each pump's approved Waste route, HOME it once, then dispense to 20500
   (empty). Pump HOME may aspirate air through the required open Waste air gap.
4. Twice: S -> P1 aspirate 5 mL (15375), select Waste, dispense to 20500.
5. B1 -> P1 one explicit 20500-pulse full aspiration, select Reactor, dispense to 20500.
6. Twice: V3=90, aspirate 5 mL from Reactor into P2 (15375) and dispense to 20500
   back into Reactor through the same confirmed bidirectional connection.
7. Reactor -> P2 full aspiration, select SF top, dispense to 20500.
8. SF mixer START, monotonic 20 s wait, required STOP even if Start/wait fails.
9. With SF CLOSED, select SF-bottom aspiration route. OPEN, full P2 aspiration,
   required CLOSE even if aspiration fails or Arduino disconnects.
10. Only after successful CLOSE select P2 Waste, dispense to 20500, and select
    P1 Waste. Successful final pumps are both 20500; all V1-V8 positions are 90/180,
    SF CLOSED and mixer stopped. No actuator remains at HOME, so no additional
    terminal HOME release is needed.

Approved destination orders are unchanged: see firmware/HARDWARE_CONFIRMATIONS.md.
P2 return priming reverses flow through the Reactor connection; it does not add
an unconfirmed valve angle. No Column actuator or carousel command is present;
Column position and carousel reference remain unknown. Flushing is not included.

## Execution boundaries and evidence

Implementation: backend/app/wet_reactor_sf.py. Default invocation only prints the
fixed plan; it neither loads the live state nor opens a device. Fixed plan SHA256:
`f29259c9735d79b5d073acc8d4d567418540bb397343b477975a6d0f683171ce`.

Real execution requires explicit arming flags, fresh operator declarations and
RUN_WET_TEST input before connection. It accepts only the existing bound
recipes-live-v1 state directory and unchanged live profile digest, with a pristine
bundle. The existing bundle process locks, durable HardwareOwnership, Arduino/SF
journals and monotonic wait journal are reused. No profile/state reprovisioning,
new schema, credential read, API activation or Recipes planner change occurs.

A single retained lease covers bootstrap through final commands. Signals request
Stop at command boundaries; a running pump/valve atomic command finishes before
continuation stops. A mixing wait is interruptible. Required mixer Stop/SF Close
retain their original follow-up semantics, and SF Close uses its independent
adapter after Arduino loss. No reconnect/retry, re-HOME, parking, or dispensing
cleanup is added after failure. Physical emergency stopping remains motor power
removal by the supervising operator.

Fault, Stop, unknown outcome, logging failure or incomplete wait retains ownership
and blocks another run. Even success does not permit replaying this first-test
runner or provisioning replacement state. The subsequent flushing test needs a
separately prepared procedure; null live Recovery/Flush plans stay unchanged.

Each execution creates a new private evidence directory with the pinned plan and
fsync'd event log, alongside the existing command journals. Completion reports
command outcomes only; request operator observations separately before claiming
physical acceptance. SIGKILL, host power loss or hardware power removal cannot
guarantee a software follow-up; retained durable evidence must be reconciled.

## Verification

71 fake-transport regression cases passed, including a transport fault at each
of 52 Arduino command positions, uncertain SF Open/Close, mandatory follow-ups,
Arduino disconnect during SF aspiration, Stop after SF Open, mixer timer/host
interruptions, durable intent before bytes, global owner retention, single-use
and bundle-lock exclusion. The complete backend suite passed 2010 tests, zero
skipped, and full Ruff passed. Firmware source/HEX is unchanged. No real
transport is used by tests.

## Explicit continuation after the recorded startup failure

Boot 111 failed before liquid priming/transfer. The operator requested completion
of the whole cycle and subsequently approved a diagnostic upload/read-only query
with motor power OFF. Boot 113 reports P1 HOME active in five samples, without
claiming a cause for the previous timeout or creating a trusted position.

The additional --reconcile-startup-timeout entry is only for the exact retained
boot 111 failure. Before a port opens, it compares all 13 Arduino and the one SF
journal rows against wet-01-result.json; any changed history, different failure,
run, lifecycle snapshot, wait or prepared plan is refused. Default pristine-only
execution is unchanged. It persists/fsyncs a separate explicit reconciliation
plan, including the prior evidence hash and unchanged physical-plan hash. Under
the existing bundle locks it uses begin_maintenance for the same blocked owner
and a new local phase; it never deletes a prior record or reconstructs a lease.

Fresh preflight must see p1_home_active=true; it is checked again immediately
before P1 HOME. False/unsupported/changed input aborts without repeating the P1
search. The confirmed Waste setup is re-established through fresh valve HOME
commands before pump initialization. This is an explicitly authorized new
reference attempt, not automatic retry or resumption of interrupted bytes.
All original mixer Stop/SF Close, no-reconnect, no-automatic-retry and stop-on-error
semantics remain. Even after all requested wet commands succeed, this continuation
retains BLOCKED ownership until the separately prepared flushing test. It does
not mark the previous failure successful or activate ordinary Recipes execution.

New powered readiness and concrete continuation approval remain pending. No new
actuator command follows the boot 111 failure during software preparation.
