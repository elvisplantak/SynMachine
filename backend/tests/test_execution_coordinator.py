from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event

import pytest

from app.demo.application_service import GuidedDemoApplicationService
from app.demo.calibration_models import PumpCalibration, PumpCalibrationSet, PumpId
from app.demo.execution_coordinator import GuidedDemoExecutionCoordinator
from app.demo.execution_lifecycle import PhaseExecutionClaimError
from app.demo.execution_lifecycle import PhaseExecutionStartCommitError
from app.demo.guided_demo_phase_executor import (
    GuidedDemoPhaseExecutor,
    GuidedDemoPhaseExecutionResult,
    MissingColumnFractionCollectionReadinessError,
    PreparedGuidedDemoPhase,
)
from app.demo.machine_models import (
    MachineState,
    PhaseExecutionOutcome,
    PhaseExecutionResult,
    RuntimeHardwareFaultReason,
)
from app.demo.machine_events import MachineEventType
from app.demo.models import AdditionOrder, DemoConfiguration, DemoExecutionSettings
from app.demo.operation_plan_runner import PlanRunOutcome, PlanRunResult
from app.demo.phases import HARDWARE_EXECUTION_PHASES, RunPhase
from app.demo.run_models import DemoRun, RunStatus
from app.persistence.sqlite_store import PersistenceConflictError, SQLiteStore

NOW = datetime(2026, 7, 27, 12, tzinfo=UTC)
CONFIGURATION = DemoConfiguration(
    b1_ratio_percent="50",
    total_mixture_volume_ml="10",
    combined_b1_b2_volume_ml="4",
    addition_order=AdditionOrder.B1_THEN_B2,
    addition_speed_command_percent="50",
    reactor_mixing_command_percent="50",
    sf_mixing_command_percent="50",
    simulated_target_temperature_c="25",
    reaction_duration_seconds="60",
    delay_between_additions_seconds="5",
)
SETTINGS = DemoExecutionSettings(
    sf_settling_duration_seconds="10",
    fraction_count=2,
    fraction_duration_seconds="5",
)
CALIBRATIONS = PumpCalibrationSet(
    p1=PumpCalibration(
        pump_id=PumpId.P1,
        working_volume_ml="2.5",
        working_full_chamber_position_steps=1000,
        working_empty_chamber_position_steps=6000,
    ),
    p2=PumpCalibration(
        pump_id=PumpId.P2,
        working_volume_ml="3",
        working_full_chamber_position_steps=2000,
        working_empty_chamber_position_steps=8000,
    ),
)


@dataclass
class RecordingPhaseExecutor:
    outcome: PhaseExecutionOutcome = PhaseExecutionOutcome.COMPLETED
    callback: object | None = None
    error: Exception | None = None
    prepare_error: Exception | None = None
    prepare_callback: object | None = None
    failure_reason: str | None = None
    cleanup_failure_reason: str | None = None
    primary_failure_reason: str | None = None
    runtime_fault_reason: RuntimeHardwareFaultReason | None = None

    def __post_init__(self) -> None:
        self.calls: list[RunPhase] = []
        self.prepared: list[PreparedGuidedDemoPhase] = []
        self.executed_prepared: list[PreparedGuidedDemoPhase] = []

    def prepare_current_phase(
        self,
        run: DemoRun,
        calibrations: PumpCalibrationSet,
        *,
        column_readiness: object | None = None,
    ) -> PreparedGuidedDemoPhase:
        if self.prepare_error is not None:
            raise self.prepare_error
        prepared = PreparedGuidedDemoPhase(
            run_id=run.run_id,
            run_event_sequence=run.event_sequence,
            phase=run.phase,
            operations=(),
        )
        self.prepared.append(prepared)
        if callable(self.prepare_callback):
            self.prepare_callback()
        return prepared

    def execute_prepared_phase(
        self, prepared: PreparedGuidedDemoPhase
    ) -> GuidedDemoPhaseExecutionResult:
        self.executed_prepared.append(prepared)
        self.calls.append(prepared.phase)
        if callable(self.callback):
            self.callback()
        if self.error is not None:
            raise self.error
        plan_result = PlanRunResult(
            outcome=(
                PlanRunOutcome.COMPLETED
                if self.outcome is PhaseExecutionOutcome.COMPLETED
                else PlanRunOutcome.STOP_REQUESTED
            ),
            completed_operation_count=0,
            total_operation_count=0,
            last_completed_operation_number=None,
            stop_operation_number=None,
        )
        return GuidedDemoPhaseExecutionResult(
            phase=prepared.phase,
            outcome=self.outcome,
            plan_run_result=plan_result,
            failure_reason=self.failure_reason,
            cleanup_failure_reason=self.cleanup_failure_reason,
            primary_failure_reason=self.primary_failure_reason,
            runtime_fault_reason=self.runtime_fault_reason,
        )


