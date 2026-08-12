# Hardware confirmations

## Confirmed present physical tubing topology — 2026-07-21

The user explicitly confirmed that the physical tubing was connected according to the approved LabForge v1 target topology. This confirms the tubing connections only; it is not permission for hardware execution and does not confirm leak-tightness, valve actuation, liquid routing, calibration, firmware execution, or safety interlocks.

### Confirmed valve and component connections

- V1: `V1.k1 <-> P1`; `V1.k2 <-> V2.k1`; `V1.k3 <-> V6.k1`.
- V2: `V2.k1 <-> V1.k2`; `V2.k2 <-> shared Waste`; `V2.k3 <-> Reactor R_IN`.
- V3: `V3.k1 <-> P2`; `V3.k2 <-> V7.k1`; `V3.k3 <-> Reactor R_OUT`.
- V4: `V4.k1 <-> V6.k3`; `V4.k2 <-> B1`; `V4.k3 <-> B2`.
- V5: `V5.k1 <-> V8.k3`; `V5.k2 <-> shared Waste`; `V5.k3 <-> Column inlet`.
- V6: `V6.k1 <-> V1.k3`; `V6.k2 <-> shared solvent S`; `V6.k3 <-> V4.k1`.
- V7: `V7.k1 <-> V3.k2`; `V7.k2 <-> SF_TOP_IN`; `V7.k3 <-> V8.k1`.
- V8: `V8.k1 <-> V7.k3`; `V8.k2 <-> SF_BOTTOM_OUT`; `V8.k3 <-> V5.k1`.
- Confirmed SF bottom tubing path: `SF bottom -> SF_BOTTOM_VALVE -> SF_BOTTOM_OUT -> V8.k2`.
- Confirmed Column bottom tubing path: `Column bottom -> COLUMN_BOTTOM_VALVE -> fractions / carousel`.
- There is one shared Waste destination. The Column bottom outlet does not connect to Waste.

### Approved Guided Demo bottom-valve operating rules

- SF is unpressurized and is filled through `SF_TOP_IN` while `SF_BOTTOM_VALVE` is closed.
- `SF_BOTTOM_VALVE` opens only during aspiration from SF and must close before route switching and dispensing.
- `COLUMN_BOTTOM_VALVE` remains closed while the Column is filled and opens only during `COLUMN_FRACTION_COLLECTION`.
- The current Guided Demo sends all nominal SF contents to the Column. This rule does not imply automatic phase detection or verified phase separation.
- These are approved operating rules, not confirmation of actuator wiring, actuation, or execution.

### Confirmed `COLUMN_BOTTOM_VALVE` signal pins and driver type — 2026-08-02

The user explicitly confirmed these physical Arduino signal-pin assignments:

- `COLUMN_BOTTOM_VALVE HOME = D10`
- `COLUMN_BOTTOM_VALVE STEP = D12`
- `COLUMN_BOTTOM_VALVE DIR = D13`

The user also explicitly confirmed that the motor driver is a `DM542T`.

### Confirmed `COLUMN_BOTTOM_VALVE` geared motor and driver setup — 2026-08-06

The user identified the motor as StepperOnline `17HS15-1584S-MG50`, a bipolar
NEMA 17 stepper with an integrated 50:1 planetary gearbox. Manufacturer data
supplied and checked during commissioning specifies:

- rated current per phase: `1.58 A`
- phase resistance: `1.65 ohm`
- phase inductance: `3.2 mH +/-20% at 1 kHz`
- motor step angle: `1.8 degrees`
- gearbox ratio: `50:1`
- gearbox efficiency: `90%`
- maximum permissible gearbox torque: `10 Nm`
- motor leads: `A+ black`, `A- green`, `B+ red`, `B- blue`

The connected `DM542T` is configured for 5 V control input and does not use
the ENA input. On 2026-08-06 its DIP switches were changed, with driver power
off, to:

| Switch | Setting | Purpose |
|---|---|---|
| SW1 | ON | current selection |
| SW2 | OFF | current selection |
| SW3 | ON | current selection |
| SW4 | OFF | half current while idle |
| SW5 | OFF | microstep selection |
| SW6 | OFF | microstep selection |
| SW7 | ON | microstep selection |
| SW8 | ON | microstep selection |

This selects `1.91 A peak / 1.36 A RMS` and `1600 pulses/revolution` at the
motor. With the 50:1 gearbox, the derived nominal output-shaft scaling is:

- `80,000 pulses/output revolution`
- `20,000 pulses/output 90 degrees`
- approximately `4,444 pulses/output 20 degrees`
- approximately `2,222 pulses/output 10 degrees`

