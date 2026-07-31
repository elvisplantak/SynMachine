from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, TypeAlias

from pydantic import ValidationError

from app.protocol.models import PROTOCOL, SUPPORTED_MESSAGE_TYPES, ProtocolMessage, parse_message

MAX_PAYLOAD_BYTES = 512


@dataclass(frozen=True)
class ParseSuccess:
    message: ProtocolMessage


@dataclass(frozen=True)
class ParseError:
    error_code: str
    message: str


ParseOutcome: TypeAlias = ParseSuccess | ParseError


class _DuplicateKey(ValueError):
    pass


class _InvalidConstant(ValueError):
    pass


def _object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _reject_json_constant(_: str) -> None:
    raise _InvalidConstant


class NdjsonStreamParser:
    """Bounded, transport-independent LABFORGE/1 NDJSON frame parser."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._discarding = False

    @property
    def retained_bytes(self) -> int:
        return len(self._buffer)

    def feed(self, chunk: bytes) -> list[ParseOutcome]:
        if not isinstance(chunk, bytes):
            raise TypeError("chunk must be bytes")
        outcomes: list[ParseOutcome] = []
        for byte in chunk:
            if self._discarding:
                if byte == 0x0A:
                    self._discarding = False
                continue
            if byte == 0x0A:
                payload = bytes(self._buffer)
                self._buffer.clear()
                if payload.endswith(b"\r"):
                    payload = payload[:-1]
                outcomes.append(self._parse_payload(payload))
                continue
            # Retain one extra byte because a 513th byte may be the CR in CRLF.
            if len(self._buffer) == MAX_PAYLOAD_BYTES and byte == 0x0D:
                self._buffer.append(byte)
                continue
            if len(self._buffer) >= MAX_PAYLOAD_BYTES:
                self._buffer.clear()
                self._discarding = True
                outcomes.append(ParseError("LINE_TOO_LONG", "Payload exceeds 512 bytes"))
                continue
            self._buffer.append(byte)
        return outcomes

    def _parse_payload(self, payload: bytes) -> ParseOutcome:
        if len(payload) > MAX_PAYLOAD_BYTES:
            return ParseError("LINE_TOO_LONG", "Payload exceeds 512 bytes")
        try:
            text = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return ParseError("MALFORMED_MESSAGE", "Invalid UTF-8 payload")
        try:
            value = json.loads(
                text,
                object_pairs_hook=_object_without_duplicates,
                parse_constant=_reject_json_constant,
            )
        except _DuplicateKey:
            return ParseError("MALFORMED_MESSAGE", "Duplicate JSON field")
        except (json.JSONDecodeError, _InvalidConstant):
            return ParseError("MALFORMED_MESSAGE", "Malformed JSON payload")
        if not isinstance(value, dict):
            return ParseError("MALFORMED_MESSAGE", "Top-level JSON value must be an object")
        if "protocol" not in value or "type" not in value:
            return ParseError("MISSING_FIELD", "protocol and type are required")
        protocol = value["protocol"]
        if not isinstance(protocol, str):
            return ParseError("INVALID_FIELD", "protocol must be a string")
        if protocol != PROTOCOL:
            return ParseError("UNSUPPORTED_PROTOCOL_VERSION", "Unsupported protocol version")
        message_type = value["type"]
        if not isinstance(message_type, str):
            return ParseError("INVALID_FIELD", "type must be a string")
        try:
            type_bytes = message_type.encode("ascii")
        except UnicodeEncodeError:
            return ParseError("INVALID_FIELD", "type must be ASCII")
        if not 1 <= len(type_bytes) <= 32:
            return ParseError("INVALID_FIELD", "type must be 1 to 32 ASCII bytes")
        if message_type not in SUPPORTED_MESSAGE_TYPES:
            return ParseError("UNSUPPORTED_MESSAGE_TYPE", "Unsupported message type")
        try:
            return ParseSuccess(parse_message(value))
        except ValidationError as exc:
            error_code = (
                "MISSING_FIELD"
                if any(error["type"] == "missing" for error in exc.errors())
                else "INVALID_FIELD"
            )
            return ParseError(error_code, "Message schema validation failed")
