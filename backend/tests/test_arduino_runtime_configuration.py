from __future__ import annotations

from pathlib import Path

import pytest

import app.hardware.runtime_configuration as runtime_configuration
from app.hardware.runtime_configuration import build_arduino_runtime_from_environment


def test_arduino_runtime_is_disabled_without_explicit_port() -> None:
    assert build_arduino_runtime_from_environment({}) is None
    assert build_arduino_runtime_from_environment({"LABFORGE_ARDUINO_PORT": "  "}) is None


def test_arduino_runtime_uses_explicit_stable_port_and_journal_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    class RecordingRuntime:
        def __init__(self, port: str, journal_path: str | Path) -> None:
            observed.update(port=port, journal_path=journal_path)

    monkeypatch.setattr(runtime_configuration, "ArduinoRuntime", RecordingRuntime)
    runtime = build_arduino_runtime_from_environment(
        {
            "LABFORGE_ARDUINO_PORT": "/dev/serial/by-id/arduino-mega",
            "LABFORGE_ARDUINO_JOURNAL_PATH": str(tmp_path / "commands.db"),
        }
    )

    assert isinstance(runtime, RecordingRuntime)
    assert observed == {
        "port": "/dev/serial/by-id/arduino-mega",
        "journal_path": str(tmp_path / "commands.db"),
    }


def test_arduino_runtime_rejects_empty_explicit_journal_path() -> None:
    with pytest.raises(ValueError, match="journal path must not be empty"):
        build_arduino_runtime_from_environment(
            {
                "LABFORGE_ARDUINO_PORT": "/dev/serial/by-id/arduino-mega",
                "LABFORGE_ARDUINO_JOURNAL_PATH": "  ",
            }
        )
