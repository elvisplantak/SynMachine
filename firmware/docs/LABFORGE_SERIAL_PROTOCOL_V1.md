# LabForge Serial Protocol v1

- Protocol identifier: `LABFORGE/1`
- Status: approved design contract, partially implemented
- Date: 2026-07-30
- Firmware anchor: `f1414ac`
- Backend anchor: `88d17fb`

This document is the single canonical source of truth for LabForge software
communication semantics. It does not confirm wiring, pin mappings, calibration,
actuator feedback, or physical safety.

The terms **MUST**, **MUST NOT**, **SHOULD**, and **MAY** are normative. Examples
are compact symbolic JSON and do not define actuator command names.

## 1. Document status and boundaries

This is an approved design contract with the implementation status documented
in Section 22. The firmware implements handshake, status, and bounded
protocol-error responses, but not command responses, a command cache, actuator
protocol, or physical feedback. The backend does not yet implement the real
serial adapter in this contract.

Sections 2–19 define approved requirements and implementation order. Section 20
lists explicitly deferred functionality, and Section 21 lists unresolved
decisions. Future implementations MUST satisfy the requirements below.

## 2. Scope and safety goal

The protocol MUST let the backend distinguish definitely not started, accepted
but not started, started and software-completed, explicitly failed, and outcome
unknown. `ACK` or `ACCEPTED` alone MUST NOT be treated as proof of physical
execution. No physical command with an ambiguous outcome may be automatically
repeated.

## 3. Architecture boundary and identifiers

The backend owns high-level planning, safety policy, durable intent, and
recovery decisions. Arduino Mega owns low-level real-time actuator execution.
Arduino MUST NOT contain the complete Guided Demo workflow. React/UI MUST NOT
communicate directly with Arduino.

One `PhaseExecutionIntent` MAY contain multiple low-level commands:

- `phase_execution_id` identifies one whole backend phase execution.
- `operation_command_id` identifies one exact low-level physical command. The
  backend MUST durably persist it before sending the first serial byte.
- `request_id` correlates only harmless queries and responses; it MUST NOT
  identify a physical command.
- `backend_session_nonce` identifies one backend-created handshake session.
- `controller_boot_id` identifies one trusted controller boot.

Identifiers support correlation and duplicate detection. They do not prove
exactly-once physical execution.

## 4. Framing and bounded parsing

LABFORGE/1 uses newline-delimited UTF-8 JSON with one complete JSON object per
line. LF terminates a message. A receiver MAY accept CRLF by stripping CR.

The maximum payload is **512 bytes** and applies to the complete UTF-8 encoded
JSON object, including every key, quote, separator, escaped byte, and value, but
excluding the terminating LF and excluding a stripped CR when accepting CRLF.

Firmware MUST use a fixed bounded input buffer. A payload longer than 512 bytes
MUST be rejected as `LINE_TOO_LONG`; it MUST NOT be partially parsed. No
actuator behavior may occur before complete framing, JSON parsing, schema
validation, session validation, and command validation. Malformed JSON and
oversized or invalid fields MUST NOT trigger actuator behavior.

Realistic mandatory messages exceeded the former 256-byte proposal. The
512-byte limit preserves readable field names and bounded headroom. Firmware
SRAM consumption MUST still be measured before actuator implementation; this
contract does not claim that a parser exists or that the future firmware SRAM
budget has been validated. No specific Arduino JSON library is prescribed.

## 5. Versioning, envelope, and field bounds

Every valid LABFORGE/1 message MUST contain `protocol` and `type`. `protocol`
MUST equal `"LABFORGE/1"`. Unsupported versions MUST be rejected. Version
negotiation occurs during `HELLO`.

Every successfully parsed session-bound message and response MUST contain
`backend_session_nonce` and `controller_boot_id`, except:

- `HELLO` has no `controller_boot_id`;
- a diagnostic session with untrusted identity uses
  `controller_boot_id:null`; and
