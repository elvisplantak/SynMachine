# P1 production motion checkpoint

This document records the implemented, still-disconnected P1 motion foundation.
Confirmed physical facts remain canonical in `HARDWARE_CONFIRMATIONS.md`, and
wire semantics remain canonical in `LABFORGE_SERIAL_PROTOCOL_V1.md`.

## Implemented boundary

- `PUMP_HOME` accepts exactly `{"pump":"P1"}`.
- P1 software position is untrusted after every controller boot.
- Only successful explicit homing establishes trusted coordinate `0`.
- Absolute moves require trusted position, accept the confirmed `0..20500`
  envelope, and reserve target `0` for the homing operation.
- Preparation performs no pin writes. `start()` performs the first `DIR` write,
  allowing the Serial runtime to emit `STARTED` first.
- Motion is nonblocking; `update(micros())` advances a bounded pulse state
  machine while leaving Serial processing available.
- STEP timing uses the dry-confirmed P1 values: 20 us HIGH and 1500 us between
  rising edges.
- HOME search uses `DIR=LOW` and is bounded to 20,500 pulses.
- If HOME is initially active, homing first uses `DIR=HIGH` for no more than 200
  pulses to release it, then searches toward HOME.
- A move away from trusted zero tolerates HOME only during the same bounded
  initial release window.
- Missing HOME, stuck HOME, or unexpected HOME activation stops STEP LOW and
  invalidates position trust.
- No ENA behavior is implemented or inferred.

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
