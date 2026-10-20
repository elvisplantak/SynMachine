from __future__ import annotations

from threading import Lock

from app.hardware.arduino_command_journal import (
    ArduinoCommandJournalEntry,
    ArduinoCommandJournalState,
    SQLiteArduinoCommandJournal,
)
from app.hardware.arduino_serial import (
    ArduinoCommandFailedError,
    ArduinoCommandRejectedError,
    ArduinoProtocolError,
    ArduinoSerialClient,
    ArduinoUnavailableError,
)


class ArduinoRecoveryError(RuntimeError):
    """A durable Arduino command cannot be safely resolved automatically."""


class DurableArduinoCommandExecutor:
    """Persists command identity before bytes and never retries physical commands."""

    def __init__(
        self,
        client: ArduinoSerialClient,
        journal: SQLiteArduinoCommandJournal,
    ) -> None:
        self._client = client
        self._journal = journal
        self._command_lock = Lock()

    def execute(
        self,
        *,
        phase_execution_id: str,
        operation_command_id: str,
        command: str,
        arguments: dict[str, str | int | bool],
    ) -> ArduinoCommandJournalEntry:
        if not self._command_lock.acquire(blocking=False):
            raise ArduinoCommandRejectedError("CONTROLLER_BUSY")
        try:
            return self._execute_locked(
                phase_execution_id=phase_execution_id,
                operation_command_id=operation_command_id,
                command=command,
                arguments=arguments,
            )
        finally:
            self._command_lock.release()

    def _execute_locked(
        self,
        *,
        phase_execution_id: str,
        operation_command_id: str,
        command: str,
        arguments: dict[str, str | int | bool],
    ) -> ArduinoCommandJournalEntry:
        boot_id = self._client.controller_boot_id
        if boot_id is None:
            raise ArduinoUnavailableError("Arduino is not connected")
        persisted = self._journal.persist_intent(
            operation_command_id=operation_command_id,
            phase_execution_id=phase_execution_id,
            controller_boot_id=boot_id,
            command=command,
            arguments=arguments,
        )
        intent = persisted.entry
        if not persisted.created:
            if intent.state is ArduinoCommandJournalState.INTENT_PERSISTED:
                return self._journal.record_outcome(
                    operation_command_id,
                    ArduinoCommandJournalState.OUTCOME_UNKNOWN,
                    error_code="RECOVERY_QUERY_REQUIRED",
                )
            return intent
        try:
            result = self._client.execute(
                phase_execution_id=phase_execution_id,
                operation_command_id=operation_command_id,
                command=command,
                arguments=arguments,
            )
        except ArduinoCommandRejectedError as error:
            self._journal.record_outcome(
                operation_command_id,
                ArduinoCommandJournalState.REJECTED,
                error_code=error.error_code,
                execution_started=False,
            )
            raise
        except ArduinoCommandFailedError as error:
            self._journal.record_outcome(
                operation_command_id,
                ArduinoCommandJournalState.FAILED,
                error_code=error.error_code,
                execution_started=error.execution_started,
            )
            raise
        except (ArduinoUnavailableError, ArduinoProtocolError):
            self._journal.record_outcome(
                operation_command_id,
                ArduinoCommandJournalState.OUTCOME_UNKNOWN,
            )
            raise
        return self._journal.record_outcome(
            operation_command_id,
            ArduinoCommandJournalState.COMPLETED,
            result=result.result,
            execution_started=True,
        )

    def recover(self, operation_command_id: str) -> ArduinoCommandJournalEntry:
        if not self._command_lock.acquire(blocking=False):
            raise ArduinoRecoveryError("Arduino command already active")
        try:
            return self._recover_locked(operation_command_id)
        finally:
            self._command_lock.release()

    def _recover_locked(self, operation_command_id: str) -> ArduinoCommandJournalEntry:
        entry = self._journal.load(operation_command_id)
        if entry is None:
            raise ArduinoRecoveryError("Arduino command intent was not found")
        if entry.state not in {
            ArduinoCommandJournalState.INTENT_PERSISTED,
            ArduinoCommandJournalState.OUTCOME_UNKNOWN,
        }:
            return entry
        if self._client.controller_boot_id != entry.controller_boot_id:
            return self._journal.record_outcome(
                operation_command_id,
                ArduinoCommandJournalState.OUTCOME_UNKNOWN,
                error_code="CONTROLLER_REBOOTED",
            )
        status = self._client.query_command(operation_command_id)
        if status.command_state == "COMPLETED":
            assert status.result is not None
            return self._journal.record_outcome(
                operation_command_id,
                ArduinoCommandJournalState.COMPLETED,
                result=dict(status.result),
                execution_started=True,
            )
        if status.command_state == "REJECTED":
            return self._journal.record_outcome(
                operation_command_id,
                ArduinoCommandJournalState.REJECTED,
                error_code=status.error_code,
                execution_started=False,
            )
        if status.command_state == "FAILED":
            return self._journal.record_outcome(
                operation_command_id,
                ArduinoCommandJournalState.FAILED,
                error_code=status.error_code,
                execution_started=status.execution_started,
            )
        return self._journal.record_outcome(
            operation_command_id,
            ArduinoCommandJournalState.OUTCOME_UNKNOWN,
            error_code=f"CONTROLLER_COMMAND_{status.command_state}",
            execution_started=(status.command_state == "STARTED"),
        )
