from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.protocol.models import UINT32_MAX, parse_message

NONCE = "123e4567-e89b-12d3-a456-426614174000"
OPERATION_ID = "323e4567-e89b-12d3-a456-426614174002"
REQUEST_ID = "423e4567-e89b-12d3-a456-426614174003"
BASE = {"protocol": "LABFORGE/1", "backend_session_nonce": NONCE, "controller_boot_id": 1}
COMMAND = {**BASE, "phase_execution_id": "phase-1", "operation_command_id": OPERATION_ID}
QUERY = {**BASE, "request_id": REQUEST_ID}


MINIMAL_MESSAGES = [
    {"protocol": "LABFORGE/1", "type": "HELLO", "backend_session_nonce": NONCE},
    {
        **BASE,
        "type": "HELLO_OK",
        "controller_state": "IDLE",
        "software_state_trust": "TRUSTED",
        "capabilities": [],
    },
    {**COMMAND, "type": "COMMAND", "command": "FUTURE_COMMAND", "arguments": {}},
    {**COMMAND, "type": "REJECTED", "error_code": "CONTROLLER_BUSY"},
    {**COMMAND, "type": "ACCEPTED"},
    {**COMMAND, "type": "STARTED"},
    {**COMMAND, "type": "COMPLETED", "result": {}},
    {**COMMAND, "type": "FAILED", "error_code": "ACTUATOR_FAILURE", "execution_started": True},
    {**QUERY, "type": "QUERY_STATUS"},
    {
        **QUERY,
        "type": "STATUS",
        "controller_state": "IDLE",
        "software_state_trust": "TRUSTED",
        "active_operation_command_id": None,
    },
    {**QUERY, "type": "QUERY_COMMAND", "operation_command_id": OPERATION_ID},
    {
        **QUERY,
        "type": "COMMAND_STATUS",
        "operation_command_id": OPERATION_ID,
        "command_state": "UNKNOWN",
    },
    {"protocol": "LABFORGE/1", "type": "PROTOCOL_ERROR", "error_code": "MALFORMED_MESSAGE"},
]


@pytest.mark.parametrize("message", MINIMAL_MESSAGES, ids=lambda item: str(item["type"]))
def test_every_approved_minimal_message(message: dict[str, object]) -> None:
    assert parse_message(message).type == message["type"]


@pytest.mark.parametrize(
    "change",
    [
        {"unexpected": True},
        {"protocol": "LABFORGE/2"},
        {"backend_session_nonce": NONCE.upper()},
        {"backend_session_nonce": "not-a-uuid"},
    ],
)
def test_rejects_unknown_version_and_noncanonical_identifiers(change: dict[str, object]) -> None:
    message = deepcopy(MINIMAL_MESSAGES[0])
    message.update(change)
    with pytest.raises(ValidationError):
        parse_message(message)


def test_rejects_missing_required_field() -> None:
    message = deepcopy(MINIMAL_MESSAGES[2])
    del message["arguments"]
    with pytest.raises(ValidationError):
        parse_message(message)


@pytest.mark.parametrize("boot_id", [-1, UINT32_MAX + 1, True, 1.5])
def test_controller_boot_id_bounds_and_strict_integer(boot_id: object) -> None:
    message = {**MINIMAL_MESSAGES[8], "controller_boot_id": boot_id}
    with pytest.raises(ValidationError):
        parse_message(message)


@pytest.mark.parametrize("boot_id", [0, UINT32_MAX])
def test_controller_boot_id_accepts_unsigned_boundaries(boot_id: int) -> None:
    message = {**MINIMAL_MESSAGES[8], "controller_boot_id": boot_id}
    assert parse_message(message).controller_boot_id == boot_id


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("phase_execution_id", "bad space"),
        ("command", "lowercase"),
        ("command", "A" * 33),
    ],
)
def test_ascii_identifier_character_and_length_rules(field: str, value: str) -> None:
    message = deepcopy(MINIMAL_MESSAGES[2])
    message[field] = value
    with pytest.raises(ValidationError):
        parse_message(message)


def test_utf8_string_byte_boundary() -> None:
    message = {**MINIMAL_MESSAGES[2], "arguments": {"text": "ž" * 32}}
    assert parse_message(message).arguments["text"] == "ž" * 32
    message["arguments"] = {"text": "ž" * 33}
    with pytest.raises(ValidationError):
        parse_message(message)


def test_human_message_utf8_byte_limit() -> None:
    message = {**MINIMAL_MESSAGES[3], "message": "ž" * 48}
    assert parse_message(message).message == "ž" * 48
    message["message"] = "ž" * 49
    with pytest.raises(ValidationError):
        parse_message(message)


def test_capability_count_and_value_bounds() -> None:
    message = {**MINIMAL_MESSAGES[1], "capabilities": [f"CAP_{index}" for index in range(8)]}
    assert len(parse_message(message).capabilities) == 8
    message["capabilities"] = [f"CAP_{index}" for index in range(9)]
    with pytest.raises(ValidationError):
        parse_message(message)
    message["capabilities"] = ["bad"]
    with pytest.raises(ValidationError):
        parse_message(message)