The previous driver setting was interpreted as `2.84 A peak / 2.03 A RMS`.
The motor and other energized steppers became too hot to touch comfortably
after roughly ten minutes, so physical testing was stopped and the COLUMN
driver current was reduced before further commissioning. Thermal behavior at
the new setting remains to be verified.

### Confirmed `COLUMN_BOTTOM_VALVE` switch and basic motion — 2026-08-07

The user physically traced and reconfirmed `PUL+ -> D12` and `DIR+ -> D13`.
After resolving a failed Arduino upload/USB-port timeout, bounded motion tests
with the 50:1 gearbox scaling succeeded:

- repeated nominal 10-degree forward/return motion completed successfully
- a nominal 90-degree move using 20,000 STEP pulses completed successfully
- a subsequent nominal 90-degree motion test under the installed mechanical
  load completed successfully
- no unexpected motion behavior was reported during those successful tests

The manually operated HOME switch on D10 was also tested independently with
the motor driver off:

- released: `LOW`
- pressed: `HIGH`
- release after pressing returned cleanly to `LOW`

This confirms basic STEP actuation, output-shaft scaling, and HOME input
polarity. The user also physically confirmed that the return direction used
for the 80-degree move was toward HOME. That move used `DIR=LOW`, therefore:

- direction toward HOME: `DIR=LOW`
- direction away from HOME: `DIR=HIGH`

Longer-duration thermal behavior remains unverified.

### Confirmed `COLUMN_BOTTOM_VALVE` homing sequence and speed limit — 2026-08-07

A complete geared-output test succeeded with the following sequence:

1. move toward HOME with `DIR=LOW`
2. detect D10 `HIGH / ACTIVE` after 2,173 STEP pulses
3. move 20,889 pulses (`94` nominal output degrees) away with `DIR=HIGH`
4. move 20,000 pulses (`90` nominal output degrees) back with `DIR=LOW`
5. finish approximately 4 degrees from HOME with D10 `LOW`

The sequence completed without a firmware-reported HOME or positioning error.
However, at `STEP_INTERVAL_US = 500` the user observed some mechanical shaft or
coupling slip. Therefore `500 us` is not an approved operating interval. The
previously tested and retained commissioning value is:

- `STEP_INTERVAL_US = 1000`
- `STEP_HIGH_US = 20`

The 1,000-us interval is the current confirmed reliable speed for this geared
actuator. Faster operation requires separate mechanical investigation and
revalidation; it must not be inferred from the fact that the motor still turns
at 500 us.

### Confirmed `COLUMN_BOTTOM_VALVE` operating positions — 2026-08-08

The user visually confirmed the functional positions from the HOME reference:

- `OPEN = 94 degrees from HOME`
- `CLOSED = 4 degrees from HOME`

The 4-degree CLOSED offset is intentional: it is just far enough away from HOME
to release the HOME switch. The user explicitly stated that these positions are
visually known and do not require another positioning test. This confirmation
defines the actuator positions; leak testing and fluidic execution remain
pending separately.

These confirmations still do not establish longer-duration thermal behavior
with the 2026-08-06 driver settings, `ENA` wiring or behavior, leak-tightness,
fluidic routing through the valve, independent secondary end protection, or
safe unattended/production execution.

### Confirmed `SF_BOTTOM_VALVE` actuator and connection — 2026-08-04

The user explicitly confirmed that `SF_BOTTOM_VALVE` is actuated by a
`DYNAMIXEL XL430-W250-T`. It is connected to a `U2D2`, and the `U2D2` is
connected directly to the host computer over USB. It is therefore not assigned
Arduino Mega `STEP`, `DIR`, or `HOME` pins.

At the time of this connection-only confirmation, the following remained
unconfirmed and were handled by the later commissioning records below:

- torque-enable policy
- position limits or raw position values
- which commanded position means physically open or closed
- motion speed, profile acceleration, or timeout behavior
- actuator fault handling or loss-of-communication behavior
- successful actuation, leak-tightness, or safe physical execution

### Confirmed `SF_BOTTOM_VALVE` read-only identity and status — 2026-08-08

A powered, read-only scan through the dedicated U2D2 USB adapter confirmed:

- stable host adapter path:
  `/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_FTA2U3CN-if00-port0`
- DYNAMIXEL ID: `2`
- model number: `1060` (`XL430-W250`)
- firmware version: `46`
- baud rate: `57600` (`Baud Rate` register value `1`)
- protocol: DYNAMIXEL Protocol `2.0`
- operating mode: `3` (`Position Control Mode`)

