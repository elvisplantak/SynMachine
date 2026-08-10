# LabForge hardware commissioning plan

- Status: dry commissioning completed for the currently installed valves and
  syringe pumps, except carousel commissioning; liquid commissioning and
  production integration remain pending
- Updated: 2026-08-10

This plan separates electrical identification, minimal motion, homing,
position verification, dry-route checks, and liquid testing. Passing an
earlier level does not establish any later level. Every upload, Serial session
against the controller, powered-driver test, homing action, pump action, and
liquid test requires explicit physical authorization.

## Commissioning record

Maintain one row per actuator and do not promote observations into confirmed
facts until the relevant level passes:

| Actuator | Control path | STEP/DIR or device identity | HOME/contact | Direction | Positions/steps | Dry route | Liquid route |
|---|---|---|---|---|---|---|---|
| V1-V8 | Arduino Mega | D22-D37 assignments confirmed | D39/D38/D43/D40/D41/D42/D3/D2; released LOW, active HIGH | HOME direction confirmed individually | 400 steps/90 degrees; 0/90/180 repeatability confirmed | selected P1/P2 Waste routes confirmed; all-port isolation pending | pending |
| P1/P2 | Arduino Mega | P1 D46/D47; P2 D48/D49 | P1 D45; P2 D44; `INPUT_PULLUP`; released LOW, active HIGH | HOME LOW; away HIGH for both | 20,000-pulse dry round trip passed; 20,500 approved mechanical maximum; volume calibration pending | separate Waste routes confirmed | pending |
| COLUMN_BOTTOM_VALVE | Arduino Mega / DM542T | STEP D12; DIR D13 | D10; released LOW, active HIGH | HOME LOW | CLOSED 4 degrees; OPEN 94 degrees; 80,000 pulses/rev; 1,000-us interval | mechanical dry actuation confirmed; fluid route pending | pending |
| SF_BOTTOM_VALVE | host USB / U2D2 / XL430-W250-T | stable FTDI by-id path; ID 2; model 1060; 57,600 baud; Protocol 2.0 | internal position/error/voltage/temperature telemetry confirmed | positive raw direction from CLOSED to OPEN | CLOSED 2559; OPEN 3697; profile velocity 20; acceleration 1 | repeated mechanical dry actuation confirmed | pending |

The detailed evidence, measured values, limitations, and precedence rules for
these promoted confirmations are canonical in `HARDWARE_CONFIRMATIONS.md`.
This table is a concise progress index and must not be used to infer unlisted
fluidic, electrical, thermal, or production-safety properties.

## Current commissioning checkpoint

Completed with explicit physical authorization and user observation:

- V1-V8 STEP/DIR identity, HOME identity and polarity, direction toward HOME,
  bounded homing, and repeatable nominal 0/90/180 positioning
- P1/P2 STEP/DIR/HOME identity and polarity, common physical direction model,
  separately verified Waste routes, and 20,000-pulse dry out-and-back travel
- `COLUMN_BOTTOM_VALVE` basic motion, HOME behavior, reliable pulse interval,
  and functional CLOSED/OPEN offsets
- `SF_BOTTOM_VALVE` U2D2 identity, DYNAMIXEL identity/status, bounded motion in
  both directions, test profile, and visually calibrated CLOSED/OPEN values

Explicitly deferred or still pending:

- carousel driver, pins, positions, and motion
- leak testing and liquid verification of physical routes
- pump `steps/ml`, volumetric repeatability, and validated wet speed range
- production actuator adapters, safety interlocks, disconnect/recovery and
  fault-injection behavior
- end-to-end backend/firmware/UI execution

## Commissioning procedure reference

The following levels remain the required procedure for retesting, replacement
hardware, and work that is still pending. Completion claims above apply only to
the specifically recorded hardware and tests; they do not waive authorization
for future physical execution.

## Level 0: software-only preparation

