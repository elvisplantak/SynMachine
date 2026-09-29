# V7/V8 HOME input probe

Standalone Arduino Mega diagnostic. Reads only D2/D3 with INPUT_PULLUP and prints
raw levels every 100 ms at 115200 baud. No motion command handler, STEP/DIR output
configuration, or EEPROM access. Not production LABFORGE/1 firmware; do not connect
the production backend.

Build from this directory with `pio run`. Upload only with operator authorization
and confirmed motor supply OFF. Keep Arduino USB powered. Record released inputs,
then manually press/release physical old V7 and old V8 switches separately. Hold
each state long enough to observe several samples. Confirm which input changes
and its released/pressed polarity. Raw samples do not implement debounce or
establish motor position.

Keep motor supply OFF throughout. This program does not disable holding current.
Reconcile HOME mapping and motor directions before restoring verified production
firmware. Every powered motion test requires fresh operator readiness confirmation.
