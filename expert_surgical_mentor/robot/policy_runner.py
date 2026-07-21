"""Injectable boundary around the installed LeRobot/OMX-AI runtime."""

from threading import Event
from typing import Protocol

from .policy_registry import RobotPolicy


class PolicyRuntime(Protocol):
    def run(self, policy: RobotPolicy, cancel_requested: Event) -> None: ...

    def stop(self) -> None: ...


class UnconfiguredLeRobotRuntime:
    def run(self, policy: RobotPolicy, cancel_requested: Event) -> None:
        raise RuntimeError(
            "LeRobot OMX-AI 실행 API가 연결되지 않았습니다. "
            f"checkpoint={policy.checkpoint}"
        )

    def stop(self) -> None:
        raise RuntimeError("OMX-AI driver stop API가 연결되지 않았습니다.")
