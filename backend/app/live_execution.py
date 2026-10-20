"""Explicit localhost Recipes entry point. Import/validate/provision opens no device.

Only `serve --connect-real-devices` selects real adapters. It performs the existing
HELLO at startup; actuator work still needs an explicit UI action and fresh input.
No legacy environment composition, automatic HOME, recovery, retry or state repair.
"""

import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
from secrets import token_urlsafe
import stat

from app.hardware.adapter_configuration import AdapterExecutionConfiguration
from app.hardware.owned_startup_inspection import (
    OfflineDatabaseBundle, StartupInspectionError, inspect_owned_startup,
)

MARKER = "labforge-live-recipes-v1"
LEGACY_ENV = ("LABFORGE_ARDUINO_PORT", "LABFORGE_SF_BOTTOM_VALVE_PORT")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _read_json(path):
    if path.stat().st_size > 1_000_000:
        raise ValueError("configuration file is too large")
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique)


def load_profile(path):
    configuration = AdapterExecutionConfiguration.model_validate(_read_json(Path(path)))
    # Stable identities are selected explicitly, never discovered or substituted.
    ports = (configuration.arduino.port, configuration.sf.port)
    if any(not port.startswith("/dev/serial/by-id/") or Path(port).name in ("", ".", "..")
           or "/.." in port for port in ports):
        raise ValueError("live profile requires explicit /dev/serial/by-id device paths")
    if Path(ports[0]).resolve() == Path(ports[1]).resolve():
        raise ValueError("Arduino and SF paths resolve to the same device")
    return configuration


def _digest(configuration):
    payload = json.dumps(configuration.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _paths(directory):
    return tuple(directory / name for name in ("owner.sqlite3", "execution.sqlite3", "lifecycle.sqlite3"))


def provision(directory, configuration):
    """New directory only; explicit provisioning never replaces existing history."""
    from app.hardware.owned_transfer_runner import provision_execution
    from app.hardware.sequence_ownership import provision_ownership
    from app.hardware.simulated_lifecycle import provision_lifecycle

    directory = Path(directory).absolute()
    if directory.is_symlink():
        raise ValueError("live state directory must not be a symlink")
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    owner, execution, lifecycle = _paths(directory)
    # Any partial failure is left intact and rejected on reopening, never repaired.
    oid = provision_ownership(owner)
    eid = provision_execution(execution, oid)
    lid = provision_lifecycle(lifecycle, eid)
    data = dict(profile=MARKER, profile_id=configuration.profile_id,
                profile_digest=_digest(configuration), ownership_id=oid, execution_id=eid, lifecycle_id=lid)
    with (directory / "live-state.json").open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2)
    key = directory / "operator.key"
    fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="ascii") as stream:
        stream.write(token_urlsafe(32) + "\n")
    return load_bundle(directory, configuration)


def load_bundle(directory, configuration):
    directory = Path(directory).absolute()
    paths = _paths(directory)
    marker = directory / "live-state.json"
    if directory.is_symlink() or any(path.is_symlink() for path in (*paths, marker)):
        raise ValueError("live bundle paths must not be symlinks")
    data = _read_json(marker)
    expected = {"profile", "profile_id", "profile_digest", "ownership_id", "execution_id", "lifecycle_id"}
    if (type(data) is not dict or set(data) != expected or data["profile"] != MARKER
        or data["profile_id"] != configuration.profile_id or data["profile_digest"] != _digest(configuration)):
        raise ValueError("live state/profile identity mismatch; no reset or rebind is performed")
    bundle = OfflineDatabaseBundle(paths[0], data["ownership_id"], paths[1], data["execution_id"],
                                   paths[2], data["lifecycle_id"])
    try:
        inspect_owned_startup(bundle)  # Existing schemas, identities and journal bindings, read-only.
    except StartupInspectionError as error:
        raise ValueError("live bundle inspection failed; no file is recreated or repaired") from error
    return bundle


