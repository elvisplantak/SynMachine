"""Cooperative monotonic waits; no persistence, transport or recovery side effects."""

from decimal import Decimal
from fractions import Fraction
from time import monotonic_ns, sleep

from app.demo.operation_executor import CollectionTimerOutcome


class MonotonicExecutionTimer:
    """Stop wins at the deadline. Sleep is bounded, not a hard real-time guarantee.

    Clock/sleeper injection permits deterministic fault tests. Restart never
    restores an elapsed timer: the caller must retain unresolved execution intent.
    """

    def __init__(self, *, clock=monotonic_ns, sleeper=sleep, poll_seconds=0.05):
        if not 0 < poll_seconds <= 1:
            raise ValueError("timer polling interval must be in (0, 1] seconds")
        self._clock = clock
        self._sleep = sleeper
        self._poll_seconds = poll_seconds

    def wait(self, duration_seconds: Decimal, stop_requested):
        if (
            type(duration_seconds) is not Decimal
            or not duration_seconds.is_finite()
            or duration_seconds < 0
        ):
            raise ValueError("timer duration must be a finite non-negative Decimal")
        nanos = Fraction(duration_seconds) * 1_000_000_000
        budget = -(-nanos.numerator // nanos.denominator)
        previous = self._clock()
        if type(previous) is not int or previous < 0:
            raise ValueError("invalid monotonic clock reading")
        deadline = previous + budget
        while True:
            if stop_requested():
                return CollectionTimerOutcome.STOP_REQUESTED
            current = self._clock()
            if type(current) is not int or current < previous:
                raise ValueError("monotonic clock regressed or became invalid")
            previous = current
            if current >= deadline:
                return CollectionTimerOutcome.COMPLETED
            remaining = deadline - current
            # Compare integers before converting to float (even for huge durations).
            poll_nanos = int(self._poll_seconds * 1_000_000_000)
            self._sleep(min(remaining, max(1, poll_nanos)) / 1_000_000_000)

    def wait_pausable(self, duration_seconds: Decimal, control):
        """Charge only intervals proven RUNNING with unchanged control generation.

        Control returns (RUNNING/PAUSED/ABORTING, durable run event sequence).
        Polling intervals containing even a complete Pause/Resume pair are not
        charged. This is conservative (may extend the wait), never wall-clock
        reconstruction. Read overhead is excluded with monotonic clock bracketing.
        """
        from app.demo.run_models import RunStatus

        if (
            type(duration_seconds) is not Decimal
            or not duration_seconds.is_finite()
            or duration_seconds < 0
        ):
            raise ValueError("timer duration must be a finite non-negative Decimal")
        nanos = Fraction(duration_seconds) * 1_000_000_000
        remaining = -(-nanos.numerator // nanos.denominator)
        previous_time = 0
        previous_state = None
        while True:
            before = self._clock()
            if type(before) is not int or before < previous_time:
                raise ValueError("monotonic clock regressed or became invalid")
            state = control()
            after = self._clock()
            if type(after) is not int or after < before:
                raise ValueError("monotonic clock regressed or became invalid")
            if (
                type(state) is not tuple
                or len(state) != 2
                or type(state[0]) is not RunStatus
                or state[0] not in (RunStatus.RUNNING, RunStatus.PAUSED, RunStatus.ABORTING)
                or type(state[1]) is not int
                or state[1] < 0
                or (previous_state is not None and state[1] < previous_state[1])
            ):
                raise ValueError("invalid wait control state")
            if state[0] is RunStatus.ABORTING:
                return CollectionTimerOutcome.STOP_REQUESTED
            if previous_state == state and state[0] is RunStatus.RUNNING:
                remaining -= before - previous_time
            if state[0] is RunStatus.RUNNING and remaining <= 0:
                return CollectionTimerOutcome.COMPLETED
            previous_state, previous_time = state, after
            poll_nanos = max(1, int(self._poll_seconds * 1_000_000_000))
            delay = poll_nanos if state[0] is RunStatus.PAUSED else min(remaining, poll_nanos)
            self._sleep(delay / 1_000_000_000)
