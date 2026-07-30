from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from app.demo.machine_models import MachineSnapshot, MachineState
from app.persistence.sqlite_store import SQLiteStore


class ProcessStartupDisposition(StrEnum):
    UNINITIALIZED = "UNINITIALIZED"
    STARTUP_PENDING = "STARTUP_PENDING"
    READY = "READY"
    PHASE_EXECUTION_RECONCILED = "PHASE_EXECUTION_RECONCILED"
    ACTIVE_RUN_RECONCILED = "ACTIVE_RUN_RECONCILED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
    RECOVERING = "RECOVERING"
    FLUSH_REQUIRED = "FLUSH_REQUIRED"
    FLUSHING = "FLUSHING"


class ProcessStartupResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    disposition: ProcessStartupDisposition
    machine: MachineSnapshot | None
    persistent_reconciliation_occurred: bool

    @model_validator(mode="after")
    def validate_disposition_fields(self) -> Self:
        if self.disposition is ProcessStartupDisposition.UNINITIALIZED:
            if self.machine is not None:
                raise ValueError("UNINITIALIZED requires machine to be None")
            if self.persistent_reconciliation_occurred:
                raise ValueError(
                    "UNINITIALIZED rejects persistent reconciliation"
                )
            return self

        if self.machine is None:
            raise ValueError(
                f"{self.disposition.value} requires a machine snapshot"
            )
        reconciled = self.disposition in {
            ProcessStartupDisposition.PHASE_EXECUTION_RECONCILED,
            ProcessStartupDisposition.ACTIVE_RUN_RECONCILED,
        }
        if self.persistent_reconciliation_occurred is not reconciled:
            raise ValueError(
                f"{self.disposition.value} requires "
                f"persistent_reconciliation_occurred={reconciled}"
            )
        return self


def bootstrap_process_startup(
    store: SQLiteStore,
    occurred_at: datetime,
) -> ProcessStartupResult:
    if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
        raise ValueError("process startup occurred_at must be timezone-aware")

    machine = store.load_machine_snapshot()
    if machine is None:
        return ProcessStartupResult(
            disposition=ProcessStartupDisposition.UNINITIALIZED,
            machine=None,
            persistent_reconciliation_occurred=False,
        )

    if machine.state is MachineState.BUSY:
        if machine.active_execution is not None:
            reconciled = store.reconcile_interrupted_phase_execution_at_startup(
                occurred_at
            )
            disposition = (
                ProcessStartupDisposition.PHASE_EXECUTION_RECONCILED
            )
        else:
            reconciled = store.reconcile_interrupted_active_run_at_startup(
                occurred_at
            )
            disposition = ProcessStartupDisposition.ACTIVE_RUN_RECONCILED
        return ProcessStartupResult(
            disposition=disposition,
            machine=reconciled.machine,
            persistent_reconciliation_occurred=True,
        )

    dispositions = {
        MachineState.STARTING: ProcessStartupDisposition.STARTUP_PENDING,
        MachineState.READY: ProcessStartupDisposition.READY,
        MachineState.RECOVERY_REQUIRED: (
            ProcessStartupDisposition.RECOVERY_REQUIRED
        ),
        MachineState.RECOVERING: ProcessStartupDisposition.RECOVERING,
        MachineState.FLUSH_REQUIRED: ProcessStartupDisposition.FLUSH_REQUIRED,
        MachineState.FLUSHING: ProcessStartupDisposition.FLUSHING,
    }
    return ProcessStartupResult(
        disposition=dispositions[machine.state],
        machine=machine,
        persistent_reconciliation_occurred=False,
    )
