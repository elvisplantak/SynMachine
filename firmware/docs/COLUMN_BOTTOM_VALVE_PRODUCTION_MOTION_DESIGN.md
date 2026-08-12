# COLUMN_BOTTOM_VALVE production motion design

## Scope

This checkpoint connects the confirmed COLUMN_BOTTOM_VALVE STEP, DIR, and HOME
wiring to the LABFORGE/1 runtime. It does not by itself authorize firmware
upload or physical motion. The machine remains a supervised demo with the
operator present at the power switch; unattended and production operation are
out of scope.

## Commands and coordinates

- `COLUMN_BOTTOM_VALVE_HOME` accepts an exactly empty arguments object.
- `COLUMN_BOTTOM_VALVE_SET_POSITION` accepts exactly one integer
  `position_degrees`, restricted to `4` (CLOSED) or `94` (OPEN).
- HOME is software coordinate zero. CLOSED is 889 pulses from HOME and OPEN is
  20,889 pulses from HOME, derived from the confirmed 80,000 pulses per output
  revolution.
- Position trust starts untrusted after boot. Only successful homing establishes
  trusted zero; positioning is rejected while untrusted.
- `HOME` completes at the switch. Moving to the intentional 4-degree CLOSED
  offset is a separate truthful positioning command.

## Motion and HOME policy

- HOME D10 is released LOW and active HIGH.
- STEP is D12, DIR is D13, toward HOME is DIR LOW, and away is DIR HIGH.
- STEP HIGH is a bounded 20 us pulse; DIR setup is at least 5 us.
- Consecutive STEP rising edges are separated by at least the physically
  confirmed 1,000 us interval. Late servicing emits no catch-up burst.
- HOME arrival, release, and trusted-zero consistency are stability-checked for
  30 ms while STEP remains inactive.
- A transient inactive sample at trusted zero never authorizes movement toward
  HOME. A persistent inconsistency, stuck HOME, unexpected HOME, timeout, or
  local abort fails closed and invalidates position trust.
- Search stops after 80,000 pulses. This bounds software execution but is not a
  claim of independent mechanical protection or a proven safe missing-HOME
  distance. For this supervised demo, the HOME switch is treated as functional,
  the operator remains at the power switch, and the missing-HOME overtravel risk
  is accepted under the same user-approved assumption as P1/P2 and V1-V8.

The production loop must service `update()` at a cadence materially shorter
than the 30 ms stability interval and must not add blocking delays. Lifecycle
ordering remains `ACCEPTED -> STARTED -> terminal`, with the complete `STARTED`
frame handed to Serial before any DIR or STEP side effect. Only one physical
command may execute globally at a time.

## AVR resource checkpoint

The integrated Mega build uses 36,710 of 253,952 bytes of flash and 2,762 of
8,192 bytes of static SRAM. The warning-clean AVR build uses the same accepted
parser/dispatch call structure as the V1-V8 checkpoint. Its worst credible
simultaneous project path remains approximately 3.8 KB; the column controller
does not add a large nested stack frame to that path. Static SRAM increased by
86 bytes from the accepted V1-V8 checkpoint, leaving approximately 1.6 KB after
static data and the conservative credible project stack, before interrupt and
runtime-library margin. This is acceptable for the supervised v1 checkpoint
and must be refreshed after further parser, cache, protocol, or actuator growth.
