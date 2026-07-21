"""A small non-reentrant lease for serial VLM and ACT GPU phases."""

from contextlib import contextmanager
from threading import Lock


class GpuLease:
    def __init__(self) -> None:
        self._lock = Lock()
        self._owner: str | None = None

    @contextmanager
    def acquire(self, owner: str):
        if not self._lock.acquire(blocking=False):
            raise RuntimeError(f"GPU는 {self._owner} 작업이 사용 중입니다.")
        self._owner = owner
        try:
            yield
        finally:
            self._owner = None
            self._lock.release()