- `PROTOCOL_ERROR` MAY omit correlation fields that framing, oversize, or
  malformed JSON prevents the receiver from recovering safely.

Inbound session-bound `controller_boot_id` parsing distinguishes an absent
field, explicit JSON null, and an unsigned 32-bit value. Null is syntactically
supported for an untrusted diagnostic session, but semantic acceptance still
depends on current session and boot-identity validation and never authorizes a
physical command by itself.

Query responses MUST echo `request_id`. Command lifecycle messages MUST contain
`phase_execution_id` and `operation_command_id`. Unknown and duplicate JSON
fields MUST be rejected in LABFORGE/1. Missing fields are protocol errors.

### Normative field and collection bounds

| Field | LABFORGE/1 bound |
|---|---|
| `protocol` | Exact ASCII value `LABFORGE/1` |
| `type` | 1–32 ASCII bytes |
| `backend_session_nonce` | Canonical lowercase UUID text, exactly 36 ASCII bytes |
| `phase_execution_id` | 1–64 ASCII bytes; only `A-Z`, `a-z`, `0-9`, `-`, `_`, `.`, `:` |
| `operation_command_id` | Canonical lowercase UUID text, exactly 36 ASCII bytes |
| `request_id` | Canonical lowercase UUID text, exactly 36 ASCII bytes |
| `controller_boot_id` | Unsigned 32-bit JSON integer when trusted; null only in the defined untrusted-identity diagnostic state |
| `command` | 1–32 uppercase ASCII bytes; only `A-Z`, `0-9`, `_` |
| `error_code` | 1–40 uppercase ASCII bytes; only `A-Z`, `0-9`, `_` |
| Human-readable `message` | Optional; at most 96 UTF-8 bytes |
| Capability name | 1–32 uppercase ASCII bytes; at most 8 capabilities |
| `arguments` object | At most 8 members; keys are 1–24 ASCII bytes; scalar values only: string, signed 64-bit integer, or boolean; null and floating-point numbers are not allowed; strings at most 64 UTF-8 bytes; no nested object or array |
| `result` object | Same structural bounds as `arguments`, except future command-specific schemas may explicitly permit selected null values |
| Any other protocol collection | At most 8 entries unless its schema sets a smaller limit |

Every field and collection MUST pass its bound before actuator behavior, and
the complete message MUST still fit within 512 bytes. A command with
individually valid large arguments MAY therefore be rejected by the total
limit. Excessive field or collection size returns `INVALID_FIELD`; excessive
total payload returns `LINE_TOO_LONG`.

Optional command arguments MUST be omitted. Optional fields MUST be omitted
rather than set to null. Only
`controller_boot_id` in the untrusted-identity diagnostic state,
`active_operation_command_id` when no command is active, and `result` values
explicitly permitted as null by a future command schema may be null.

## 6. Controller boot identity and fail-closed behavior

The approved design derives `controller_boot_id` from an EEPROM-backed unsigned
boot counter advanced once per controller boot. The pure, storage-independent
record codec and selection/update logic, Arduino EEPROM adapter, and startup
integration are implemented.
`MCUSR` reset cause is diagnostic metadata only and MUST NOT identify a session.

EEPROM bytes `0..31` are reserved exclusively for boot identity. Slot 0 uses
bytes `0..15`, and slot 1 uses bytes `16..31`. The Arduino adapter maps each
logical address directly to the same EEPROM address, reports the actual
`EEPROM.length()` capacity, and uses `EEPROM.update()` for writes. Because the
Arduino EEPROM API does not report physical cell-write success, a successful
adapter write return alone does not establish trust. The complete read-back
validation performed by the boot-identity store establishes trusted identity.

A trusted boot ID exists only after a record passes version and CRC/checksum
validation, has unambiguous ordering, is initialized or advanced successfully,
and passes read-back verification. Storage consists of two fixed 16-byte slots:

