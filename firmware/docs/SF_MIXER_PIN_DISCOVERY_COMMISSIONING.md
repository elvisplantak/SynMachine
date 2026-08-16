# SF mixer pin discovery commissioning

This procedure identifies which one of two currently unconfirmed Arduino Mega
STEP/DIR pairs drives the SF mixer. It does not establish a production pin
assignment, direction convention, speed, or mixing calibration.

## Candidate pairs

- Pair A: STEP D4, DIR D5
- Pair B: STEP D6, DIR D7

The Reactor mixer is not connected. The user identified the SF mixer as a
NEMA 17 motor with the same DM542T driver type used for the valves, but the
driver current and microstep settings remain unconfirmed.

## Safety behavior

Build and upload the dedicated `mixer_pin_discovery_mega` environment only
while motor power is off. The firmware leaves both candidate pairs as inputs
at startup and cannot emit motion until all of these commands have completed:

1. `SELECT A` or `SELECT B`
2. `DIR LOW` or `DIR HIGH`
3. `ARM`
4. `PULSE 1` through `PULSE 1600`

Every pulse command consumes the arm state. A fresh `ARM` is therefore required
before every pulse command. Arming also expires after ten seconds. Invalid,
incomplete, or state-changing commands disarm the controller. After a pulse
burst, STEP and DIR return to inputs. The dedicated mixer build uses the
confirmed valve-test interval of 2 ms between pulses; this borrows only a
previously exercised electrical pulse rate and does not establish an SF mixer
production speed.

The serial banner must display the intended mapping before testing:

```text
PAIR A STEP D4 DIR D5
PAIR B STEP D6 DIR D7
```

## Supervised sequence

Keep the mechanism clear and observe all actuators, not only the SF mixer.
Test one pair at a time, initially with `DIR LOW`:

```text
SELECT A
DIR LOW
ARM
PULSE 1
```

If one pulse is too small to observe and there is no abnormal sound, heat, or
vibration, repeat with a fresh `ARM` and `PULSE 100`. Only after observing that
the selected pair drives the SF mixer may a fresh arm be used for `PULSE 500`
and then `PULSE 1600`. Stop and obtain user feedback between bursts. If pair A
produces no observed response at 100 pulses, run the one-pulse and 100-pulse
sequence on pair B.

Immediately switch motor power off if any unintended actuator moves or if any
abnormal sound, heat, binding, or vibration is observed. Do not test the other
logical direction merely to discover rotation direction; first identify the
correct physical SF mixer pair.

After the user physically identifies the SF mixer pair, switch motor power off,
restore production firmware, and record only the observed pair as confirmed.
Production SF mixer integration requires a separate bounded speed and direction
commissioning step.

## Result — 2026-08-16

Pair A produced no observed motion at 100 pulses. Pair B physically rotated the
SF mixer at `DIR LOW` during a 500-pulse burst, and the user confirmed the
movement. The confirmed SF mixer assignment is STEP D6 and DIR D7. Physical
CW/CCW direction naming and the intended production mixing speed remain
unconfirmed.
