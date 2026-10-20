# SynMachine firmware

The Arduino Mega firmware implements the bounded `LABFORGE/1` serial protocol
and low-level commissioned actuator paths. It owns pins, motor directions,
stepping, homing and device execution; high-level routes and procedure execution
belong to the backend.

The [project README](../README.md) describes the current prototype and materials.
[HARDWARE_CONFIRMATIONS.md](HARDWARE_CONFIRMATIONS.md) is canonical for physical
facts. [The serial contract](docs/LABFORGE_SERIAL_PROTOCOL_V1.md) is canonical for
communication semantics. Historical commissioning records remain under `docs/`.

From this directory, with PlatformIO installed:

```bash
pio test -e native
pio run -e megaatmega2560
```

The native tests do not use the machine. The build command compiles for Mega 2560
without upload. No firmware upload, EEPROM operation or physical motion is part
of the repository migration. Installed machine firmware remains unchanged.

Historical `recovery/` artifacts retain their original bytes and remain outside
active build behavior. Access to those artifacts requires the explicit scope in
[AGENTS.md](AGENTS.md); their import does not authorize future modifications.
Current system state is in [../docs/LABFORGE_CURRENT_STATE.md](../docs/LABFORGE_CURRENT_STATE.md).