class StopAfterClaimStore(SQLiteStore):
    def __init__(self) -> None:
        super().__init__()
        self.after_claim: object | None = None

    def claim_phase_execution(self, **kwargs: object):  # type: ignore[no-untyped-def]
        intent = super().claim_phase_execution(**kwargs)  # type: ignore[arg-type]
        if callable(self.after_claim):
            self.after_claim()
        return intent


class FailingResolutionStore(SQLiteStore):
    def resolve_phase_execution(self, result):  # type: ignore[no-untyped-def]
        raise RuntimeError("resolution persistence failed")


class InconsistentPostClaimStore(SQLiteStore):
    def __init__(self, mismatch: str) -> None:
        super().__init__()
        self.mismatch = mismatch
        self.claimed = False

    def claim_phase_execution(self, **kwargs: object):  # type: ignore[no-untyped-def]
        intent = super().claim_phase_execution(**kwargs)  # type: ignore[arg-type]
        self.claimed = True
        return intent

    def load_demo_run(self, run_id: str):  # type: ignore[no-untyped-def]
        run = super().load_demo_run(run_id)
        if self.claimed and self.mismatch == "phase" and run is not None:
            return run.model_copy(
                update={"phase": RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR}
            )
        return run

    def load_machine_snapshot(self):  # type: ignore[no-untyped-def]
        machine = super().load_machine_snapshot()
        if not self.claimed or machine is None:
            return machine
        if self.mismatch == "active_execution":
            return machine.model_copy(update={"active_execution": None})
        if self.mismatch == "active_run_id":
            return machine.model_copy(update={"active_run_id": "other-run"})
        return machine


def _started_service(store: SQLiteStore) -> GuidedDemoApplicationService:
    service = GuidedDemoApplicationService(store)
    service.initialize_machine(NOW)
    service.complete_startup(NOW + timedelta(seconds=1))
    service.create_run("run-1", CONFIGURATION, SETTINGS, NOW)
    service.start_run("run-1", NOW + timedelta(seconds=2))
    return service


def _clock() -> object:
    times = iter(
        [
            NOW + timedelta(seconds=3),
            NOW + timedelta(seconds=4),
            NOW + timedelta(seconds=5),
        ]
    )
    return lambda: next(times)


def _complete_hardware_phase(store: SQLiteStore, execution_id: str) -> None:
    run = store.load_demo_run("run-1")
    assert run is not None
    intent = store.claim_phase_execution(
        run_id=run.run_id,
        execution_id=execution_id,
        claimed_at=NOW,
        expected_run_event_sequence=run.event_sequence,
        expected_phase=run.phase,
    )
    store.commit_phase_execution_start(
        intent,
        expected_run_event_sequence=run.event_sequence,
        expected_phase=run.phase,
        start_committed_at=NOW,
    )
    store.resolve_phase_execution(
        PhaseExecutionResult(
            execution_id=execution_id,
            outcome=PhaseExecutionOutcome.COMPLETED,
            reported_at=NOW,
        )
    )