| Bytes | Value |
|---|---|
| `0..3` | ASCII magic `LFBI` |
| `4` | format version `1` |
| `5..7` | reserved, all zero |
| `8..11` | `controller_boot_id`, unsigned 32-bit little-endian |
| `12..13` | CRC-16/CCITT-FALSE, little-endian |
| `14` | commit marker A, `0xA5` |
| `15` | commit marker B, `0x5A` |

CRC-16/CCITT-FALSE uses polynomial `0x1021`, initial value `0xFFFF`, no
reflection, and no final XOR, covering bytes `0..11`. A slot is valid only when
both commit markers, magic, supported version, zero reserved bytes, CRC, and a
nonzero boot ID all validate. Records are encoded byte by byte; C++ structure
layout is not serialized.

If both slots are fully erased (`0xFF` in every byte), slot 0 is initialized with
ID 1. With exactly one valid slot, its ID is newest and the next ID is written to
the other slot. With two valid slots, their IDs MUST be consecutive; the larger
is newest and the next ID is written into the older slot. Equal, non-consecutive,
or otherwise ambiguous valid IDs are untrusted. If neither slot is valid and the
pair is not fully erased, identity is untrusted.

Updating a target slot MUST first invalidate commit marker B, then write bytes
`0..13`, write commit marker A, and write commit marker B last. The complete slot
MUST then be read back and validated. The previously valid slot remains untouched
during this sequence. Any insufficient capacity, read or write failure, failed
read-back validation, ambiguity, or invalid non-erased pair fails closed without
guessing an ID. A newest ID of `UINT32_MAX` is untrusted and MUST NOT wrap.
Physical commands MUST remain disabled until initialization or advancement and
read-back verification succeed. EEPROM MUST NOT be written per command.

For invalid checksum, ambiguous ordering, an interrupted update without a
uniquely valid newest record, read failure, unsupported record version, or any
other identity uncertainty, the controller MUST:

- use `controller_boot_id:null`;
- report `controller_state:"IDENTITY_UNTRUSTED"`;
- report `software_state_trust:"UNTRUSTED"`;
- allow only `HELLO` and harmless diagnostic queries;
- reject every physical `COMMAND` with
  `CONTROLLER_IDENTITY_UNTRUSTED`; and
- never invent or guess a trusted boot ID.

Firmware makes one boot-identity initialization call per startup after starting
Serial and retains the complete result internally: either a trusted
`controller_boot_id`, or an explicit untrusted failure result. `HELLO_OK` and
valid session-bound `STATUS` responses expose the trusted or explicitly
untrusted identity state without converting an untrusted result into a guessed
boot ID.

Only recovery or provisioning after a fail-closed identity boot remains
unresolved.

## 7. Controller software state and trust

`controller_state` has these values:

- `PROTOCOL_ONLY`: the protocol shell is available and no actuator command
  capability is implemented.
- `IDLE`: no non-terminal command exists in controller software state.
- `BUSY`: one command is `ACCEPTED` or `STARTED`.
- `ERROR`: a controller software fault blocks new physical commands.
- `IDENTITY_UNTRUSTED`: `controller_boot_id` cannot be trusted.

`software_state_trust` is `TRUSTED` or `UNTRUSTED`. It describes only whether
firmware can account for its current software, session, and command state. It
does not prove physical valve position, delivered volume, carousel position,
mixer rotation, fluidic safety, or machine readiness. `IDLE` never means the
physical LabForge machine is safe or `READY`; physical readiness remains a
backend lifecycle and future sensor/recovery decision.

## 8. Message schemas

Fields listed as required MUST be present. Fields listed as optional MUST follow
the omission rule in Section 5. All examples are valid compact JSON.

### `HELLO`

Required: `protocol`, `type`, `backend_session_nonce`.

```json
{"protocol":"LABFORGE/1","type":"HELLO","backend_session_nonce":"123e4567-e89b-12d3-a456-426614174000"}
```

### `HELLO_OK`

