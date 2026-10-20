# Owned application execution

This explicit candidate connects FastAPI and the Guided Demo UI to the existing
owned recovery/flush executor. `create_app(application_execution=...)` accepts an
`OwnedApplicationExecution`; the environment/default application does not enable
it. Construction opens no port. Tests supply fake transports and temporary,
explicitly provisioned `OfflineDatabaseBundle` files. Production composition,
device connection and physical execution remain separate approval gates.

## One application owner

The application constructs the timer, `OwnedOfflineRuntime`, writable SQLite
handles and then its deferred device on one dedicated worker. All bundle locks
and schema/identity checks precede invoking the device factory. A factory may
return an existing caller-owned fixture or a context manager owning its connection
lifetime. Its existing advisory locks exclude a second candidate runtime before
that runtime can invoke its factory. Guided Demo, recovery, flushing,
Arduino Service and SF Service all use that runtime's `HardwareOwnership`, command
runner and journals. Mixed owned/unguarded injected adapters are rejected.

HTTP snapshot/event queries use independent, identity-validated read-only lifecycle
handles with per-request read transactions. They are observations, never hardware
permissions. Cached execution status describes worker activity; a retained owner
is refreshed at idle boundaries. Backend checks remain authoritative when reads
race with a command. Configuration and competing Service/execution requests are
rejected while the worker is busy.

Run Start and maintenance Start return HTTP 202 with an operation identity: this
acknowledges acceptance, not completion. One worker runs the existing ten phases
or maintenance plan. Completion and errors appear in the existing machine/run
snapshots and journal evidence, with the worker's latest error exposed separately.
No automatic command retry, old-run reconstruction or automatic recovery occurs.

## Control and interruption

Stop bypasses the worker queue. For a run it persists the existing abort request;
before the run binds, it records a pending request which is consumed before the
first actuator command. Between phases the exact abort transition is validated,
ownership is retained before confirming ABORTED/FLUSH_REQUIRED, and nothing moves.
Failure to persist Stop blocks subsequent primary work at the next control poll;
required cleanup remains enabled. Shutdown requests Stop before waiting for the
worker and never force-releases retained ownership.

Maintenance Stop uses an attempt-local signal and the same protected atomic
boundaries. `/execution/{operation_id}/stop` checks the exact executing identity,
including maintenance with no run. Pause/Resume are limited to started
DELAY_BETWEEN_ADDITIONS and REACTION_HOLD wait intents; they use existing persisted
wait controls and are not a physical emergency stop.

Startup reconciliation performs only existing interruption reconciliation plus
metadata-only reconciliation of retained Service ownership with no active run.
It sends no query or actuator command and rewrites no historical command. The
explicit adapter resource factory described below first establishes a Serial
handshake; default startup does not enable that composition. An
interrupted maintenance attempt returns to RECOVERING. A successful recovery
retains exclusion and requires explicit flushing. Only fully validated flush
completion commits READY and releases the owner.

## Maintenance without a run

Standalone flushing is available from idle READY using fresh or retained current
command state. No terminal demo run is required. `MaintenanceIntent.run_id` and
maintenance `PlanSource.run_id` may be null; ordinary phase plans still require a
run. For machine-only source plans, `run_event_sequence` binds the machine sequence.
`interrupted_maintenance_id` distinguishes machine-only interruption from a run
interruption; during an attempt it matches its execution identity. READY clears
that scope. These fields use existing snapshot/event/plan JSON, with no new SQL
schema, table, database or migration. Older executable versions are not supported
against new machine-only payloads.

A retained Service owner discovered at startup with an absent/READY machine
receives an explicit machine-only RECOVERING event. It is never assigned a fake
DemoRun. Recovery and required flushing then use the original owner and journals.
Historical unknown/failed command records remain unchanged.

Initial READY may be established only from explicitly supplied unused context,
idle ownership and no unresolved execution history. A partially written STARTING
lifecycle or configured-but-never-started CREATED run may be explicitly continued;
no execution resumes at startup. Successful earlier Service history does not
establish current trust: initialization after Service requires a newly supplied
unused fixture/context. A live instance with changed claim history fails closed.

## HTTP contract

All paths below use `/api/v1`:

| Request | Owned candidate behavior |
| --- | --- |
| GET `/execution` | Busy/executing, current operation, error, retained owner, ephemeral flow activity; automatic resume false |
| GET `/machine`, `/runs/{id}`, `/machine/events`, `/runs/{id}/events` | Persisted observations/history |
| POST `/machine/initialize` | Explicit initial state from supplied fresh context; no actuator command |
| POST `/runs`, `/runs/{id}/start` | Persist configuration, then explicitly execute a CREATED run |
| POST `/runs/{id}/stop/request`, `/execution/{operation_id}/stop` | Out-of-queue orderly Stop |
| POST `/runs/{id}/pause`, `/runs/{id}/resume` | Current started pause-capable wait only |
| POST `/machine/recovery/start`, `/machine/flush/start` | Supplied plan plus fresh per-attempt `MaintenanceReadiness`; nullable maintenance run identity |
| Existing Arduino/SF Service requests | Same shared owner, runner and durable journals |
| Manual startup/phase/Stop/flush confirmation requests | HTTP 409; cannot bypass command-result resolution |

