# P1 production motion checkpoint

This document records the implemented, still-disconnected P1 motion foundation.
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
- Motion is nonblocking; `update(micros())` advances a bounded pulse state
  machine while leaving Serial processing available.
- STEP timing uses the dry-confirmed P1 values: 20 us HIGH and 1500 us between
  rising edges. The first STEP rise is delayed at least 5 us after every DIR
  write, matching the installed DM542T manufacturer's minimum DIR setup time.
- HOME search uses `DIR=LOW` and, under the user's accepted supervised-demo
  assumption, is bounded to 20,500 pulses. This is not fail-safe against a
  missing HOME signal from an arbitrary initial position.
- HOME must remain continuously active or released for 30 ms before the state
  machine accepts the transition. Motion pauses during this stability window,
  so a one-sample glitch cannot establish trusted zero.
- An initially active HOME at untrusted boot is confirmed without first moving
  away. A repeated home from trusted zero may release by no more than 200
  pulses before searching toward HOME again.
- A move away from trusted zero tolerates HOME only while performing a bounded,
  stability-confirmed release. It cannot complete while HOME remains active,
  including when the requested target is inside the physical release zone.
- Missing HOME, stuck HOME, or unexpected HOME activation stops STEP LOW and
  invalidates position trust.
- Local abort forces STEP LOW, stops future pulses, returns the controller to
  idle, and invalidates position trust whenever execution had started. Abort
  after completion is a no-op and preserves the completed trusted position.
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
guarantee prevention of mechanical overtravel. GPIO integration, upload, and
physical execution remain separate approval gates, and unattended or
production use is not approved by this design.

## Fluidic ownership

P1 homing can aspirate fluid. Firmware owns homing direction, pulses, HOME
handling, bounds, and low-level failure. Backend owns route selection and must
configure a physically safe route before sending `PUMP_HOME`. The Arduino must
not infer or autonomously move valves as part of pump homing.

## Deliberately not connected yet

The controller is not instantiated by `src/main.cpp`; no Arduino pin adapter or
Serial command dispatcher invokes it. This preserves the repository's current
no-motion production entry point while the first actuator checkpoint is
reviewed. The next integration slice must add lifecycle serialization, cache
ownership, session-validated command dispatch, an Arduino P1 pin adapter, and
tests proving `STARTED` precedes the first driver-affecting write.

No firmware from this checkpoint has been uploaded or physically executed.
