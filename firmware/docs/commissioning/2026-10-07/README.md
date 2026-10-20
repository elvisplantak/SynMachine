# Supervised dry P1 check — 2026-10-07

Scope: operator-authorized individual valve commands through the existing backend
`prepare_command_plan`, `ArduinoSerialClient` and `DurableArduinoCommandExecutor`.
No pump, P2, bottom-valve, carousel or mixer command; no liquid, firmware upload,
production configuration, EEPROM provisioning or complete autonomous run.
Motor power was newly confirmed before the P1 check and again before the separate
V2 recheck. Command progression waited for operator confirmation in the chat.

## Evidence

- `arduino-communication-check.json`: authorized HELLO/QUERY_STATUS, boot 78,
  trusted software IDLE, no active command. Connection closed; no motion command.
- `p1-dry-057273c5-3c81-4019-b850-4800b3bd665c/`: boot 79, startup then EOF
  before the first command because the host terminal lacked interactive stdin.
  Zero journal intents. Closed without cleanup motion. The host launch was
  corrected to allocate a PTY; this did not retry a physical command.
- `p1-dry-b2f322e1-1736-4dd4-8613-696cd38bea3c/`: boot 80, HOME V1, V2, V4,
  V6, V6=180, V1=90 all COMPLETED and operator-confirmed. V2=90 FAILED with
  `VALVE_HOME_SWITCH_UNEXPECTED`, execution_started=true. No later command sent.
  The operator missed that attempted movement, then confirmed motor power OFF
  and observed the HOME lever close to, but not pressing, the switch. This later
  observation does not establish the electrical signal at the time of failure.
- `v2-recheck-0f4ddec5-05d1-49b4-baa9-dca4229a4a12/`: separately authorized
  HOME V2 then V2=90, boot 81. Both COMPLETED; operator confirmed correct HOME
  and departure to the expected 90-degree position without abnormal behavior.
  Connection closed. The preceding fault's cause remains unresolved.

Each directory retains raw events and a SQL export. Original SQLite journals
are preserved locally and ignored by Git; no historical record is overwritten.
`supervised-runner.py.txt` and `offline-supervision-checks.py.txt` preserve the
host procedure source, not production firmware or a new backend diagnostic layer.
The final source supports both the full P1 proposal and the two-command V2 recheck.
Five fake-only supervision checks passed: durable intent before execution,
halt before commands/on missing NEXT, no continuation/retry after unknown outcome,
and no 90-degree command after failed V2 HOME. No production code changed.

## Stop and next session

The user stopped for lack of time and plans to continue on 2026-10-08. Latest
physical observations: V1=90, V2=90, V4=HOME, V6=180. These are historical
observations, not current-session references; every reconnect/reset invalidates
firmware reference trust. Other actuators and fluid routes were not verified.
Latest motor-power confirmation was ON for the V2 recheck; power OFF was requested
at stop but has not yet been confirmed. No running host connection or queued motion.

The user requests slower valve rotation. Current source has a fixed 2000 us
STEP interval and 400 steps/90 degrees; the protocol has no valve-speed argument.
No speed, timing or protocol change is made today. Before later motion, prepare
and verify a slower firmware profile, obtain any upload authorization, and obtain
NEW motor-power readiness. Do not infer that the successful recheck fixes the
original electrical/mechanical cause or resume the interrupted 19-command plan.
First complete/verify the demo; UVP follows, retaining all necessary tests, then
flow animation based on executed commands rather than measured liquid flow.
