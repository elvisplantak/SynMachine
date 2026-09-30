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