Required: `protocol`, `type`, `backend_session_nonce`, `controller_boot_id`,
`controller_state`, `software_state_trust`, `capabilities`. Optional:
`reset_cause`.

The current implementation emits one compact LF-terminated `HELLO_OK` for each
valid parsed `HELLO`, with deterministic field order, empty `capabilities`, and
no `reset_cause`. A trusted identity emits its numeric boot ID with
`controller_state:"PROTOCOL_ONLY"` and `software_state_trust:"TRUSTED"`. An
untrusted identity emits `controller_boot_id:null`,
`controller_state:"IDENTITY_UNTRUSTED"`, and
`software_state_trust:"UNTRUSTED"` for diagnostic-only correlation.

```json
{"protocol":"LABFORGE/1","type":"HELLO_OK","backend_session_nonce":"123e4567-e89b-12d3-a456-426614174000","controller_boot_id":4294967295,"controller_state":"PROTOCOL_ONLY","software_state_trust":"TRUSTED","capabilities":[]}
```

### `COMMAND`

Required: `protocol`, `type`, `backend_session_nonce`, `controller_boot_id`,
`phase_execution_id`, `operation_command_id`, `command`, `arguments`.

```json
{"protocol":"LABFORGE/1","type":"COMMAND","backend_session_nonce":"123e4567-e89b-12d3-a456-426614174000","controller_boot_id":4294967295,"phase_execution_id":"phase-execution-1","operation_command_id":"323e4567-e89b-12d3-a456-426614174002","command":"FUTURE_COMMAND","arguments":{}}
```

### `REJECTED`

Required: common command correlation fields and `error_code`. Optional:
`message`. It means the command was sufficiently parsed and correlated but
controller ownership was refused before any actuator side effect. The result is
terminal and cached.

```json
{"protocol":"LABFORGE/1","type":"REJECTED","backend_session_nonce":"123e4567-e89b-12d3-a456-426614174000","controller_boot_id":4294967295,"phase_execution_id":"phase-execution-1","operation_command_id":"323e4567-e89b-12d3-a456-426614174002","error_code":"CONTROLLER_BUSY"}
```

### `ACCEPTED`

Required: common command correlation fields. It means parsed, validated, and
owned by the controller, but not started.

```json
{"protocol":"LABFORGE/1","type":"ACCEPTED","backend_session_nonce":"123e4567-e89b-12d3-a456-426614174000","controller_boot_id":4294967295,"phase_execution_id":"phase-execution-1","operation_command_id":"323e4567-e89b-12d3-a456-426614174002"}
```

### `STARTED`

Required: common command correlation fields. It means execution crossed the
boundary immediately before the first actuator side effect.

```json
{"protocol":"LABFORGE/1","type":"STARTED","backend_session_nonce":"123e4567-e89b-12d3-a456-426614174000","controller_boot_id":4294967295,"phase_execution_id":"phase-execution-1","operation_command_id":"323e4567-e89b-12d3-a456-426614174002"}
```

### `COMPLETED`

Required: common command correlation fields and `result`, which MAY be empty.
It means the firmware state machine completed and internally implies `STARTED`
was crossed. It does not prove sensor-confirmed physical success.

```json
{"protocol":"LABFORGE/1","type":"COMPLETED","backend_session_nonce":"123e4567-e89b-12d3-a456-426614174000","controller_boot_id":4294967295,"phase_execution_id":"phase-execution-1","operation_command_id":"323e4567-e89b-12d3-a456-426614174002","result":{}}
```

### `FAILED`

Required: common command correlation fields, `error_code`, and
`execution_started`. Optional: `message`; bounded `result` only when a future
command schema defines partial-result reporting. `execution_started:false`
means failure before the `STARTED` boundary; `true` means failure after it.

```json
{"protocol":"LABFORGE/1","type":"FAILED","backend_session_nonce":"123e4567-e89b-12d3-a456-426614174000","controller_boot_id":4294967295,"phase_execution_id":"phase-execution-1","operation_command_id":"323e4567-e89b-12d3-a456-426614174002","error_code":"ACTUATOR_FAILURE","execution_started":true}
```

