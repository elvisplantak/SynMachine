# P2 production motion integration

## Scope

This checkpoint extends the reviewed P1 pump motion path to P2 without adding
new motion semantics. P1 and P2 use separate GPIO adapters and separate
controller instances. The Serial runtime selects the instance from the exact
`pump` command argument and still permits only one active command globally.

## Confirmed P2 hardware contract

- STEP: Arduino Mega D48
- DIR: Arduino Mega D49
- HOME: Arduino Mega D44 with `INPUT_PULLUP`
- HOME released: LOW
- HOME active: HIGH
- direction toward HOME: LOW
- direction away from HOME: HIGH
- STEP rising-edge interval: 1500 us
- STEP HIGH pulse: 20 us
- absolute command range: `1..20500` steps

These values come from `HARDWARE_CONFIRMATIONS.md`. P2 has the same confirmed
physical orientation and pump travel model as P1, so it deliberately reuses
`P1MotionController`; the class name is historical, while each instance owns
independent state and position trust.

## Lifecycle and safety behavior

- Parsing and preparation remain side-effect-free.
- The complete `STARTED` frame is handed to the cooperative Serial transport
  before the selected controller may write DIR or STEP.
- A successful HOME establishes trusted zero only for the selected pump.
- An absolute move is rejected while that pump's position is untrusted.
- HOME stability, timeout, abort, STEP pulse width, and no-catch-up behavior are
  identical to the reviewed P1 path.
- Firmware never infers a fluid route. Sending `PUMP_HOME` asserts that the
  backend/operator has already established a verified safe route.

## Runtime cadence

Both controller instances must be serviced frequently from the production
loop. The selected active instance is updated through the shared command
runtime; no blocking delay is added for HOME stability or motion scheduling.

## Checkpoint boundary

Native tests and Mega compilation verify this software integration. Upload,
Serial Monitor use, and physical P2 movement remain a separate supervised
checkpoint.
