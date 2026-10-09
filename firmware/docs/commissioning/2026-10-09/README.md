# Slower valve firmware and supervised checks — 2026-10-09

Production firmware `caef934` was uploaded with explicit authorization and motor
power OFF. Avrdude verified the 40806-byte image; see `upload-verification.json`.
The fixed V1-V8 STEP interval is now 4000 us. Software preparation passed 18
focused and 197 complete warning-enabled native tests and the Mega build.

## Bounded V2 recheck

With fresh user readiness and authorization, boot 84 completed HOME V2 and V2=90
without retry. The host closed after the two commands. The user confirmed correct
HOME and acceptable slower movement after the first command. Visual confirmation
of the final 90-degree position is still pending; do not infer it from COMPLETED.
The original October 7 failure's cause remains unresolved. Events and journal SQL
are in `v2-recheck-dc56a4c5-45b3-4d07-80f6-8483c833b425/`.

## P1 block — software completed and operator confirmed

The user requested faster commissioning by grouping related checks. The proposed
first block retains the existing isolated dry P1 scope, stationary pumps and
HOME order V1 -> V2 -> V4 -> V6. It then exercises the existing planner's sequence:
S -> Reactor -> S -> Reactor -> B1 -> Reactor -> B2 -> Reactor -> Waste -> Reactor.
Route names denote valve selections only. The offline plan contains 19 commands:
four HOME and fifteen position moves, solely on V1/V2/V4/V6. This is selected
transition coverage, not every startup/Recovery/flush entry or verified flow.

The host runner now offers explicit `--run-block`, restricted to this P1 scope.
Execution still requires procedure approval and NEW motor-power readiness flags;
it also waits for `RUN_BLOCK` before opening Serial. It awaits each terminal
result and records durable intent through the existing executor. A failure,
unknown outcome or interruption closes without retry or cleanup movement.
The original single-command `NEXT` mode remains available. Neither mode activates
the incomplete full-run profile or commands pumps/other actuators.

Nine fake-only supervision checks passed: existing five plus approved-block
completion/durable intent, unknown-outcome stop, HOME-failure stop and cancellation
before Serial opens. Host/test snapshots are retained alongside this README.
After fresh user readiness, boot 85 completed all 19 commands without error
or retry in approximately 37.4 seconds. The connection closed automatically;
no pump/other actuator or cleanup motion was commanded. Final commanded positions:
V1=180, V2=90, V4=90, V6=90. The user subsequently confirmed that the whole
block moved normally without binding or unusual sound. This is dry mechanical
confirmation of this sequence, not liquid flow or every route-history case.
Historical logs cannot restore current trust on the next reconnect. Events and SQL are in
`p1-dry-4eb43859-4a41-4eda-8dcd-f35184ace9bf/`. The earlier V2 failure did not recur
in this block; its original cause is not established. GitHub pushes remain deferred.


## P2 block — software completed and operator confirmed

After the P1 block's physical confirmation, the user approved starting the described
P2 valve-only block in reply to its listed prerequisites. The plan used fresh
operator-declared empty-system/power-ready, SF and Column CLOSED, Reactor mixer
OFF conditions; these are not sensor observations. No SF SDK/device connection
or bottom-valve command was made. The isolated HOME order was V3 -> V7 -> V8 -> V5;
this does not establish a universal startup/Recovery HOME procedure.

Boot 86 completed all 25 commands (four HOME, 21 position moves) without error or
retry in approximately 47.8 seconds and closed. Scope was V3/V5/V7/V8 only; pumps,
SF/Column bottom valves, mixers and carousel remained uncommanded. Final commanded
positions are V3=90, V5=180, V7=90, V8=90. The user subsequently confirmed
that the complete block proceeded correctly. This is dry mechanical confirmation;
recorded software success does not establish actual fluid flow,
sealing, or current reference trust after another reconnect.

