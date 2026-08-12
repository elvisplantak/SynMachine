# Carousel production motion design

## Confirmed hardware contract

The carousel uses the Arduino Mega and the StepperOnline CL57T closed-loop
driver. The confirmed control mapping is STEP D8 and DIR D9; ENA is not
connected. The physically tested logical travel direction is `DIR=HIGH`.
Physical clockwise/counter-clockwise naming is intentionally unspecified.

The carousel has 40 tube positions and no HOME sensor. The confirmed scale is
10,000 STEP pulses per output revolution, therefore 250 pulses (9 degrees) per
tube position. The accepted smooth one-position profile is:

- 20 us bounded STEP HIGH pulse;
- 6,000 us start and stop rising-edge interval;
- 1,200 us cruise rising-edge interval;
- 125-pulse cubic smoothstep acceleration and 125-pulse deceleration; and
- no catch-up pulse burst when runtime servicing is late.

## Position trust and commands

`CAROUSEL_SET_REFERENCE` accepts exactly one integer `position` in `1..40`.
It records an operator-aligned tube position and emits no DIR or STEP side
effect. It is required after every controller boot and after any motion abort
or other loss of pulse accounting.

`CAROUSEL_MOVE_TO_POSITION` accepts the same position range. It moves only in
the confirmed `DIR=HIGH` logical-forward direction, including wrap from
position 40 to position 1. A request for the already current position is
rejected rather than reported as newly executed motion.

Both commands use the normal LABFORGE/1 operation identity and truthful
`ACCEPTED -> STARTED -> terminal` lifecycle. A move cannot produce DIR or STEP
side effects until the complete STARTED frame has been handed to the Serial
transport. Deliberate abort after STARTED produces `COMMAND_ABORTED` and
invalidates carousel position trust.

## Column outlet interlock

Carousel motion is fail-closed unless firmware has trusted
`COLUMN_BOTTOM_VALVE` position state equal to the confirmed CLOSED position
(4 degrees / 889 steps from HOME). Otherwise the request is rejected with
`CAROUSEL_COLUMN_VALVE_NOT_CLOSED` and emits no carousel GPIO side effect.

The backend still owns orchestration: it must close the column outlet before
requesting carousel motion and reopen it when the higher-level route requires
that. Firmware does not contain a compound fraction-collection workflow.

## AVR resource checkpoint

The integrated warning-clean Mega build uses 38,246 of 253,952 bytes of flash
and 2,889 of 8,192 bytes of static SRAM. A warning-enabled AVR
`-fstack-usage` build without LTO reports the largest individual project frames
as 2,075 bytes for `MessageParser::parse()`, 1,055 bytes for
`MessageParser::recoverErrorCorrelation()`, 972 bytes for
`P1CommandRuntime::dispatch()`, and 522 bytes for
`writeCommandLifecycle()`.

The worst credible simultaneous project path remains `loop() ->
P1CommandRuntime::dispatch() -> MessageParser::parse()` with the strict JSON
validator's maximum two permitted object levels. Conservatively summing the
reported project frames gives approximately 3.8 KB, leaving approximately
1.5 KB after static data before interrupt and runtime-library margin. Carousel
motion servicing and its cubic interval calculation have small frames and do
not nest under parsing. This remains acceptable for the supervised v1
checkpoint and must be refreshed after further parser, cache, protocol, or
actuator growth.

## Deliberately deferred

This checkpoint does not add a HOME sensor, absolute encoder readback, CL57T
alarm input, EEPROM position persistence, automatic tube alignment, UI service
tuning, backend orchestration, firmware upload, or physical execution. Because
there is no carousel HOME sensor, software-completed pulse accounting is not
independent proof of physical tube alignment.
