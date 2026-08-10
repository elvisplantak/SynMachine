# SF bottom valve DYNAMIXEL commissioning

This host-side utility commissions the directly connected control path:

`host -> USB -> U2D2 -> DYNAMIXEL XL430-W250-T`

It is intentionally separate from Arduino `src/main.cpp`. Identification and
inspection are read-only. The guarded `test-motion` command is limited to one
bounded out-and-back commissioning move and disables torque when it exits.

## Setup

From the firmware repository:

```bash
python3 -m venv .venv-dynamixel
source .venv-dynamixel/bin/activate
python -m pip install --upgrade pip
python -m pip install -r tools/dynamixel/requirements.txt
```

The virtual environment is local development state and must not be committed.

Run the software-only guard and motion-sequence test without connected hardware:

```bash
PYTHONPATH=tools/dynamixel python -m unittest \
  tools/dynamixel/test_sf_bottom_valve_commission.py
```

## Level 1: identify the U2D2 and actuator

The U2D2 does not power the actuator. Connect the correct TTL port and provide
the separately verified actuator supply. Before scanning, power-cycle the one
expected actuator so its RAM `Torque Enable(64)` returns to the default `0`.

List serial devices:

```bash
python tools/dynamixel/sf_bottom_valve_commission.py list-ports
```

Prefer the stable `/dev/serial/by-id/...` path printed by the command. Do not
silently substitute a different `/dev/ttyUSB*` device after reconnecting.

Run one read-only Protocol 2.0 scan at the expected factory baud rate:

```bash
python tools/dynamixel/sf_bottom_valve_commission.py scan \
  --port /dev/serial/by-id/REPLACE_WITH_THE_ACTUAL_U2D2_PATH \
  --baud 57600 \
  --confirm-read-only-scan
```

Inspect the discovered ID without changing any register:

```bash
python tools/dynamixel/sf_bottom_valve_commission.py inspect \
  --port /dev/serial/by-id/REPLACE_WITH_THE_ACTUAL_U2D2_PATH \
  --baud 57600 \
  --id REPLACE_WITH_DISCOVERED_ID
```

The report includes model number, firmware version, configured ID/baud code,
protocol type, operating mode, torque state, hardware error status, present
position, input voltage, and temperature. Motion commissioning must not begin
unless the model is `1060` (XL430-W250), torque is disabled, and hardware error
status is clear.

## Level 2: guarded bounded out-and-back test

Run only after physically confirming that the current position is CLOSED and
that the complete requested path is clear:

```bash
python tools/dynamixel/sf_bottom_valve_commission.py test-motion \
  --port /dev/serial/by-id/REPLACE_WITH_THE_ACTUAL_U2D2_PATH \
  --baud 57600 \
  --id REPLACE_WITH_DISCOVERED_ID \
  --confirm-clear-path-and-motion
```

The command validates model, mode, torque state, hardware-error state, and
position limits before motion. It temporarily applies a bounded profile,
performs the requested bounded outward and return moves with a bounded dwell,
disables torque, and restores the original profile values.

## Confirmed SF bottom valve calibration

The canonical physical confirmation record is `HARDWARE_CONFIRMATIONS.md`.
The currently confirmed values for DYNAMIXEL ID `2` are:

- `CLOSED = 2559`
- `OPEN = 3697`
- direction from CLOSED to OPEN: positive raw-position direction
- commissioning `Profile Velocity = 20`
- commissioning `Profile Acceleration = 1`

The OPEN position is a visually confirmed nominal 100-degree motion from
CLOSED. These values must be recalibrated after mechanical coupling or horn
adjustment, actuator replacement, or position-reference changes.

## Not implemented yet

- production OPEN/CLOSED commands and persistent position configuration
- reconnect, timeout, or U2D2-disconnect handling for production
- UI/backend integration

Those require a separately reviewed production-integration phase.