### `QUERY_STATUS`

Required: `protocol`, `type`, `backend_session_nonce`, `controller_boot_id`,
`request_id`.

```json
{"protocol":"LABFORGE/1","type":"QUERY_STATUS","backend_session_nonce":"123e4567-e89b-12d3-a456-426614174000","controller_boot_id":4294967295,"request_id":"423e4567-e89b-12d3-a456-426614174003"}
```

### `STATUS`

Required: `protocol`, `type`, `backend_session_nonce`, `controller_boot_id`,
`request_id`, `controller_state`, `software_state_trust`, and
`active_operation_command_id`. The active ID is null when no command is active.
`STATUS` MUST NOT repeat capabilities or claim physical truth.

The current protocol-only implementation emits one compact LF-terminated
`STATUS` after a valid session-bound `QUERY_STATUS`. It echoes the nonce and
request ID, reports the trusted numeric or untrusted null boot ID, uses
`PROTOCOL_ONLY` or `IDENTITY_UNTRUSTED` as applicable, and reports
`active_operation_command_id:null`. Queries that fail session or boot-ID
validation cannot produce `STATUS` and instead receive a correlated
`PROTOCOL_ERROR`.

```json
{"protocol":"LABFORGE/1","type":"STATUS","backend_session_nonce":"123e4567-e89b-12d3-a456-426614174000","controller_boot_id":4294967295,"request_id":"423e4567-e89b-12d3-a456-426614174003","controller_state":"PROTOCOL_ONLY","software_state_trust":"TRUSTED","active_operation_command_id":null}
```

### `QUERY_COMMAND`

Required: `protocol`, `type`, `backend_session_nonce`, `controller_boot_id`,
`request_id`, and `operation_command_id`.

```json
{"protocol":"LABFORGE/1","type":"QUERY_COMMAND","backend_session_nonce":"123e4567-e89b-12d3-a456-426614174000","controller_boot_id":4294967295,"request_id":"423e4567-e89b-12d3-a456-426614174003","operation_command_id":"323e4567-e89b-12d3-a456-426614174002"}
```

### `COMMAND_STATUS`

Required: `protocol`, `type`, `backend_session_nonce`, `controller_boot_id`,
`request_id`, `operation_command_id`, and `command_state`.
`phase_execution_id` is required when known. State-specific cached fields are:
`error_code` and optional `message` for `REJECTED`; `result` for `COMPLETED`;
and `error_code`, `execution_started`, and optional `message`/permitted `result`
for `FAILED`.

```json
{"protocol":"LABFORGE/1","type":"COMMAND_STATUS","backend_session_nonce":"123e4567-e89b-12d3-a456-426614174000","controller_boot_id":4294967295,"request_id":"423e4567-e89b-12d3-a456-426614174003","phase_execution_id":"phase-execution-1","operation_command_id":"323e4567-e89b-12d3-a456-426614174002","command_state":"STARTED"}
```

### `PROTOCOL_ERROR`

Required: `protocol`, `type`, `error_code`. Optional: `message`. When safely
recoverable it MUST also contain `backend_session_nonce`, `controller_boot_id`,
and either `request_id` for a query error or both command IDs for a command
error. Query and command correlation fields MUST NOT be mixed. Correlation MAY
be omitted only when framing, oversize, or malformed JSON prevents safe
extraction. Semantic refusal of a valid `COMMAND` uses `REJECTED`.

The current no-motion dispatcher emits bounded deterministic errors with no
optional `message`. Oversized and malformed input produces an uncorrelated
error. Schema errors are correlated only when a valid LABFORGE/1 message type
and the complete relevant query or command identifiers can be recovered
safely. A parsed `QUERY_STATUS` receives correlated `HANDSHAKE_REQUIRED`,
`STALE_SESSION`, `CONTROLLER_BOOT_MISMATCH`, or
`CONTROLLER_IDENTITY_UNTRUSTED` as applicable. Writer failure emits no partial
frame, and dispatch selects at most one response per received frame.