The same read-only observation reported `Torque Enable = 0`,
`Hardware Error Status = 0`, `Present Input Voltage = 12.1 V`,
`Present Temperature = 32 C`, and `Present Position = 2583`. These are
time-specific observations, not permanent operating limits or position
semantics. No register was written and no actuator motion was requested.

This does not yet confirm the production torque-enable policy, profile
velocity or acceleration, bounded motion behavior, raw OPEN/CLOSED positions,
or safe physical actuation.

### Confirmed `SF_BOTTOM_VALVE` motion and position calibration — 2026-08-08

The user visually observed and explicitly confirmed successful bounded motion
of the `XL430-W250-T` on DYNAMIXEL ID `2`. Motion in both directions completed
without impact, slipping, or unusual sound. The user also confirmed that the
test speed was appropriate.

After iterative visual alignment, the stable read-only position observed with
torque disabled was explicitly accepted as the calibrated closed position:

- `CLOSED = 2559` raw position units
- the selected direction from `CLOSED` toward `OPEN` is the positive raw
  position direction
- `OPEN = 3697` raw position units (`2559 + 1138`, nominally 100 degrees)
- confirmed commissioning profile: `Profile Velocity = 20`
- confirmed commissioning profile: `Profile Acceleration = 1`

The final 100-degree OPEN/CLOSED sequence was executed twice with a two-second
OPEN dwell and was visually confirmed by the user both times. The measured
OPEN positions were `3677` and `3678` while moving toward the commanded
`OPEN = 3697`. After torque disable, the stable observed closed-side position
was approximately `2574` while the calibrated command remains
`CLOSED = 2559`. Both repetitions completed without impact, slipping, unusual
sound, or a reported hardware error. The two-second dwell was a commissioning
test parameter and is not yet a production timing requirement.

The `CLOSED` value is tied to the current physical coupling and alignment of
this actuator. Mechanical disassembly, horn/coupling adjustment, actuator
replacement, or position-reset changes require recalibration before automatic
operation. The production implementation must still enforce position bounds,
communication timeout behavior, hardware-error checks, and torque disable on
failure.

### Confirmed V1-V8 valve position semantics — 2026-08-04

The user reconfirmed the previously documented intended position semantics for
the motorized three-port valves V1-V8:

- `0 degrees = closed`
- `90 degrees = k1 <-> k3`
- `180 degrees = k1 <-> k2`

This confirms the intended logical position mapping. It does not yet confirm
that any individual valve physically reaches the commanded position, uses the
expected direction or step count, or provides the expected fluidic route.

### Arduino pin commissioning — updated 2026-08-05

The available partially outdated wiring notes suggested the following map.
Controlled motor and manual HOME-switch testing subsequently confirmed all
listed entries, with detailed pump confirmation recorded below:

| Actuator | STEP candidate | DIR candidate | HOME candidate |
|---|---:|---:|---:|
| V1 | D22 confirmed | D23 confirmed | D39 confirmed |
| V2 | D24 confirmed | D25 confirmed | D38 confirmed |
| V3 | D26 confirmed | D27 confirmed | D43 confirmed |
| V4 | D28 confirmed | D29 confirmed | D40 confirmed |
| V5 | D30 confirmed | D31 confirmed | D41 confirmed |
| V6 | D32 confirmed | D33 confirmed | D42 confirmed |
| P1 | D46 | D47 | D45 |
| P2 | D48 | D49 | D44 |

Controlled sequential motion testing on 2026-08-05 confirmed that the listed
STEP/DIR pairs actuate V1-V6 as labelled. V7 and V8, which were absent from the
old notes, were also physically identified:

| Actuator | STEP confirmed | DIR confirmed | HOME |
|---|---:|---:|---:|
| V7 | D36 | D37 | D3 confirmed |
| V8 | D34 | D35 | D2 confirmed |

The V1-V7 HOME inputs were manually tested and confirmed as released `LOW` and
active `HIGH`. After repair of its mechanical wiring error, the V8 HOME input
was manually tested on 2026-08-07 and confirmed with the same semantics:
released `LOW`, pressed `HIGH`, and a clean return to `LOW` after release.

### Confirmed V1-V8 direction polarity — 2026-08-05

A finite cascade test commanded 200 STEP pulses (approximately 45 degrees) at
`DIR=LOW` for each valve. Visual observation established the direction relative
to its HOME position:

| Valve | `DIR=LOW` movement | Direction toward HOME |
|---|---|---|
| V1 | away from HOME | `HIGH` |
| V2 | toward HOME | `LOW` |
| V3 | away from HOME | `HIGH` |
| V4 | away from HOME | `HIGH` |
| V5 | away from HOME | `HIGH` |
| V6 | toward HOME | `LOW` |
| V7 | away from HOME | `HIGH` |
| V8 | away from HOME | `HIGH` |