- native tests pass with warnings treated as errors
- production Mega build remains isolated from commissioning sources
- commissioning Mega build succeeds without upload
- every command is bounded and fail-closed
- no candidate pin is described as confirmed
- operator procedure and result fields are documented

## Level 1: control-path identification

### Arduino STEP/DIR axes

- power only one intended driver
- select only one bounded candidate pair
- emit one step, then at most five, with a fresh arm for each series
- identify the observed actuator
- record both logic-direction observations without assigning semantic meaning
- stop on unexpected motion, binding, noise, or heating

The dedicated V7/V8 procedure is in
`docs/PIN_DISCOVERY_COMMISSIONING.md`.

### Arduino HOME inputs

HOME discovery requires a separate read-only input tool after the switch
contact choice and expected electrical arrangement are confirmed. Do not apply
`INPUT_PULLUP` to unknown wiring merely to scan pins. Record the inactive and
manually activated logic levels before any homing movement.

### DYNAMIXEL path

With torque disabled:

- identify the U2D2 USB device deterministically
- scan only the expected bus and record device ID
- record baud rate, protocol version, model number, firmware version, present
  position, hardware error status, and operating mode
- verify that reconnecting or renumbering USB devices cannot select an
  unrelated adapter silently

No torque-enable or goal-position write belongs in this level.

## Level 2: bounded no-fluid motion

For one actuator at a time:

- establish a safe mechanical starting condition
- make the smallest observable motion in each direction
- record the physical meaning of both logic directions
- verify timeout and explicit de-energization behavior
- confirm that unrelated actuators remain stationary

For pumps, no movement is considered no-fluid merely because tubing appears
empty. Pump motion and especially homing can aspirate from the selected route;
a physically verified safe route is required first.

## Level 3: HOME behavior

Before homing any axis, confirm:

- HOME pin or sensor identity
- contact selection and inactive/active logic levels
- debounce behavior
- homing direction
- release/backoff/search sequence
- maximum steps or time before failure
- behavior when the switch is active before start
- behavior when it activates unexpectedly early

Complete each valve individually. Pump homing additionally requires a verified
fluidic route and separate authorization for possible aspiration.

## Level 4: position and port verification

For V1-V8, verify individually that the physical routes match the intended
semantics:

- `0 degrees = closed`
- `90 degrees = k1 <-> k3`
- `180 degrees = k1 <-> k2`

Record actual step counts, directions, repeatability, and whether returning to
HOME restores the same reference. Motor completion alone is not route proof.

For both bottom valves, determine and record physically closed and open
positions. The SF DYNAMIXEL raw values must be mapped to symbolic `CLOSED` and
`OPEN`; callers must not use arbitrary raw positions in normal operation.

## Level 5: dry route verification

- use a harmless, low-pressure dry method appropriate for the tubing
- verify one intended connection at a time
- verify that every non-selected branch remains isolated
- check bottom-valve closure before relying on gravity containment
- record route evidence separately from motor-position evidence

## Level 6: low-risk liquid commissioning

- use only the separately approved low-risk test liquid
- begin with minimal volume and one route
- check leaks before pump movement and after every route change
- verify aspiration and dispense as separate operations
- measure delivered volume rather than infer it from command completion
- keep Column and SF bottom-valve operating rules in force

Pump calibration must determine working endpoint margins, `steps/ml`,
repeatability, and validated speed limits. The recovered `0..20500` coordinate
envelope is not itself a calibrated safe working range.

## Level 7: fault and integration checks

Inject faults without liquid first where possible:

- HOME inactive for the entire timeout
- HOME active before start
- unexpected early HOME activation
- driver unpowered or motor disconnected
- Arduino reset and Serial disconnect
- U2D2 disconnect and DYNAMIXEL hardware error
- command timeout with ambiguous outcome
- attempted route switch while SF bottom valve is open
- attempted carousel motion while Column bottom valve is open

No physical command is automatically retried after an ambiguous outcome.
Backend lifecycle state, firmware software state, and actual physical state
must remain explicitly distinct.
