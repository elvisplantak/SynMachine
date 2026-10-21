from __future__ import annotations

from typing import Annotated, Any, Literal, TypeAlias, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

PROTOCOL = "LABFORGE/1"
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1
UINT32_MAX = 2**32 - 1

UuidText = Annotated[StrictStr, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")]
PhaseExecutionId = Annotated[StrictStr, Field(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")]
UpperIdentifier = Annotated[StrictStr, Field(pattern=r"^[A-Z0-9_]+$")]

ControllerState = Literal["PROTOCOL_ONLY", "IDLE", "BUSY", "ERROR", "IDENTITY_UNTRUSTED"]
SoftwareStateTrust = Literal["TRUSTED", "UNTRUSTED"]
CommandState = Literal["UNKNOWN", "REJECTED", "ACCEPTED", "STARTED", "COMPLETED", "FAILED"]
Scalar: TypeAlias = StrictStr | StrictInt | StrictBool


def _utf8_at_most(value: str, limit: int, field: str) -> str:
    if len(value.encode("utf-8")) > limit:
        raise ValueError(f"{field} exceeds {limit} UTF-8 bytes")
    return value


def _validate_map(value: dict[str, Any], field: str) -> dict[str, Scalar]:
    if len(value) > 8:
        raise ValueError(f"{field} has more than 8 members")
    validated: dict[str, Scalar] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"invalid {field} key")
        try:
            key_bytes = key.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError(f"invalid {field} key") from exc
        if not 1 <= len(key_bytes) <= 24:
            raise ValueError(f"invalid {field} key")
        if item is None or type(item) not in (str, int, bool):
            raise ValueError(f"invalid {field} scalar value")
        if isinstance(item, str):
            _utf8_at_most(item, 64, f"{field} string")
        elif type(item) is int and not INT64_MIN <= item <= INT64_MAX:
            raise ValueError(f"{field} integer is outside signed 64-bit range")
        validated[key] = item
    return validated


class StrictMessage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    protocol: Literal[PROTOCOL]

    def to_wire_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_unset=True)


class SessionMessage(StrictMessage):
    backend_session_nonce: UuidText
    controller_boot_id: Annotated[StrictInt, Field(ge=0, le=UINT32_MAX)] | None


class ControllerStateMessage(SessionMessage):
    controller_state: ControllerState
    software_state_trust: SoftwareStateTrust

    @model_validator(mode="after")
    def validate_identity_state(self) -> ControllerStateMessage:
        identity_untrusted = self.controller_state == "IDENTITY_UNTRUSTED"
        if self.controller_boot_id is None:
            if not identity_untrusted or self.software_state_trust != "UNTRUSTED":
                raise ValueError("controller identity fields are inconsistent")
        elif identity_untrusted:
            raise ValueError("controller identity fields are inconsistent")
        return self


class CommandCorrelation(SessionMessage):
    phase_execution_id: PhaseExecutionId
    operation_command_id: UuidText


class Hello(StrictMessage):
    type: Literal["HELLO"]
    backend_session_nonce: UuidText


class HelloOk(ControllerStateMessage):
    type: Literal["HELLO_OK"]
    capabilities: list[UpperIdentifier]
    reset_cause: StrictStr | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_optional_null(cls, value: Any) -> Any:
        if isinstance(value, dict) and value.get("reset_cause", ...) is None:
            raise ValueError("reset_cause must be omitted rather than null")
        return value

    @field_validator("capabilities")
    @classmethod
    def validate_capabilities(cls, value: list[str]) -> list[str]:
        if len(value) > 10 or any(len(item.encode("ascii")) > 32 for item in value):
            raise ValueError("invalid capabilities")
        return value

    @field_validator("reset_cause")
    @classmethod
    def validate_reset_cause_utf8(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as exc:
                raise ValueError("reset_cause must be valid UTF-8") from exc
        return value


class Command(CommandCorrelation):
    type: Literal["COMMAND"]
    command: Annotated[UpperIdentifier, Field(max_length=32)]
    arguments: dict[str, Scalar]

    @field_validator("arguments", mode="before")
    @classmethod
    def validate_arguments(cls, value: Any) -> dict[str, Scalar]:
        if not isinstance(value, dict):
            raise ValueError("arguments must be an object")
        return _validate_map(value, "arguments")


class ErrorFields(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    error_code: Annotated[UpperIdentifier, Field(max_length=40)]
    message: StrictStr | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_message_null(cls, value: Any) -> Any:
        if isinstance(value, dict) and value.get("message", ...) is None:
            raise ValueError("message must be omitted rather than null")
        return value

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return _utf8_at_most(value, 96, "message")


class Rejected(CommandCorrelation, ErrorFields):
    type: Literal["REJECTED"]


class Accepted(CommandCorrelation):
    type: Literal["ACCEPTED"]


class Started(CommandCorrelation):
    type: Literal["STARTED"]


class Completed(CommandCorrelation):
    type: Literal["COMPLETED"]
    result: dict[str, Scalar]

    @field_validator("result", mode="before")
    @classmethod
    def validate_result(cls, value: Any) -> dict[str, Scalar]:
        if not isinstance(value, dict):
            raise ValueError("result must be an object")
        return _validate_map(value, "result")


class Failed(CommandCorrelation, ErrorFields):
    type: Literal["FAILED"]
    execution_started: StrictBool


class QueryStatus(SessionMessage):
    type: Literal["QUERY_STATUS"]
    request_id: UuidText


class Status(ControllerStateMessage):
    type: Literal["STATUS"]
    request_id: UuidText
    active_operation_command_id: UuidText | None
    column_motion_state: Annotated[UpperIdentifier, Field(max_length=40)] | None = None
    column_stage_steps: Annotated[StrictInt, Field(ge=0, le=UINT32_MAX)] | None = None
    column_home_active: StrictBool | None = None


class QueryCommand(QueryStatus):
    type: Literal["QUERY_COMMAND"]  # type: ignore[assignment]
    operation_command_id: UuidText


class CommandStatus(QueryCommand, ErrorFields):
    type: Literal["COMMAND_STATUS"]  # type: ignore[assignment]
    phase_execution_id: PhaseExecutionId | None = None
    command_state: CommandState
    result: dict[str, Scalar] | None = None
    execution_started: StrictBool | None = None
    error_code: Annotated[UpperIdentifier, Field(max_length=40)] | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_optional_nulls(cls, value: Any) -> Any:
        if isinstance(value, dict):
            for name in ("phase_execution_id", "result", "execution_started", "error_code", "message"):
                if value.get(name, ...) is None:
                    raise ValueError(f"{name} must be omitted rather than null")

        return value

    @field_validator("result", mode="before")
    @classmethod
    def validate_result(cls, value: Any) -> dict[str, Scalar] | None:
        if value is None:
            return value
        if not isinstance(value, dict):
            raise ValueError("result must be an object")
        return _validate_map(value, "result")

    @model_validator(mode="after")
    def validate_state_fields(self) -> CommandStatus:
        state = self.command_state
        required = {
            "REJECTED": {"error_code"},
            "COMPLETED": {"result"},
            "FAILED": {"error_code", "execution_started"},
        }.get(state, set())
        present = {
            name
            for name in ("error_code", "result", "execution_started", "message")
            if getattr(self, name) is not None
        }
        allowed = {
            "REJECTED": {"error_code", "message"},
            "COMPLETED": {"result"},
            "FAILED": {"error_code", "execution_started", "message"},
        }.get(state, set())
        if not required <= present or not present <= allowed:
            raise ValueError("fields do not match command_state")
        if state == "UNKNOWN" and self.phase_execution_id is not None:
            raise ValueError("UNKNOWN command cannot have phase_execution_id")
        if state != "UNKNOWN" and self.phase_execution_id is None:
            raise ValueError("known command requires phase_execution_id")
        return self


class ProtocolError(StrictMessage, ErrorFields):
    type: Literal["PROTOCOL_ERROR"]
    backend_session_nonce: UuidText | None = None
    controller_boot_id: Annotated[StrictInt, Field(ge=0, le=UINT32_MAX)] | None = None
    request_id: UuidText | None = None
    phase_execution_id: PhaseExecutionId | None = None
    operation_command_id: UuidText | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_optional_nulls(cls, value: Any) -> Any:
        if isinstance(value, dict):
            for name in (
                "backend_session_nonce",
                "request_id",
                "phase_execution_id",
                "operation_command_id",
                "message",
            ):
                if value.get(name, ...) is None:
                    raise ValueError(f"{name} must be omitted rather than null")
            correlation_names = {
                "backend_session_nonce",
                "controller_boot_id",
                "request_id",
                "phase_execution_id",
                "operation_command_id",
            }
            present = correlation_names.intersection(value)
            if present:
                query = {"backend_session_nonce", "controller_boot_id", "request_id"}
                command = {
                    "backend_session_nonce",
                    "controller_boot_id",
                    "phase_execution_id",
                    "operation_command_id",
                }
                if present not in (query, command):
                    raise ValueError("incomplete protocol error correlation")
        return value

    @model_validator(mode="after")
    def validate_correlations(self) -> ProtocolError:
        query = self.request_id is not None
        command = self.phase_execution_id is not None or self.operation_command_id is not None
        if query and command:
            raise ValueError("query and command correlations cannot be mixed")
        if not query and not command and self.error_code not in {
            "MALFORMED_MESSAGE",
            "LINE_TOO_LONG",
        }:
            raise ValueError("protocol error correlation is required")
        return self


ProtocolMessage: TypeAlias = Union[
    Hello,
    HelloOk,
    Command,
    Rejected,
    Accepted,
    Started,
    Completed,
    Failed,
    QueryStatus,
    Status,
    QueryCommand,
    CommandStatus,
    ProtocolError,
]

MESSAGE_MODELS_BY_TYPE: dict[str, type[StrictMessage]] = {
    "HELLO": Hello,
    "HELLO_OK": HelloOk,
    "COMMAND": Command,
    "REJECTED": Rejected,
    "ACCEPTED": Accepted,
    "STARTED": Started,
    "COMPLETED": Completed,
    "FAILED": Failed,
    "QUERY_STATUS": QueryStatus,
    "STATUS": Status,
    "QUERY_COMMAND": QueryCommand,
    "COMMAND_STATUS": CommandStatus,
    "PROTOCOL_ERROR": ProtocolError,
}
SUPPORTED_MESSAGE_TYPES = frozenset(MESSAGE_MODELS_BY_TYPE)


def parse_message(value: dict[str, Any]) -> ProtocolMessage:
    message_type = value.get("type")
    model = MESSAGE_MODELS_BY_TYPE.get(message_type) if isinstance(message_type, str) else None
    if model is None:
        raise ValueError("unsupported message type")
    return model.model_validate(value)  # type: ignore[return-value]