This confirms signal polarity relative to HOME and V1-V8 HOME switch operation.
Fluidic port alignment remains separate from these electrical and mechanical
tests. In particular, the physically observed V3 and V5 polarity differs
from the older recovered-program assumptions, so the 2026-08-05 physical test
must take precedence.

### Confirmed V1-V7 homing execution — 2026-08-06

A bounded cascade test homed V1-V7 individually using the confirmed HOME pins
and direction levels above. Each valve stopped when its HOME input became
`HIGH`, paused briefly, then moved 356 steps away from HOME (nominally about
80.1 degrees at the recovered 400-steps-per-90-degrees assumption). Results:

| Valve | Steps taken to HOME | Final HOME input | Result |
|---|---:|---|---|
| V1 | 615 | `LOW / RELEASED` | PASS |
| V2 | 223 | `LOW / RELEASED` | PASS |
| V3 | 602 | `LOW / RELEASED` | PASS |
| V4 | 627 | `LOW / RELEASED` | PASS |
| V5 | 595 | `LOW / RELEASED` | PASS |
| V6 | 232 | `LOW / RELEASED` | PASS |
| V7 | 568 | `LOW / RELEASED` | PASS |

The user visually confirmed that all seven moved toward HOME, stopped briefly
at switch activation, moved back to approximately 80 degrees, released their
HOME levers, and produced no unusual noise, binding, or other unexpected
behavior. This confirms bounded homing execution and HOME release for V1-V7.
It does not constitute precise angular calibration or fluidic port alignment.

### Confirmed V1-V7 nominal position stepping — 2026-08-06

A three-phase position test was completed successfully for V1-V7:

1. Each valve homed and moved 400 steps away from HOME to nominal 90 degrees.
2. Each valve moved another 400 steps to nominal 180 degrees.
3. Each valve moved back toward HOME and stopped on switch activation.

All seven valves reported PASS at nominal 90 and nominal 180, and the user
visually confirmed that every phase proceeded as intended. Return-to-HOME
results from nominal 180 were:

| Valve | Steps from nominal 180 to HOME | Result |
|---|---:|---|
| V1 | 801 | PASS |
| V2 | 800 | PASS |
| V3 | 801 | PASS |
| V4 | 799 | PASS |
| V5 | 800 | PASS |
| V6 | 799 | PASS |
| V7 | 800 | PASS |

The 799-801-step return range confirms that 400-step increments consistently
produce the intended nominal 90-degree spacing and that 800 steps spans the
nominal HOME-to-180 range within one detected step for V1-V7. This verifies
repeatable mechanical position stepping, but not the liquid routing associated
with each physical port.

### Confirmed V8 homing and nominal position stepping — 2026-08-07

After repair and manual confirmation of the D2 HOME input, V8 completed the
same staged position test:

- bounded HOME search with `DIR=HIGH`: HOME found after 585 steps
- HOME to nominal 90 degrees: 400 steps, PASS
- nominal 90 to nominal 180 degrees: 400 steps, PASS
- nominal 180 degrees back to HOME: 800 steps, PASS

The user visually confirmed that all V8 phases proceeded as intended. This
confirms bounded V8 homing and repeatable nominal 0/90/180 stepping, completing
the equivalent electrical and mechanical commissioning checks for V1-V8. It
does not by itself verify liquid routing through the physical valve ports.

### Pending verification and commissioning

- Leak testing and liquid route testing remain pending.
- Verification of every physical valve route remains pending. STEP/DIR pair
  identity, direction polarity, HOME inputs, bounded homing, and repeatable
  nominal 0/90/180 stepping are confirmed for V1-V8 above.
- `SF_BOTTOM_VALVE` identity, basic dry actuation, direction, test profile, and
  raw OPEN/CLOSED calibration are confirmed above. Leak-tightness, liquid-route
  execution, and production fault handling remain pending.
- `COLUMN_BOTTOM_VALVE` basic actuation, homing, and functional OPEN/CLOSED
  positions are confirmed above; longer-duration thermal behavior and fluidic
  execution remain pending.
- Pump volumetric calibration remains pending.
- Safe execution interlocks and end-to-end hardware execution remain pending.
- Automatic phase detection and automatic or actual liquid-phase separation are not confirmed.
- Safe routes must be physically verified before pump homing or any liquid movement.

## Confirmed hardware behavior — 2026-07-16

### Confirmed facts: P1 and P2 syringe orientation

