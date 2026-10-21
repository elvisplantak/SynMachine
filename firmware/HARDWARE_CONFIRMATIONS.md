# Hardware confirmations

## Supervised wet-test startup halted — 2026-10-21, boot 111

Fresh full-block approval and powered readiness preceded the attempt using
runner 87a6afd and installed firmware dc7a53f. Initial mixer STOP, SF CLOSE,
V1-V8 HOME and the P1 Waste route completed. P1 ordinary startup PUMP_HOME
then returned FAILED/PUMP_MOTION_TIMEOUT with execution_started=true. This
was not PUMP_ASPIRATE_FULL_STROKE. No priming, B1 transfer, P2 command, mixer
START, Column or carousel command followed. Owner is durably BLOCKED and
ports are closed; no retry, state reset, new bundle or post-fault movement.

The operator first reported P1 HOME pressed/power ON, then corrected that
HOME may not be pressed and now thinks P1 is only near the switch. Physical
HOME contact is unconfirmed; do not preserve the earlier statement as fact.
Motor power was requested OFF but this is not yet confirmed. No new sensor
polarity, travel allowance, reference or mechanical fault is inferred.
Read-only pump HOME diagnostics are being prepared, not uploaded or sampled.
Evidence: docs/commissioning/2026-10-21/wet-01-result.json.

## Requested supervised wet-test preparation — 2026-10-21

The owner requested nominal one-full-stroke 20 mL from B1 colored water into
Reactor, Reactor-to-SF transfer, SF mixing for 20 seconds, then SF-to-P2-to-Waste.
Column and carousel are excluded. B2 contains ordinary water. S was initially
empty; the owner now confirms S filled with ordinary water, its intake submerged
and Reactor empty. P1 priming is approved as two 5 mL S-to-P1-to-Waste cycles.
The owner also approved two 5 mL Reactor-to-P2-to-Reactor return-priming cycles
after Reactor filling. SF empty, free mixing element, clear Waste and USB
connections were reported. Motor power is last reported OFF; fresh powered
readiness and final Waste-air-gap/mixer preparation remain pending.

The owner explicitly selected software preparation of full-stroke aspiration
and approved a 600 pulses/s SF trial (prepared integer interval 1667 us).
These are requested trial inputs, not confirmed physical results. No new pins,
direction, volume calibration, route geometry or working limits are inferred.
The owner subsequently explicitly approved uploading prepared commit
`dc7a53fcdd93315965bf82ba143bf4def17688e7` with motor power OFF. The upload
completed with signature 0x1e9801 and all 41570 flash bytes verified (exit 0); HEX
SHA256 is 61feb4425fddee73799191faf5a1bf98bb684db601a598712b30a7fe8a1c0d45.
This is now the installed artifact. No actuator command, application Serial
monitor, EEPROM provisioning or wet test was performed. Full stroke and 600
pulses/s mixing remain physically unverified; power is last reported OFF.
Evidence: docs/commissioning/2026-10-21/upload-verification.json.

## Owner clarification: colored-liquid prototype materials — 2026-10-20

The owner clarified that the prototype's intended purpose is mechatronic testing
with colored liquids. Current tubing is silicone; valves and syringes are described
by the owner as medical plastic. No exact polymer grade or manufacturer rating is
inferred. Planned upgrades are PTFE tubing/valves and glass syringes with PTFE
plungers for progression toward actual reagent/solvent procedures, with materials
selected for the particular chemistry. These are owner statements/plans, not new
chemical-compatibility measurements or hardware already installed. Repository
consolidation performs no physical test, device connection or firmware upload.

## Owner-reported material scope — 2026-10-19

For public documentation preparation, the owner clarified that the present
project evaluates mechanics, electronics, electrical wiring/power and software.
PTFE valves and tubing have not yet been installed. Chemical compatibility of
the complete wetted system has not been established for intended chemistry.
Prior dry checks and reported liquid checks do not supply that compatibility
validation. No alternative installed material, reagent list, temperature/pressure
rating or chemical capability is inferred. No device action accompanies this
public-documentation clarification.

## User-reported independent liquid checks — 2026-10-19

The user reports having independently performed liquid tests multiple times and
that those tests were satisfactory. They requested preparation of the real-device
Recipes UI, choosing the existing high-level recipe actions and mL/step-based
pump operation rather than raw valve sequences or time-driven pumping. They will
perform the next liquid test themselves after preparation.

This records the user's operational report. No specific tested volumes, liquids,
route list, delivered-volume measurements, HOME entry order, automatic flush
volumes/drain timing or current device references were supplied. It does not
change the nominal 1025 steps/mL mapping, actuator wiring/coupling or previous
commissioning records, and supplies no new command or motion during software
preparation. Current readiness remains a fresh per-attempt operator declaration.

## SF mixer detached-wire recheck accepted — 2026-10-11, boot 98

The user found one motor wire detached from its joint after the boot96 abnormal
physical test, requested a new short SF-only test, and asked to keep motor power
OFF until preparation was finished. With 44 fake/ownership checks passing and
USB port unoccupied, the host signalled readiness. User confirmed power-ready,
secured connection, empty SF and free element before any real connection.

STOP -> START -> wait 3 seconds -> STOP completed in boot98: all 3 durable
commands and 2 owned sequences COMPLETED, owner idle, exit0, connection closed.
The user confirmed normal physical rotation and stop without twitching or
unpleasant buzzing. This isolated dry start/stop check is accepted. The detached
wire is a user-reported finding, not a measured electrical diagnosis.
Existing D6/D7, DIR=LOW and 500 pulses/s unchanged; firmware still e2e9d3c.
Other actuators uncommanded, no upload/retry/reconnect/production activation.
Motor power last confirmed ON; no further motion queued. Boot96 failure and
boot94 corrected physical acceptance remain unchanged. No wet-performance or
complete-demo physical mixing claim. Evidence: docs/commissioning/2026-10-11/README.md.

