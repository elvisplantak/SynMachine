# Owned recovery, mandatory flush and new-run entry

This candidate connects maintenance to the existing `OwnedOfflineRuntime`,
`OwnedTransferRunner`, immutable plan store, Arduino/SF journals and shared
`HardwareOwnership`. There is no new diagnostic layer, database or transport
implementation. Environment startup and production APIs remain unchanged.

## Execution and release

- Explicit interruption reconciliation still sends nothing and preserves old
  run/command evidence. The old run remains FAULTED or ABORTED; it cannot resume.
- An explicit maintenance attempt persists its complete source/prepared plan,
  deliberately replaces only an unresolved process-local lease, and commits
  `MaintenanceIntent` in the machine snapshot before any actuator command.
  The same durable owner remains reserved across recovery and required flush.
- Recovery sends mixer STOP and SF CLOSE; Column HOME has required CLOSED
  followup. V1-V8 HOME order is supplied explicitly. Each pump's supplied Waste
  switching sequence must finish before its HOME, then its configured working
  empty target. Carousel reference is an explicit manual alignment declaration.
  Recovery completion commits FLUSH_REQUIRED and retains ownership.
- The operator explicitly starts mandatory flush. It requires successful recovery
  continuity in this process, or a clean Stop with retained command-confirmed
  state. A clean Stop can leave liquid in a pump: flush preparation empties it
  toward Waste, without re-homing. Stored reference reports cannot grant entry.
- Flush uses two liquid cycles followed by an air pass over the same SF/Waste
  and Column paths. Syringe aspiration and dispense remain separate. SF aspiration
  keeps required CLOSE, and Column drain keeps required CLOSE on Stop or error.
  Carousel moves only after closed drain completion; rinse alignment is supplied.
- Volumes, working calibrations, proposed switching orders, Column drain duration,
  and safe tube volume are explicit inputs. No volume, speed, tube alignment or
  working margin is inferred. Tube policy requires a supplied margin below the
  confirmed nominal 10 ml capacity. Timed/nominal completion is not proof of
  delivered volume, empty vessels, effective cleaning or measured drainage.
- Successful required flush commits READY before owner release. Release occurs
  only after command results, lifecycle commit and final session/state validation.
  Domain-only completion is rejected while an owned maintenance intent exists.
- `start_new_run` requires READY, no unresolved owner/intent and a new run ID.
  It consumes a process-local state binding, checks ownership generation and
  enters the same ten-phase executor. Normal completion also permits a new run
  without a mandatory flush. Reopen requires an independently supplied fresh
  fixture/context; history is never reconstructed into current position trust.

## Crash boundaries

The ownership, plan/journal and lifecycle databases remain separate. Their commits
are deliberately not described as atomic. An exception, Stop, unknown outcome,
write failure, session change or process death retains exclusion. Commands already
recorded for an attempt cannot be replayed; a deliberate new maintenance attempt
uses fresh identities and leaves the old evidence unchanged.

Interrupted maintenance keeps its durable intent. Explicit
`reconcile_maintenance_interruption` clears only that lifecycle intent, returns
to RECOVERING and retains the owner; it sends no command. A fresh full recovery
and required flush are needed after restart. A crash/failure after READY but before
owner release likewise blocks new-run entry and requires deliberate recovery.
Recovery does not automatically start flush. Default application startup remains
unchanged. Optional standalone flush from READY is not integrated by this slice.

## Existing adapter preparation

`PreparedAdapterDevice` binds the existing `ArduinoSerialClient` and
`SfBottomValveActuator` to the same runner/journals. Its construction opens no port
and sends no command. Arduino must be explicitly connected by the caller. An
explicit monotonic timer is required; adapter execution cannot use virtual waits.
The tests inject fake Serial ports and fake DYNAMIXEL sessions.

Preflight reuses fresh bracketed Arduino/SF observations while ownership is held.
Capabilities, trusted IDLE, boot/nonce/connection epoch and, outside recovery,
observed SF state/torque must agree. Required cleanup can still use its surviving
transport after the other transport fails. Arduino is not automatically reconnected.
SF's scope identifier is host-only correlation, not persistent physical/session
trust; short-lived SF sessions still close and disable torque on terminal outcomes.

Readiness inputs are attributed operator statements about Waste air gap, working
calibrations, switching sequences, stopped Reactor mixer and manual carousel
alignment. They are not sensors or authenticated identities. Actual route safety,
wet calibration, working margins/drain timing and physical commissioning remain
separate gates. The only added route targets are the confirmed P1/P2 Waste routes
from firmware HARDWARE_CONFIRMATIONS; switching order is still caller supplied.

No real Serial/U2D2 port, actuator, production process, firmware upload, main merge
or original project database was used. Existing advisory locks still protect only
this explicit composition, not unwrapped adapters or arbitrary SQLite writers.

## Persistence and verification

Maintenance source data uses the existing immutable plan payload. Intent/result
metadata uses the existing machine snapshot/event JSON. No SQL table, schema
version, automatic provisioning or migration was added. Older software is not
promised to execute the new maintenance payloads safely; no downgrade is supported.

Tests cover recovery + required flush + a complete new run, clean Stop with retained
pump contents, adapter execution over fake transports, intent-before-first-byte,
Service exclusion, required CLOSE/Stop, dual primary/cleanup errors, unknown command
outcomes at each recovery stage, completion/release write failures, reconnect/state
loss and actual subprocess death during both recovery and flush. Historical tests
continue covering the shared runner's detailed journal/persistence failure matrix.
