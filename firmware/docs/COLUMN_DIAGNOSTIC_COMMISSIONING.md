# Column bottom valve diagnostic commissioning

This isolated Mega 2560 firmware diagnoses the confirmed Column bottom valve
signals without the backend. It uses only confirmed D10 HOME, D12 STEP, D13
DIR, DIR HIGH away from HOME, 889 pulses for the 4-degree CLOSED offset,
20,000 additional pulses from CLOSED to the 94-degree OPEN position, a 20 us
STEP high time, and a 1,000 us rising-edge interval.

The diagnostic target is separate from production firmware:

```text
pio run -e column_diagnostic_mega
```

On boot, STEP and DIR are inputs and no motion occurs. `STATUS` only reports
the raw D10 level as `HIGH` or `LOW` and disarms motion. `DISARM` also disarms.
The bounded motion sequences are:

```text
ARM
MOVE_CLOSED

ARM
MOVE_OPEN
```

`ARM` expires after ten seconds and is consumed by the motion. `MOVE_CLOSED`
without a live arm does nothing. `MOVE_CLOSED` emits exactly 889 pulses and
`MOVE_OPEN` emits exactly 20,000 pulses, both at DIR HIGH. Each move releases
STEP and DIR back to inputs and reports the raw HOME level. `MOVE_OPEN` is
authorized only after the operator has confirmed the mechanism is physically
at the diagnostic CLOSED position.

After the operator has confirmed that `MOVE_OPEN` stopped short of the physical
OPEN position, fine calibration may use `ARM` followed by `NUDGE_OPEN_500`.
Each nudge emits exactly 500 additional DIR HIGH pulses, consumes the arm, and
must be visually confirmed before another nudge is authorized.

If the final 500-pulse OPEN nudge passes the visual target, `ARM` followed by
`NUDGE_HOME_250` emits exactly 250 DIR LOW pulses toward HOME for a bounded
midpoint check. It also consumes the arm and requires visual confirmation.

For the final operator-requested fine adjustment, `ARM` followed by
`NUDGE_OPEN_100` emits exactly 100 DIR HIGH pulses away from HOME. It consumes
the arm and requires a final visual OPEN-position confirmation.

Uploading, opening Serial, powering the driver, arming, and motion are separate
operator-authorized steps. Keep immediate access to motor power. After the
diagnostic, rebuild, upload, and flash-verify `megaatmega2560` before resuming
production Service testing.