```json
{"protocol":"LABFORGE/1","type":"PROTOCOL_ERROR","backend_session_nonce":"123e4567-e89b-12d3-a456-426614174000","controller_boot_id":4294967295,"request_id":"423e4567-e89b-12d3-a456-426614174003","error_code":"INVALID_FIELD","message":"Invalid query field"}
```

## 9. Handshake and session replacement

`backend_session_nonce` is the sole LABFORGE/1 session identifier. The backend
generates the canonical lowercase UUID, and firmware copies it unchanged into
fixed-capacity volatile storage. Firmware does not generate a separate
`session_id`. The backend MUST generate a new `backend_session_nonce` for every
handshake.
The controller MUST NOT accept physical commands before a successful handshake.
Every successful `HELLO` establishes one current nonce. A later successful
`HELLO` in the same controller boot replaces it; messages and queued lifecycle
messages carrying the old nonce are stale and MUST be rejected or ignored.

Retrying the same valid nonce is idempotent and emits the same semantic
`HELLO_OK`. A different valid nonce immediately replaces the previous session.
Invalid, malformed, oversized, unsupported, or otherwise rejected input does
not alter session state. It produces the bounded protocol error defined above
when serialization succeeds. There is no firmware-side session timeout or
inactivity expiry in LABFORGE/1; controller reboot naturally clears the
volatile session.

Session replacement MUST NOT resume, repeat, stop, cancel, complete, or
otherwise alter an active physical command. Command identity and cached state
are scoped to (`controller_boot_id`, `operation_command_id`), not permanently to
the submitting nonce. A new session in the same boot MAY query an existing
command by ID. If it is non-terminal, new physical `COMMAND` messages MUST be
rejected with `CONTROLLER_BUSY`. The backend MUST use `QUERY_COMMAND` after
replacement rather than rely on lifecycle messages queued for the old session.
Session establishment and replacement provide correlation only and have no
command or physical side effect.

A changed boot ID means volatile state was lost and unresolved prior physical
commands become outcome unknown. A handshake never automatically resumes,
repeats, stops, or marks a command completed. LABFORGE/1 assumes one backend
process and one active controller session; multiple simultaneous backend-client
ownership is outside v1.

## 10. Command lifecycle ordering

The internal lifecycle is:

```text
COMMAND -> exactly one of REJECTED or ACCEPTED
ACCEPTED -> exactly one of STARTED or FAILED(execution_started=false)
STARTED -> exactly one of COMPLETED or FAILED(execution_started=true)
```

`REJECTED`, `COMPLETED`, and `FAILED` are terminal. Exactly one terminal state
MUST exist per `operation_command_id` within one controller boot. `COMPLETED`
internally requires that `STARTED` was crossed. The backend MAY observe a
terminal state without receiving the earlier `STARTED` message due to loss or
reconnect; absence of observed `STARTED` is not proof execution never started.

Retransmission of an identical lifecycle state with identical semantic content
is idempotent. State regression is invalid. Different terminal results for one
ID are a controller protocol fault; an identical terminal retransmission is
accepted. Lifecycle messages from a stale nonce are rejected or ignored by the
current backend session. `COMMAND_STATUS` is authoritative for cached state
within the current controller boot.

All lifecycle states are software evidence, not physical sensor evidence.

## 11. Command status semantics

`command_state` is `UNKNOWN`, `REJECTED`, `ACCEPTED`, `STARTED`, `COMPLETED`, or
`FAILED`. `UNKNOWN` means no cache entry exists in the current boot; it does not
prove a physical command never executed and never authorizes automatic
re-execution. `ACCEPTED` and `STARTED` contain no invented terminal result.
Queries MUST NOT initiate or repeat motion.

