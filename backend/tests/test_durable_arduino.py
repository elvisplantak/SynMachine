from __future__ import annotations

from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from app.hardware.arduino_command_journal import (
    ArduinoCommandIdentityConflictError,
    ArduinoCommandJournalState,
    SQLiteArduinoCommandJournal,
)
from app.hardware.arduino_serial import (
    ArduinoCommandFailedError,
    ArduinoCommandRejectedError,
    ArduinoCommandResult,
    ArduinoUnavailableError,
)
from app.hardware.durable_arduino import DurableArduinoCommandExecutor
from app.protocol import CommandStatus

OPERATION_ID = "323e4567-e89b-12d3-a456-426614174002"
SECOND_OPERATION_ID = "423e4567-e89b-12d3-a456-426614174003"


@dataclass
class FakeClient:
    journal: SQLiteArduinoCommandJournal
    controller_boot_id: int | None = 7
    execute_result: ArduinoCommandResult | Exception = ArduinoCommandResult(
        result={"position_steps": 0}, accepted=True, started=True
    )
    query_result: CommandStatus | None = None
    execute_calls: int = 0

    def execute(self, **values):
        self.execute_calls += 1
        persisted = self.journal.load(values["operation_command_id"])
        assert persisted is not None
        assert persisted.state is ArduinoCommandJournalState.INTENT_PERSISTED
        if isinstance(self.execute_result, Exception):
            raise self.execute_result
        return self.execute_result

    def query_command(self, operation_command_id: str) -> CommandStatus:
        assert operation_command_id == OPERATION_ID
        assert self.query_result is not None
        return self.query_result


class BlockingClient:
    controller_boot_id = 7

    def __init__(self) -> None:
        self.entered = Event()
        self.release = Event()
        self.execute_calls = 0

    def execute(self, **values: object) -> ArduinoCommandResult:
        del values
        self.execute_calls += 1
        self.entered.set()
        assert self.release.wait(timeout=2)
        return ArduinoCommandResult(result={}, accepted=True, started=True)

    def query_command(self, operation_command_id: str) -> CommandStatus:
        raise AssertionError(f"unexpected recovery query for {operation_command_id}")


def command_status(state: str, **extra: object) -> CommandStatus:
    values: dict[str, object] = {
        "protocol": "LABFORGE/1",
        "type": "COMMAND_STATUS",
        "backend_session_nonce": "123e4567-e89b-12d3-a456-426614174000",
        "controller_boot_id": 7,
        "request_id": "223e4567-e89b-12d3-a456-426614174001",
        "phase_execution_id": "phase-1",
        "operation_command_id": OPERATION_ID,
        "command_state": state,
    }
    values.update(extra)
    return CommandStatus.model_validate(values)


def test_intent_is_durable_before_first_serial_command_byte(tmp_path) -> None:
    with SQLiteArduinoCommandJournal(tmp_path / "commands.db") as journal:
        client = FakeClient(journal)
        executor = DurableArduinoCommandExecutor(client, journal)  # type: ignore[arg-type]
        result = executor.execute(
            phase_execution_id="phase-1",
            operation_command_id=OPERATION_ID,
            command="PUMP_HOME",
            arguments={"pump": "P1"},
        )
        assert result.state is ArduinoCommandJournalState.COMPLETED
        assert result.result == {"position_steps": 0}


def test_journal_can_persist_and_complete_from_fastapi_worker_thread(tmp_path) -> None:
    with SQLiteArduinoCommandJournal(tmp_path / "commands.db") as journal:
        client = FakeClient(journal)
        executor = DurableArduinoCommandExecutor(client, journal)  # type: ignore[arg-type]

        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(
                executor.execute,
                phase_execution_id="phase-1",
                operation_command_id=OPERATION_ID,
                command="PUMP_HOME",
                arguments={"pump": "P1"},
            ).result()

        assert result.state is ArduinoCommandJournalState.COMPLETED
        assert journal.load(OPERATION_ID) == result