def _advance_to_phase(
    service: GuidedDemoApplicationService,
    store: SQLiteStore,
    target: RunPhase,
) -> None:
    execution_number = 1
    while store.load_demo_run("run-1").phase is not target:  # type: ignore[union-attr]
        run = store.load_demo_run("run-1")
        assert run is not None
        if run.phase in HARDWARE_EXECUTION_PHASES:
            _complete_hardware_phase(store, f"setup-execution-{execution_number}")
            execution_number += 1
        else:
            service.complete_current_phase("run-1", NOW)


def test_intermediate_success_claims_executes_and_advances_once() -> None:
    with SQLiteStore() as store:
        _started_service(store)
        executor = RecordingPhaseExecutor()

        result = GuidedDemoExecutionCoordinator(
            store,
            executor,  # type: ignore[arg-type]
            execution_id_factory=lambda: "execution-1",
            clock=_clock(),  # type: ignore[arg-type]
        ).execute_current_phase("run-1", CALIBRATIONS)

        assert result.intent.execution_id == "execution-1"
        assert result.intent.phase is RunPhase.P1_TRANSFER_S_TO_REACTOR
        assert result.intent.start_committed_at == NOW + timedelta(seconds=4)
        assert executor.calls == [RunPhase.P1_TRANSFER_S_TO_REACTOR]
        assert executor.executed_prepared[0] is executor.prepared[0]
        assert result.resolution.run.phase is (
            RunPhase.P1_TRANSFER_FIRST_LIQUID_TO_REACTOR
        )
        assert result.resolution.machine.state is MachineState.BUSY
        assert result.resolution.machine.active_execution is None


def test_preparation_failure_occurs_before_claim_or_hardware() -> None:
    with SQLiteStore() as store:
        _started_service(store)
        executor = RecordingPhaseExecutor(
            prepare_error=ValueError("invalid deterministic input")
        )

        with pytest.raises(ValueError, match="invalid deterministic input"):
            GuidedDemoExecutionCoordinator(
                store,
                executor,  # type: ignore[arg-type]
                execution_id_factory=lambda: "must-not-be-claimed",
                clock=lambda: NOW + timedelta(seconds=3),
            ).execute_current_phase("run-1", CALIBRATIONS)

        assert store.load_machine_snapshot().active_execution is None  # type: ignore[union-attr]
        assert executor.calls == []


def test_missing_column_readiness_does_not_persist_claim() -> None:
    with SQLiteStore() as store:
        service = _started_service(store)
        _advance_to_phase(
            service,
            store,
            RunPhase.COLUMN_FRACTION_COLLECTION,
        )
        executor = GuidedDemoPhaseExecutor(object())  # type: ignore[arg-type]

        with pytest.raises(MissingColumnFractionCollectionReadinessError):
            GuidedDemoExecutionCoordinator(
                store,
                executor,
                execution_id_factory=lambda: "missing-readiness",
                clock=lambda: NOW + timedelta(seconds=4),
            ).execute_current_phase("run-1", CALIBRATIONS)

        assert store.load_machine_snapshot().active_execution is None  # type: ignore[union-attr]


def test_invalid_calibration_input_does_not_persist_claim() -> None:
    with SQLiteStore() as store:
        _started_service(store)
        executor = GuidedDemoPhaseExecutor(object())  # type: ignore[arg-type]

        with pytest.raises(AttributeError):
            GuidedDemoExecutionCoordinator(
                store,
                executor,
                execution_id_factory=lambda: "invalid-calibration",
                clock=lambda: NOW + timedelta(seconds=3),
            ).execute_current_phase(
                "run-1",
                object(),  # type: ignore[arg-type]
            )

        assert store.load_machine_snapshot().active_execution is None  # type: ignore[union-attr]


def test_final_success_completes_run_and_releases_machine() -> None:
    with SQLiteStore() as store:
        service = _started_service(store)
        _advance_to_phase(
            service,
            store,
            RunPhase.COLUMN_FRACTION_COLLECTION,
        )
        executor = RecordingPhaseExecutor()

        result = GuidedDemoExecutionCoordinator(
            store,
            executor,  # type: ignore[arg-type]
            execution_id_factory=lambda: "execution-final",
            clock=_clock(),  # type: ignore[arg-type]
        ).execute_current_phase("run-1", CALIBRATIONS)

        assert executor.calls == [RunPhase.COLUMN_FRACTION_COLLECTION]
        assert result.resolution.run.status is RunStatus.COMPLETED
        assert result.resolution.machine.state is MachineState.READY


