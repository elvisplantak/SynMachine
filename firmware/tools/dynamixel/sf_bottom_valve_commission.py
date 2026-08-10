#!/usr/bin/env python3
"""Commissioning utility for SF_BOTTOM_VALVE over U2D2.

Identification and inspection commands are read-only. The separately guarded
motion command performs one bounded out-and-back test and always disables
torque when it exits.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time
from dataclasses import dataclass
from typing import Any


PROTOCOL_VERSION = 2.0
EXPECTED_MODEL_NUMBER = 1060
DEFAULT_BAUD_RATE = 57_600
POSITION_UNITS_PER_DEGREE = 4_096 / 360.0
POSITION_TOLERANCE = 20
TEST_PROFILE_VELOCITY = 20
TEST_PROFILE_ACCELERATION = 1
MOTION_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True)
class Register:
    address: int
    size: int


REGISTERS = {
    "model_number": Register(0, 2),
    "firmware_version": Register(6, 1),
    "id": Register(7, 1),
    "baud_rate_code": Register(8, 1),
    "operating_mode": Register(11, 1),
    "protocol_type": Register(13, 1),
    "velocity_limit": Register(44, 4),
    "max_position_limit": Register(48, 4),
    "min_position_limit": Register(52, 4),
    "torque_enable": Register(64, 1),
    "hardware_error_status": Register(70, 1),
    "profile_acceleration": Register(108, 4),
    "profile_velocity": Register(112, 4),
    "goal_position": Register(116, 4),
    "present_position": Register(132, 4),
    "present_input_voltage": Register(144, 2),
    "present_temperature": Register(146, 1),
}


def load_sdk() -> tuple[Any, Any, int]:
    try:
        from dynamixel_sdk import COMM_SUCCESS, PacketHandler, PortHandler
    except ImportError as exc:
        raise SystemExit(
            "Missing dependency 'dynamixel_sdk'. Follow "
            "tools/dynamixel/README.md to create the virtual environment."
        ) from exc
    return PortHandler, PacketHandler, COMM_SUCCESS


def serial_candidates() -> list[str]:
    patterns = (
        "/dev/serial/by-id/*",
        "/dev/ttyUSB*",
        "/dev/ttyACM*",
    )
    candidates: set[str] = set()
    for pattern in patterns:
        candidates.update(glob.glob(pattern))
    return sorted(candidates)


def list_ports() -> int:
    candidates = serial_candidates()
    if not candidates:
        print("No candidate serial devices found.")
        print("Connect U2D2 and run this command again.")
        return 1

    print("Candidate serial devices:")
    for path in candidates:
        real_path = os.path.realpath(path)
        suffix = "" if real_path == path else f" -> {real_path}"
        print(f"  {path}{suffix}")
    print("\nPrefer a /dev/serial/by-id/... path when available.")
    return 0


def open_bus(port_name: str, baud_rate: int) -> tuple[Any, Any, int]:
    PortHandler, PacketHandler, comm_success = load_sdk()
    port = PortHandler(port_name)
    packet = PacketHandler(PROTOCOL_VERSION)

    try:
        if not port.openPort():
            raise SystemExit(f"Failed to open serial port: {port_name}")
        if not port.setBaudRate(baud_rate):
            port.closePort()
            raise SystemExit(f"Failed to set baud rate {baud_rate} on {port_name}")
    except OSError as exc:
        raise SystemExit(
            f"Cannot open serial port {port_name}: {exc}. "
            "Run list-ports again and use the exact reported path."
        ) from exc
    return port, packet, comm_success


def ping(packet: Any, port: Any, device_id: int, comm_success: int) -> int | None:
    model_number, comm_result, device_error = packet.ping(port, device_id)
    if comm_result != comm_success or device_error != 0:
        return None
    return int(model_number)


def scan_bus(port_name: str, baud_rate: int, confirmed: bool) -> int:
    if not confirmed:
        raise SystemExit(
            "Refusing scan without --confirm-read-only-scan. "
            "Power-cycle the single expected actuator first so torque is off."
        )

    port, packet, comm_success = open_bus(port_name, baud_rate)
    found: list[dict[str, int]] = []
    try:
        print(
            f"Read-only Protocol 2.0 scan on {port_name} at {baud_rate} baud...",
            flush=True,
        )
        for device_id in range(253):
            model_number = ping(packet, port, device_id, comm_success)
            if model_number is not None:
                found.append({"id": device_id, "model_number": model_number})
                print(f"Found ID {device_id}, model {model_number}")
    finally:
        port.closePort()

    if not found:
        print("No DYNAMIXEL devices responded.")
        return 2

    print(json.dumps({"port": port_name, "baud": baud_rate, "devices": found}, indent=2))
    return 0


def read_register(
    packet: Any,
    port: Any,
    device_id: int,
    register: Register,
    comm_success: int,
) -> int:
    readers = {
        1: packet.read1ByteTxRx,
        2: packet.read2ByteTxRx,
        4: packet.read4ByteTxRx,
    }
    value, comm_result, device_error = readers[register.size](
        port, device_id, register.address
    )
    if comm_result != comm_success:
        raise RuntimeError(packet.getTxRxResult(comm_result))
    if device_error != 0:
        raise RuntimeError(packet.getRxPacketError(device_error))
    return int(value)


def write_register(
    packet: Any,
    port: Any,
    device_id: int,
    register: Register,
    value: int,
    comm_success: int,
) -> None:
    writers = {
        1: packet.write1ByteTxRx,
        2: packet.write2ByteTxRx,
        4: packet.write4ByteTxRx,
    }
    comm_result, device_error = writers[register.size](
        port, device_id, register.address, value
    )
    if comm_result != comm_success:
        raise RuntimeError(packet.getTxRxResult(comm_result))
    if device_error != 0:
        raise RuntimeError(packet.getRxPacketError(device_error))


def wait_for_position(
    packet: Any,
    port: Any,
    device_id: int,
    target: int,
    comm_success: int,
) -> int:
    deadline = time.monotonic() + MOTION_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        hardware_error = read_register(
            packet, port, device_id, REGISTERS["hardware_error_status"], comm_success
        )
        if hardware_error != 0:
            raise RuntimeError(f"hardware_error_status={hardware_error}")

        present = read_register(
            packet, port, device_id, REGISTERS["present_position"], comm_success
        )
        if abs(present - target) <= POSITION_TOLERANCE:
            return present
        time.sleep(0.05)
    raise RuntimeError(
        f"motion timeout: target={target}, last_present_position={present}"
    )


def test_bounded_out_and_back(
    port_name: str,
    baud_rate: int,
    device_id: int,
    confirmed: bool,
    direction: str,
    trim_degrees: float,
    out_degrees: float,
    back_degrees: float,
    base_position: int | None,
    pause_seconds: float,
) -> int:
    if not confirmed:
        raise SystemExit(
            "Refusing motion without --confirm-clear-path-and-motion."
        )
    if not 0.0 <= trim_degrees <= 15.0:
        raise SystemExit("--trim-degrees must be between 0 and 15")
    if not 0.0 < out_degrees <= 120.0:
        raise SystemExit("--out-degrees must be greater than 0 and at most 120")
    if not 0.0 < back_degrees <= 120.0:
        raise SystemExit("--back-degrees must be greater than 0 and at most 120")
    if not 0.0 <= pause_seconds <= 5.0:
        raise SystemExit("--pause-seconds must be between 0 and 5")
    if base_position is not None and trim_degrees != 0.0:
        raise SystemExit("--base-position and --trim-degrees cannot be combined")

    port, packet, comm_success = open_bus(port_name, baud_rate)
    torque_enabled = False
    original_profile_velocity: int | None = None
    original_profile_acceleration: int | None = None
    try:
        model_number = ping(packet, port, device_id, comm_success)
        if model_number != EXPECTED_MODEL_NUMBER:
            raise RuntimeError(
                f"expected model {EXPECTED_MODEL_NUMBER}, received {model_number}"
            )

        operating_mode = read_register(
            packet, port, device_id, REGISTERS["operating_mode"], comm_success
        )
        torque = read_register(
            packet, port, device_id, REGISTERS["torque_enable"], comm_success
        )
        hardware_error = read_register(
            packet, port, device_id, REGISTERS["hardware_error_status"], comm_success
        )
        start = read_register(
            packet, port, device_id, REGISTERS["present_position"], comm_success
        )
        minimum = read_register(
            packet, port, device_id, REGISTERS["min_position_limit"], comm_success
        )
        maximum = read_register(
            packet, port, device_id, REGISTERS["max_position_limit"], comm_success
        )
        original_profile_acceleration = read_register(
            packet, port, device_id, REGISTERS["profile_acceleration"], comm_success
        )
        original_profile_velocity = read_register(
            packet, port, device_id, REGISTERS["profile_velocity"], comm_success
        )

        if operating_mode != 3:
            raise RuntimeError(f"operating_mode must be 3, received {operating_mode}")
        if torque != 0:
            raise RuntimeError("torque must be disabled before the test")
        if hardware_error != 0:
            raise RuntimeError(f"hardware_error_status={hardware_error}")

        direction_sign = 1 if direction == "positive" else -1
        trim_units = round(trim_degrees * POSITION_UNITS_PER_DEGREE)
        closed = (
            base_position
            if base_position is not None
            else start + direction_sign * trim_units
        )
        if closed < minimum or closed > maximum:
            raise RuntimeError(
                f"trim target {closed} is outside {minimum}..{maximum}"
            )

        out_units = round(out_degrees * POSITION_UNITS_PER_DEGREE)
        back_units = round(back_degrees * POSITION_UNITS_PER_DEGREE)
        target = closed + direction_sign * out_units
        if target < minimum or target > maximum:
            raise RuntimeError(
                f"outward target {target} is outside {minimum}..{maximum}"
            )
        final_target = target - direction_sign * back_units
        if final_target < minimum or final_target > maximum:
            raise RuntimeError(
                f"return target {final_target} is outside {minimum}..{maximum}"
            )

        print("SF_BOTTOM_VALVE bounded out-and-back test", flush=True)
        print(
            f"Captured start={start}; trim={trim_degrees} degrees "
            f"{direction}; base={closed}; outward {out_degrees} degrees "
            f"to {target}; return {back_degrees} degrees to {final_target}",
            flush=True,
        )
        print(
            f"Temporary profile: velocity={TEST_PROFILE_VELOCITY}, "
            f"acceleration={TEST_PROFILE_ACCELERATION}",
            flush=True,
        )

        write_register(
            packet,
            port,
            device_id,
            REGISTERS["profile_acceleration"],
            TEST_PROFILE_ACCELERATION,
            comm_success,
        )
        write_register(
            packet,
            port,
            device_id,
            REGISTERS["profile_velocity"],
            TEST_PROFILE_VELOCITY,
            comm_success,
        )
        # Prevent motion toward a stale Goal Position when torque is enabled.
        write_register(
            packet, port, device_id, REGISTERS["goal_position"], start, comm_success
        )
        write_register(
            packet, port, device_id, REGISTERS["torque_enable"], 1, comm_success
        )
        torque_enabled = True

        if closed != start:
            print(f"Trimming CLOSED position: {start} -> {closed}...", flush=True)
            write_register(
                packet,
                port,
                device_id,
                REGISTERS["goal_position"],
                closed,
                comm_success,
            )
            trimmed_position = wait_for_position(
                packet, port, device_id, closed, comm_success
            )
            print(f"New CLOSED reached at {trimmed_position}", flush=True)

        print(f"Moving outward {out_degrees} degrees...", flush=True)
        write_register(
            packet, port, device_id, REGISTERS["goal_position"], target, comm_success
        )
        open_position = wait_for_position(
            packet, port, device_id, target, comm_success
        )
        print(
            f"Outward target reached at {open_position}; "
            f"pause {pause_seconds} seconds",
            flush=True,
        )
        time.sleep(pause_seconds)

        print(f"Returning {back_degrees} degrees...", flush=True)
        write_register(
            packet,
            port,
            device_id,
            REGISTERS["goal_position"],
            final_target,
            comm_success,
        )
        closed_position = wait_for_position(
            packet, port, device_id, final_target, comm_success
        )
        print(f"Return target reached at {closed_position}", flush=True)
        print("TEST PASSED", flush=True)
        return 0
    except (RuntimeError, KeyboardInterrupt) as exc:
        print(f"TEST ABORTED: {exc}", file=sys.stderr, flush=True)
        return 6
    finally:
        if torque_enabled:
            try:
                write_register(
                    packet,
                    port,
                    device_id,
                    REGISTERS["torque_enable"],
                    0,
                    comm_success,
                )
                print("Torque disabled", flush=True)
            except RuntimeError as exc:
                print(f"WARNING: failed to disable torque: {exc}", file=sys.stderr)
        if original_profile_acceleration is not None:
            try:
                write_register(
                    packet,
                    port,
                    device_id,
                    REGISTERS["profile_acceleration"],
                    original_profile_acceleration,
                    comm_success,
                )
            except RuntimeError as exc:
                print(f"WARNING: failed to restore acceleration: {exc}", file=sys.stderr)
        if original_profile_velocity is not None:
            try:
                write_register(
                    packet,
                    port,
                    device_id,
                    REGISTERS["profile_velocity"],
                    original_profile_velocity,
                    comm_success,
                )
            except RuntimeError as exc:
                print(f"WARNING: failed to restore velocity: {exc}", file=sys.stderr)
        port.closePort()


def trim_position(
    port_name: str,
    baud_rate: int,
    device_id: int,
    degrees: float,
    direction: str,
    confirmed: bool,
) -> int:
    if not confirmed:
        raise SystemExit("Refusing motion without --confirm-clear-path-and-motion.")
    if not 0.0 < degrees <= 15.0:
        raise SystemExit("--degrees must be greater than 0 and at most 15")

    port, packet, comm_success = open_bus(port_name, baud_rate)
    torque_enabled = False
    original_profile_velocity: int | None = None
    original_profile_acceleration: int | None = None
    try:
        model_number = ping(packet, port, device_id, comm_success)
        if model_number != EXPECTED_MODEL_NUMBER:
            raise RuntimeError(
                f"expected model {EXPECTED_MODEL_NUMBER}, received {model_number}"
            )
        operating_mode = read_register(
            packet, port, device_id, REGISTERS["operating_mode"], comm_success
        )
        torque = read_register(
            packet, port, device_id, REGISTERS["torque_enable"], comm_success
        )
        hardware_error = read_register(
            packet, port, device_id, REGISTERS["hardware_error_status"], comm_success
        )
        start = read_register(
            packet, port, device_id, REGISTERS["present_position"], comm_success
        )
        minimum = read_register(
            packet, port, device_id, REGISTERS["min_position_limit"], comm_success
        )
        maximum = read_register(
            packet, port, device_id, REGISTERS["max_position_limit"], comm_success
        )
        original_profile_acceleration = read_register(
            packet, port, device_id, REGISTERS["profile_acceleration"], comm_success
        )
        original_profile_velocity = read_register(
            packet, port, device_id, REGISTERS["profile_velocity"], comm_success
        )
        if operating_mode != 3 or torque != 0 or hardware_error != 0:
            raise RuntimeError(
                f"unsafe initial state: mode={operating_mode}, torque={torque}, "
                f"hardware_error={hardware_error}"
            )

        direction_sign = 1 if direction == "positive" else -1
        target = start + direction_sign * round(degrees * POSITION_UNITS_PER_DEGREE)
        if target < minimum or target > maximum:
            raise RuntimeError(f"trim target {target} is outside {minimum}..{maximum}")

        print(
            f"Trimming {degrees} degrees {direction}: {start} -> {target}", flush=True
        )
        write_register(
            packet, port, device_id, REGISTERS["profile_acceleration"],
            TEST_PROFILE_ACCELERATION, comm_success
        )
        write_register(
            packet, port, device_id, REGISTERS["profile_velocity"],
            TEST_PROFILE_VELOCITY, comm_success
        )
        write_register(
            packet, port, device_id, REGISTERS["goal_position"], start, comm_success
        )
        write_register(
            packet, port, device_id, REGISTERS["torque_enable"], 1, comm_success
        )
        torque_enabled = True
        write_register(
            packet, port, device_id, REGISTERS["goal_position"], target, comm_success
        )
        reached = wait_for_position(packet, port, device_id, target, comm_success)
        print(f"TRIM COMPLETED at {reached}", flush=True)
        return 0
    except (RuntimeError, KeyboardInterrupt) as exc:
        print(f"TRIM ABORTED: {exc}", file=sys.stderr, flush=True)
        return 6
    finally:
        if torque_enabled:
            try:
                write_register(
                    packet, port, device_id, REGISTERS["torque_enable"], 0,
                    comm_success
                )
                print("Torque disabled", flush=True)
            except RuntimeError as exc:
                print(f"WARNING: failed to disable torque: {exc}", file=sys.stderr)
        if original_profile_acceleration is not None:
            try:
                write_register(
                    packet, port, device_id, REGISTERS["profile_acceleration"],
                    original_profile_acceleration, comm_success
                )
            except RuntimeError as exc:
                print(f"WARNING: failed to restore acceleration: {exc}", file=sys.stderr)
        if original_profile_velocity is not None:
            try:
                write_register(
                    packet, port, device_id, REGISTERS["profile_velocity"],
                    original_profile_velocity, comm_success
                )
            except RuntimeError as exc:
                print(f"WARNING: failed to restore velocity: {exc}", file=sys.stderr)
        port.closePort()


def inspect_device(port_name: str, baud_rate: int, device_id: int) -> int:
    port, packet, comm_success = open_bus(port_name, baud_rate)
    try:
        model_number = ping(packet, port, device_id, comm_success)
        if model_number is None:
            print(
                f"No Protocol 2.0 response from ID {device_id} "
                f"on {port_name} at {baud_rate} baud."
            )
            return 2

        values: dict[str, int] = {}
        for name, register in REGISTERS.items():
            try:
                values[name] = read_register(
                    packet, port, device_id, register, comm_success
                )
            except RuntimeError as exc:
                raise SystemExit(f"Failed reading {name}: {exc}") from exc
    finally:
        port.closePort()

    report = {
        "control_path": "host USB / U2D2 / Protocol 2.0",
        "port": port_name,
        "baud": baud_rate,
        "device": values,
        "derived": {
            "model_matches_xl430_w250": values["model_number"]
            == EXPECTED_MODEL_NUMBER,
            "torque_is_disabled": values["torque_enable"] == 0,
            "hardware_error_is_clear": values["hardware_error_status"] == 0,
            "present_input_voltage_v": values["present_input_voltage"] / 10.0,
            "present_temperature_c": values["present_temperature"],
        },
    }
    print(json.dumps(report, indent=2))

    if values["model_number"] != EXPECTED_MODEL_NUMBER:
        print(
            f"ERROR: expected XL430-W250 model {EXPECTED_MODEL_NUMBER}, "
            f"received {values['model_number']}.",
            file=sys.stderr,
        )
        return 3
    if values["torque_enable"] != 0:
        print(
            "ERROR: torque is enabled. Do not continue to motion commissioning.",
            file=sys.stderr,
        )
        return 4
    if values["hardware_error_status"] != 0:
        print(
            "ERROR: hardware_error_status is not clear.",
            file=sys.stderr,
        )
        return 5
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Guarded U2D2/XL430-W250 commissioning utility"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-ports", help="List candidate serial devices")

    scan = subparsers.add_parser("scan", help="Read-only Protocol 2.0 ID scan")
    scan.add_argument("--port", required=True)
    scan.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE)
    scan.add_argument("--confirm-read-only-scan", action="store_true")

    inspect = subparsers.add_parser("inspect", help="Read the XL430 control table")
    inspect.add_argument("--port", required=True)
    inspect.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE)
    inspect.add_argument("--id", type=int, required=True, choices=range(253))

    motion = subparsers.add_parser(
        "test-motion", help="One guarded bounded out-and-back motion test"
    )
    motion.add_argument("--port", required=True)
    motion.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE)
    motion.add_argument("--id", type=int, required=True, choices=range(253))
    motion.add_argument(
        "--direction", choices=("positive", "negative"), default="positive"
    )
    motion.add_argument("--trim-degrees", type=float, default=0.0)
    motion.add_argument("--out-degrees", type=float, default=90.0)
    motion.add_argument("--back-degrees", type=float, default=90.0)
    motion.add_argument("--base-position", type=int)
    motion.add_argument("--pause-seconds", type=float, default=1.0)
    motion.add_argument("--confirm-clear-path-and-motion", action="store_true")

    trim = subparsers.add_parser("trim", help="One guarded calibration trim")
    trim.add_argument("--port", required=True)
    trim.add_argument("--baud", type=int, default=DEFAULT_BAUD_RATE)
    trim.add_argument("--id", type=int, required=True, choices=range(253))
    trim.add_argument("--degrees", type=float, required=True)
    trim.add_argument(
        "--direction", choices=("positive", "negative"), required=True
    )
    trim.add_argument("--confirm-clear-path-and-motion", action="store_true")

    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "list-ports":
        return list_ports()
    if args.command == "scan":
        return scan_bus(args.port, args.baud, args.confirm_read_only_scan)
    if args.command == "inspect":
        return inspect_device(args.port, args.baud, args.id)
    if args.command == "test-motion":
        return test_bounded_out_and_back(
            args.port,
            args.baud,
            args.id,
            args.confirm_clear_path_and_motion,
            args.direction,
            args.trim_degrees,
            args.out_degrees,
            args.back_degrees,
            args.base_position,
            args.pause_seconds,
        )
    if args.command == "trim":
        return trim_position(
            args.port,
            args.baud,
            args.id,
            args.degrees,
            args.direction,
            args.confirm_clear_path_and_motion,
        )
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
