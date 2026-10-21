"""Pump HOME telemetry is optional raw input, never a position reference."""

import pytest
from pydantic import ValidationError

from app.protocol.models import Status, parse_message
from tests.test_protocol_models import QUERY

STATUS = {**QUERY, "type": "STATUS", "controller_state": "IDLE",
          "software_state_trust": "TRUSTED", "active_operation_command_id": None}


def test_older_firmware_status_remains_unsupported_not_false():
    message = parse_message(STATUS)
    assert isinstance(message, Status)
    assert message.p1_home_active is None and message.p2_home_active is None


@pytest.mark.parametrize("one,two", [(False, False), (False, True), (True, False), (True, True)])
def test_raw_home_booleans_do_not_claim_pump_position(one, two):
    message = parse_message({**STATUS, "p1_home_active": one, "p2_home_active": two})
    assert message.p1_home_active is one and message.p2_home_active is two
    assert not hasattr(message, "p1_position_steps")
    assert message.active_operation_command_id is None


@pytest.mark.parametrize("field", ["p1_home_active", "p2_home_active"])
@pytest.mark.parametrize("invalid", [0, 1, "true", "false", []])
def test_home_telemetry_cannot_coerce_integers_or_strings(field, invalid):
    with pytest.raises(ValidationError):
        parse_message({**STATUS, field: invalid})
