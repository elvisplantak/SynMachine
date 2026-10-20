# SynMachine

SynMachine is an experimental mechatronics platform for laboratory automation.
The project explores mechanical assemblies, electronics, electrical wiring and
power systems, and the software that coordinates them. Its longer-term goal is
a modular platform for executing reproducible laboratory procedures.

## Current prototype

The current prototype is used to develop and test mechatronic integration,
liquid-transfer paths and automated workflows. It has been tested with colored
liquids to observe fluid movement and the execution of programmed procedures.

This development version uses silicone tubing, medical-plastic valves and
medical-plastic syringes. The next material-development stage is planned around
PTFE tubing and valves, plus glass syringes with PTFE plungers, as preparation
for experiments with actual reagents and solvents. Materials will be selected
for the particular chemical procedure.

## Software and controls

- A schematic of the physical machine and command-driven route animation.
- Recipes / Procedure Builder for composing, saving and reviewing supported
  procedures, with immutable saved versions and a separate explicit Start.
- Supported operations include reagent/solvent addition, passive waits,
  reactor-to-SF transfer, SF mixing and settling, SF-to-column transfer and timed
  fraction collection.
- Execution status, command journals and supervised Service controls.
- A fake-device browser profile for software exploration without physical motion.

Volumes in the current demo profile are nominal command inputs. Route animation
shows commanded actions rather than sensor-measured liquid flow. Physical setup
and the applicability of a recipe remain separate from a successful software run.

## Repository layout

| Directory | Responsibility |
| --- | --- |
| [ui/](ui/README.md) | React interface, schematic, recipes and operator interaction |
| [backend/](backend/README.md) | Validation, persistence, routing and orchestration |
| [firmware/](firmware/README.md) | Arduino Mega serial protocol and low-level device execution |
| [docs/](docs/README.md) | Current state, development workflow and migration records |
| [hardware/](hardware/README.md) | Reserved for future mechanical/electrical design documentation |

## Try the software with fake devices

Use Python 3.12 or newer and Node.js supported by Vite 8 (the migrated UI was
verified with Node 24). In one terminal:

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
env -u LABFORGE_ARDUINO_PORT -u LABFORGE_SF_BOTTOM_VALVE_PORT \
  .venv/bin/python -m tests.browser_check \
  --state-dir /tmp/synmachine-browser-preview --port 8000
```

In a second terminal:

```bash
cd ui
npm ci
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open **http://127.0.0.1:5173/**. The backend terminal identifies this profile as
`FAKE TRANSPORTS ONLY`; the interface reports `Test devices`. No connected
Arduino or servo is needed for this profile. Keep fake state separate from any
real-machine state. An existing incompatible state directory is refused rather
than repaired or reset.

Real-device preparation is documented separately in
[backend/docs/LIVE_RECIPES.md](backend/docs/LIVE_RECIPES.md). That explicit path
requires the actual device setup and fresh operator references. Its nominal live
profile currently leaves automatic Recovery/Flush unconfigured; a Stop or fault
can therefore retain mandatory maintenance and block another run.

## Development checks

Run commands from their component directory:

```bash
# ui/
npm test
npm run lint
npm run build

# backend/ with its virtual environment activated
python -m pytest -q
ruff check .

# firmware/ with PlatformIO installed
pio test -e native
pio run -e megaatmega2560
```

The firmware build command compiles only; it does not upload to a device.

## Project history and technical names

This repository combines the former `labforge-ui`, `labforge-backend` and
`labforge-firmware` repositories. Their development histories are retained under
component directories and `history/<component>/...` branches. Author email
metadata was corrected during import; [the migration record](docs/MIGRATION.md)
and [commit maps](docs/history/README.md) preserve traceability to original
reviewed commits. Existing `labforge` package names, `LABFORGE_*` variables,
profile identities and the `LABFORGE/1` protocol remain technical identifiers.

## License

A project license has not yet been selected. Publication and licensing are being
prepared; this repository does not yet grant an open-source license. Third-party
dependencies retain their respective licenses. See
[the publication status](docs/PUBLICATION.md).
