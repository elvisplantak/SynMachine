# LabForge Current Development State

- Checkpoint date: 2026-08-02
- Development phase: no-motion LABFORGE/1 software foundations
- Primary implementation agent: Codex
- Independent reviewer: ChatGPT

## Repository checkpoints

### UI

- Branch: `codex/harden-env-ignore-rules-2026-07-30`
- HEAD: `54e6f0ff4747d13b5312c07f8e1e044ef4c571ee`
- Working tree was clean when governance alignment started.

### Backend

- Branch: `codex/labforge-v1-message-models-parser-contract-fixes`
- HEAD: `7f8697c6b3ea02f1ff9450faa2d55149ace2f180`
- Working tree was clean when governance alignment started.
- LABFORGE/1 message models and parser contract fixes are pushed at this
  checkpoint.

### Firmware

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

## Latest firmware milestone

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

The next no-motion firmware milestone is `QUERY_COMMAND` / `COMMAND_STATUS`
with a bounded volatile command-status cache shell and no command dispatch.

## Approved phase and next phase boundary

Codex may autonomously complete the current no-motion LABFORGE/1 software
foundation phase, including handshake/session corrections and subsequent
harmless protocol-shell milestones. Codex must obtain concise user approval
before entering actuator implementation, firmware upload, or physical testing.

Expected no-motion progression:

1. finish handshake/session foundation;
2. implement harmless status-query responses;
3. implement remaining bounded protocol-error/session shell behavior;
4. implement bounded command-status cache and lifecycle foundations without
   actuator dispatch; and
5. review the complete no-motion boundary before actuator work.

## Current limitations and unresolved physical decisions

- `QUERY_COMMAND`, command-status responses, command cache, and command dispatch
  are not yet implemented in firmware.
- EEPROM fail-closed recovery/provisioning remains unresolved.
- No actuator command or physical behavior is authorized by current protocol
  work.
- Unconfirmed pin, polarity, direction, angle, step, calibration, homing, and
  safe-route decisions must be obtained from the user and canonical hardware
  documentation.
- Firmware has not been uploaded, no Serial monitor has been opened against the
  controller, and no physical test has been performed in the current phase.

## Governance alignment work

Governance alignment is pushed on `codex/align-development-governance` in the
UI, backend, and firmware repositories. No PR or merge has been performed.
