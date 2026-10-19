# SynMachine backend

SynMachine is the machine's current working name, formerly LabForge. Repository
and package names, paths, `LABFORGE_*` environment variables, `LABFORGE/1`, profile
IDs and persistent state bindings retain their existing technical names. This
presentation change does not alter execution or previously accepted review refs.

This repository will contain the SynMachine backend and domain core. Its current focus is the Guided Demo and the data needed by Demo Log, separate from the sibling UI and firmware repositories.

The backend contains the Guided Demo domain, persistence and execution boundaries.
Arduino pin assignments and low-level Arduino motion remain firmware-owned.

The host-connected `SF_BOTTOM_VALVE` has a production adapter for its confirmed
U2D2/DYNAMIXEL XL430-W250-T path. The adapter is intentionally composed around
the Arduino `HardwareContract`: it owns only the SF valve and delegates all
other hardware commands. Application startup does not construct or run the
physical adapter yet; that belongs to the later complete runtime-composition
checkpoint.

Confirmed defaults are ID `2`, baud `57600`, Protocol `2.0`, `CLOSED=2559`,
`OPEN=3697`, Profile Velocity `20`, and Profile Acceleration `1`. The stable
U2D2 `/dev/serial/by-id/...` path is supplied explicitly through
`SfBottomValveConfiguration`; the backend never guesses a `/dev/ttyUSB*` path.

Enable the local Service API for this actuator by exporting the confirmed,
stable U2D2 path before starting Uvicorn:

```bash
export LABFORGE_SF_BOTTOM_VALVE_PORT=/dev/serial/by-id/usb-FTDI_USB__-__Serial_Converter_FTA2U3CN-if00-port0
uvicorn app.main:app --reload
```

`POST /api/v1/service/sf-bottom-valve` accepts exactly `{"state":"OPEN"}` or
`{"state":"CLOSED"}`. If the environment variable is absent, the endpoint
fails closed with HTTP `503`; importing or starting the backend never opens the
U2D2 or moves the actuator.

## Local setup

Ubuntu with Python 3.12:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Run the checks:

```bash
pytest
ruff check .
```

Start the local API:

```bash
uvicorn app.main:app --reload
```

`GET /health` reports only backend application availability. It does not indicate hardware readiness.

## Offline command preparation

The backend can now lower existing transfer and fraction-collection operation
plans into immutable Arduino command specifications and separate SF-valve/timer
actions, without accessing hardware. See
[the scope, assumptions, tests, and remaining runtime boundary](docs/OFFLINE_COMMAND_PLANNING.md).
This is not connected to the application runtime or an execution endpoint.
