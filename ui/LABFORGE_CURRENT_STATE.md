# LabForge Current Development State

- Checkpoint date: 2026-08-10
- Development phase: P1 production Serial/runtime software integration; physical upload deferred
- Primary implementation agent: Codex
- Independent reviewer: ChatGPT

## Repository checkpoints

### UI

- Branch: `codex/harden-env-ignore-rules-2026-07-30`
- HEAD before this checkpoint documentation update:
  `2715b92035277626ebb86e8a38906d1c683896bf`
- Working tree was clean before this checkpoint documentation update.

### Backend

- Branch: `codex/labforge-v1-message-models-parser-contract-fixes`
- HEAD: `7f8697c6b3ea02f1ff9450faa2d55149ace2f180`
- Working tree was clean when governance alignment started.
- LABFORGE/1 message models and parser contract fixes are pushed at this
  checkpoint.

### Firmware

- Current P1 runtime checkpoint:
  - branch: `codex/p1-motion-safety-hardening`
  - commit: `430f7534b4d554c81af39338280f5aa95835727a`
    (`Bound P1 step pulses and serial output`)
  - production Mega build connects the confirmed P1 STEP/DIR/HOME pins, the
    nonblocking controller, bounded Serial servicing, lifecycle output, and
    volatile command-status recovery;
  - each STEP pulse uses the confirmed bounded 20 us HIGH primitive and returns
    LOW before controller update returns;
  - Serial output is cooperatively handed to the AVR transport in fixed chunks,
    with motion servicing between chunks;
  - a complete `STARTED` frame must be handed to Serial before motion starts or
    the cache advances to `STARTED`;
  - reconnect preserves active motion, suppresses lifecycle frames tied to the
    replaced nonce, reports `BUSY`, and permits recovery through
    `QUERY_COMMAND`;
  - identity-untrusted physical commands fail closed;
  - focused P1 motion/runtime/transport tests: `36/36 passed`;
  - complete warning-clean native suite: `118/118 passed`;
  - warning-clean Mega 2560 build: successful;
  - flash: `30,816 / 253,952 bytes` (`12%`);
  - static RAM: `2,241 / 8,192 bytes` (`27%`);
  - refreshed no-LTO AVR stack analysis places the worst credible integrated
    parser/dispatch path at approximately `5.0 KB`, leaving approximately
    `0.9 KB` before interrupt/runtime margin; and
  - physical upload and execution were not performed.

- Completed and pushed EEPROM bootstrap:
  - branch: `codex/labforge-v1-arduino-eeprom-identity-bootstrap`
  - commit: `cde95cae8860f8ef0b417d95b0b1ee3d1848031e`
- Completed and pushed handshake/session foundation:
  - branch: `codex/labforge-v1-handshake-session-foundation`
  - commit: `1a4f72668045bb63cb8411b6a12249fdd9aa6320`
- Completed and pushed status-query foundation:
  - branch: `codex/labforge-v1-status-query-foundation`
  - commit: `81bc8037c35edbfc6576a32daf93f8a753f62b49`
- Completed and pushed protocol-error/dispatch foundation:
  - branch: `codex/labforge-v1-protocol-error-dispatch-foundation`
  - commit: `2d793369ba4a91bb9fbbbcaf48de963fbc650af2`
- Completed and pushed command-status cache foundation:
  - branch: `codex/labforge-v1-command-status-cache-foundation`
  - commit: `ab6c1747f70ed99885fa2bcb38f4ee425cc7ac82`
- Completed and pushed command-lifecycle integrity foundation:
  - branch: `codex/labforge-v1-command-lifecycle-integrity-foundation`
  - commit: `99101b93f2d44c4e2e5722398653d665c9b031c1`
- Completed and pushed P1 absolute-step command contract:
  - branch: `codex/labforge-v1-p1-absolute-command-contract`
  - commit: `d0f295005f77da673cc4c0b8376f6b003cce08e5`
- Completed and pushed P1 command-boundary hardening:
  - branch: `codex/labforge-v1-p1-command-boundary-hardening`
  - commit: `52fa9188f91bc1e08036bb8d1f769e634b156f29`

The milestone sections below preserve the state recorded when each checkpoint
was completed. They are historical; the current firmware state is the P1
runtime checkpoint above.

## Handshake/session milestone

Implemented and pushed:

- trusted and untrusted deterministic `HELLO_OK` serialization;
- fixed-capacity volatile session state;
- nullable inbound `controller_boot_id` representation;
- stale-session and boot-ID validation foundation; and
- valid `HELLO` to `HELLO_OK` Serial integration without motion.

Latest verified results:

- focused handshake/session/writer and parser tests: `16/16 passed`;
- focused boot-identity tests: `12/12 passed`;
- complete native suite: `41/41 passed`;
- warning-enabled native suite: `41/41 passed`;
- Mega 2560 build: successful;
- flash: `17,302 / 253,952 bytes`;
- static RAM: `1,231 / 8,192 bytes`; and
- `git diff --check`: passed.

Independent review identified unnecessary AVR SRAM use in the writer format
strings. The final implementation stores those constant strings in flash and
retains:

- global `helloOkFrame`: `256` bytes;
- `SessionState`: `38` bytes.

The optimization reduced static RAM from `1,609` to `1,231` bytes (`378` bytes
recovered) without changing flash usage or byte-exact `HELLO_OK` output.

## Status-query milestone

The status-query foundation now implements:

- session and boot-ID validation for `QUERY_STATUS`;
- byte-exact trusted and untrusted `STATUS` serialization;
- echoed session nonce and request ID;
- `PROTOCOL_ONLY` or `IDENTITY_UNTRUSTED` software state;
- `active_operation_command_id:null`; and
- no command dispatch, pin access, or physical behavior.

Latest verified results:

- focused status-query tests: `3/3 passed`;
- complete native suite: `44/44 passed`;
- warning-enabled native suite: `44/44 passed`;
- Mega 2560 build: successful;
- flash: `17,984 / 253,952 bytes`;
- static RAM: `1,295 / 8,192 bytes`; and
- `git diff --check`: passed.

## Protocol-error/dispatch milestone

The protocol-error/dispatch foundation now implements:

- a small testable no-motion dispatch path from parsed frame to one response or
  intentional no response;
- bounded deterministic `PROTOCOL_ERROR` serialization;
- safe query or command correlation for recoverable schema errors;
- uncorrelated malformed and oversized errors;
- correlated `QUERY_STATUS` session and boot-identity errors;
- transactional writer failure with no partial Serial output; and
- at most one selected response per received frame.

Latest verified results:

- focused protocol-error/dispatch tests: `7/7 passed`;
- complete native suite: `51/51 passed`;
- warning-enabled native suite: `51/51 passed`;
- Mega 2560 build: successful;
- flash: `20,682 / 253,952 bytes`;
- static RAM: `1,359 / 8,192 bytes`; and
- `git diff --check`: passed.

An AVR `-fstack-usage` analysis without LTO estimated the deepest current
parser/dispatch path at approximately `3.3–3.6 KB`, including parser, JSON
document, and validator calls. This is acceptable for the current no-motion
shell but must be reassessed before command-cache growth and actuator work.

## Command-status cache milestone

The command-status cache foundation now implements:

- valid session-bound `QUERY_COMMAND` / `COMMAND_STATUS` responses;
- a two-entry volatile per-boot cache with at most one non-terminal entry;
- deterministic oldest-terminal eviction;
- read-only query behavior and `UNKNOWN` for absent or evicted IDs;
- mandatory serialization for all six command states, without optional message
  or result payloads; and
- no incoming `COMMAND` acceptance, lifecycle progression, duplicate-command
  identity comparison, dispatch, or physical behavior.

Latest verified results:

- focused command-status and protocol-error/dispatch tests: `16/16 passed`;
- complete native suite: `60/60 passed`;
- warning-enabled native suite: `60/60 passed`;
- Mega 2560 build: successful;
- flash: `22,286 / 253,952 bytes`;
- static RAM: `1,665 / 8,192 bytes`; and
- `git diff --check`: passed.

AVR memory details:

- `CommandStatusEntry`: `111` bytes;
- `CommandStatusCache`: `226` bytes;
- shared output buffer: `464` bytes;
- maximum implemented mandatory `COMMAND_STATUS`: `443` bytes including LF;
- deepest estimated parser/dispatch stack path: approximately `3.3–3.6 KB`;
- command-status writer path: approximately `1.7 KB`; and
- nominal SRAM remaining after static use plus the conservative deepest stack
  estimate: approximately `2.9 KB` before interrupt/runtime margin.

## Command-lifecycle integrity milestone

The command-lifecycle integrity foundation now adds:

- strict `ACCEPTED -> STARTED -> COMPLETED` lifecycle ordering;
- idempotent exact replay without insertion-sequence changes;
- immutable terminal states and phase identity;
- canonical lowercase UUID and safe phase-ID validation;
- rejection of invalid enum values and invalid cached identifiers; and
- structural recognition of both valid `FAILED` boundaries, while actual
  `FAILED` storage remains blocked until execution-failure error codes are
  explicitly defined and reviewed.

At this historical checkpoint the production runtime did not yet call
`CommandStatusCache::store()`. The current P1 runtime now stores lifecycle
states, and deliberate post-`STARTED` abort uses the distinct
`COMMAND_ABORTED` execution-failure code.

Latest verified results:

