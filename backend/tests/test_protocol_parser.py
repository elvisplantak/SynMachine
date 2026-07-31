import json

import pytest

from app.protocol import Hello, NdjsonStreamParser, ParseError, ParseSuccess

NONCE = "123e4567-e89b-12d3-a456-426614174000"


def frame(value: object, ending: bytes = b"\n") -> bytes:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode() + ending


def hello() -> dict[str, object]:
    return {"protocol": "LABFORGE/1", "type": "HELLO", "backend_session_nonce": NONCE}


def error_code(outcome: object) -> str:
    assert isinstance(outcome, ParseError)
    return outcome.error_code


def parse_error(payload: bytes) -> ParseError:
    outcomes = NdjsonStreamParser().feed(payload)
    assert len(outcomes) == 1
    assert isinstance(outcomes[0], ParseError)
    return outcomes[0]


def test_parses_lf_and_crlf_frames() -> None:
    parser = NdjsonStreamParser()
    outcomes = parser.feed(frame(hello()) + frame(hello(), b"\r\n"))
    assert [type(outcome) for outcome in outcomes] == [ParseSuccess, ParseSuccess]
    assert all(isinstance(outcome.message, Hello) for outcome in outcomes if isinstance(outcome, ParseSuccess))


def test_retains_split_incomplete_frame_without_premature_result() -> None:
    parser = NdjsonStreamParser()
    encoded = frame(hello())
    assert parser.feed(encoded[:20]) == []
    assert 0 < parser.retained_bytes <= 513
    outcomes = parser.feed(encoded[20:])
    assert len(outcomes) == 1
    assert isinstance(outcomes[0], ParseSuccess)
    assert parser.retained_bytes == 0


def test_bad_frame_does_not_block_following_valid_frame() -> None:
    outcomes = NdjsonStreamParser().feed(b"{bad json}\n" + frame(hello()))
    assert error_code(outcomes[0]) == "MALFORMED_MESSAGE"
    assert isinstance(outcomes[1], ParseSuccess)


def test_oversized_frame_reports_once_and_recovers() -> None:
    parser = NdjsonStreamParser()
    outcomes = parser.feed(b"x" * 513 + b"more ignored\n" + frame(hello()))
    assert len(outcomes) == 2
    assert error_code(outcomes[0]) == "LINE_TOO_LONG"
    assert isinstance(outcomes[1], ParseSuccess)
    assert parser.retained_bytes == 0


def test_exactly_512_payload_bytes_can_parse() -> None:
    compact = frame(hello())[:-1]
    payload = compact + b" " * (512 - len(compact))
    outcomes = NdjsonStreamParser().feed(payload + b"\n")
    assert len(payload) == 512
    assert isinstance(outcomes[0], ParseSuccess)


def test_513_payload_bytes_are_too_long() -> None:
    outcomes = NdjsonStreamParser().feed(b"x" * 513 + b"\n")
    assert [error_code(outcome) for outcome in outcomes] == ["LINE_TOO_LONG"]


def test_cr_is_excluded_only_directly_before_lf_at_boundary() -> None:
    compact = frame(hello())[:-1]
    payload = compact + b" " * (512 - len(compact))
    assert isinstance(NdjsonStreamParser().feed(payload + b"\r\n")[0], ParseSuccess)
    outcomes = NdjsonStreamParser().feed(payload + b"\rX\n")
    assert error_code(outcomes[0]) == "LINE_TOO_LONG"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (b"\xff\n", "MALFORMED_MESSAGE"),
        (b"\n", "MALFORMED_MESSAGE"),
        (b"[]\n", "MALFORMED_MESSAGE"),
        (b'{"protocol":"LABFORGE/1","protocol":"LABFORGE/1","type":"HELLO"}\n', "MALFORMED_MESSAGE"),
        (frame({"type": "HELLO", "backend_session_nonce": NONCE}), "MISSING_FIELD"),
        (frame({**hello(), "protocol": "LABFORGE/2"}), "UNSUPPORTED_PROTOCOL_VERSION"),
        (frame({**hello(), "type": "BOGUS"}), "UNSUPPORTED_MESSAGE_TYPE"),
    ],
)
def test_parse_error_classification(payload: bytes, expected: str) -> None:
    outcomes = NdjsonStreamParser().feed(payload)
    assert error_code(outcomes[0]) == expected


@pytest.mark.parametrize("constant", [b"NaN", b"Infinity", b"-Infinity"])
def test_rejects_non_standard_json_constants(constant: bytes) -> None:
    payload = b'{"protocol":"LABFORGE/1","type":"HELLO","value":' + constant + b"}\n"
    outcome = parse_error(payload)
    assert outcome.error_code == "MALFORMED_MESSAGE"
    assert outcome.message == "Malformed JSON payload"


@pytest.mark.parametrize(
    ("field_value", "expected"),
    [
        (None, "INVALID_FIELD"),
        (123, "INVALID_FIELD"),
        ("", "INVALID_FIELD"),
        ("Ž", "INVALID_FIELD"),
        ("A" * 33, "INVALID_FIELD"),
        ("BOGUS", "UNSUPPORTED_MESSAGE_TYPE"),
    ],
)
def test_validates_type_shape_before_dispatch(field_value: object, expected: str) -> None:
    assert parse_error(frame({**hello(), "type": field_value})).error_code == expected


@pytest.mark.parametrize(
    ("protocol", "expected"),
    [(1, "INVALID_FIELD"), ("LABFORGE/2", "UNSUPPORTED_PROTOCOL_VERSION")],
)
def test_validates_protocol_shape_before_dispatch(protocol: object, expected: str) -> None:
    assert parse_error(frame({**hello(), "protocol": protocol})).error_code == expected


@pytest.mark.parametrize(
    ("payload", "expected_message"),
    [
        (b"\xff\n", "Invalid UTF-8 payload"),
        (b"{bad json}\n", "Malformed JSON payload"),
        (
            b'{"protocol":"LABFORGE/1","protocol":"LABFORGE/1","type":"HELLO"}\n',
            "Duplicate JSON field",
        ),
    ],
)
def test_parse_errors_use_bounded_stable_messages(payload: bytes, expected_message: str) -> None:
    outcome = parse_error(payload)
    assert outcome.message == expected_message
    assert len(outcome.message.encode("utf-8")) <= 96


def test_feed_requires_bytes() -> None:
    with pytest.raises(TypeError, match="chunk must be bytes"):
        NdjsonStreamParser().feed(bytearray(b"x"))  # type: ignore[arg-type]