def test_timed_phase_and_active_claim_reject_without_hardware() -> None:
    with SQLiteStore() as store:
        service = _started_service(store)
        _complete_hardware_phase(store, "setup-execution-1")
        _complete_hardware_phase(store, "setup-execution-2")
        executor = RecordingPhaseExecutor()
        coordinator = GuidedDemoExecutionCoordinator(
            store,
            executor,  # type: ignore[arg-type]
            execution_id_factory=lambda: "execution-timed",
            clock=lambda: NOW + timedelta(seconds=4),
        )

        with pytest.raises(PhaseExecutionClaimError, match="does not support"):
            coordinator.execute_current_phase("run-1", CALIBRATIONS)
        assert executor.calls == []

        service.complete_current_phase("run-1", NOW + timedelta(seconds=4))
        run = store.load_demo_run("run-1")
        assert run is not None
        store.claim_phase_execution(
            run_id="run-1",
            execution_id="existing",
            claimed_at=NOW + timedelta(seconds=5),
            expected_run_event_sequence=run.event_sequence,
            expected_phase=run.phase,
        )
        with pytest.raises(PhaseExecutionClaimError, match="already active"):
            coordinator.execute_current_phase("run-1", CALIBRATIONS)
        assert executor.calls == []


def test_stop_before_claim_rejects_without_hardware() -> None:
    with SQLiteStore() as store:
        service = _started_service(store)
        service.request_stop_demo("run-1", NOW + timedelta(seconds=3))
        executor = RecordingPhaseExecutor()

        with pytest.raises(PhaseExecutionClaimError, match="RUNNING"):
            GuidedDemoExecutionCoordinator(
                store,
                executor,  # type: ignore[arg-type]
                execution_id_factory=lambda: "execution-after-stop",
                clock=lambda: NOW + timedelta(seconds=4),
            ).execute_current_phase("run-1", CALIBRATIONS)

        assert executor.calls == []


@pytest.mark.parametrize("change", ["phase", "sequence"])
def test_prepared_run_precondition_rejects_stale_state(change: str) -> None:
    with SQLiteStore() as store:
        service = _started_service(store)

        def change_run() -> None:
            if change == "phase":
                _complete_hardware_phase(store, "concurrent-execution")
            else:
                service.request_stop_demo(
                    "run-1", NOW + timedelta(seconds=3)
                )

        executor = RecordingPhaseExecutor(prepare_callback=change_run)
        with pytest.raises(PersistenceConflictError, match="precondition failed"):
            GuidedDemoExecutionCoordinator(
                store,
                executor,  # type: ignore[arg-type]
                execution_id_factory=lambda: "stale-plan",
                clock=lambda: NOW + timedelta(seconds=4),
            ).execute_current_phase("run-1", CALIBRATIONS)

        assert store.load_machine_snapshot().active_execution is None  # type: ignore[union-attr]
        assert executor.calls == []


@pytest.mark.parametrize(
    ("mismatch", "message"),
    [
        ("phase", "inconsistent start aggregate"),
        ("active_execution", "NO_ACTIVE_EXECUTION"),
        ("active_run_id", "inconsistent start aggregate"),
    ],
)
def test_post_claim_consistency_mismatch_leaves_token_unresolved(
    mismatch: str, message: str
) -> None:
    with InconsistentPostClaimStore(mismatch) as store:
        _started_service(store)
        executor = RecordingPhaseExecutor()

        with pytest.raises(PhaseExecutionStartCommitError, match=message):
            GuidedDemoExecutionCoordinator(
                store,
                executor,  # type: ignore[arg-type]
                execution_id_factory=lambda: "inconsistent",
                clock=lambda: NOW + timedelta(seconds=3),
            ).execute_current_phase("run-1", CALIBRATIONS)

        assert executor.calls == []
        assert SQLiteStore.load_machine_snapshot(store).active_execution is not None  # type: ignore[union-attr]