- focused command-lifecycle tests: `11/11 passed`;
- complete native suite: `63/63 passed`;
- warning-enabled native suite: `63/63 passed`;
- Mega 2560 build: successful;
- flash: `22,286 / 253,952 bytes`;
- static RAM: `1,665 / 8,192 bytes`; and
- `git diff --check`: passed.

The memory measurements and conservative stack estimate from the preceding
command-status checkpoint are unchanged. The next step is independent review
of this checkpoint before selecting the first actual command contract or any
Service-layer actuator boundary. Incoming `COMMAND` handling, duplicate-command
identity comparison, dispatch, and physical behavior remain unimplemented.

## P1 absolute-step contract milestone

The first approved Service-mode contract is now implemented as a no-motion
foundation:

- exact `PUMP_MOVE_ABSOLUTE_STEPS` schema, restricted to `P1`;
- exactly `pump:"P1"` and integer `target_steps` in `1..20500`;
- compact exact semantic duplicate identity without hash-only comparison;
- testable `ACCEPTED -> STARTED -> COMPLETED/FAILED` Service lifecycle using a
  fake executor; and
- precise `PUMP_MOTION_TIMEOUT` and `PUMP_HOME_SWITCH_UNEXPECTED` execution
  failure codes.

Production `main.cpp` and `NoMotionDispatcher` remain unchanged. The Service
is not connected to Serial, pins, a motor driver, or physical behavior, and the
real `QUERY_COMMAND` path can still return only `UNKNOWN`.

Latest verified results:

- focused P1 contract tests: `5/5 passed`;
- complete native suite: `68/68 passed`;
- warning-enabled native suite: `68/68 passed`;
- Mega 2560 build: successful;
- flash: `22,358 / 253,952 bytes`;
- static RAM: `1,675 / 8,192 bytes`; and
- `git diff --check`: passed.

Compared with the preceding checkpoint, this adds 72 bytes of flash and 10
bytes of static RAM. The next boundary is independent review, followed by
confirmation of P1 pins, home-switch electrical semantics, tested pulse timing,
`ENA` behavior, initial trusted-position policy, and the safe manually prepared
fluidic route before any production adapter, upload, or physical test.

The user explicitly approved `PUMP_MOVE_ABSOLUTE_STEPS` as the first no-motion
Service-mode contract before this implementation was created. That approval
does not authorize production Serial integration, an actuator adapter, upload,
or physical execution.

## Latest firmware milestone

The no-motion P1 command boundary is now hardened with:

- disjoint request-rejection and execution-failure error categories;
- detailed cache-store outcomes so only a real non-terminal conflict maps to
  `CONTROLLER_BUSY`;
- side-effect-free preflight before `ACCEPTED` and `STARTED`;
- explicit handling of every declared executor outcome and fail-closed handling
  of an invalid outcome without inventing a physical cause;
- `PUMP_HOME_SWITCH_UNEXPECTED` restricted to unexpected activation after the
  physical execution boundary; and
- `0..20500` documented as a representable coordinate envelope, not a validated
  safe physical working range.

Latest verified results:

- focused cache and P1 boundary tests: `20/20 passed`;
- complete native suite: `72/72 passed`;
- warning-enabled native suite: `72/72 passed`;
- Mega 2560 build: successful;
- flash: `22,358 / 253,952 bytes`;
- static RAM: `1,675 / 8,192 bytes`; and
- `git diff --check`: passed.

Flash, SRAM, cache sizes, output capacity, and the production stack path are
unchanged from the preceding contract checkpoint. Production `main.cpp` and
`NoMotionDispatcher` remain unchanged and disconnected from the Service.

## Approved phase and next phase boundary

The user approved the focused P1 Arduino GPIO and production Serial/lifecycle
software integration. That checkpoint is implemented and reviewed in software.
No firmware upload, Serial Monitor use, physical P1 execution, PR, or merge to
`main` is authorized by that approval. The next boundary is an explicit
physical integration/test authorization or a separately scoped software
checkpoint for another actuator.

## Current limitations and unresolved physical decisions

- Incoming production P1 `PUMP_HOME` and `PUMP_MOVE_ABSOLUTE_STEPS` handling,
  Serial lifecycle dispatch, runtime cache population, and the Arduino P1
  adapter are implemented in the Mega build. Other actuator runtimes remain
  unintegrated.
- EEPROM fail-closed recovery/provisioning remains unresolved.
- No firmware upload or physical execution is authorized by the current P1
  software checkpoint.
- Unconfirmed pin, polarity, direction, angle, step, calibration, homing, and
  safe-route decisions must be obtained from the user and canonical hardware
  documentation.
- Firmware has not been uploaded, no Serial monitor has been opened against the
  controller, and no physical test has been performed in the current phase.

## Governance alignment work

Governance alignment is pushed on `codex/align-development-governance` in the
UI, backend, and firmware repositories. No PR or merge has been performed.
