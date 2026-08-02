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
- Active branch: `codex/labforge-v1-handshake-session-foundation`
- Active branch base HEAD: `cde95cae8860f8ef0b417d95b0b1ee3d1848031e`
- Handshake/session changes are implemented but not yet committed or pushed.

## Active firmware milestone

Implemented in the working tree:

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
- static RAM: `1,609 / 8,192 bytes`; and
- `git diff --check`: passed.

Independent review identified `678` additional bytes of static RAM:

- global `helloOkFrame`: `256` bytes;
- `SessionState`: `38` bytes; and
- two writer format strings in AVR `.data`: approximately `384` bytes.

The next action inside the current milestone is to optimize `HelloOkWriter`
SRAM use without changing wire output, rerun verification, complete independent
review, then commit and push the handshake/session feature branch.

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

Governance alignment is being prepared on isolated
`codex/align-development-governance` documentation branches/worktrees so the
active firmware handshake working tree remains untouched. No PR or merge has
been performed.
