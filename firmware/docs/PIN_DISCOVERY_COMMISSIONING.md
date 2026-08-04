# LabForge V7/V8 pin-discovery commissioning

- Status: prepared, not physically executed
- Date: 2026-08-04
- Scope: identify the currently unknown V7/V8 Arduino `STEP` and `DIR` pins

This procedure is a commissioning aid, not production firmware. It does not
change the LABFORGE/1 protocol, does not establish valve positions, and does
not authorize upload or physical execution.

## Candidate boundary

Partially outdated wiring notes account for V1-V6 on consecutive pin pairs
`D22/D23` through `D32/D33`. The first candidates for the two missing axes are:

| Discovery pair | STEP candidate | DIR candidate | Confirmation status |
|---|---:|---:|---|
| A | D34 | D35 | unverified inference |
| B | D36 | D37 | unverified inference |

The commissioning build intentionally supports only these two pairs. If
neither pair identifies V7/V8, stop and revise the candidate boundary rather
than expanding to arbitrary Arduino pins during a live session.

HOME pins are outside this first tool. They remain unknown because input
pull-up behavior, switch contact selection, and active polarity are not yet
confirmed.

## Isolation requirements

Before any future upload or movement:

1. Confirm that no liquid movement can result from the small valve motion.
2. Power only the one V7 or V8 motor driver being identified; keep every other
   motor driver unpowered.
3. Ensure the mechanism can tolerate five individual steps in either
   direction from its current position.
4. Keep an immediate, physically accessible means of removing motor power.
5. Do not run homing, route selection, pump movement, or any other actuator.

Software isolation is not a substitute for powering only the intended driver.

## Separate build target

The discovery firmware is isolated from the production source entry point:

```text
pio run -e pin_discovery_mega
```

The normal `megaatmega2560` environment excludes all commissioning sources.
Building the target is a no-motion software check. Uploading it, opening a
Serial Monitor against the controller, powering a driver, or emitting a pulse
requires explicit physical authorization.

## Fail-safe interaction

On boot, the tool does not configure either candidate pair as an output and
prints that outputs are inactive. The complete sequence for one bounded pulse
request is:

```text
SELECT A
DIR LOW
ARM
PULSE 1
```

Pair B and direction HIGH use `SELECT B` and `DIR HIGH`. `PULSE` accepts only
`1..5`. Each pulse request consumes the armed state, so another request needs a
new `ARM`. Arming expires after ten seconds. Selection changes, direction
changes, malformed commands, oversized input, and `DISARM` all leave the tool
disarmed. After a pulse series the STEP and DIR pins return to `INPUT` mode.

Every response begins with `STATUS` followed by a human-readable result such
as `OK`, `NOT_ARMED`, or `INVALID_PULSE_COUNT`.

## Recording results

For each powered motor, record:

- whether pair A or B caused the observed motion
- whether the observed motor is physically V7 or V8
- observed direction for `DIR LOW` and `DIR HIGH`
- pulse count and whether motion was unambiguous
- any unexpected sound, binding, heating, or movement

Only an unambiguous result may be promoted from a candidate into
`HARDWARE_CONFIRMATIONS.md`. Direction observations do not establish the
correct homing direction, valve position, port route, or steps per angle.

## Deferred commissioning

The following remain separate future tests:

- V7/V8 HOME pin identification, contact choice, and polarity
- homing direction and early-switch handling
- steps for 90 and 180 degrees
- physical verification of `closed`, `k1 <-> k3`, and `k1 <-> k2`
- dry route testing and later low-risk liquid route testing
- production actuator adapter and LABFORGE/1 integration
