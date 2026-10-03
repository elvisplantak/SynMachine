# Fresh hardware observations before a future recovery/release decision

This step follows offline interruption reconciliation at `d5d1843`. It reuses the
existing Arduino Serial client/protocol and SF actuator register adapter. It is
not wired into startup, an API or a recovery executor, and was tested only with
injected fake ports/sessions. No real Serial/Dynamixel port was opened.

## What is implemented

`observe_current_hardware(arduino, sf_valve, required_commands=...)` requires an
already connected Arduino client and an explicitly supplied non-empty set of
required command capabilities. It does not connect, reset or reconnect Arduino.
It issues a fresh correlated QUERY_STATUS, performs a read-only SF sample and
then issues another correlated QUERY_STATUS. Both replies must report trusted
software state, IDLE and no active command. Missing capabilities, correlation
errors, timeouts, disconnection, changed connection generation or changed session
identity prevent a report from being returned. There is no cached fallback.
The report preserves both bracketing query IDs in
`arduino_status_request_ids` (before, after); they must be distinct within the
observation. Consumers checking freshness across observations must track both.

`ArduinoSerialClient.connection_epoch` is a process-local generation incremented
on close/reconnect. It detects a reconnect even when a fake/misconfigured transport
reuses the boot ID and nonce. It is not a persistent identity, command permission
or substitute for the existing protocol's correlation checks.

`SfBottomValveActuator.inspect_state()` uses the actuator's existing command lock
and device validation. It reads the model, operating mode, hardware error, limits,
present position and torque state. It validates both configured endpoints and
rechecks hardware error after reading position. It never writes a register,
enables/disables torque, updates a goal or attempts to close the valve. The
short-lived session is closed even on failure; a close failure prevents success.
When a primary read/validation error and close failure both occur, the primary
exception is preserved and the close failure is added as a note.

A position within exactly one configured endpoint tolerance is reported as
observed OPEN/CLOSED. A position near neither endpoint, or ambiguous overlapping
tolerances, remains unknown. Torque-on is reported as torque-on, not silently
corrected or mistaken for a stationary actuator. These samples cannot prove
fluidic closure, mechanical coupling, sealing or continued position after reading.

## Explicit trust boundary

The resulting `CurrentHardwareObservations` always has `may_release_owner=False`.
This is an observational result, never a recovery permit. The canonical protocol
states that IDLE/TRUSTED describes controller software only. SF opens a temporary
connection for a sample, so it supplies no lasting SF session identity or boot
continuity. Neither sample resolves a previously unknown physical outcome.

The caller must serialize these reads with all hardware work under the shared
owner. The probe itself does not obtain or release a durable lease, and the
Arduino client remains a synchronous single-command adapter. Bracketing the SF
read is not an atomic hardware snapshot and does not prevent another uncoordinated
program from acting on the devices. Production-wide ownership/composition and a
persistent SF session/trust strategy remain required before live integration.

## Conditions still required before any real release

- Independently establish current physical references after loss of trust. Stored
  plan assumptions and previous commissioning logs are not current observations.
- Use backend-owned approved valve routes, including safe pump-homing routes.
  Pump HOME can aspirate fluid; a controller status cannot establish route safety.
- Supply commissioned pump working positions/calibration and current carousel
  reference. Carousel reference is an operator assertion, not a nonexistent sensor.
- Resolve the interrupted run deliberately while preserving durable command history.
  Successful reads do not change unknown commands into completed commands.
- Execute and verify the agreed recovery/flush workflow before a new run where
  required by machine lifecycle. This checkpoint does not perform that workflow.
- Define the durable release transaction and its cross-database failure policy,
  fresh session lifetime, live SF OPEN/Stop policy and production startup binding.

No owner-release method, physical recovery, firmware change, protocol schema
change, database schema/migration, UI behavior change or main merge is included.
The existing command execution behavior remains unchanged; only new explicit
read methods and the local connection-generation counter are added.

## Verification

Focused tests exercise real adapter code with fake transports, and assert the
only Arduino frames are HELLO/test setup and QUERY_STATUS; SF register writes
remain empty. Cases include both idle samples, every relevant non-ready/status
correlation failure, absent capabilities, disconnect/reconnect with reused IDs,
SF endpoint ambiguity/torque-on, read/close errors, late hardware error, timeout,
shared SF command exclusion and fresh requests on every observation.

Local verification: 34 new tests; 72 focused adapter tests and all 1642 backend
tests pass (56.75 s full suite). Ruff and `git diff --check` pass. No independent
review requested for this diagnostic step; consolidate before live composition.
