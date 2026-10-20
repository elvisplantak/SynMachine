# P1 production motion checkpoint

This document records the implemented P1 motion foundation and its focused
Arduino/Serial integration.
Confirmed physical facts remain canonical in `HARDWARE_CONFIRMATIONS.md`, and
wire semantics remain canonical in `LABFORGE_SERIAL_PROTOCOL_V1.md`.

## Implemented boundary

- `PUMP_HOME` accepts exactly `{"pump":"P1"}`.
- P1 software position is untrusted after every controller boot.
- Only successful explicit homing establishes trusted coordinate `0`.
- Absolute moves require trusted position, accept `1..20500`, and reserve
  coordinate `0` exclusively for the homing operation.
- Preparation performs no pin writes. `start()` performs the first `DIR` write,
  allowing the Serial runtime to emit `STARTED` first.
- Motion is cooperative; `update(micros())` advances at most one complete pulse
  or one state transition while leaving Serial processing available.
- STEP timing uses the dry-confirmed P1 values: a narrowly bounded primitive
  drives exactly 20 us HIGH and returns LOW before `update()` returns, while
  rising edges are scheduled no closer than 1500 us. The first STEP rise is
  delayed at least 5 us after every DIR write, matching the installed DM542T
  manufacturer's minimum DIR setup time.
- HOME search uses `DIR=LOW` and, under the user's accepted supervised-demo
  assumption, is bounded to 20,500 pulses. This is not fail-safe against a
  missing HOME signal from an arbitrary initial position.
- HOME must remain continuously active or released for 30 ms before the state
  machine accepts the transition. Motion pauses during this stability window,
  so a one-sample glitch cannot establish trusted zero.
- An initially active HOME at untrusted boot is confirmed without first moving
  away. A repeated home from trusted zero first holds STEP inactive and checks
  HOME stability. Stable active HOME permits release by no more than 400 pulses
  before searching again; stable inactive HOME contradicts trusted zero and
  fails closed without a STEP rising edge toward HOME.
- The production runtime calls nonblocking `update()` regularly at a
  cadence materially shorter than 30 ms. The sampling-based stability policy
  is not meaningful if runtime scheduling leaves gaps comparable to its full
  interval. Serial output is therefore queued and handed to `HardwareSerial`
  in fixed chunks no larger than the space reported by `availableForWrite()`,
  with controller servicing between chunks.
- A move away from trusted zero tolerates HOME while performing a
  stability-confirmed release, bounded by the validated absolute target rather
  than the repeated-homing release allowance. It cannot complete while HOME
  remains active, including when the requested target is inside the physical
  release zone.
- Missing HOME or stuck HOME stops STEP LOW and invalidates position trust.
  Unexpected HOME activation during an absolute move first pauses STEP and must
  remain active for the full 30 ms stability interval before it fails closed;
  a shorter glitch resumes without catch-up pulses or shortened edge spacing.
- Local abort forces STEP LOW, stops future pulses, returns the controller to
  idle, and invalidates position trust whenever execution had started. Abort
  after completion is a no-op and preserves the completed trusted position. A
  lifecycle adapter stores a deliberate post-`STARTED` abort as `FAILED` with
  `COMMAND_ABORTED` and `execution_started:true`.
- No ENA behavior is implemented or inferred.

The DM542T timing value is taken from the manufacturer's `DM542T(V4.0) Digital
Stepper Drive User Manual`, which specifies a minimum 5 us DIR advance before
PUL in single-pulse mode:
`https://www.omc-stepperonline.com/download/DM542T_V4.0_user_manual.pdf`.

## Demo homing limitation

P1/P2 have no independent protection capable of stopping travel if HOME fails.
The user accepted continued automatic startup homing for this supervised demo
because all HOME switches were manually tested and the operator remains at the
power switch. Consequently the implementation retains a 20,500-pulse search
bound from an untrusted start. That bound limits software activity but cannot
guarantee prevention of mechanical overtravel. Firmware upload and physical
execution remain separate approval gates, and unattended or production use is
not approved by this design.

## Fluidic ownership

P1 homing can aspirate fluid. Firmware owns homing direction, pulses, HOME
handling, bounds, and low-level failure. Backend owns route selection and must
configure a physically safe route before sending `PUMP_HOME`. The Arduino must
not infer or autonomously move valves as part of pump homing.

## Integrated production boundary

`src/main.cpp` instantiates the P1 controller through an Arduino adapter for
confirmed pins STEP D46, DIR D47, and HOME D45. Boot configuration holds STEP
and DIR inactive and does not move the actuator. Only session-validated
`PUMP_HOME` and `PUMP_MOVE_ABSOLUTE_STEPS` commands can cross the motion
boundary.

The runtime emits and caches `ACCEPTED`, serializes `STARTED`, and only after
the caller writes that frame invokes `start()`, whose first physical side
effect is DIR setup. All response and lifecycle frames are handed to Serial in
fixed cooperative chunks while `update()` continues to run, and the cached
terminal `COMPLETED` or `FAILED` frame is emitted the same way. Exact duplicate command
identity replays cached state without motion. `QUERY_STATUS` reports `BUSY`
with the active operation ID while a command is nonterminal, otherwise `IDLE`.

Automated native coverage verifies lifecycle ordering, writer failure, session
rejection, BUSY status, abort semantics, successful HOME completion, bounded
atomic STEP HIGH timing, cooperative Serial transmission under sustained query
traffic, no catch-up pulses, HOME servicing, and duplicate replay. No firmware
from this checkpoint has been uploaded or physically executed.

## AVR SRAM and stack checkpoint

The integrated Mega build uses 2,241 of 8,192 bytes of static SRAM, leaving
5,951 bytes for stack, interrupt frames, and runtime library use. A warning-clean
AVR `-fstack-usage` build without LTO reports the largest individual project
frames as 2,075 bytes for `MessageParser::parse()`, 1,154 bytes for
`NoMotionDispatcher::dispatch()`, and 970 bytes for
`P1CommandRuntime::dispatch()`.

The worst credible current path is a non-command frame entering
`loop() -> P1CommandRuntime::dispatch() -> NoMotionDispatcher::dispatch() ->
MessageParser::parse()`, while the strict lexical validator traverses the
maximum permitted two object levels. Conservatively summing the reported
simultaneous frames gives approximately 5.0 KB, leaving approximately 0.9 KB
before interrupt and runtime-library margin. The motion-update and cooperative
TX paths are small by comparison (`P1MotionController::update()` is 11 bytes
and `loop()` is 18 bytes in this analysis). This is adequate for the current
supervised checkpoint but is a tight margin: future parser, dispatch, cache, or
actuator growth requires another stack analysis and should avoid additional
simultaneously live parsed-message objects.
