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

## Latest firmware milestone

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

The next no-motion firmware milestone is harmless `QUERY_STATUS` / `STATUS`
response behavior, including bounded deterministic serialization, session and
boot-ID validation, protocol documentation, and native/Mega verification.

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

- `PROTOCOL_ERROR`, status/query responses, command cache, and command dispatch
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