## SF mixer cable repair: isolated recheck — 2026-10-10, boot 96

The user reported that SF mixing did not physically occur during boot94 due to
an observed damaged motor cable, and that the cable was repaired today. This
supersedes only yesterday's SF physical confirmation, not the durable command
results or other actuator observations. Raw event journals and SQL remain intact.
Today is SF-only; the previously proposed liquid check is deferred.

With fresh empty-SF/free-element/motor-power-ON confirmation, the authorized
STOP -> START -> wait 3 seconds -> STOP completed in boot96. All three durable
commands and two owned sequences completed; owner idle and connection closed.
Existing DIR=LOW and 500 pulses/s profile unchanged. No pumps, valves, carousel,
Reactor, SF bottom adapter, firmware upload or production activation. Forty-four
fake-only/ownership checks passed. The user reports that physical operation was
not normal: twitching and buzzing with an unpleasant sound. The user switched
motor power OFF. This isolated physical test is NOT accepted; root cause is not
established. No further movement attempted. Software completion
alone does not confirm rotation or mixing performance.
Evidence: docs/commissioning/2026-10-10/README.md.

## Whole supervised empty-system demo — 2026-10-09, boot 94; SF observation corrected

Boot93 first handshook Arduino but SF read-only identity probe returned
There is no status packet. Verified zero actuator commands/phase plans/waits;
exit1, closed, no retry/cleanup. Its probe owner remains BLOCKED and unchanged.
The user clarified SF servo power had been OFF, switched it ON and explicitly
requested repeating. A separately authorized fresh attempt followed only because
the first attempt proved no actuation; no unresolved physical command was retried,
no blocked owner adopted/released, no journal replayed. In boot94 the existing
SF adapter read present_position2573, torque OFF, CLOSED within tolerance.

Bootstrap plus all ten existing Guided Demo phases completed normally in one
Arduino session: 57 Arduino + 4 SF commands, 6 timed waits, all durable entries
COMPLETED; exit0 and connection closed. About 7 minutes15 seconds elapsed. Scope
was empty system, nominal10ml (S6/B1 1.6/B2 2.4), Reactor mixer OFF, SF mixing10s,
settling5s and two5s fractions. Carousel reference1 used fresh user alignment;
actual move1-to-2 occurred while Column CLOSED. User saw the full sequence and
initially confirmed all pumps/valves/SF mixer/SF bottom/Column/carousel operated
normally. On 2026-10-10 the user corrected the SF mixer observation: its damaged
motor cable prevented rotation. The original statement remains historical;
whole-demo physical SF mixing acceptance is withdrawn. Other actuator
confirmations and all software command completions remain unchanged.
It does not confirm wet flow/sealing/delivered volume, general startup/Recovery
HOME orders, production profile, or Reactor mixer control.

Final command-confirmed P1=P2=20500; V1=180,V2=90,V4=90,V6=90,V3=180,V7=90,
V8=90,V5=90; SF bottom CLOSED, Column CLOSED4, SF mixer OFF, carousel2. No
actuator left at HOME, hence no terminal parking required. These positions are
historical after close, not current-session references for a later reconnect.
No host connection/queued motion remains; motor power last confirmed ON.
Installed firmware remains e2e9d3c, no new upload. Events/SQL/result verification:
docs/commissioning/2026-10-09/full-dry-demo-56594eb7-bbbb-4525-9254-e99d585a01c6/.

## Terminal release dry acceptance and full-demo prerequisites — 2026-10-09

Following explicit empty-system/power-ready/closed-bottom/Reactor-stopped approval,
boot 91 completed 16 commands: HOME V1/V2/V4/V6/V3/V7/V8/V5, then terminal nominal
5 degrees in the same order. All durable results were COMPLETED and the host
closed without retry or cleanup. Pumps and other actuators were not commanded.
The user subsequently confirmed all V1-V8 offsets normal and HOME levers released.
This establishes this dry 22-step (4.95-degree) release, not safe wet alignment.

Boot 92 completed the P2-only 12-command block: HOME V3/V7/V8/V5; select P2 Waste
V5=180 -> V8=90 -> V7=90 -> V3=180; P2 HOME -> 1000 -> HOME -> terminal 1000.
All durable results were COMPLETED; exit 0, connection closed, no error/retry/
cleanup. P1 remained uncommanded. The user confirmed P2 normal movement and
HOME-lever release. This dry P2 short-stroke/parking check is accepted; it is not
new measured-volume calibration. Historical positions do not establish fresh
references on reconnect. Installed firmware remains e2e9d3c, no new upload.
Evidence/events/SQL/result verification: docs/commissioning/2026-10-09/
valve-park-dry-88a0ba90-c9df-4aab-9929-28d27acc954a/ and
p2-pump-dry-2282ffd4-54ee-4598-a071-3cd01b5dee9d/.

The user approved continuing into one whole supervised empty-system demo, stated
that components are connected, and explicitly confirmed carousel aligned at tube
1 and installed SF mixing element safe in existing DIR=LOW clockwise direction
viewed from motor front. Motor power last confirmed ON; Reactor remains stopped.
These are fresh operator statements, not sensor readings or generic wet-startup
approval. No new Reactor mixer control/pins are inferred from connected hardware.
The full dry demo subsequently completed; its SF physical observation was later
corrected as recorded above.
Production profile, wet acceptance, UVP and animation remain gated.

## Terminal HOME release request — earlier preparation, 2026-10-09

The user selected a separate end-of-whole-test/procedure movement for actuators
left at HOME: P1/P2 to 1000 absolute steps and V1-V8 to nominal 5 degrees. The
existing 400 steps/90 degrees ratio maps this trial to 22 steps (4.95 degrees).
This is an authorized trial target, not confirmed release distance or safe wet
alignment. The existing Column bottom CLOSED offset remains 4 degrees; no new
HOME offset is assumed for the SF bottom adapter.

