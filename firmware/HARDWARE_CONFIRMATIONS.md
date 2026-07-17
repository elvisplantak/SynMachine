# Hardware confirmations

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