The planner selected Reactor -> SF top -> Reactor -> SF top -> SF bottom ->
Column -> SF bottom -> Column -> Reactor -> SF top -> Waste -> Reactor -> Column
-> Waste -> Reactor. The five destination orders were checked against the approved
worksheet; already-reached targets were skipped. This is selected transition
coverage, not every route-history case. P2 host safety checks: ten fake-only tests
passed, including missing closure/mixer guards, missing conditions confirmation,
HOME failure, unknown outcome, cancellation, and durable intent before each command.
The runner reuses the existing P1 sequential host loop and backend planner/executor,
not a new diagnostic or production execution layer. Snapshots:
`p2-supervised-runner.py.txt`, `p2-offline-supervision-checks.py.txt`.
Events and SQL: `p2-dry-c5c3b311-0125-4369-b767-0feee8b11cf0/`.


## Dry pump block — halted on P1 full-span HOME failure

The user requested moving on to pumps. The prepared plan contains 22 commands:
HOME V1/V2, select approved P1 Waste (V2=180 then V1=180), then P1 HOME -> absolute
1000 -> HOME -> absolute 20500 -> HOME -> absolute 200. Next HOME V3/V7/V8/V5,
select approved P2 Waste (V5=180 -> V8=90 -> V7=90 -> V3=180), then P2 HOME ->
absolute 1000 -> HOME -> absolute 200. Final pump targets are 200, with both Waste
routes retained. Existing firmware pump timing remains 1500 us; the slower valve
profile does not change pump timing. No absolute zero target or volume-transfer
HOME substitution occurs. This is dry commissioning, not a 20 ml delivery claim.

The P1 20500-to-HOME step is a supervised full-span regression after the previously
recorded boundary correction; a successful HOME cannot prove activation happened
on exactly the final permitted pulse, because this interface reports no pump pulse
counter. Known test distances/limits come from the canonical hardware record.
The isolated HOME/setup orders do not establish a general Recovery procedure.

The block requires NEW dry-system/power readiness, the stated closed/stopped
conditions, and explicit approval for the P1 20500-step regression before Serial
opens. The default preview is offline; RUN_BLOCK gates live startup. Twelve
fake-only supervision checks passed, including a Waste-route failure preventing
pump HOME, absent full-span approval preventing Serial open, and existing durable
intent/failure/unknown/cancellation boundaries. The existing planner, Serial client,
durable executor and P1 sequential host loop are reused. Snapshots: `pump-supervised-runner.py.txt` and
`pump-offline-supervision-checks.py.txt`. GitHub push remains deferred.

After fresh operator confirmation of the described prerequisites and full-span
scope, boot 87 executed eight commands successfully. P1 Waste setup, initial
HOME, the 1000-step move, its return HOME and the move to 20500 all reported
COMPLETED. Command 9, P1 HOME from 20500, failed with `PUMP_MOTION_TIMEOUT`
after approximately 31.1 seconds. The durable journal records FAILED with
execution_started=1. The runner immediately halted and closed without retry or
cleanup motion; commands 10-22, including all P2 setup/motion, were not sent.

In the installed controller, this error denotes exhaustion of the bounded HOME
search (20500 pulses) without an accepted HOME signal. It is not a host Serial
timeout. The log does not establish the physical stop position or whether the
lever reached the switch; operator observation is pending. No cause, repair,
additional travel allowance or successful full-span regression is inferred.
Motor power OFF was requested after the failure but is not yet confirmed.
Evidence: `pump-dry-fa3ce511-3f30-4170-9fed-c68eb98a897e/events.jsonl` and
`commands.sql`; the original SQLite journal is retained locally and ignored.

The user subsequently reported P1 seated at HOME and pressing the switch, with
normal sound. This is a mechanical observation; no electrical input or timing
was measured. The user subsequently confirmed motor power OFF. The software
command remains FAILED and position untrusted. Source inspection found a timing
edge: if HOME is inactive on the immediate read after pulse 20500, the controller
finishes with timeout and cannot observe a later activation. Pre-correction native
coverage activates the fake input inside the final pulse and did not establish
behavior for a mechanically delayed signal. This is a candidate explanation,
not proof of the physical failure's cause. No code change, upload, Serial reopen
or additional movement was performed during this follow-up inspection.

## Prepared final HOME signal wait — software verified, not uploaded

