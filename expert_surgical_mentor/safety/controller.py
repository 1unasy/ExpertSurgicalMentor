"""Fail-closed safety latch driven by YOLO hand observations."""

from dataclasses import dataclass
from enum import Enum


class SafetyState(str, Enum):
    UNKNOWN = "unknown"
    SAFE = "safe"
    STOP_LATCHED = "stop_latched"
    SAFETY_FAULT = "safety_fault"


@dataclass(frozen=True, slots=True)
class SafetySnapshot:
    state: SafetyState = SafetyState.UNKNOWN
    epoch: int = 0
    observed_at_ns: int | None = None


class SafetyController:
    def __init__(self, ttl_ns: int = 1_000_000_000) -> None:
        self._ttl_ns = ttl_ns
        self._snapshot = SafetySnapshot()

    @property
    def snapshot(self) -> SafetySnapshot:
        return self._snapshot

    def observe(self, hand_detected: bool, observed_at_ns: int) -> SafetySnapshot:
        if (
            self._snapshot.observed_at_ns is not None
            and observed_at_ns <= self._snapshot.observed_at_ns
        ):
            return self._snapshot
        if hand_detected:
            self._snapshot = SafetySnapshot(
                SafetyState.STOP_LATCHED,
                self._snapshot.epoch + 1,
                observed_at_ns,
            )
        elif self._snapshot.state in {SafetyState.UNKNOWN, SafetyState.SAFE}:
            self._snapshot = SafetySnapshot(
                SafetyState.SAFE, self._snapshot.epoch, observed_at_ns
            )
        return self._snapshot

    def require_safe(self, now_ns: int) -> int:
        snapshot = self._snapshot
        if snapshot.observed_at_ns is None or now_ns - snapshot.observed_at_ns > self._ttl_ns:
            raise RuntimeError("최신 YOLO 안전 관측이 없어 로봇 명령을 차단합니다.")
        if snapshot.state is not SafetyState.SAFE:
            raise RuntimeError(f"안전 상태가 아닙니다: {snapshot.state.value}")
        return snapshot.epoch

    def validate_epoch(self, expected_epoch: int, now_ns: int) -> None:
        current_epoch = self.require_safe(now_ns)
        if current_epoch != expected_epoch:
            raise RuntimeError("명령 생성 후 안전 상태가 변경되어 실행을 차단합니다.")

    def reset(self, observed_at_ns: int) -> SafetySnapshot:
        if self._snapshot.state is not SafetyState.STOP_LATCHED:
            raise RuntimeError("래치된 정지 상태가 없습니다.")
        self._snapshot = SafetySnapshot(
            SafetyState.UNKNOWN, self._snapshot.epoch, observed_at_ns
        )
        return self._snapshot

    def fault(self, observed_at_ns: int) -> SafetySnapshot:
        self._snapshot = SafetySnapshot(
            SafetyState.SAFETY_FAULT,
            self._snapshot.epoch + 1,
            observed_at_ns,
        )
        return self._snapshot