- P1 and P2 use 20 mL syringes.
- P1 and P2 have the same confirmed mechanical syringe orientation.
- For both P1 and P2, position `0` is the home-switch end and corresponds to the maximum syringe chamber volume.
- For both P1 and P2, position `20500` is the recovered approximate minimum-volume, practically empty position.
- For both P1 and P2, movement toward `0` increases syringe chamber volume and physically aspirates.
- For both P1 and P2, movement toward `20500` decreases syringe chamber volume and physically dispenses.
- The tested move `20000 -> 10000` aspirated liquid from B1 into P1.
- The tested move `10000 -> 20000` dispensed liquid from P1 toward the Reactor.

### Confirmed P1/P2 HOME inputs — 2026-08-08

Manual press-and-release tests were completed first with the main motor supply
off and then repeated with it on. Both tests produced the same clean transitions
without false activation:

- `P1 HOME = D45`
- `P2 HOME = D44`
- input configuration: `INPUT_PULLUP`
- released state: `LOW`
- pressed/active state: `HIGH`

Each switch produced the expected `LOW -> HIGH -> LOW` sequence. Tests that
used plain `INPUT` did not detect the switches; the recovered working `Pump`
implementation and the successful physical retest both require
`INPUT_PULLUP`.

### Confirmed P1 Waste-route homing and short motion — 2026-08-08

The user physically verified the dry, unobstructed route:

- `P1 -> V1.k1`
- `V1 = 180 degrees` (`k1 <-> k2`)
- `V1.k2 -> V2.k1`
- `V2 = 180 degrees` (`k1 <-> k2`)
- `V2.k2 -> shared Waste`

A controlled commissioning sequence then completed successfully:

1. V1 homed and moved to nominal 180 degrees.
2. V2 homed and moved to nominal 180 degrees.
3. P1 homed toward `DIR=LOW`, finding HOME after 20,048 search pulses.
4. P1 moved 1,000 pulses away from HOME with `DIR=HIGH`.
5. P1 returned toward HOME with `DIR=LOW`; HOME activated after 998 pulses.
6. The test stopped at HOME with V1 and V2 remaining at nominal 180 degrees.

This physically confirms for P1:

- STEP `D46`
- DIR `D47`
- HOME `D45`, `INPUT_PULLUP`, active `HIGH`
- direction toward HOME: `DIR=LOW`
- direction away from HOME: `DIR=HIGH`
- the P1-to-Waste valve route listed above

The near-full-stroke homing distance is consistent with P1 having started near
its recovered far-end position, but it does not calibrate volume or validate
`20500` as a production travel limit. The 998-versus-1,000-pulse return reflects
the physical switch activation point/hysteresis and is not a volume calibration.

### Confirmed P2 Waste-route homing and short motion — 2026-08-08

The user physically verified and commissioned the dry Waste route:

- `P2 -> V3.k1`
- `V3 = 180 degrees` (`k1 <-> k2`) to `V7.k1`
- `V7 = 90 degrees` (`k1 <-> k3`) to `V8.k1`
- `V8 = 90 degrees` (`k1 <-> k3`) to `V5.k1`
- `V5 = 180 degrees` (`k1 <-> k2`) to shared Waste

A controlled commissioning sequence completed successfully:

1. V3 homed and moved to nominal 180 degrees.
2. V7 homed and moved to nominal 90 degrees.
3. V8 homed and moved to nominal 90 degrees.
4. V5 homed and moved to nominal 180 degrees.
5. P2 homed toward `DIR=LOW`, finding HOME after 20,028 search pulses.
6. P2 moved 1,000 pulses away from HOME with `DIR=HIGH`.
7. P2 returned toward HOME with `DIR=LOW`; HOME activated after 999 pulses.
8. The test stopped at HOME with the Waste route remaining configured.

This physically confirms for P2:

- STEP `D48`
- DIR `D49`
- HOME `D44`, `INPUT_PULLUP`, active `HIGH`
- direction toward HOME: `DIR=LOW`
- direction away from HOME: `DIR=HIGH`
- the P2-to-Waste valve route listed above

The initial 20,028-pulse homing distance records only the arbitrary starting
position of this test. It is not a calibration result or validation of the
recovered `20500` endpoint. The 999-versus-1,000-pulse return is consistent
with the physical HOME-switch activation point/hysteresis and is not a volume
calibration.

### P1/P2 20,000-pulse dry-travel results — 2026-08-08

A combined bounded dry-air test used the confirmed Waste routes and completed
without a firmware-reported error:

- P1: HOME to 20,000 pulses away, then HOME detected after 20,003 return
  pulses; final position 200 pulses away from HOME with D45 released `LOW`.
- P2: initially on HOME, switch released after 140 pulses, re-homed after 190
  search pulses, moved 20,000 pulses away, then HOME detected after 19,998
  return pulses; final position 200 pulses away from HOME with D44 released
  `LOW`.
