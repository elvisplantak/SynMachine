"""Manual browser profile: real application/adapters, fake transports only.

Run with `python -m tests.browser_check`. Imports are deferred until live-port
environment settings are rejected. Fixture routes/calibrations are test data.
"""

import argparse
import json
import math
import os
from pathlib import Path
from time import sleep
from uuid import UUID

PROFILE = "labforge-browser-check-fake-v1"
LIVE_PORT_VARIABLES = ("LABFORGE_ARDUINO_PORT", "LABFORGE_SF_BOTTOM_VALVE_PORT")


def require_fake_environment():
    if any(os.environ.get(name, "").strip() for name in LIVE_PORT_VARIABLES):
        raise ValueError("unset LABFORGE_ARDUINO_PORT and LABFORGE_SF_BOTTOM_VALVE_PORT for this fake profile")


def load_bundle(directory):
    """Create an empty fake fixture once; reopen never repairs or resets it."""
    from app.hardware.owned_startup_inspection import OfflineDatabaseBundle
    from app.hardware.owned_transfer_runner import provision_execution
    from app.hardware.sequence_ownership import provision_ownership
    from app.hardware.simulated_lifecycle import provision_lifecycle

    directory = Path(directory).absolute()
    if directory.is_symlink():
        raise ValueError("browser state directory must not be a symlink")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    manifest = directory / "browser-check.json"
    paths = tuple(directory / name for name in ("fake-owner.db", "fake-execution.db", "fake-lifecycle.db"))
    if manifest.is_symlink() or any(path.is_symlink() for path in paths):
        raise ValueError("browser state files must not be symlinks")
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if (type(data) is not dict or set(data) != {"profile", "ownership_id", "execution_id", "lifecycle_id"}
            or data["profile"] != PROFILE):
            raise ValueError("state directory is not this fake browser profile")
        identities = tuple(data[name] for name in ("ownership_id", "execution_id", "lifecycle_id"))
        for identity in identities:
            if type(identity) is not str:
                raise ValueError("invalid fake browser database identity")
            UUID(identity)
        if not all(path.is_file() for path in paths):
            raise ValueError("incomplete browser state; existing data will not be recreated")
    else:
        if any(directory.iterdir()):
            raise ValueError("nonempty state directory without browser marker; nothing will be reset")
        owner = provision_ownership(paths[0])
        execution = provision_execution(paths[1], owner)
        lifecycle = provision_lifecycle(paths[2], execution)
        identities = (owner, execution, lifecycle)
        with manifest.open("x", encoding="utf-8") as stream:
            json.dump(dict(profile=PROFILE, ownership_id=owner,
                execution_id=execution, lifecycle_id=lifecycle), stream)
    return OfflineDatabaseBundle(paths[0], identities[0], paths[1], identities[1], paths[2], identities[2])


def build_profile(directory, *, command_delay=0.15, fault_command=None):
    require_fake_environment()
    if not math.isfinite(command_delay) or not 0 <= command_delay <= 1:
        raise ValueError("fake command delay must be finite and in 0..1 seconds")
    if fault_command is not None and (type(fault_command) is not int or fault_command < 1):
        raise ValueError("fault command must be a positive command number")

    # No imports of app.main/test helpers precede the environment guard above.
    from app.demo.maintenance_plan import MaintenanceKind
    from app.hardware.adapter_application import build_adapter_application_execution
    from app.hardware.arduino_serial import ArduinoSerialConfiguration, ArduinoUnavailableError
    from app.hardware.sf_bottom_valve import REGISTERS
    from app.main import create_app
    from tests.test_adapter_application import ConnectingPort
    from tests.test_command_planning import context
    from tests.test_owned_maintenance import plan
    from tests.test_owned_phase_session import READINESS
    from tests.test_prepared_adapter_execution import FollowingSession
    from tests.test_sf_bottom_valve import configuration

    bundle = load_bundle(directory)

    def port_factory(_):
        port = ConnectingPort()
        sent = 0

        def before_command(_message):
            nonlocal sent
            sent += 1
            sleep(command_delay)
            if sent == fault_command:
                raise ArduinoUnavailableError("Browser-check injected fake transport failure")
        port.before_command = before_command
        return port

    def sf_factory(_):
        session = FollowingSession()
        session.values[REGISTERS["torque_enable"]] = 0
        return session

    def current_context(boot):
        fixture = context()
        if fixture.controller_boot_id != boot:
            raise ValueError("fake browser fixture boot mismatch")
        return fixture

    execution = build_adapter_application_execution(
        bundle, ArduinoSerialConfiguration(port="browser-check-fake-arduino"),
        configuration(port="browser-check-fake-sf"), plan(MaintenanceKind.RECOVERY).calibrations,
        context_factory=current_context, sf_mixer_running=False, column_readiness=READINESS,
        recovery_plan=plan(MaintenanceKind.RECOVERY), flush_plan=plan(MaintenanceKind.FLUSH),
        arduino_port_factory=port_factory, arduino_sleep=lambda _: None,
        sf_session_factory=sf_factory, sf_sleep=lambda _: None,
    )
    return create_app(application_execution=execution), execution


def main(argv=None):
    parser = argparse.ArgumentParser(description="LabForge browser check — fake transports only")
    parser.add_argument("--state-dir", type=Path, default=Path("/tmp/labforge-browser-check"))
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--command-delay", type=float, default=0.15)
    parser.add_argument("--fault-command", type=int)
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("port must be in 1..65535")
    try:
        app, _ = build_profile(args.state_dir, command_delay=args.command_delay,
            fault_command=args.fault_command)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        parser.error(str(error))
    import uvicorn
    print(f"FAKE TRANSPORTS ONLY | state={args.state_dir.absolute()} | pid={os.getpid()}", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, workers=1)


if __name__ == "__main__":
    main()
