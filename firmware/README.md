# LabForge firmware

This repository contains LabForge Arduino firmware work and historical recovery artifacts. Its current state is a recovery baseline, not production firmware.

The recovered sketch represents a legacy/test topology and must not be treated as the current approved complete machine topology. No active production sketch or serial command protocol exists yet, and no PlatformIO or Arduino build configuration has been selected. The repository therefore does not claim to compile or control the approved Guided Demo workflow.

The recovered `Pump` and `Valve` implementations were experimentally useful and should be reviewed conservatively rather than rewritten automatically. Files under `recovery/` are intentionally preserved unchanged. `LabForge_recovered.ino` and `LabForge_recovered_clean.ino` contain the same logical text after line-ending normalization, but both remain as historical recovery artifacts.

System-level topology and decisions are documented in `../labforge-ui/LABFORGE_CONTEXT.md`. Confirmed firmware-specific hardware facts are documented in `HARDWARE_CONFIRMATIONS.md`.

## Repository layout

- `recovery/` — untouched historical recovery files
- `HARDWARE_CONFIRMATIONS.md` — confirmed low-level hardware behavior, implications, and pending decisions
- `AGENTS.md` — firmware repository working rules
- `README.md` — repository scope and baseline status