- The test retained `PUMP_STEP_INTERVAL_US = 1500` and `STEP_HIGH_US = 20`.

These results confirm repeatable near-full dry travel in both directions at the
tested pulse timing and leave both pumps off their HOME switches. They do not
calibrate volume, prove that 20,000 is a safe production endpoint under every
load, or replace the user's physical observation for binding, impact, skipped
steps, abnormal noise, or end clearance.

The user subsequently confirmed that the 20,000-pulse test produced no
mechanical-end impact, binding, skipped motion, slipping, or abnormal noise.
The user also confirmed that position `20500` has been physically exercised
successfully multiple times and may be retained as the currently approved
maximum step position for both pumps. This confirms mechanical reach, not
volume accuracy; wet testing and `steps/ml` calibration are intentionally
deferred.

Pump speed was acceptable at `PUMP_STEP_INTERVAL_US = 1500`. A future UI
setting may request pump speed, but firmware must own and validate the allowed
range and reject unsupported values. No final UI control, protocol field, or
validated speed range is established by this confirmation.

### Accepted demo-only P1/P2 homing assumption — 2026-08-10

The user confirmed that P1/P2 have no independent end sensor, second limit,
stall feedback, or other protection capable of preventing mechanical damage if
HOME fails to activate. The HOME switches have been manually tested and the
user explicitly chose, for the supervised demo machine, to assume that they
remain functional. At startup, homing is therefore expected to move toward
HOME from any initial pump position until HOME activates, bounded to 20,500
STEP pulses. The operator remains physically present at the power switch during
physical demo operation.

This is an explicitly accepted demo risk, not a fail-safe hardware property.
The 20,500-pulse bound is the confirmed coordinate span and cannot prevent
overtravel when the unknown starting position is closer to HOME and the HOME
signal is missing. A stuck-LOW switch, broken signal path that appears LOW, or
mechanical failure to actuate the switch can still cause damage before the
software pulse bound is reached. Production or unattended use remains blocked
until an independent protection or a different safe recovery design exists.

### Accepted demo-only V1-V8 homing assumption — 2026-08-11

The user explicitly confirmed that the same supervised-demo assumption applies
to V1-V8. Their manually tested HOME switches are treated as functional, the
operator remains physically present at the power switch, and possible
mechanical overtravel if a HOME signal fails is an accepted demo-only risk.
Unattended and production operation remain out of scope.

The V1-V8 1,600-pulse HOME-search limit is only a software execution timeout.
It has not been physically established as a mechanically safe missing-HOME
travel bound and must not be represented as independent end protection.

### Confirmed production V1-V8 GPIO and LABFORGE/1 motion — 2026-08-12

Firmware commit `c6a523440f4c187f092926db242d7b9e317d94a3` was built,
uploaded, and flash-verified on the Arduino Mega through its stable USB by-id
path. A no-motion LABFORGE/1 handshake then reported controller state `IDLE`,
trusted software identity, and the expected pump and valve capabilities.

The supervised production Serial/lifecycle test first executed `VALVE_HOME`
for V1 alone. It completed with the truthful `ACCEPTED -> STARTED -> COMPLETED`
lifecycle, and the user physically confirmed correct movement toward HOME,
correct stop on HOME, and no impact, slipping, or abnormal sound.

A subsequent supervised cascade executed, for each valve V1 through V8 in
order, `VALVE_HOME` followed by `VALVE_SET_POSITION` to nominal 90 degrees,
with a two-second dwell between valves. Every individual command completed
with `ACCEPTED -> STARTED -> COMPLETED`; firmware reported no failure,
rejection, or timeout. The user physically confirmed that all eight valves
homed, moved back to approximately 90 degrees, released their HOME switches,
and completed without impact, slipping, or abnormal sound. V1-V8 were left at
nominal 90 degrees after the test.

This confirms the V1-V8 Arduino GPIO, LABFORGE/1 lifecycle, HOME, and nominal
90-degree production-runtime paths for the supervised dry demo. It does not
verify liquid routing or leak-tightness and does not authorize unattended or
production operation; the accepted demo-only HOME assumptions above remain
unchanged.

### Confirmed production P1 GPIO and LABFORGE/1 motion — 2026-08-11

The supervised dry physical integration test used firmware commit
`5e1dbc79ba959d3c49bcecb8262c9714b950d010` and the previously confirmed safe
route `P1 -> V1(180 degrees) -> V2(180 degrees) -> Waste`.

The production Serial/lifecycle path and GPIO controller completed:

