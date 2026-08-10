# P1 motion hardening review request

## Review scope

Review branch `codex/p1-motion-safety-hardening` from base commit
`647fb47f0bb2a18d8f6e66569d59b96755201baf`.

Read these sources first:

1. `../labforge-ui/LABFORGE_DEVELOPMENT_GOVERNANCE.md`
2. `../labforge-ui/LABFORGE_CURRENT_STATE.md`
3. `../labforge-ui/LABFORGE_CONTEXT.md`
4. `HARDWARE_CONFIRMATIONS.md`
5. `docs/LABFORGE_SERIAL_PROTOCOL_V1.md`
6. `docs/P1_PRODUCTION_MOTION_DESIGN.md`

Do not inspect `recovery/`.

## What changed

- `PUMP_MOVE_ABSOLUTE_STEPS` now rejects target `0`; only `PUMP_HOME` may
  establish coordinate zero.
- HOME activation and release used by homing require 30 ms of continuous
  stability while motion is paused.
- An initially active HOME at untrusted boot is stability-confirmed without an
  away move. A repeated home from trusted zero retains the bounded release and
  re-search sequence.
- Absolute movement cannot report completion while HOME remains active,
  including a target inside the release zone.
- Every DIR write precedes the next STEP rising edge by at least 5 us.
- A local abort API forces STEP low and invalidates position trust after the
  execution boundary.
- Pulse timing tests cover `micros()` wraparound, delayed updates without
  catch-up bursts, and STEP-low terminal behavior.

## Explicitly accepted deviation

P1/P2 have no independent end protection. The user explicitly accepted
automatic startup homing from any initial position for the supervised demo,
with the operator at the power switch and manually tested HOME switches. The
20,500-pulse software bound does not prevent mechanical overtravel if HOME is
missing or stuck LOW. This branch documents that risk; it does not solve it and
must not be described as safe for unattended or production use.

## Review focus

- State-machine behavior around HOME bounce, release, and target completion.
- STEP-low and position-trust behavior on abort and every terminal failure.
- Wrap-safe timing and absence of catch-up pulse bursts.
- Agreement among code, protocol, design, and hardware confirmations.
- Confirmation that no dispatcher, Arduino GPIO adapter, upload, Serial
  lifecycle integration, or physical movement was added.

## Verification already completed

- `pio test -e native`: 96/96 passed with `-Wall -Wextra -Werror`.
- `pio run -e megaatmega2560`: passed.
- Mega resource report: 22,392 / 253,952 bytes flash (8.8%) and
  1,675 / 8,192 bytes RAM (20.4%).
- `git diff --check`: passed.