Default domain-only API behavior remains available without this composition;
execution/recovery/wait-control endpoints then return 503. The connected UI requires
the execution contract and does not fall back to domain-only phase completion.

## Explicit adapter resource composition

`build_adapter_application_execution` in `app/hardware/adapter_application.py`
prepares `OwnedApplicationExecution` with the existing Serial and SF adapter classes
and existing monotonic timer. Creating this object opens nothing and reads no
environment. Explicit application startup locks/validates the existing bundle
before opening Serial and sending HELLO. No SF connection, actuator command,
automatic retry, recovery or flushing is part of resource startup.

The caller supplies both transport configurations, pump calibrations, an explicit
SF mixer state (or unknown), optional readiness/plans and an independent
`context_factory(connected_boot_id)`. This callback runs on the worker after the
handshake and supplies current `CommandPlanningContext`; it is not given the
unwrapped adapter. The boot argument is connection correlation, not position
evidence. Context/calibration disagreement, an unexpected boot or invalid/unavailable
context fails startup and closes the connection. The factory must independently
establish current physical context; relabeling historical references to a new boot
is not supported. No concrete live-context provider or physical defaults are added.

The configured preparation variant, `build_configured_adapter_application_execution`,
uses an explicit validated profile and a session-bound current-state provider.
Startup leaves actuator references unknown; initial READY/Start and recovery obtain
fresh attributed input on the worker before planning. Missing or late input blocks
without sending commands. The original callback contract remains available for
existing explicit callers and still requires complete pump positions at startup.
Neither variant provides a concrete live evidence source or activation permission.
See `docs/ADAPTER_CURRENT_CONTEXT.md` for the strict inputs, continuity rules and
physical confirmation matrix.

Startup failures close acquired resources and release runtime locks. On normal
shutdown the existing application first requests orderly Stop and joins execution;
the runner closes, the resource scope invalidates the binding/closes Serial on the
worker, then lifecycle/owner handles and bundle locks close. Teardown does not send
an implicit actuator/torque command or release unresolved hardware ownership. SF
sessions retain the existing actuator's short-lived cleanup semantics. Context
manager cleanup also applies when runner construction fails after connection.

The adapter factory uses the existing transport/clock injection interfaces. Tests
cover no access during construction, lock/identity checks before transport creation,
only HELLO during startup, complete HTTP execution, recovery/flush/new run, failed
handshake/context/timer setup and shutdown during an active command. Every test
uses fake Serial/DYNAMIXEL transports. Existing preconnected caller-owned fixtures
remain supported; their external connection lifetime remains the caller's duty.

## Inputs, verification and limits

Calibrations, switching sequences, maintenance plans, independently established
device context and Column readiness are supplied by the server composition.
The UI sends configured volumes/times and attributed per-attempt maintenance
statements, never route or calibration defaults. SF duration is explicit; its
percent control does not claim a commissioned physical-speed mapping.

Tests cover full HTTP execution and a second run, actual adapters on fake Serial/
DYNAMIXEL transports, intent before bytes, concurrent reads/Stop, early and
between-phase Stop, wait Pause/Resume, shared Service exclusion, transport/write
failures, shutdown, startup without replay, standalone flushing, and recovery/
mandatory flushing with zero DemoRuns. UI API tests check acknowledgement identity,
unavailable executors, null maintenance scope, invalid responses and no retries.

This does not activate environment/production startup, authenticate operator statements,
prove cleaning/volume/movement, or commission routes and working margins. SF host
scope remains correlation rather than persistent physical trust. Cross-database
commits remain non-atomic, and advisory locks do not govern unwrapped adapters or
arbitrary database writers. No firmware or physical device was changed or used.

## Command-driven flow display

GET `/execution` now adds nullable `flow_activity` for ordinary Guided Demo and
recipe RUN phases. It contains `phase_execution_id`, `run_id`, prepared
`operation_number`, `operation_command_id`, `kind` (ASPIRATE/DISPENSE/COLLECT),
and symbolic `route`. Pump activity identifies the exact absolute-move action
and its separately selected aspiration or dispense route. Collection identifies
the protected dwell (command ID null), only after OPEN has completed, and clears
before required CLOSE or carousel movement.

This describes an active runner call including intent persistence, dispatch and
awaiting the command result. It does **not** assert receipt of controller STARTED,
sensor-observed flow, delivered volume, liquid presence or valve sealing. Existing
journals remain the authority for command lifecycle. Display state is immutable,
protected by a separate short lock, never read from SQLite on a status request,
and cleared in `finally` for success, Stop and exceptions before protected
follow-up. There is no new command, route policy, protocol frame, durable schema,
permission, replay or recovery decision. Restart starts with no activity and
never reconstructs it from historical plans/positions.

Maintenance/Service/HOME, route switching, passive or paused waits, SF mixing and
settling expose no flow activity. In particular, expanded maintenance operation
numbers are not interpreted as ordinary logical operation indices. Unsupported
paths remain static. An absent field from an older backend is also static in the
new UI; no whole-phase route is guessed. Tests: `tests/test_execution_flow.py`.
