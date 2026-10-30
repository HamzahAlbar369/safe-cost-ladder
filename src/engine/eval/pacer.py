"""Adaptive pacing against Anthropic rate limits (one Pacer per model; limits are per model).

It reads the `anthropic-ratelimit-*` headers returned on every live call: when the remaining request or output
token budget runs low it pauses new sends briefly, and on a 429 it halves the number of calls in flight and
pauses for the server's `retry-after`. After a run of successes the allowance creeps back up. Time spent
waiting here is returned to the caller as `queue_wait_ms` and is NOT part of a call's latency (Hamzah, D2.1).
"""

from __future__ import annotations

import threading
import time

from engine.contracts import RateLimitInfo

LOW_WATER_FRACTION = 0.05  # pause when this little of the request limit remains
RECOVER_AFTER = 20  # successful calls before the allowance grows by one
PAUSE_S = 2.0


class Pacer:
    def __init__(self, max_inflight: int, *, clock=time.monotonic, sleep=time.sleep) -> None:
        self.max_inflight = max_inflight
        self.allowed = max_inflight
        self.inflight = 0
        self.resume_at = 0.0
        self._ok_streak = 0
        self._cond = threading.Condition()
        self._clock, self._sleep = clock, sleep
        self.rate_limited = 0  # 429s seen (reported in the run summary)

    def acquire(self, min_output_tokens: int = 0) -> float:
        """Block until a send is allowed; returns the milliseconds spent waiting."""
        start = self._clock()
        with self._cond:
            while self.inflight >= self.allowed or self._clock() < self.resume_at:
                wait = max(self.resume_at - self._clock(), 0.0) if self.inflight < self.allowed else 0.5
                self._cond.wait(timeout=max(wait, 0.05))
            self.inflight += 1
        return (self._clock() - start) * 1000

    def release(self, info: RateLimitInfo | None, *, rate_limited: bool, next_max_tokens: int = 0) -> None:
        with self._cond:
            self.inflight -= 1
            if rate_limited:
                self.rate_limited += 1
                self.allowed = max(1, self.allowed // 2)
                self._ok_streak = 0
                self.resume_at = max(
                    self.resume_at, self._clock() + ((info and info.retry_after_s) or PAUSE_S)
                )
            else:
                self._ok_streak += 1
                if self._ok_streak >= RECOVER_AFTER and self.allowed < self.max_inflight:
                    self.allowed += 1
                    self._ok_streak = 0
                if info and self._running_low(info, next_max_tokens):
                    self.resume_at = max(self.resume_at, self._clock() + PAUSE_S)
            self._cond.notify_all()

    @staticmethod
    def _running_low(info: RateLimitInfo, next_max_tokens: int) -> bool:
        if info.requests_remaining is not None and info.requests_limit:
            floor = max(2, LOW_WATER_FRACTION * info.requests_limit)
            if info.requests_remaining <= floor:
                return True
        return info.output_tokens_remaining is not None and info.output_tokens_remaining < 2 * next_max_tokens