def test_concurrent_command_is_known_busy_without_second_serial_call(tmp_path) -> None:
    with SQLiteArduinoCommandJournal(tmp_path / "commands.db") as journal:
        client = BlockingClient()
        executor = DurableArduinoCommandExecutor(client, journal)  # type: ignore[arg-type]

        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(
                executor.execute,
                phase_execution_id="phase-1",
                operation_command_id=OPERATION_ID,
                command="VALVE_SET_POSITION",
                arguments={"valve": "V1", "position_degrees": 180},
            )
            assert client.entered.wait(timeout=2)

            with pytest.raises(ArduinoCommandRejectedError, match="CONTROLLER_BUSY"):
                executor.execute(
                    phase_execution_id="phase-2",
                    operation_command_id=SECOND_OPERATION_ID,
                    command="VALVE_SET_POSITION",
                    arguments={"valve": "V2", "position_degrees": 90},
                )

            client.release.set()
            assert first.result().state is ArduinoCommandJournalState.COMPLETED

        assert client.execute_calls == 1
        assert journal.load(SECOND_OPERATION_ID) is None


def test_transport_failure_is_durable_unknown_and_never_auto_retried(tmp_path) -> None:
    with SQLiteArduinoCommandJournal(tmp_path / "commands.db") as journal:
        client = FakeClient(journal, execute_result=ArduinoUnavailableError("lost"))
        executor = DurableArduinoCommandExecutor(client, journal)  # type: ignore[arg-type]
        with pytest.raises(ArduinoUnavailableError):
            executor.execute(
                phase_execution_id="phase-1",
                operation_command_id=OPERATION_ID,
                command="PUMP_HOME",
                arguments={"pump": "P1"},
            )
        assert journal.load(OPERATION_ID).state is ArduinoCommandJournalState.OUTCOME_UNKNOWN  # type: ignore[union-attr]
        result = executor.execute(
            phase_execution_id="phase-1",
            operation_command_id=OPERATION_ID,
            command="PUMP_HOME",
            arguments={"pump": "P1"},
        )
        assert result.state is ArduinoCommandJournalState.OUTCOME_UNKNOWN
        assert client.execute_calls == 1


def test_operation_id_cannot_be_reused_with_different_semantics(tmp_path) -> None:
    with SQLiteArduinoCommandJournal(tmp_path / "commands.db") as journal:
        journal.persist_intent(
            operation_command_id=OPERATION_ID,
            phase_execution_id="phase-1",
            controller_boot_id=7,
            command="PUMP_HOME",
            arguments={"pump": "P1"},
        )
        with pytest.raises(ArduinoCommandIdentityConflictError):
            journal.persist_intent(
                operation_command_id=OPERATION_ID,
                phase_execution_id="phase-1",
                controller_boot_id=7,
                command="PUMP_HOME",
                arguments={"pump": "P2"},
            )


def test_executor_rejects_conflicting_identity_without_serial_command(tmp_path) -> None:
    with SQLiteArduinoCommandJournal(tmp_path / "commands.db") as journal:
        journal.persist_intent(
            operation_command_id=OPERATION_ID,
            phase_execution_id="phase-1",
            controller_boot_id=7,
            command="PUMP_HOME",
            arguments={"pump": "P1"},
        )
        client = FakeClient(journal)
        executor = DurableArduinoCommandExecutor(client, journal)  # type: ignore[arg-type]
        with pytest.raises(ArduinoCommandIdentityConflictError):
            executor.execute(
                phase_execution_id="phase-1",
                operation_command_id=OPERATION_ID,
                command="PUMP_HOME",
                arguments={"pump": "P2"},
            )
        assert client.execute_calls == 0