1. `PUMP_HOME` with `ACCEPTED -> STARTED -> COMPLETED` lifecycle reporting.
2. An absolute move from HOME/zero to 2,000 steps.
3. A stronger sequence consisting of HOME, an absolute move to 10,000 steps,
   a two-second stationary observation, and an absolute return to 2,000 steps.

The operator physically confirmed the commanded movement in both directions
and reported that the complete stronger test passed without mechanical impact,
slipping, binding, abnormal noise, or other unusual behavior. The final
firmware includes stable confirmation of an unexpected HOME activation before
failing motion, so a transient HOME sample does not immediately terminate a
move.

This confirms the P1 Arduino GPIO, LABFORGE/1 command lifecycle, homing, and
absolute-position motion path for the supervised dry demo. It is not a wet
volume calibration and does not authorize unattended or production operation;
the accepted demo-only HOME assumptions above remain unchanged.

### Confirmed production P2 GPIO and LABFORGE/1 motion — 2026-08-11

The supervised dry physical integration test used firmware commit
`e01d9084227d7180209c12d60ca4743db4465588` and the previously confirmed safe
route `P2 -> V3(180 degrees) -> V7(90 degrees) -> V8(90 degrees) -> V5(180
degrees) -> Waste`.

The firmware was uploaded to the Arduino Mega through its stable USB by-id path
and upload verification completed successfully. The production Serial/lifecycle
path and the independent P2 GPIO controller then completed:

1. `PUMP_HOME` with `ACCEPTED -> STARTED -> COMPLETED` lifecycle reporting.
2. A stronger sequence consisting of HOME, an absolute move to 5,000 steps, a
   two-second stationary observation, and a return to HOME.
3. A final HOME followed by an absolute move to 2,000 steps, where P2 was left
   parked before machine power was switched off.

The operator physically confirmed the correct movement, HOME-switch stop, and
smooth execution. No mechanical impact, slipping, binding, leakage, abnormal
noise, or other unusual behavior was observed.

This confirms the P2 Arduino GPIO, LABFORGE/1 command lifecycle, homing, and
absolute-position motion path for the supervised dry demo. It does not establish
wet volume accuracy or authorize unattended or production operation; the
accepted demo-only HOME assumptions above remain unchanged.

### Confirmed end-to-end P1/P2 Service path — 2026-08-12

The supervised dry test exercised the complete host-to-machine path through
the Service UI/backend boundary, the durable backend command journal, the
LABFORGE/1 Serial session, production firmware lifecycle handling, and the
confirmed Arduino Mega GPIO controllers. The operator manually established
and visually confirmed the safe Waste routes before enabling motor power:

- `P1 -> V1(180 degrees) -> V2(180 degrees) -> Waste`
- `P2 -> V3(180 degrees) -> V7(90 degrees) -> V8(90 degrees) -> V5(180 degrees) -> Waste`

The following commands each reached a terminal `COMPLETED` result through the
backend API and production firmware:

1. P1 `PUMP_HOME`
2. P1 `PUMP_MOVE_ABSOLUTE_STEPS` to `2,000`
3. P2 `PUMP_HOME`
4. P2 `PUMP_MOVE_ABSOLUTE_STEPS` to `2,000`

The operator physically confirmed correct movement toward HOME, correct stop
on each HOME switch, and smooth absolute movement away from HOME. No impact,
slipping, binding, abnormal sound, or other unusual physical behavior was
observed. P1 and P2 were left at 2,000 steps before machine motor power was
explicitly switched off.

During host integration, an initial API request failed before any Serial byte
or actuator movement because the SQLite command-journal connection was used
from a different backend worker thread. The backend was corrected to serialize
access to a cross-thread-enabled connection and regression-tested. The backend
also waits for the Arduino Mega USB-reset settling interval before performing
the LABFORGE/1 handshake. These host corrections were in effect for all four
successful physical commands listed above.

This confirms the complete supervised dry P1/P2 Service control path. It does
not establish wet volume calibration, dead-volume compensation, leak-tightness,
automatic route planning, or unattended/production operation. The accepted
demo-only HOME assumptions remain unchanged.

### Confirmed carousel control path and position model — 2026-08-10

The user physically identified the lowest installed driver as the carousel
driver and confirmed it is a StepperOnline `CL57T` closed-loop driver. Its ENA
input is not connected. A controlled 400-pulse out-and-back test identified
the Arduino Mega signal pins:

- `CAROUSEL STEP = D8`
- `CAROUSEL DIR = D9`

The same test produced visible carousel movement and return. A subsequent
controlled test at `DIR=HIGH` experimentally produced one full 360-degree
carousel revolution from 10,000 STEP pulses. With 40 equally spaced tube
positions, this establishes the nominal conversion:

