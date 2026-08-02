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

This wiring update does not confirm:

- home-switch contact selection such as `NC` versus `NO`
- input polarity or the electrical meaning of `HIGH` and `LOW`
- motor rotation direction
- valve open and closed directions
- valve angles or step counts
- homing behavior
- early-switch handling
- driver current or microstep settings
- `ENA` wiring or behavior
- motor power wiring
- successful actuation
- leak-tightness
- fluidic routing through the valve
- safe physical execution

### Pending verification and commissioning

- Leak testing and liquid route testing remain pending.
- Verification of every valve angle, every physical valve route, and V1-V8 actuation remains pending.
- Verification of `SF_BOTTOM_VALVE` and `COLUMN_BOTTOM_VALVE` actuation remains pending.
- Pump volumetric calibration remains pending.
- Safe execution interlocks and end-to-end hardware execution remain pending.
- Automatic phase detection and automatic or actual liquid-phase separation are not confirmed.
- Safe routes must be physically verified before pump homing or any liquid movement.

## Confirmed hardware behavior — 2026-07-16

### Confirmed facts: P1 and P2 syringe orientation

- P1 and P2 use 10 mL syringes.
- P1 and P2 have the same confirmed mechanical syringe orientation.
- For both P1 and P2, position `0` is the home-switch end and corresponds to the maximum syringe chamber volume.
- For both P1 and P2, position `20500` is the recovered approximate minimum-volume, practically empty position.
- For both P1 and P2, movement toward `0` increases syringe chamber volume and physically aspirates.
- For both P1 and P2, movement toward `20500` decreases syringe chamber volume and physically dispenses.
- The tested move `20000 -> 10000` aspirated liquid from B1 into P1.
- The tested move `10000 -> 20000` dispensed liquid from P1 toward the Reactor.

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