def test_concurrent_coordinators_execute_hardware_once(tmp_path: Path) -> None:
    database = tmp_path / "coordinator.db"
    with SQLiteStore(database) as store:
        _started_service(store)
    winner_can_finish = Event()
    executor = RecordingPhaseExecutor(callback=winner_can_finish.wait)
    start = Barrier(2)

    def invoke(execution_id: str) -> object:
        with SQLiteStore(database) as store:
            start.wait()
            try:
                return GuidedDemoExecutionCoordinator(
                    store,
                    executor,  # type: ignore[arg-type]
                    execution_id_factory=lambda: execution_id,
                    clock=_clock(),  # type: ignore[arg-type]
                ).execute_current_phase("run-1", CALIBRATIONS)
            except PhaseExecutionClaimError:
                winner_can_finish.set()
                raise

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(invoke, "execution-a"),
            pool.submit(invoke, "execution-b"),
        ]
        outcomes: list[object] = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except Exception as error:
                outcomes.append(error)

    assert len(executor.calls) == 1
    assert sum(isinstance(value, PhaseExecutionClaimError) for value in outcomes) == 1


def test_stop_during_execution_resolves_safe_boundary() -> None:
    with SQLiteStore() as store:
        service = _started_service(store)
        executor = RecordingPhaseExecutor(
            outcome=PhaseExecutionOutcome.STOPPED_AT_SAFE_BOUNDARY,
            callback=lambda: service.request_stop_demo(
                "run-1", NOW + timedelta(seconds=3, microseconds=500_000)
            ),
        )

        result = GuidedDemoExecutionCoordinator(
            store,
            executor,  # type: ignore[arg-type]
            execution_id_factory=lambda: "execution-stop",
            clock=_clock(),  # type: ignore[arg-type]
        ).execute_current_phase("run-1", CALIBRATIONS)

        assert result.resolution.run.status is RunStatus.ABORTED
        assert result.resolution.machine.state is MachineState.FLUSH_REQUIRED
        assert result.intent.start_committed_at is not None
        assert result.resolution.run.phase is RunPhase.P1_TRANSFER_S_TO_REACTOR


def test_stop_after_claim_before_hardware_resolves_without_executor() -> None:
    with StopAfterClaimStore() as store:
        service = _started_service(store)
        store.after_claim = lambda: service.request_stop_demo(
            "run-1", NOW + timedelta(seconds=3, microseconds=500_000)
        )
        executor = RecordingPhaseExecutor()

        result = GuidedDemoExecutionCoordinator(
            store,
            executor,  # type: ignore[arg-type]
            execution_id_factory=lambda: "execution-pre-stop",
            clock=_clock(),  # type: ignore[arg-type]
        ).execute_current_phase("run-1", CALIBRATIONS)

        assert executor.calls == []
        assert result.executor_result is None
        assert result.phase_result.outcome is (
            PhaseExecutionOutcome.STOPPED_AT_SAFE_BOUNDARY
        )
        assert result.resolution.run.status is RunStatus.ABORTED
        assert result.resolution.machine.state is MachineState.FLUSH_REQUIRED
        assert all(
            event.event_type
            is not MachineEventType.PHASE_EXECUTION_START_COMMITTED
            for event in store.load_events("MACHINE", "machine")
        )