Software preparation uses existing sequential Service commands. HOME still
establishes coordinate zero. Only successful completion of the entire dry block
permits its parking suffix; failure/unknown result/cancellation halts without
parking or retry. Pump parking requires the block's verified Waste selection.
The valve controller verifies stable HOME release at 22 steps, without further
travel if release fails. Hardware validation is still required.

All 211 warning-enabled native tests and the Mega build passed (41056 flash,
3148 static SRAM bytes). The user subsequently confirmed motor power OFF and
explicitly authorized upload. Firmware e2e9d3c is now installed on the same
confirmed Mega USB identity; avrdude verified all 41056 flash bytes, with HEX
SHA-256 matching the prepared artifact. No actuator command or EEPROM provisioning
occurred. Evidence: `docs/commissioning/2026-10-09/terminal-parking-upload-verification.json`.
At upload completion motor power was confirmed OFF. With subsequent NEW
empty-system/closed-bottom/stopped-mixer prerequisites, motor power ON and explicit
approval of the P1-only full-span block, boot 90 completed all 8 commands:
HOME V1/V2 -> P1 Waste (V2=180, V1=180) -> P1 HOME -> 20500 -> HOME -> 1000.
The user physically confirmed normal P1 return to HOME, subsequent parking away
and release of the HOME lever, without unusual sound. This confirms this dry P1
full-span HOME and terminal 1000-step check; it does not prove the cause of boot
87's earlier failure or wet behavior. The earlier failed journal is unchanged.
No error/retry/cleanup occurred, and the connection closed. Other actuators were
not commanded. Last commanded V1/V2=180 and P1=1000 are historical only after
reconnect; motor power is last confirmed ON. Valve 5-degree release and P2 pump
checks remain pending and need separate fresh readiness/authorization. Evidence:
`docs/commissioning/2026-10-09/p1-span-dry-521e41d1-4885-4972-bb46-00ddea2d05f5/`.
Commissioning scope: `docs/commissioning/2026-10-09/README.md`.

## Slower route-valve firmware and grouped dry checks — 2026-10-09

At the user's request to resume testing with slower valve movement, source now
uses a 4000 us STEP interval for V1-V8 instead of 2000 us. This halves the nominal
pulse rate from 500 to 250 steps/s; 400 steps per 90 degrees remains unchanged.
The interval applies to both HOME searches and position moves. Pulse width,
direction setup, HOME filtering, search/release bounds and failure behavior are
unchanged. Pumps and other actuators retain their existing timing.

This is a software preparation, not a confirmed physical speed or a repair of
the original V2 `VALVE_HOME_SWITCH_UNEXPECTED` failure described below. Focused
valve controller/runtime verification passed 18 tests; all 197 native tests passed
with `-Wall -Wextra -Werror`. New/extended coverage checks pulse deadlines after
delayed updates and HOME pulse spacing across clock wrap. Mega 2560 build passed:
40806 flash bytes and 3140 static SRAM bytes, unchanged from the prior build.

After software preparation, the user confirmed motor power OFF and explicitly
authorized upload. Production firmware `caef934` was uploaded to the confirmed
Arduino Mega USB identity ending `14532303532351F0D070-if00` (`/dev/ttyACM1`).
Avrdude verified all 40806 flash bytes against the built HEX; SHA-256:
`d67e80eb8003c9b9fc2f8e35fc0d3c3f23175561c2671627e55f8f0739ce65d9`.
No EEPROM provisioning or actuator command was performed during upload. Motor
power was confirmed OFF for upload. The host runner was prepared for today's evidence directory;
five fake-only supervision checks and the offline two-command preview passed.

The separately authorized boot-84 V2 recheck completed HOME and V2=90 without
error and closed. The user confirmed HOME/acceptable slower movement; visual
confirmation of the final 90-degree position is pending. This does not resolve
the original fault. Motor power was last confirmed ON for this check.

With fresh readiness, boot 85 completed the grouped dry P1 block: 19 commands on
V1/V2/V4/V6, pumps stationary, no error/retry. The user confirmed that all movements
were normal without binding or unusual sound. The earlier V2 error did not recur;
its original cause remains unproven. Final commanded V1=180, V2=90, V4=90, V6=90.

The user then approved the described P2 block in reply to listed prerequisites.
Its planning guards were operator-declared empty system, power readiness, SF and
Column bottom CLOSED and Reactor mixer OFF, not sensor measurements. Boot 86
completed all 25 commands on V3/V7/V8/V5 without error/retry. Final commanded
V3=90, V5=180, V7=90, V8=90; the user confirmed the complete block proceeded correctly.
No pump, mixer, bottom valve or carousel command was sent. Both connections closed.
P1/P2 host supervision checks passed nine/ten fake-only tests respectively.

The isolated four-valve HOME orders used in these empty-system checks are not a
general startup/Recovery procedure. These selected transitions do not establish
liquid flow, sealing or every route-history case. Historical positions/readiness
cannot establish fresh trust on reconnect. Obtain NEW readiness before any next
powered test. No pump/wet/full-demo acceptance is claimed. Scope and journals:
`docs/commissioning/2026-10-09/README.md`. Upload evidence:
`docs/commissioning/2026-10-09/upload-verification.json`. GitHub pushes are deferred
at the user's request while connectivity/authentication is being resolved.

