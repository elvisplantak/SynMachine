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


## P2 block — software completed, physical confirmation pending

After the P1 block's physical confirmation, the user approved starting the described
P2 valve-only block in reply to its listed prerequisites. The plan used fresh
operator-declared empty-system/power-ready, SF and Column CLOSED, Reactor mixer
OFF conditions; these are not sensor observations. No SF SDK/device connection
or bottom-valve command was made. The isolated HOME order was V3 -> V7 -> V8 -> V5;
this does not establish a universal startup/Recovery HOME procedure.

Boot 86 completed all 25 commands (four HOME, 21 position moves) without error or
retry in approximately 47.8 seconds and closed. Scope was V3/V5/V7/V8 only; pumps,
SF/Column bottom valves, mixers and carousel remained uncommanded. Final commanded
positions are V3=90, V5=180, V7=90, V8=90. Operator visual confirmation of this
block is pending. Recorded software success does not establish actual fluid flow,
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