@pytest.mark.parametrize(
    (
        "executor",
        "expected_outcome",
        "expected_runtime_reason",
        "carousel_untrusted",
    ),
    [
        (
            RecordingPhaseExecutor(
                outcome=PhaseExecutionOutcome.HARDWARE_COMMAND_FAILED,
                failure_reason="pump failed",
                runtime_fault_reason=(
                    RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED
                ),
            ),
            PhaseExecutionOutcome.HARDWARE_COMMAND_FAILED,
            RuntimeHardwareFaultReason.HARDWARE_COMMAND_FAILED,
            False,
        ),
        (
            RecordingPhaseExecutor(
                outcome=PhaseExecutionOutcome.HARDWARE_COMMAND_FAILED,
                failure_reason="carousel failed",
                runtime_fault_reason=(
                    RuntimeHardwareFaultReason.CAROUSEL_MOVEMENT_FAILED
                ),
            ),
            PhaseExecutionOutcome.HARDWARE_COMMAND_FAILED,
            RuntimeHardwareFaultReason.CAROUSEL_MOVEMENT_FAILED,
            True,
        ),
        (
            RecordingPhaseExecutor(
                outcome=PhaseExecutionOutcome.REQUIRED_CLEANUP_FAILED,
                cleanup_failure_reason="close failed",
                primary_failure_reason="aspirate failed",
                runtime_fault_reason=(
                    RuntimeHardwareFaultReason.REQUIRED_FOLLOWUP_FAILED
                ),
            ),
            PhaseExecutionOutcome.REQUIRED_CLEANUP_FAILED,
            RuntimeHardwareFaultReason.REQUIRED_FOLLOWUP_FAILED,
            False,
        ),
    ],
)
def test_structured_failure_is_persisted_as_runtime_fault(
    executor: RecordingPhaseExecutor,
    expected_outcome: PhaseExecutionOutcome,
    expected_runtime_reason: RuntimeHardwareFaultReason,
    carousel_untrusted: bool,
) -> None:
    with SQLiteStore() as store:
        _started_service(store)
        result = GuidedDemoExecutionCoordinator(
            store,
            executor,  # type: ignore[arg-type]
            execution_id_factory=lambda: "execution-fault",
            clock=_clock(),  # type: ignore[arg-type]
        ).execute_current_phase("run-1", CALIBRATIONS)

        assert result.phase_result.outcome is expected_outcome
        assert result.resolution.run.status is RunStatus.FAULTED
        assert result.resolution.machine.state is MachineState.RECOVERY_REQUIRED
        assert (
            result.resolution.machine.runtime_fault_reason
            is expected_runtime_reason
        )
        assert (
            result.resolution.machine.carousel_position_untrusted
            is carousel_untrusted
        )


def test_unexpected_executor_exception_leaves_claim_unresolved() -> None:
    with SQLiteStore() as store:
        _started_service(store)
        executor = RecordingPhaseExecutor(error=RuntimeError("unexpected"))
        coordinator = GuidedDemoExecutionCoordinator(
            store,
            executor,  # type: ignore[arg-type]
            execution_id_factory=lambda: "execution-ambiguous",
            clock=lambda: NOW + timedelta(seconds=3),
        )

        with pytest.raises(RuntimeError, match="unexpected"):
            coordinator.execute_current_phase("run-1", CALIBRATIONS)

        active = store.load_machine_snapshot().active_execution  # type: ignore[union-attr]
        assert active is not None
        assert active.execution_id == "execution-ambiguous"
        assert active.start_committed_at is not None
        assert executor.calls == [RunPhase.P1_TRANSFER_S_TO_REACTOR]


def test_resolution_persistence_failure_does_not_repeat_hardware() -> None:
    with FailingResolutionStore() as store:
        _started_service(store)
        executor = RecordingPhaseExecutor()
        coordinator = GuidedDemoExecutionCoordinator(
            store,
            executor,  # type: ignore[arg-type]
            execution_id_factory=lambda: "execution-persistence-failure",
            clock=_clock(),  # type: ignore[arg-type]
        )

        with pytest.raises(RuntimeError, match="resolution persistence failed"):
            coordinator.execute_current_phase("run-1", CALIBRATIONS)

        active = store.load_machine_snapshot().active_execution  # type: ignore[union-attr]
        assert active is not None
        assert active.execution_id == "execution-persistence-failure"
        assert executor.calls == [RunPhase.P1_TRANSFER_S_TO_REACTOR]