The subsequently approved dry pump block on boot 87 halted at command 9.
Eight commands reported COMPLETED: P1 Waste setup, initial P1 HOME, absolute
1000, return HOME and absolute 20500. The following P1 HOME failed with
`PUMP_MOTION_TIMEOUT` after approximately 31.1 seconds; the journal records
FAILED with execution started. The installed controller reports this error
when the bounded HOME search reaches 20500 pulses without accepting HOME.
No final physical position or failure cause is established by this receipt.
The connection closed without retry or cleanup motion. P1 final 200 and all P2
setup/pump commands were not sent. Operator physical observation is pending;
motor power OFF was requested but is not yet confirmed. No full-span pump
acceptance or limit change is claimed. Evidence:
`docs/commissioning/2026-10-09/pump-dry-fa3ce511-3f30-4170-9fed-c68eb98a897e/`.

The user subsequently observed P1 seated at HOME, pressing the switch, with
normal sound. This confirms the visible mechanical arrival, not the electrical
HOME level or its timing at the final pulse. The failed command remains FAILED;
this observation does not establish trusted coordinate zero. The user subsequently
confirmed motor power OFF. Inspection of installed source shows that after the
final permitted pulse an inactive immediate read terminates HOME without waiting for later activation;
activation after that read is a possible explanation, not an established cause.

A software-only correction is now prepared and natively verified; see
`docs/commissioning/2026-10-09/README.md` and the serial protocol's pump HOME
section. It waits motionless for a late signal without increasing search travel.
This is not a measured switch-settling fact or a confirmed repair of the physical
failure. At preparation the installed firmware was `caef934`. The user then
explicitly approved upload while motor power remained OFF. Firmware `8a5d93c`
is now installed on the same confirmed Mega USB identity; avrdude verified all
40880 flash bytes, with prepared HEX hash unchanged. No actuator command or
EEPROM provisioning occurred during upload. Evidence:
`docs/commissioning/2026-10-09/pump-home-wait-upload-verification.json`.
Full-span HOME and P2 pump acceptance remain pending. No physical retest or Serial
reopen followed upload; NEW powered-test readiness/authorization are required.

## Current supervised P1 dry-check checkpoint — 2026-10-07

The user authorized a valve-only dry P1 procedure with stationary pumps and an
empty system, then a separate bounded V2 recheck. Fresh motor-power readiness
was obtained for each powered test. Existing backend planner/Serial/durable
Service primitives were used; no firmware code, upload or live demo profile changed.

In boot 80, HOME V1/V2/V4/V6, V6=180 and V1=90 completed and the user confirmed
each physical result. The next V2=90 command failed after STARTED with
`VALVE_HOME_SWITCH_UNEXPECTED`. The host stopped and closed without retry or
cleanup motion. The user did not observe that attempted movement, then confirmed
motor power OFF and that V2's HOME lever was close to, but not pressing, the switch.
This later mechanical observation does not establish the electrical input at failure.

The separately approved HOME V2 -> V2=90 recheck in boot 81 completed both commands.
The user confirmed correct HOME and movement away to the expected position without
abnormal behavior. The original failure's cause remains unresolved; this is not
proof of a repaired switch, wiring, stable signal or a complete verified route.

At the user's stop, latest physically confirmed nominal positions are V1=90,
V2=90, V4=HOME and V6=180. These historical observations cannot restore reference
trust after reconnect/reset. No pump, P2 or other actuator was exercised.
The full 19-command P1 plan was not completed. Evidence and SQL journals:
`docs/commissioning/2026-10-07/README.md`.

The user requested slower valve rotation for later checks. Current source's
2000 us STEP interval/400 steps per 90 degrees is unchanged. A slower profile
requires a separately prepared/verified firmware timing change and upload approval;
no unsupported speed field or workaround is inferred. The user plans to resume
on 2026-10-08. At stop the connection is closed and there is no queued host motion.
Motor power was last confirmed ON for the recheck; OFF was requested but has
not yet been confirmed. Obtain NEW readiness before every next powered test.

## Current V7/V8 repair and commissioning checkpoint — 2026-09-29

This checkpoint supersedes the historical V7/V8 drive-fault status and STEP/DIR
mapping below for the current wiring. Historical production-test records remain
historical evidence, not a declaration that their configuration is still installed.

The user repaired the damaged motor connection, then discovered that a driver
had remained disconnected while a different driver was being wired. After reconnecting
it, the user observed motor operation and explicitly declared the fault resolved.
Earlier no-motion tests do not establish a failed motor or driver. The exact original
cause of the melted connection and long-term thermal performance are not established.

Physical identities below use the user's labels "old V7" and "old V8", not the
historical software names for the diagnostic channels:

| Physical identity | Diagnostic channel | STEP | DIR | Latest physical evidence |
|---|---|---|---|---|
| Old V7 | A | D34 | D35 | 266 pulses at DIR LOW moved approximately 60 degrees toward HOME; explicitly confirmed |
| Old V8 | B | D36 | D37 | 133 pulses at DIR LOW moved this motor toward HOME; identity and direction explicitly confirmed |

The user subsequently explicitly confirmed that old V8 moved toward HOME at
DIR LOW. Both individual-valve identities and HOME directions are now confirmed.
Earlier contradictory observations must not override these single-valve tests.
No tubing identity or route has been changed by these tests.

Manual HOME-switch tests with motor supply OFF now confirm:

- physical old V7: D3 LOW -> HIGH for about 2.5 s -> LOW; D2 stayed LOW;
- physical old V8: D2 LOW -> HIGH for about 1.9 s -> LOW; D3 stayed LOW.

The recorded transitions are in `docs/commissioning/2026-09-29/home-switch-transitions.jsonl`.
Both inputs remain INPUT_PULLUP, active HIGH. Production source is now corrected
to V7 D34/D35/HOME D3 and V8 D36/D37/HOME D2, both DIR LOW toward HOME.
Other actuator bindings, timing, limits, protocol and EEPROM logic are unchanged.