The new native delayed-input regression failed on the installed source: its
fake switch activates after the final STEP pulse and the command has already
terminated. This proves a software timing edge, not the cause of boot 87's
physical failure. The shared P1/P2 controller now holds STEP inactive at the
20500-pulse search limit if HOME is initially inactive. It permits an observed
activation strictly before 30 ms from the final pulse, then requires the existing
30 ms continuous-active confirmation. Missing/deadline-late input fails with
PUMP_MOTION_TIMEOUT; a candidate that goes inactive at the search limit also
fails immediately. The wait is not restarted, and no additional pulse occurs.
The 30 ms arrival budget is software policy, not measured mechanical settling.
Targets, pins, polarity, pump speed, ordinary homing and command schemas are unchanged.

Verification after the correction: 46 focused controller/runtime tests passed;
all 204 warning-enabled native tests passed (-Wall -Wextra -Werror). Seven new
tests cover delayed signal, last permitted arrival across clock wrap, deadline
rejection, glitch/abort without extra motion, and both pumps' lifecycle/cache
completion/failure replay without retry. The existing missing-HOME bound test
now also checks the motionless deadline. Mega 2560 build passed: 40880 flash
bytes (+74 over installed firmware), 3140 static SRAM bytes (unchanged).
Prepared HEX SHA-256:
`8b87d2fb0b0cc2efbd4544b0ac5d6755d5a62a7799f0d6008daff1668da57a8b`.
Self-review and diff checks passed. No upload or new hardware communication was
performed; installed firmware remains caef934 and its separate upload evidence
above is unchanged. The failed physical journal remains FAILED. Upload and a
new bounded dry recheck require separate authorization/readiness. No increase
of travel allowance or wet/full-demo acceptance is inferred. GitHub push is deferred.


## Corrective upload completed — physical recheck pending

After explicit user approval with motor power OFF, firmware 8a5d93c was uploaded
to the confirmed Mega by-id device. Avrdude verified all 40880 flash bytes;
upload exited 0 and HEX SHA-256 matches the prepared artifact above. No actuator
command or EEPROM provisioning occurred. The previous caef934 upload evidence
is retained unchanged; this upload has its own
`pump-home-wait-upload-verification.json`. There is no open host connection or
queued motion. Motor power remains last confirmed OFF. Boot 87's failed journal
is not changed by upload, and the physical failure's cause remains unproven.

Proposed next powered scope is a dry P1-only repeat: HOME V1/V2, select P1 Waste
(V2=180 then V1=180), P1 HOME -> absolute 20500 -> HOME -> final 1000.
The final parking target was subsequently selected by the user, as recorded below. This omits the already
completed short stroke and all P2 commands. Fresh empty-system/air-outlet, closed
bottom-valve/stopped-mixer prerequisites and motor readiness/approval are required
before execution. On any failure the host halts without retry or cleanup movement.


## Terminal HOME release — software verified, upload and dry trial pending

The user selected parking at the end of the whole successful test/procedure:
1000 absolute steps for either pump left at HOME, and nominal 5 degrees for any
V1-V8 left at HOME. This valve trial uses 22 steps (4.95 degrees) from the existing
400 steps/90 degrees ratio. It is not yet a confirmed release distance or wet
alignment. Column uses its existing CLOSED 4-degree offset; no comparable SF
adapter HOME movement is invented. Normal route targets remain 90/180.

Firmware extends the existing VALVE_SET_POSITION command to accept 5 only from
trusted raw zero. After 22 steps, STEP stays inactive while inactive HOME must
remain stable for 30 ms within a fixed 60 ms target-arrival deadline. Failed
release invalidates trust and reports VALVE_HOME_SWITCH_STUCK without extra
travel. HOME itself still ends at zero, and parking retains the raw offset for
subsequent 90/180 positioning. Integer degree reporting uses a 32-bit product to
avoid AVR 16-bit overflow and rounds the trial offset to 5.

The host derives terminal positions only from the current block's completed
command path. Uncommanded/unknown and non-HOME actuators are untouched. Pump
parking requires final verified Waste selection; both pumps park after the whole
combined 22-command block, not after its individual P1/P2 parts. Cancellation,
failure or unknown outcome halts before any remaining suffix; no finally cleanup
motion is sent. A parking failure is not reported as sequence success.

