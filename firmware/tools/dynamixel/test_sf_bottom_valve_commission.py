"""Software-only tests for the guarded DYNAMIXEL commissioning utility."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import sf_bottom_valve_commission as commission


class FakePort:
    def __init__(self) -> None:
        self.closed = False

    def closePort(self) -> None:
        self.closed = True


class MotionTest(unittest.TestCase):
    def test_confirmed_bounded_motion_writes_expected_targets_and_disables_torque(
        self,
    ) -> None:
        port = FakePort()
        packet = object()
        writes: list[tuple[str, int]] = []
        values = {
            "operating_mode": 3,
            "torque_enable": 0,
            "hardware_error_status": 0,
            "present_position": 2559,
            "min_position_limit": 0,
            "max_position_limit": 4095,
            "profile_acceleration": 1,
            "profile_velocity": 20,
        }

        def read_register(_packet, _port, _device_id, register, _comm_success):
            name = next(
                name
                for name, candidate in commission.REGISTERS.items()
                if candidate == register
            )
            return values[name]

        def write_register(
            _packet, _port, _device_id, register, value, _comm_success
        ) -> None:
            name = next(
                name
                for name, candidate in commission.REGISTERS.items()
                if candidate == register
            )
            writes.append((name, value))

        with (
            patch.object(commission, "open_bus", return_value=(port, packet, 0)),
            patch.object(
                commission,
                "ping",
                return_value=commission.EXPECTED_MODEL_NUMBER,
            ),
            patch.object(commission, "read_register", side_effect=read_register),
            patch.object(commission, "write_register", side_effect=write_register),
            patch.object(
                commission,
                "wait_for_position",
                side_effect=lambda _packet, _port, _id, target, _comm: target,
            ),
            patch.object(commission.time, "sleep"),
        ):
            result = commission.test_bounded_out_and_back(
                "/dev/fake-u2d2",
                57_600,
                2,
                True,
                "positive",
                0.0,
                100.0,
                100.0,
                2559,
                2.0,
            )

        self.assertEqual(result, 0)
        self.assertTrue(port.closed)
        self.assertIn(("goal_position", 3697), writes)
        self.assertGreaterEqual(writes.count(("goal_position", 2559)), 2)
        self.assertIn(("torque_enable", 1), writes)
        self.assertEqual(writes[-3], ("torque_enable", 0))


if __name__ == "__main__":
    unittest.main()