Previously installed for the movement tests: bounded pin-discovery diagnostic, maximum 133 pulses per
burst, 10 ms pulse spacing, 20 us STEP high, no automatic startup movement.
The Mega build/upload verification passed (5680 flash bytes, 278 static SRAM
bytes); six focused native tests passed. The 60-degree test used two separately
armed 133-pulse bursts on A. With the previously confirmed 400 pulses per 90
degrees and unchanged microstep settings, totals are nominally 29.925 and 59.85
degrees. These are relative moves, not HOME searches or position calibration.

Successful powered single-valve test logs are retained in
`docs/commissioning/2026-09-29/`. STATUS OK confirms diagnostic command execution;
physical identity/direction comes from the operator. Attempts later reported to
have motor power off are excluded from physical evidence.

Current session: corrected production firmware is installed and flash-verified
(40806 flash bytes, 3140 SRAM bytes), replacing the read-only probe. Verification:
12/12 focused valve tests and 196/196 warning-enabled native tests passed; Mega
build passed. Added regression checks LOW-direction HOME switch stop and HIGH
direction for departure. Probe source remains in `tools/home_input_probe`.

The supervised production-path regression completed in controller boot 71:
V7 HOME -> V7 90 degrees -> 10-second pause -> V8 HOME -> V8 90 degrees.
All four durable commands reached COMPLETED without retry. The user explicitly
confirmed both valves stopped at their HOME switches, returned correctly to
90 degrees, and the tests passed. V7/V8 repair and dry recommissioning are closed.
Evidence: `docs/commissioning/2026-09-29/home-and-90-events.jsonl` and the associated
SQLite journal SQL export. These include software outcomes; physical success is
the operator confirmation recorded here.

Final state: both valves last physically confirmed at 90 degrees; host Serial
connection closed; no queued motion. Motor power was last confirmed ON and
power-off was requested but not yet confirmed. A later Arduino reset invalidates
volatile position trust; stored logs do not re-establish current position trust.
Other route valves and pumps were not exercised, so this is not full P2 route,
wet operation, or end-to-end demo validation.

Before EVERY powered physical test, explicitly ask the user to enable motor
power and wait for a NEW readiness confirmation; never reuse an earlier one.
Next software work remains backend lifecycle/shared ownership integration under
fake transport. A future end-to-end dry test needs a fresh hardware session and
independently verified route readiness.

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

### Deferred Column Service UI attempt with coupling removed — 2026-08-13

After a successful V1 HOME-to-90-degree smoke test, the user attempted
`COLUMN_BOTTOM_VALVE_HOME` from the live Service UI while the Column valve
shaft/coupling pin was intentionally removed pending replacement to prevent
future slipping. The disconnected mechanism could not provide a valid
end-to-end mechanical HOME test or actuate the installed HOME relationship as
normally assembled.

The backend command timed out before receiving a terminal lifecycle result and
durably recorded `OUTCOME_UNKNOWN`. It was not retried. The UI and backend were
stopped, and the user explicitly confirmed that machine motor power was then
switched off. Five accidental SF bottom valve UI requests during this session
all failed closed with HTTP 503 because the U2D2 runtime was not configured;
the backend did not open or command the SF actuator.

This attempt confirms no Column HOME or operating position. After the new
shaft/coupling pin is installed, testing must begin in a new controller session
with a fresh command identity and a supervised HOME operation before CLOSED or
OPEN positioning. The prior unknown command must never be resent.

### Reassembled `COLUMN_BOTTOM_VALVE` calibration — 2026-08-15

After installation of the replacement shaft/coupling pin, the previous OPEN
pulse target no longer reached the visually known physical OPEN position. A
backend-independent, no-motion-on-boot commissioning firmware used only the
confirmed D10 HOME, D12 STEP, D13 DIR, DIR HIGH away from HOME, 20 us STEP HIGH,
and 1,000 us rising-edge interval.

With the operator at motor power, the following sequence was physically
confirmed:

1. D10 read `HIGH` while HOME was pressed with motor power off and on;
2. 889 DIR HIGH pulses moved from HOME to the correct CLOSED position and
   released D10 to `LOW`;
3. incremental bounded DIR HIGH and DIR LOW adjustments located the visually
   confirmed OPEN position at 23,850 pulses from CLOSED;
4. therefore the reassembled absolute targets are `CLOSED = 889` pulses and
   `OPEN = 24,739` pulses from HOME; and
5. motion was reported smooth, with no abnormal sound, and the user explicitly
   confirmed the final physical OPEN position.

This post-reassembly calibration supersedes the earlier 20,889-pulse OPEN
target for production positioning. The canonical Service/API command remains
`94` degrees as the logical OPEN label; `24,739` is now the authoritative
physical pulse target. Leak-tightness and liquid-route verification remain
pending.

### Production HOME diagnostic and safe parking — 2026-08-15

Read-only production snapshots during a motionless HOME request at the
physically pressed switch repeatedly reported
`CONFIRMING_HOME`, `stage_steps=0`, and mostly D10 `HIGH` with intermittent D10
`LOW` samples while motor power was on. No STEP pulses were emitted. After
motor power was physically removed, D10 remained sufficiently stable HIGH for
the same production command to return HTTP 200 / `COMPLETED`.

This establishes that the pending HOME behavior is caused by an unstable D10
signal under powered-machine conditions, not by HOME direction, step count,
backend timeout, or attempted motor travel. The source of that instability and
the appropriate electrical or bounded software filtering correction remain
unresolved; the HOME interlock must not be bypassed.

At session end, the tested no-motion-on-boot Column commissioning firmware was
flash-verified, D10 read `HIGH` at HOME, and one explicitly armed DIR HIGH move
of exactly 889 pulses completed. The user confirmed the physical CLOSED
position was correct and D10 read `LOW`. Motor power was then physically
switched off. The Mega is intentionally left on the commissioning firmware and
must be restored to the production image before any Service-path test.

### Production Column Service regression and D10 filtering — 2026-08-16