- `10,000 pulses / revolution`
- `250 pulses / tube position`
- `25 pulses / degree`

The user then confirmed that a one-tube movement using 250 pulses aligned as
intended and that the following S-curve profile produced acceptably smooth
motion for the current demo:

- tested logical direction: `DIR=HIGH`
- starting/stopping STEP interval: `6,000 us`
- fastest STEP interval: `1,200 us`
- acceleration: 125 pulses using cubic smoothstep
- deceleration: 125 pulses using cubic smoothstep

These values are the accepted initial carousel operating profile. A subsequent
40-position test advanced the carousel by one nominal tube position at a time,
held each position for two seconds, and completed the full revolution using
this profile. The user confirmed that the complete test passed. Physical
CW/CCW naming for `DIR=HIGH` remains intentionally unspecified because the
logical direction and position progression are sufficient for the current
machine behavior.

The future Service interface should expose bounded carousel commissioning
settings for:

- pulses per revolution and derived pulses/degrees per tube position
- movement direction
- starting/stopping STEP interval
- fastest STEP interval
- acceleration/deceleration pulse count and motion-profile selection
- dwell time and a bounded number of test positions

These are calibration and service parameters, not unrestricted direct GPIO
controls. The backend owns authorization and persistence policy, while firmware
must validate every received value against explicit safe numeric bounds before
using it for motion.

The carousel has 40 tube positions, so adjacent nominal positions are separated
by 9 degrees. There is no carousel HOME sensor. The operator will therefore
align and declare the initial tube position manually. Software must treat the
position as unknown after controller startup or any event that can lose step
accounting until that explicit manual initialization occurs; it must not invent
an absolute carousel position.

### Common DM542T driver DIP layout — 2026-08-08

The user confirmed that all currently discussed stepper drivers are `DM542T`
except the carousel driver, which is explicitly deferred for separate work.
The `COLUMN_BOTTOM_VALVE` DM542T is also an exception because its separately
confirmed DIP configuration is documented above.

For the remaining DM542T drivers used by V1-V8 and P1/P2, the user confirmed
the same physical lever pattern:

- SW1: down
- SW2: down
- SW3: up
- SW4: up
- SW5: up
- SW6: up
- SW7: down
- SW8: down

These are recorded as physical up/down positions only. They must not be
silently translated to `ON/OFF`, current, or pulses-per-revolution without a
clear orientation reference and the table from the installed driver. The
carousel driver is not covered by this confirmation.

The user declined a new formal thermal-soak test because these motors have
already operated repeatedly for extended periods under observation. The user
reports that they warm during operation but remain controlled and have not
shown concerning thermal behavior. This operational history is accepted for
the current commissioning stage; it is not a measured temperature profile or
a manufacturer-limit validation.

### Confirmed limitations

- `20500` remains a recovered software travel value and approximate endpoint, not a validated volume calibration.
- `steps/ml` remains pending experimental calibration.
- Working full and working empty margins remain pending experimental calibration.
- No validated aspiration or dispense volume accuracy is documented yet.
- No validated physical speed range exists yet.
- No acceleration ramp or stall detection is currently confirmed.

### Recovered `Pump` API mismatch

The recovered helper-method names appear semantically reversed for the confirmed P1 and P2 physical orientation:

- Recovered `startAspirateSteps()` increases the step position.
- Recovered `startDispenseSteps()` decreases the step position.
- Confirmed P1 and P2 hardware aspirates when the step position decreases.
- Confirmed P1 and P2 hardware dispenses when the step position increases.

The tested recovery demo worked because it used explicit absolute positions. The recovery files must remain unchanged, and this mismatch must be handled later on a dedicated experimental branch. Backend commands must remain semantic, such as `aspirate` and `dispense`; firmware must translate those commands into the correct motor direction according to per-pump physical configuration.

No final C++ API or direction enum is defined by this baseline.

### Inferred implication: homing is fluidic

- P1 homing moves toward position `0`.
- Because chamber volume increases toward `0`, homing may aspirate from whichever route is currently connected to P1.
- Pump homing is therefore a fluidic operation, not merely a mechanical initialization.
- A safe homing route must be configured and confirmed before starting P1 homing.

The exact safe route and valve sequence remain pending and must be defined later using the approved and physically verified topology. No specific valve position is confirmed here as the final safe route.

### Pending safety decision: early home-switch activation

- The recovered `Pump` implementation may treat an unexpectedly early home-switch activation during movement toward home as arrival at position `0`.
- This behavior is not yet accepted as safe operation-completion semantics.
- Future active firmware must distinguish expected home arrival from unexpected early limit activation.
- No code change is made in this baseline task.