## 12. Duplicate-command semantics

The controller MUST maintain a bounded volatile per-boot cache; exact size
remains unresolved. Its key is `operation_command_id`. Command identity is the
parsed, validated semantic tuple (`phase_execution_id`, `command`, `arguments`).
It excludes the nonce, JSON whitespace, JSON object key order, boot ID (already
scoped by the cache), and operation ID (the key).

Comparison MUST occur after JSON parsing and command-schema validation. Argument
values are compared by validated typed representation, so formatting and object
key order are irrelevant. Generic `arguments` integers use the signed 64-bit
range; `controller_boot_id` remains a separate unsigned 32-bit field. Argument
values remain non-null, and floating-point numbers are unsupported.

The same key and identity returns cached status/result without execution. The
same key with different identity returns `COMMAND_ID_CONFLICT`. Cache loss after
reboot does not permit automatic execution; `UNKNOWN` is not permission.

## 13. Reconnect and timeout behavior

On reconnect, the backend sends a new `HELLO`, receives `HELLO_OK`, and compares
boot ID. With the same boot ID it MAY query an existing command. With a changed
boot ID, unresolved non-terminal physical commands become outcome unknown and
new physical work remains blocked until backend recovery resolves the state.

Timeout implies neither failure nor completion. The backend MAY automatically
retry only `HELLO`, `QUERY_STATUS`, and `QUERY_COMMAND`. Physical commands MUST
NOT be automatically resent after timeout, disconnect, missing `ACCEPTED`,
missing `STARTED`, missing terminal result, or controller reboot. The backend
MUST query state when possible; unresolved results become outcome unknown.
Exact timeout durations and reconnect backoff remain unresolved.

## 14. Protocol errors

Error codes include:

- `MALFORMED_MESSAGE`
- `LINE_TOO_LONG`
- `UNSUPPORTED_PROTOCOL_VERSION`
- `HANDSHAKE_REQUIRED`
- `STALE_SESSION`
- `CONTROLLER_BOOT_MISMATCH`
- `CONTROLLER_IDENTITY_UNTRUSTED`
- `MISSING_FIELD`
- `INVALID_FIELD`
- `UNSUPPORTED_MESSAGE_TYPE`
- `UNSUPPORTED_COMMAND`
- `COMMAND_ID_CONFLICT`
- `CONTROLLER_BUSY`
- `UNKNOWN_COMMAND`

Future actuator-specific errors MUST be added only after actuator contracts
exist.

## 15. Retry-safety policy

Only `HELLO`, `QUERY_STATUS`, and `QUERY_COMMAND` are automatically retryable.
After an ambiguous outcome, route selection, valve or pump homing/movement,
aspiration, dispense, bottom-valve movement, carousel movement, and mixer
commands MUST NOT be automatically retried. Even apparently idempotent actions
depend on liquid contents, route, trusted homing, and physical state.

## 16. Exactly-once limits

V1 MAY support correlation, at-most-once dispatch in one healthy session,
bounded duplicate suppression during one Arduino boot, and cached software
terminal-result replay. It cannot prove exactly-once physical action, delivered
volume, physical valve or carousel position, actual mixer rotation, or motion
completion without sensors.

Stronger guarantees would require a durable command journal, physical feedback,
atomic persistent lifecycle transitions, defined partial-execution recovery,
and storage-corruption handling.

## 17. Approved initial implementation scope

The first implementation MUST include only:

- fixed bounded line receiver and NDJSON parser;
- protocol version and field-bound validation;
- `HELLO` / `HELLO_OK`, nonce handling, and boot-ID exposure;
- `QUERY_STATUS` / `STATUS` and `QUERY_COMMAND` / `COMMAND_STATUS`;
- protocol errors and stale-session rejection;
- parser and handshake tests; and
- a volatile bounded command-status cache shell.

It MUST include no physical movement, homing, route selection, fluid handling,
automatic recovery/flush, actuator command, or Guided Demo execution.