After restoring production firmware, supervised Service-path testing confirmed
that the powered D10 input remained noisy while the HOME lever was physically
pressed. A bounded active-evidence filter allowed a motionless HOME request at
the already pressed switch to complete with HTTP 200 without bypassing the HOME
interlock. An initial release-filter revision still allowed D10 transitions to
delay HOME-to-CLOSED movement by approximately 30 to 60 seconds, although that
request eventually reached the correct CLOSED position and returned HTTP 200.

The release path was then changed to use only the already confirmed mechanical
facts: from trusted HOME it may move at most 889 pulses in DIR HIGH, away from
HOME, without interpreting raw D10 transitions. At that CLOSED/release bound,
STEP is held inactive and D10 must remain continuously LOW for 30 ms before
positioning may complete or continue. A still-active or unresolved input fails
closed without any motion beyond the 889-pulse bound.

The flash-verified production build with that release behavior completed this
supervised dry sequence through the backend/UI Service path:

1. CLOSED to HOME, with correct travel and physical HOME-lever activation;
2. HOME to CLOSED, starting immediately and reaching the confirmed position;
3. CLOSED to the visually confirmed OPEN position;
4. OPEN to HOME, stopping on physical HOME activation; and
5. HOME to CLOSED, again starting immediately and parking correctly.

Every command returned HTTP 200, UI controls were disabled only while its
command was running, and the user reported normal direction, movement, stop,
and final positions with no abnormal sound or impact.

Read-only snapshots during the longer OPEN-to-HOME return also showed repeated
false HOME candidates under motor power. The per-stage diagnostic counter reset
after each rejected candidate, revealing that the nominal 80,000-pulse search
limit was not cumulative. Firmware now keeps a separate whole-command HOME
search counter, reports that cumulative value during HOME diagnostics, and
times out exactly at 80,000 total pulses even across rejected candidates. The
final build passed 183/183 warning-enabled native tests, used 39,394 bytes of
flash and 3,079 bytes of static SRAM, and was uploaded and flash-verified with
motor power off. No additional motion was performed after that accounting-only
safety correction. The valve remains physically at the confirmed CLOSED
position and the user confirmed motor power off.

### Final production Column regression after HOME-search accounting correction — 2026-08-16

A subsequent supervised UI-to-hardware regression used the final production
firmware in controller boot session `58`. Four `OPEN` requests made before a
fresh HOME reference were rejected with `INVALID_FIELD` and
`execution_started=false`; the motor did not move. This confirms that a new
controller session fails closed and does not reuse the previous session's
volatile Column position trust.

The operator then completed `HOME -> OPEN -> CLOSED`. All three commands were
durably recorded as `COMPLETED` with `execution_started=true`, and the user
physically confirmed that the complete test passed. This supersedes the prior
statement that no physical motion had been performed after the accounting-only
correction: the final production firmware and its required HOME-first session
behavior are now physically validated. The Column bottom valve finished at the
confirmed CLOSED position.

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

### User-confirmed V1-V8 connection change behavior — 2026-10-06

Asked about the installed V1-V8 switching between 90 and 180 degrees, the user
explicitly confirmed that the old connection is interrupted before the new
connection opens. Record this as operator-confirmed break-before-make behavior
for that change, together with the endpoint semantics above.

This is not a new measurement of timing, sealing, pressure or passive fluid
movement. It does not approve an overall valve switching/HOME order or physical
execution. Destination-order approval is recorded separately below;
no extra HOME step is inferred to be necessary solely to prevent overlap of the
old and new connection in a 90/180 change.

### User-approved demo destination switching orders — 2026-10-06

After reviewing the concrete proposal, the user explicitly confirmed all ten
destination switching orders for the supervised demo:

| Destination route | Approved ordered targets in degrees |
| --- | --- |
| S -> P1 | V6=180 -> V1=90 |
| B1 -> P1 | V4=180 -> V6=90 -> V1=90 |
| B2 -> P1 | V4=90 -> V6=90 -> V1=90 |
| P1 -> Reactor | V2=90 -> V1=180 |
| P1 -> Waste | V2=180 -> V1=180 |
| Reactor -> P2 | V3=90 |
| P2 -> SF top | V7=180 -> V3=180 |
| SF bottom -> P2 | V8=180 -> V7=90 -> V3=180 |
| P2 -> Column | V5=90 -> V8=90 -> V7=90 -> V3=180 |
| P2 -> Waste | V5=180 -> V8=90 -> V7=90 -> V3=180 |

Procedure: keep pumps stationary while switching, await each command completion,
omit already-reached targets and retain positions of valves not selected by the
destination. Keep SF bottom CLOSED during P2 switching and Column bottom CLOSED
during filling. Start pumping only after route commands complete, preserving
the existing Reactor mixer-stopped requirements for Reactor/SF transfer.

This is approval of the proposed demo procedure, not a new observed dry/wet
test result. These destination orders do not select the overall startup/Recovery
valve HOME order or grant physical-test authorization. Earlier dry Waste HOME
setup records remain evidence for those distinct recorded setups. The user
asked about a future supervised machine check; before each actual powered test,
obtain its concrete authorization and a new motor-power readiness confirmation.

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
- Precise pump volumetric calibration remains pending; the later accepted
  demo-only nominal mapping does not replace it.
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

### Accepted demo-only P1/P2 nominal volume mapping — 2026-08-16

For the supervised colored-liquid demo, the user explicitly accepted the same
linear nominal mapping for P1 and P2:

- raw position `0` = nominally `20 ml` in the syringe chamber;
- raw position `20500` = nominally `0 ml` in the syringe chamber; and
- nominal conversion = `1025 steps/ml` across that full coordinate range.

Therefore the nominal chamber-content display mapping is
`volume_ml = (20500 - position_steps) / 1025`. Aspirating increases nominal
chamber content by moving toward lower raw positions; dispensing decreases it
by moving toward higher raw positions, preserving the confirmed physical
orientation above.

