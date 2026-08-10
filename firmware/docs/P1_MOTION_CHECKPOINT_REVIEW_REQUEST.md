# P1 Motion Checkpoint Review Request

## Review target

- Repository: `labforge-firmware`
- Branch: `codex/p1-production-lifecycle`
- Implementation commit: `647fb47f0bb2a18d8f6e66569d59b96755201baf`
- Scope: the fail-closed P1 motion foundation before Arduino pin and serial-dispatch integration

This checkpoint intentionally cannot move physical hardware. It defines and tests
the motion state machine and protocol semantics, but it is not connected to
`main.cpp`, Arduino GPIO, or the serial dispatcher.

## Included in this checkpoint

- Exact `PUMP_HOME` command parsing and semantic identity for P1.
- `PUMP_HOME_SWITCH_STUCK` protocol error support.
- A non-blocking `P1MotionController` with explicit prepare/start separation.
- Trusted/untrusted position handling.
- Bounded homing, HOME-release, absolute-position, and abort behavior.
- Native tests for the command contract, status cache, and motion controller.
- Protocol and design documentation.

## Confirmed P1 hardware facts

These values come from `HARDWARE_CONFIRMATIONS.md` and are not inferred by the
implementation:

| Property | Confirmed value |
|---|---:|
| STEP pin | D46 |
| DIR pin | D47 |
| HOME pin | D45 |
| HOME released | LOW |
| HOME active | HIGH |
| Direction toward HOME | LOW |
| Direction away from HOME | HIGH |
| Tested working travel | 20,000 steps from HOME |
| Absolute safety ceiling | 20,500 steps from HOME |
| Final released offset used in dry tests | 200 steps from HOME |
| STEP interval | 1,500 microseconds |
| STEP HIGH time | 20 microseconds |
| ENA control | Not used |

Pump homing can move fluid. The backend remains responsible for establishing and
verifying a safe fluid route before issuing the firmware command. This controller
does not configure valves or infer route safety.

## Safety invariants implemented

1. Position trust starts as `UNTRUSTED` after boot.
2. Only a successful explicit P1 homing cycle establishes trusted position zero.
3. Command preparation has no hardware side effects.
4. `startPrepared()` is the execution boundary; its first hardware operation is
   the required DIR write, allowing `STARTED` to be emitted before motion begins.
5. Homing search is bounded by the confirmed 20,500-step ceiling.
6. If HOME is initially active, release travel is bounded to 200 steps.
7. Missing, unexpected, or stuck HOME behavior stops STEP LOW and invalidates
   position trust.
8. Absolute target zero is reserved for explicit homing rather than blind motion
   toward the mechanical boundary.
9. Abort stops pulse generation and invalidates position trust when motion was in
   progress.

## Verification completed

- Focused native tests: 24/24 passed.
- Complete native suite: 89/89 passed.
- Warning-enabled native compilation: passed.
- Arduino Mega 2560 build: passed.
- Mega SRAM: 1,675 / 8,192 bytes (20.4%).
- Mega flash: 22,392 / 253,952 bytes (8.8%).
- `git diff --check`: passed.
- No firmware upload or physical execution was performed for this checkpoint.

Reviewer reproduction commands:

```bash
pio test -e native
pio run -e megaatmega2560
git diff 647fb47^ 647fb47 --check
```

## Requested review focus

Please specifically assess the following:

1. Is the prepare/start boundary strong enough to guarantee that lifecycle
   `STARTED` can be reported before the first actuator side effect?
2. Is a bounded 200-step release when HOME is initially active appropriate, or
   should release distance have a separate named/configurable policy?
3. Is reserving absolute target zero for `PUMP_HOME` the correct fail-closed
   interpretation, given that the generic move schema otherwise permits targets
   from 0 through 20,500?
4. Are all failure and abort paths conservative enough about invalidating trusted
   position?
5. Are the `micros()` wraparound handling and non-blocking pulse transitions safe
   on AVR?
6. Does HOME-switch validation correctly cover unexpected activation, failure to
   release, and failure to find HOME?
7. Is the static memory and virtual hardware-interface design appropriate for the
   Mega 2560?
8. Is representing `PUMP_HOME` in command identity with `targetSteps = 0`
   sufficiently unambiguous, or should the identity representation be changed?
9. Before connecting this controller to Arduino GPIO and the serial dispatcher,
   what additional interface or lifecycle tests should be required?

## Explicitly out of scope

- Arduino GPIO adapter and pin initialization.
- Integration into production `main.cpp`.
- Serial-dispatch and command-lifecycle wiring.
- Firmware upload or physical motion testing.
- Wet testing, pump calibration, or route validation.
- P2 motion integration.
- Valve orchestration, which belongs to the backend.

## Acceptance gate for the next checkpoint

Before production integration begins, the review should:

- identify no unresolved critical or high-severity motion-safety defect;
- agree on target-zero versus explicit-homing semantics;
- approve or amend the HOME-release policy; and
- confirm the required lifecycle tests for the Arduino/serial integration slice.