Prepared bounded scopes (offline previews, not authorization):
- P1-only recheck: 8 commands, HOME V1/V2 -> Waste (V2=180 then V1=180) ->
  P1 HOME -> 20500 -> HOME -> 1000. P2 remains uncommanded.
- Separate empty-system valve trial: 16 commands, HOME V1,V2,V4,V6,V3,V7,V8,V5,
  then terminal SET_POSITION=5 for each in that order. Pumps/bottom adapters,
  mixers and carousel remain uncommanded. This isolated dry HOME order is not
  a general wet startup or Recovery sequence.

Both live modes require NEW power/empty-system/closed-bottom/stopped-mixer
readiness and exact procedure approval, plus RUN_BLOCK before Serial open.
The P1 full-span recheck additionally requires explicit 20500-step approval.
The trial target selection does not establish present physical readiness.

Verification: 45 focused valve controller/contract/cache/runtime tests passed;
all 211 native tests passed with -Wall -Wextra -Werror. Mega 2560 build passed:
41056 flash bytes (+176), 3148 static SRAM bytes (+8), compared with installed
8a5d93c. Prepared HEX SHA-256:
93e133bdc130583edfcd27a12ef61cbe396d0a2bf6dd972d913f3447a4745dcf.
Ten new fake-only terminal checks passed, including final HOME failure/unknown
blocking every park, park failure halting the suffix, and whole-block ordering.
Existing host checks passed: P1 9, P2 10, pump 16. No device was opened or moved.

Snapshots below preserve this preparation separately from the earlier physical
run's immutable helpers/journal:
- terminal-parking.py.txt -> /tmp/labforge_terminal_parking.py
- terminal-parking-offline-checks.py.txt -> /tmp/check_labforge_terminal_parking.py
- p1-terminal-parking-runner.py.txt -> /tmp/labforge_p1_dry_check.py
- valve-terminal-parking-runner.py.txt -> /tmp/labforge_p2_dry_check.py
- pump-terminal-parking-runner.py.txt -> /tmp/labforge_pump_dry_check.py
- pump-terminal-parking-checks.py.txt -> /tmp/check_labforge_pump_dry_runner.py

Restore the related helpers together. Run offline with the backend venv Python
and PYTHONPATH=/home/elvis/Documents/labforge-backend-multiphase. Preview modes
are --p1-full-span-only on the pump runner and --all-valves-parking-trial on the
P2 runner; neither opens a transport without --execute and the approval flags.

Motor power remains last confirmed OFF. Installed firmware remains 8a5d93c;
this parking artifact is not uploaded. Boot 87's failed journal/root-cause status
is unchanged. Physical 5-degree release, P1 full-span HOME/P2 pump acceptance,
and wet/demo acceptance remain pending. Full production procedure parking is
not activated through the UI; safe wet alignment and the complete live profile
must be confirmed before that integration. GitHub push remains deferred.


## Terminal parking upload completed — physical checks pending

After the user explicitly confirmed motor power OFF and authorized this exact
artifact, firmware e2e9d3c was uploaded to the confirmed Mega USB by-id device
(resolved /dev/ttyACM1). Avrdude verified all 41056 flash bytes; upload exited 0.
Post-upload HEX SHA-256 remains
93e133bdc130583edfcd27a12ef61cbe396d0a2bf6dd972d913f3447a4745dcf.
Static SRAM is 3148 bytes. Raw upload output: terminal-parking-upload.log.txt;
structured evidence: terminal-parking-upload-verification.json. Earlier uploads
and boot 87's failed journal remain unchanged.

No actuator command, EEPROM provisioning, subsequent Serial monitor/session or
physical test occurred. The port was checked unoccupied before upload, which
completed and closed. Motor power remains last confirmed OFF. This does not
confirm HOME release at 5 degrees or repair the earlier physical HOME failure.
The prepared P1-only 8-command recheck and separate 16-command valve trial each
require NEW stated dry/closed/stopped prerequisites, motor-power readiness and
exact physical authorization. No queued motion remains; GitHub push is deferred.