@pytest.mark.parametrize(
    ("error", "expected_state", "execution_started"),
    [
        (
            ArduinoCommandRejectedError("INVALID_ARGUMENT"),
            ArduinoCommandJournalState.REJECTED,
            False,
        ),
        (
            ArduinoCommandFailedError(
                "PUMP_MOTION_TIMEOUT", execution_started=True
            ),
            ArduinoCommandJournalState.FAILED,
            True,
        ),
    ],
)
def test_definitive_command_outcome_is_durable_before_error_is_raised(
    tmp_path,
    error: Exception,
    expected_state: ArduinoCommandJournalState,
    execution_started: bool,
) -> None:
    with SQLiteArduinoCommandJournal(tmp_path / "commands.db") as journal:
        client = FakeClient(journal, execute_result=error)
        executor = DurableArduinoCommandExecutor(client, journal)  # type: ignore[arg-type]
        with pytest.raises(type(error)):
            executor.execute(
                phase_execution_id="phase-1",
                operation_command_id=OPERATION_ID,
                command="PUMP_HOME",
                arguments={"pump": "P1"},
            )
        entry = journal.load(OPERATION_ID)
        assert entry is not None
        assert entry.state is expected_state
        assert entry.execution_started is execution_started


def test_same_boot_recovery_queries_without_resending_command(tmp_path) -> None:
    with SQLiteArduinoCommandJournal(tmp_path / "commands.db") as journal:
        journal.persist_intent(
            operation_command_id=OPERATION_ID,
            phase_execution_id="phase-1",
            controller_boot_id=7,
            command="PUMP_HOME",
            arguments={"pump": "P1"},
        )
        client = FakeClient(
            journal,
            query_result=command_status("COMPLETED", result={"position_steps": 0}),
        )
        executor = DurableArduinoCommandExecutor(client, journal)  # type: ignore[arg-type]
        result = executor.recover(OPERATION_ID)
        assert result.state is ArduinoCommandJournalState.COMPLETED
        assert client.execute_calls == 0


def test_existing_persisted_intent_is_never_resent_by_execute(tmp_path) -> None:
    with SQLiteArduinoCommandJournal(tmp_path / "commands.db") as journal:
        journal.persist_intent(
            operation_command_id=OPERATION_ID,
            phase_execution_id="phase-1",
            controller_boot_id=7,
            command="PUMP_HOME",
            arguments={"pump": "P1"},
        )
        client = FakeClient(journal)
        executor = DurableArduinoCommandExecutor(client, journal)  # type: ignore[arg-type]
        result = executor.execute(
            phase_execution_id="phase-1",
            operation_command_id=OPERATION_ID,
            command="PUMP_HOME",
            arguments={"pump": "P1"},
        )
        assert result.state is ArduinoCommandJournalState.OUTCOME_UNKNOWN
        assert result.error_code == "RECOVERY_QUERY_REQUIRED"
        assert client.execute_calls == 0


def test_journal_survives_process_reopen(tmp_path) -> None:
    database = tmp_path / "commands.db"
    with SQLiteArduinoCommandJournal(database) as journal:
        persisted = journal.persist_intent(
            operation_command_id=OPERATION_ID,
            phase_execution_id="phase-1",
            controller_boot_id=7,
            command="PUMP_HOME",
            arguments={"pump": "P1"},
        )
        assert persisted.created is True
    with SQLiteArduinoCommandJournal(database) as reopened:
        persisted = reopened.persist_intent(
            operation_command_id=OPERATION_ID,
            phase_execution_id="phase-1",
            controller_boot_id=7,
            command="PUMP_HOME",
            arguments={"pump": "P1"},
        )
        assert persisted.created is False
        assert persisted.entry.state is ArduinoCommandJournalState.INTENT_PERSISTED


def test_changed_boot_keeps_outcome_unknown_without_query_or_resend(tmp_path) -> None:
    with SQLiteArduinoCommandJournal(tmp_path / "commands.db") as journal:
        journal.persist_intent(
            operation_command_id=OPERATION_ID,
            phase_execution_id="phase-1",
            controller_boot_id=7,
            command="PUMP_HOME",
            arguments={"pump": "P1"},
        )
        client = FakeClient(journal, controller_boot_id=8)
        executor = DurableArduinoCommandExecutor(client, journal)  # type: ignore[arg-type]
        result = executor.recover(OPERATION_ID)
        assert result.state is ArduinoCommandJournalState.OUTCOME_UNKNOWN
        assert result.error_code == "CONTROLLER_REBOOTED"
        assert client.execute_calls == 0