## 18. Representative 512-byte budget

The following compact examples use a 36-byte nonce, 64-byte worst-case phase
ID where applicable, 36-byte operation/request IDs, a uint32 boot ID, and
representative enum/error names. State-specific `COMMAND_STATUS` sizes include
their mandatory minimal cached fields.

| Message | Representative/worst-case bytes |
|---|---:|
| `HELLO` | 103 |
| `HELLO_OK` | 225 |
| `COMMAND` with empty `arguments` | 329 |
| `REJECTED` | 327 |
| `ACCEPTED` | 288 |
| `STARTED` | 287 |
| `COMPLETED` | 301 |
| `FAILED` | 343 |
| `QUERY_STATUS` | 194 |
| `STATUS` | 292 |
| `QUERY_COMMAND` | 257 |
| `COMMAND_STATUS UNKNOWN` | 372 |
| `COMMAND_STATUS REJECTED` | 418 |
| `COMMAND_STATUS ACCEPTED` | 373 |
| `COMMAND_STATUS STARTED` | 372 |
| `COMMAND_STATUS COMPLETED` | 386 |
| `COMMAND_STATUS FAILED` | 428 |
| `PROTOCOL_ERROR` query correlation | 235 |
| `PROTOCOL_ERROR` command correlation | 333 |

Every mandatory minimal form fits within 512 bytes. Optional messages and
bounded objects MUST still satisfy the total limit.

## 19. Approved implementation sequence

1. Canonical protocol document — firmware repository.
2. Pure message models and stream parser — backend repository.
3. Protocol shell without movement — firmware repository.
4. Handshake/session tests — backend and firmware repositories.
5. Harmless status queries — backend and firmware repositories.
6. One separately approved Service-mode actuator — firmware repository.
7. Real serial adapter — backend repository.
8. Coordinator integration — backend repository.
9. Disconnect/reset/fault injection — backend and firmware repositories.
10. Guided Demo physical execution — backend and firmware repositories.

Approval of one stage MUST NOT imply approval of a later stage.

## 20. Explicitly deferred functionality

Actuator command names/contracts and actuator-specific schemas are deferred.
Production movement, homing, route selection, fluid handling, automatic
recovery/flush, Guided Demo execution, durable per-command EEPROM journaling,
and stronger physical execution guarantees are outside the initial shell.

## 21. Open decisions

The following remain unresolved and MUST NOT be inferred:

- identity-recovery procedure after a fail-closed boot;
- duplicate-cache size within the documented collection bounds;
- timeout durations and serial reconnect backoff;
- first Service-mode actuator and actuator-specific schemas;
- pump semantic direction API and early-limit-switch policy;
- carousel position model and mixer command semantics;
- bottom-valve wiring and feedback;
- emergency-stop hardware contract; and
- whether physical sensors will be added.

## 22. Current implementation reality

The current firmware implementation includes bounded serial line reception,
strict UTF-8/JSON validation, inbound parsing for the currently supported
backend message types, a pure boot-identity record codec, storage-independent
boot-identity selection/update logic, an Arduino EEPROM adapter, and one
boot-identity initialization call per firmware startup that retains the complete
trusted or untrusted result.
It also includes nullable inbound boot-ID parsing, fixed-capacity volatile
session state, bounded deterministic `HELLO_OK` serialization, and actual
`HELLO` to `HELLO_OK` Serial integration for trusted and untrusted identity.
It now also validates session-bound `QUERY_STATUS` messages, emits bounded
deterministic trusted or untrusted `STATUS` responses, and uses a testable
no-motion dispatcher for bounded parser, session, and boot-ID protocol errors.
`QUERY_COMMAND`, command responses, a command cache, actuator commands, and
physical execution remain unimplemented. Fail-closed recovery and provisioning
remain unresolved. This firmware has not been uploaded or physically tested.
No component is claimed to measure delivered volume or provide exactly-once
physical execution.