This is an explicitly accepted demo approximation for low-risk liquids, not a
precision calibration, measured delivered-volume claim, dead-volume correction,
repeatability result, or production working-margin decision. Precise P1/P2
calibration remains deferred for the real machine.

### User-selected nominal demo pump range — 2026-10-06

For the supervised demo, the user explicitly selected the following for both
P1 and P2, citing the previously successful pumping tests:

- working full-chamber coordinate: `0` steps;
- working empty-chamber coordinate: `20500` steps;
- additional endpoint reserve: none;
- nominal working volume: `20 ml`, retaining the existing `1025 steps/ml` mapping;
- precise measured-volume calibration: deferred for this demo.

This resolves the earlier pending working-margin choice for `DEMO_NOMINAL`
use only. It is a user-selected demo policy, not a new measurement, precision
calibration, production working-range validation or physical-execution approval.
The common aspiration/dispense orientation and existing mechanical evidence
remain unchanged.

The current communication contract still permits ordinary absolute pump targets
only in `1..20500`; reaching zero requires `PUMP_HOME`. The backend planner
currently rejects an ordinary aspiration that would end at zero, including a
nominal 20 ml stroke from 20500. This record does not alter that contract or
authorize replacing a volume transfer with HOME.

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

### Confirmed end-to-end V1-V8 Service UI path — 2026-08-13

The user explicitly authorized and performed a supervised dry V1-V8 test from
the live Service UI through the backend durable-command API, LABFORGE/1 Serial,
the production firmware runtime, and Arduino GPIO. The operator remained at the
machine and selected the commands manually rather than using an automatic
cascade.

The durable journal recorded 39 requests on trusted controller boot ID 34:

- 38 commands reached terminal `COMPLETED` with `execution_started=true`;
- every valve V1 through V8 completed `VALVE_HOME`, 90-degree positioning, and
  180-degree positioning;
- 0-degree positioning also completed for V1-V4 and V6-V8; V5 0 degrees was
  not requested in this session; and
- one additional V6 180-degree request was terminally rejected as
  `INVALID_FIELD` with `execution_started=false`, so it caused no actuator
  movement. V6 had already completed a separate 180-degree request and later
  completed its final 90-degree request.

The user physically reported that all eight valves operated as planned. The
final journaled positions were V1, V2, and V4-V8 at nominal 90 degrees, and V3
at nominal 180 degrees. No outcome remained unknown and no automatic retry was
performed.

Focused follow-up retests then completed V6 at 180 degrees and returned it to
90 degrees, and completed V8 at 180 degrees and returned it to 90 degrees. The
user confirmed V6 movement; both V8 commands had terminal `COMPLETED` lifecycle
results. A separate accidental V8 90-degree request was rejected as
`INVALID_FIELD` with `execution_started=false`. Together with the earlier V6
rejection, this exposed a backend concurrency gap: the SQLite journal was
thread-safe, but the shared durable executor/Serial transaction was not
globally serialized across FastAPI worker threads. The backend and UI were
stopped before diagnosis and no further physical command was issued as part of
the software correction.

This confirms the supervised end-to-end V1-V8 Service UI control path. It does
not verify liquid routing, port isolation, leak-tightness, missing-HOME
mechanical protection, or unattended/production operation; the accepted
demo-only HOME assumptions remain unchanged.

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

The first supervised dry test exercised the backend API, durable backend
command journal, LABFORGE/1 Serial session, production firmware lifecycle
handling, and confirmed Arduino Mega GPIO controllers. A subsequent supervised
test exercised the same four operations by clicking the actual Service UI,
thereby additionally confirming the frontend-to-backend boundary. The operator
manually established and visually confirmed the safe Waste routes before
enabling motor power:

- `P1 -> V1(180 degrees) -> V2(180 degrees) -> Waste`
- `P2 -> V3(180 degrees) -> V7(90 degrees) -> V8(90 degrees) -> V5(180 degrees) -> Waste`

The following commands each reached a terminal `COMPLETED` result first through
direct backend API invocation and then, in the final end-to-end test, through
the Service UI:

1. P1 `PUMP_HOME`
2. P1 `PUMP_MOVE_ABSOLUTE_STEPS` to `2,000`
3. P2 `PUMP_HOME`
4. P2 `PUMP_MOVE_ABSOLUTE_STEPS` to `2,000`

The operator physically confirmed correct movement toward HOME, correct stop
on each HOME switch, and smooth absolute movement away from HOME. No impact,
slipping, binding, abnormal sound, or other unusual physical behavior was
observed in either run. In the final UI-driven test, the UI displayed a
successful terminal result for all four operations. P1 and P2 were left at
2,000 steps before machine motor power was explicitly switched off.

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

### Confirmed carousel Service path — 2026-08-16

With the Column bottom valve homed and parked at its trusted CLOSED position in
controller boot session `58`, the operator physically aligned tube 1 and the
production UI/backend/Serial path completed `CAROUSEL_SET_REFERENCE` at logical
position 1 without carousel motion. The supervised movement sequence then
completed:

1. position 1 to position 2;
2. position 2 to position 10;
3. position 10 to position 40; and
4. the one-position logical-forward wrap from position 40 to position 1.

Every accepted movement was durably recorded as `COMPLETED` with
`execution_started=true`. The user physically confirmed correct alignment at
positions 2, 10, 40, and the returned position 1. The short 40-to-1 motion was
the expected adjacent-position movement of 250 pulses / 9 degrees. The carousel
finished at position 1 and the user confirmed motor power was switched off.