@pytest.mark.parametrize(
    "arguments",
    [
        {"": 1},
        {"é": 1},
        {"x" * 25: 1},
        {str(index): index for index in range(9)},
        {"nested": {}},
        {"nested": []},
        {"null": None},
        {"float": 1.5},
    ],
)
def test_arguments_reject_invalid_keys_collections_nesting_and_scalars(arguments: object) -> None:
    with pytest.raises(ValidationError):
        parse_message({**MINIMAL_MESSAGES[2], "arguments": arguments})


def test_result_uses_same_structural_bounds() -> None:
    with pytest.raises(ValidationError):
        parse_message({**MINIMAL_MESSAGES[6], "result": {"nested": [1]}})


@pytest.mark.parametrize("field", ["message", "result"])
def test_optional_fields_must_be_omitted_instead_of_null(field: str) -> None:
    message = deepcopy(MINIMAL_MESSAGES[7])
    message[field] = None
    with pytest.raises(ValidationError):
        parse_message(message)


def test_failed_result_requires_a_future_command_schema() -> None:
    with pytest.raises(ValidationError):
        parse_message({**MINIMAL_MESSAGES[7], "result": {}})


@pytest.mark.parametrize("state", ["BOGUS", "idle"])
def test_rejects_invalid_enum_values(state: str) -> None:
    message = {**MINIMAL_MESSAGES[9], "controller_state": state}
    with pytest.raises(ValidationError):
        parse_message(message)


@pytest.mark.parametrize("message_index", [1, 9], ids=["HELLO_OK", "STATUS"])
def test_controller_identity_and_software_trust_combinations(message_index: int) -> None:
    base = MINIMAL_MESSAGES[message_index]
    identity_untrusted = {
        **base,
        "controller_boot_id": None,
        "controller_state": "IDENTITY_UNTRUSTED",
        "software_state_trust": "UNTRUSTED",
    }
    assert parse_message(identity_untrusted).controller_boot_id is None

    trusted_identity_with_untrusted_software = {
        **base,
        "controller_boot_id": 5,
        "controller_state": "ERROR",
        "software_state_trust": "UNTRUSTED",
    }
    assert parse_message(trusted_identity_with_untrusted_software).controller_boot_id == 5

    with pytest.raises(ValidationError):
        parse_message({**identity_untrusted, "controller_state": "ERROR"})
    with pytest.raises(ValidationError):
        parse_message({**identity_untrusted, "controller_boot_id": 5})
    with pytest.raises(ValidationError):
        parse_message({**identity_untrusted, "software_state_trust": "TRUSTED"})


def test_wire_dict_omits_optional_fields_and_preserves_required_nulls() -> None:
    hello_ok = parse_message(MINIMAL_MESSAGES[1])
    assert "reset_cause" not in hello_ok.to_wire_dict()

    protocol_error = parse_message(MINIMAL_MESSAGES[12])
    assert "backend_session_nonce" not in protocol_error.to_wire_dict()
    assert "controller_boot_id" not in protocol_error.to_wire_dict()

    status_wire = parse_message(MINIMAL_MESSAGES[9]).to_wire_dict()
    assert status_wire["active_operation_command_id"] is None

    identity_untrusted = {
        **MINIMAL_MESSAGES[1],
        "controller_boot_id": None,
        "controller_state": "IDENTITY_UNTRUSTED",
        "software_state_trust": "UNTRUSTED",
    }
    assert parse_message(identity_untrusted).to_wire_dict()["controller_boot_id"] is None


def test_reset_cause_must_be_utf8_encodable() -> None:
    with pytest.raises(ValidationError):
        parse_message({**MINIMAL_MESSAGES[1], "reset_cause": "\ud800"})


@pytest.mark.parametrize(
    "changes",
    [
        {"command_state": "UNKNOWN", "phase_execution_id": "phase-1"},
        {"command_state": "STARTED"},
        {"command_state": "STARTED", "phase_execution_id": "phase-1", "result": {}},
        {"command_state": "REJECTED", "phase_execution_id": "phase-1"},
        {"command_state": "COMPLETED", "phase_execution_id": "phase-1"},
        {"command_state": "FAILED", "phase_execution_id": "phase-1", "error_code": "FAIL"},
    ],
)
def test_command_status_state_specific_correlations(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        parse_message({**MINIMAL_MESSAGES[11], **changes})


def test_protocol_error_correlation_combinations() -> None:
    base = MINIMAL_MESSAGES[12]
    valid_query = {**base, **BASE, "request_id": REQUEST_ID}
    assert parse_message(valid_query).request_id == REQUEST_ID
    with pytest.raises(ValidationError):
        parse_message({**valid_query, "phase_execution_id": "phase-1", "operation_command_id": OPERATION_ID})
    with pytest.raises(ValidationError):
        parse_message({**base, **BASE, "phase_execution_id": "phase-1"})
