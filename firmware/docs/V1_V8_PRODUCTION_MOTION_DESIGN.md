# V1-V8 production motion design

## Scope

This checkpoint connects confirmed V1-V8 STEP, DIR, and HOME wiring to the
LABFORGE/1 runtime. It does not authorize upload or physical motion. The machine
remains a supervised demo with the operator present at the power switch.

## Commands and coordinates

- `VALVE_HOME` accepts exactly one valve from `V1` through `V8`.
- `VALVE_SET_POSITION` accepts exactly one valve and `0`, `90`, or `180`.
- `0` is HOME/closed, `90` is k1-k3, and `180` is k1-k2.
- 400 STEP pulses represent 90 degrees; 800 represent 180 degrees.
- Every valve starts untrusted. Only successful homing establishes trusted
  zero; moves to 90 or 180 are rejected while untrusted.

## Motion and HOME policy

- STEP HIGH is a bounded 20 us pulse; DIR setup is at least 5 us.
- The initial rising-edge interval is 2,000 us. This is a conservative software
  profile, not a new physical calibration, pending the first supervised
  V1-V8 production-runtime test.
- HOME released is LOW and active is HIGH with `INPUT_PULLUP`.
- HOME arrival, release, and trusted-zero consistency use a 30 ms stability
  interval while STEP is inactive.
- A transient LOW at trusted zero never authorizes a pulse toward HOME.
  Persistent LOW fails closed and invalidates trust.
- Search has a software timeout after 1,600 pulses. This limits command
  execution time but is not established as a physically safe missing-HOME
  travel bound and must not be described as mechanical protection. The
  supervised-demo acceptance of missing-HOME overtravel risk remains a user
  decision. Missing/inconsistent HOME, stuck HOME, abort, or motion failure
  invalidates trust.
- Late servicing emits no catch-up burst and never shortens rising-edge spacing.

The production loop must service active controllers at a cadence materially
shorter than 30 ms and must not add blocking delays. Lifecycle ordering remains
`ACCEPTED -> STARTED -> terminal`, with the complete `STARTED` frame handed to
Serial before the first DIR/STEP side effect. Only one physical command may
execute globally at a time.

## AVR SRAM and stack checkpoint

The integrated Mega build uses 2,676 of 8,192 bytes of static SRAM. A
warning-enabled AVR `-fstack-usage` build without LTO reports the largest
individual project frames as 2,075 bytes for `MessageParser::parse()`, 1,055
bytes for `MessageParser::recoverErrorCorrelation()`, 972 bytes for
`P1CommandRuntime::dispatch()`, and 522 bytes for
`writeCommandLifecycle()`.

The runtime passes its already parsed result to
`NoMotionDispatcher::dispatchParsed()` instead of parsing a non-command frame a
second time while the first parsed result is still live. The worst credible
simultaneous project path is therefore `loop() -> P1CommandRuntime::dispatch()
-> MessageParser::parse()` while the strict validator traverses the maximum
permitted two object levels. Conservatively summing the reported frames gives
approximately 3.8 KB, leaving approximately 1.7 KB after static data before
interrupt and runtime-library margin. Motion update and cooperative transport
paths are much smaller. This margin is acceptable for the supervised v1
checkpoint, but it must be refreshed after future parser, cache, protocol, or
actuator growth.