During UI familiarization, the operator accidentally issued additional
no-motion reference declarations, including declaring position 2 while the
mechanism remained physically at position 1. Subsequent
move-to-2 requests were rejected as `INVALID_FIELD` with
`execution_started=false` because position 2 was already the controller's
declared logical position. No physical movement or unknown outcome occurred.
This confirms that manual reference is an absolute operator assertion of the
currently aligned logical tube, not an offset: an incorrect assertion shifts
all later logical-to-physical tube labeling until reference is corrected.

After the UI separated and locked the reference workflow, a second supervised
production-path regression completed a no-motion reference at position 1 and
the movement sequence `1 -> 2 -> 20 -> 40 -> 10 -> 1`. All six commands were
durably recorded as `COMPLETED` with `execution_started=true` and no rejection,
failure, or unknown outcome. The user physically confirmed that the complete
test passed. The carousel finished at position 1 and motor power was switched
off.

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
- `1025 steps/ml` is accepted only as the nominal supervised-demo conversion;
  precise experimental `steps/ml` calibration remains pending.
- Precise production working full/empty margins remain pending experimental
  calibration. For the supervised nominal demo only, the 2026-10-06 user
  decision above selects 0 and 20500 with no additional endpoint reserve.
- No validated aspiration or dispense volume accuracy is documented yet.
- No validated physical speed range exists yet.
- No acceleration ramp or stall detection is currently confirmed.

## Confirmed SF mixer STEP/DIR pair — 2026-08-16

The user identified the connected SF mixer actuator as the same NEMA 17 motor
type used for the valves and its driver as the same DM542T driver type. The
Reactor mixer is not connected. The exact SF mixer motor model and driver
current and microstep settings remain unconfirmed.

The supervised discovery test exercised these candidates:

- candidate A: STEP D4, DIR D5;
- candidate B: STEP D6, DIR D7.

Candidate A produced no physically observed motion during a 100-pulse burst.
Candidate B, with DIR logic low, physically rotated the SF mixer during a
500-pulse burst. The user directly confirmed the observed rotation. The SF
mixer production pin pair is therefore confirmed as:

- STEP D6;
- DIR D7.

The discovery burst used a 20 microsecond STEP-high time with 2 milliseconds
between pulses. Viewed from the front face of the motor, the user observed DIR
logic low rotating the mixer clockwise. This is an observed direction only;
the required direction for the final mixing element remains unconfirmed.

The production firmware was subsequently uploaded and flash-verified. A
supervised UI -> backend -> Arduino sequence commanded STOP -> START -> STOP at
the same fixed 500-pulse/s profile. All three durable commands completed
without an error, the user physically confirmed rotation between START and
STOP, and the final commanded state was stopped. This validates the complete
production control path, but it does not establish calibrated RPM, mixing
performance, torque, or sensor-confirmed rotation.

A final UI regression then completed three consecutive START -> STOP cycles.
All six durable commands completed without an error, the final command was
STOP, and the user confirmed that every physical start and stop worked
correctly.

## Supervised end-to-end dry-demo findings — 2026-08-16

### P1 HOME activation at the full software search boundary

A full-span dry-demo initialization commanded P1 HOME through the previously
confirmed P1 Waste route. The command emitted the full 20,500-pulse search and
returned terminal `PUMP_MOTION_TIMEOUT`; the user physically confirmed that P1
had nevertheless arrived at and remained on HOME. A new, separately identified
P1 HOME command then completed in approximately 0.14 seconds without visible
motion, confirming that the HOME input was active and functional after the
timeout.

This exposed a controller ordering boundary: activation caused by the final
allowed pulse could occur after the pre-pulse HOME read but before the immediate
20,500-pulse timeout decision. Firmware commit `0443837` re-reads HOME at that
boundary and permits only a motionless 30 ms confirmation. It emits no pulse
beyond 20,500; a candidate that drops before confirmation still times out and
leaves position untrusted. Warning-enabled native tests pass `195/195`, and the
production Mega build uses 40,806 flash bytes and 3,140 bytes of static SRAM.
The commit is uploaded and flash-verified. A physical full-span regression of
the corrected boundary remains pending because the subsequent V8 fault stopped
the end-to-end sequence before pump transfer execution.

### New V8 HOME-direction physical fault

During a later end-to-end dry-demo initialization on production firmware,
V1-V7 homed normally. V8 then emitted its bounded 1,600-pulse HOME search but
physically oscillated/made an abnormal sound instead of rotating normally and
returned `VALVE_MOTION_TIMEOUT`. The user initially observed repeated physical
lever contact during the failed fast attempt, then clarified that V8 remained
away from HOME and produced the abnormal sound while STEP pulses were sent.

A temporary V8-only diagnostic used the already confirmed STEP D34, DIR D35,
HOME D2, active-HIGH input, and DIR HIGH toward HOME. It was explicitly armed
before each bounded run and stopped after each result. Evidence was:

- a 1,600-pulse HOME-direction run observed D2 LOW for the complete motion and
  for the following 250 ms (`high_ms=0`, `transitions=0`);
- after the user manually placed V8 at approximately 90 degrees, 20 pulses at a
  slow 10 ms interval in DIR LOW, away from HOME, moved normally and sounded
  normal;
- a subsequent HOME attempt at the same slow 10 ms interval still only
  oscillated, exhausted 1,600 pulses, and again observed D2 continuously LOW.

This does not justify a polarity, pin, debounce, or software-position change.
The evidence localizes the blocker to the physical V8 drive under the confirmed
HOME direction/load: coupling or valve binding, a phase/connection fault that
appears under that load, or another driver/mechanical issue remains possible.
V8 must not be commanded again until that physical fault is resolved. Its final
position is not trusted. Because the confirmed P2 Waste route requires V8 at 90
degrees, P2 homing or parking must not be attempted from this state.

The temporary diagnostic firmware was removed. Production firmware `0443837`
was restored and flash-verified with motor power off. Backend and Serial monitor
were left off, and motor power remained physically off.

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