def _credential(directory):
    path = Path(directory) / "operator.key"
    if path.is_symlink():
        raise ValueError("operator credential must not be a symlink")
    details = path.stat()
    if not stat.S_ISREG(details.st_mode) or details.st_uid != os.getuid() or details.st_mode & 0o077:
        raise ValueError("operator credential must be an owner-only regular file (chmod 600)")
    if details.st_size > 1024:
        raise ValueError("operator credential file is too large")
    return path.read_text(encoding="ascii").strip()


def _exclusive_port(configuration):
    """Same adapter framing/timing; exclude a second live Serial process on Linux."""
    import serial
    from app.hardware.arduino_serial import ArduinoUnavailableError

    try:
        return serial.Serial(port=configuration.port, baudrate=configuration.baud_rate,
                             timeout=0.05, write_timeout=1.0, exclusive=True)
    except serial.SerialException as error:
        raise ArduinoUnavailableError("Cannot exclusively open configured Arduino port") from error


def build_live_app(configuration, bundle, *, operator, credential, arduino_port_factory=None,
                   sf_session_factory=None, **test_clocks):
    """Construction is inert. Factory injection is only for offline regressions."""
    if any(os.environ.get(key, "").strip() for key in LEGACY_ENV):
        raise ValueError("unset legacy live-port environment settings before using this entry point")
    from app.hardware.adapter_configuration import build_configured_adapter_application_execution
    from app.hardware.operator_current_input import OperatorCurrentInput
    from app.hardware.sf_bottom_valve import DynamixelSdkSession
    from app.main import create_app

    source = OperatorCurrentInput(operator=operator, credential=credential)
    execution = build_configured_adapter_application_execution(
        bundle, configuration, current_state_provider=source,
        arduino_port_factory=arduino_port_factory or _exclusive_port,
        sf_session_factory=sf_session_factory or DynamixelSdkSession,
        transport_mode="LIVE", **test_clocks,
    )
    return create_app(application_execution=execution), execution


def main(argv=None):
    parser = argparse.ArgumentParser(description="SynMachine explicit live Recipes setup")
    parser.add_argument("action", choices=("validate", "provision", "serve"))
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--operator")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--connect-real-devices", action="store_true")
    args = parser.parse_args(argv)
    try:
        if any(os.environ.get(key, "").strip() for key in LEGACY_ENV):
            raise ValueError("unset legacy live-port environment settings")
        configuration = load_profile(args.profile)
        if args.action == "validate":
            print(f"PROFILE VALID | {configuration.profile_id} | NO DEVICE OPENED")
            print("Maintenance: " + ("configured" if configuration.recovery_plan and configuration.flush_plan
                                     else "not fully configured; unavailable actions remain blocked"))
            return
        if args.state_dir is None:
            raise ValueError("explicit --state-dir required")
        if args.action == "provision":
            bundle = provision(args.state_dir, configuration)
            print(f"LIVE STATE PROVISIONED | {args.state_dir.absolute()} | NO DEVICE OPENED")
            print(f"Operator credential: {args.state_dir.absolute() / 'operator.key'} (keep private)")
            print(json.dumps({key: str(value) for key, value in asdict(bundle).items()}))
            return
        if not args.connect_real_devices or not args.operator or not args.operator.strip():
            raise ValueError("serve requires --connect-real-devices and explicit --operator")
        if not 1 <= args.port <= 65535:
            raise ValueError("port must be in 1..65535")
        # Reject an occupied listener before importing the legacy global app or opening Serial.
        import socket
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", args.port))
        bundle = load_bundle(args.state_dir, configuration)
        app, _ = build_live_app(configuration, bundle, operator=args.operator,
                                credential=_credential(args.state_dir))
    except (ValueError, OSError) as error:
        parser.error(str(error))
    import uvicorn
    print(f"REAL DEVICES | profile={configuration.profile_id} | state={args.state_dir.absolute()}", flush=True)
    print("Startup opens Arduino for HELLO only; no automatic HOME or procedure.", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=args.port, workers=1)


if __name__ == "__main__":
    main()
