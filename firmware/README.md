# SynMachine firmware

SynMachine is the machine's current working name, formerly LabForge. Repository
and package names, paths, `LABFORGE_*` environment variables, `LABFORGE/1`, profile
IDs and persistent state bindings retain their existing technical names. This
presentation change does not alter execution or previously accepted review refs.

This repository contains the active SynMachine Arduino firmware foundations and
historical recovery artifacts. The active firmware remains a no-motion
LABFORGE/1 protocol foundation, not production actuator firmware.

Historical sketches represent legacy/test topology and must not be treated as
the current approved complete machine topology. PlatformIO native and Arduino
Mega 2560 builds exist for the active bounded protocol foundation. The
repository does not claim to control the approved Guided Demo workflow.

Protected historical artifacts remain outside active production behavior and
must not be accessed without the explicit authorization required by
`AGENTS.md`.

System-level topology and decisions are documented in `../labforge-ui/LABFORGE_CONTEXT.md`. Confirmed firmware-specific hardware facts are documented in `HARDWARE_CONFIRMATIONS.md`.

The approved, partially implemented serial communication contract is
documented in
[`docs/LABFORGE_SERIAL_PROTOCOL_V1.md`](docs/LABFORGE_SERIAL_PROTOCOL_V1.md).
The current production entry point provides no actuator side effects.

## Repository layout

- `HARDWARE_CONFIRMATIONS.md` — confirmed low-level hardware behavior, implications, and pending decisions
- `AGENTS.md` — firmware repository working rules
- `README.md` — repository scope and baseline status
- `docs/PIN_DISCOVERY_COMMISSIONING.md` — isolated V7/V8 commissioning preparation; no upload or execution authorization
- `docs/HARDWARE_COMMISSIONING_PLAN.md` — staged electrical, motion, homing, route, liquid, and fault commissioning gates
