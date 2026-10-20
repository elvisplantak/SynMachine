from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from app.hardware.sf_bottom_valve import (
    SfBottomValveActuator,
    SfBottomValveConfiguration,
)
from app.hardware.arduino_command_journal import SQLiteArduinoCommandJournal
from app.hardware.arduino_serial import ArduinoSerialClient, ArduinoSerialConfiguration
from app.hardware.durable_arduino import DurableArduinoCommandExecutor


SF_BOTTOM_VALVE_PORT_ENVIRONMENT_VARIABLE = "LABFORGE_SF_BOTTOM_VALVE_PORT"
ARDUINO_PORT_ENVIRONMENT_VARIABLE = "LABFORGE_ARDUINO_PORT"
ARDUINO_JOURNAL_PATH_ENVIRONMENT_VARIABLE = "LABFORGE_ARDUINO_JOURNAL_PATH"
DEFAULT_ARDUINO_JOURNAL_PATH = Path("labforge-arduino-commands.db")


class ArduinoRuntime:
    """Owns one production Serial session and its separate durable journal."""

    def __init__(self, port: str, journal_path: str | Path) -> None:
        self._client = ArduinoSerialClient(ArduinoSerialConfiguration(port=port))
        self._journal = SQLiteArduinoCommandJournal(journal_path)
        self.executor = DurableArduinoCommandExecutor(self._client, self._journal)

    def start(self) -> None:
        try:
            self._client.connect()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        self._client.close()
        self._journal.close()


def build_arduino_runtime_from_environment(
    environment: Mapping[str, str],
) -> ArduinoRuntime | None:
    port = environment.get(ARDUINO_PORT_ENVIRONMENT_VARIABLE, "").strip()
    if not port:
        return None
    journal_path = environment.get(
        ARDUINO_JOURNAL_PATH_ENVIRONMENT_VARIABLE,
        str(DEFAULT_ARDUINO_JOURNAL_PATH),
    ).strip()
    if not journal_path:
        raise ValueError("Arduino journal path must not be empty")
    return ArduinoRuntime(port, journal_path)


def build_sf_bottom_valve_from_environment(
    environment: Mapping[str, str],
) -> SfBottomValveActuator | None:
    port = environment.get(SF_BOTTOM_VALVE_PORT_ENVIRONMENT_VARIABLE, "").strip()
    if not port:
        return None
    return SfBottomValveActuator(SfBottomValveConfiguration(port=port))
