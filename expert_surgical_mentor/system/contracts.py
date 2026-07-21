"""Transport-neutral contracts shared by VLM, safety, and robot workers."""

from dataclasses import dataclass
from enum import Enum


class Tray(str, Enum):
    MAIN = "MainToolTray"
    ASSIST = "AssistTray"


class RobotStatus(str, Enum):
    ACCEPTED = "accepted"
    RUNNING = "running"
    EXECUTION_COMPLETED = "execution_completed"
    FAILED = "failed"
    STOPPING = "stopping"
    STOPPED_SAFE = "stopped_safe"
    TIMEOUT = "timeout"


@dataclass(frozen=True, slots=True)
class MoveCommand:
    session_id: str
    command_id: str
    safety_epoch: int
    tool_id: str
    source_tray: Tray = Tray.MAIN
    target_tray: Tray = Tray.ASSIST


@dataclass(frozen=True, slots=True)
class RobotResult:
    session_id: str
    command_id: str
    safety_epoch: int
    tool_id: str
    status: RobotStatus


@dataclass(frozen=True, slots=True)
class InventoryObservation:
    session_id: str
    phase_generation: int
    frame_sequences: tuple[int, int, int]
    main_tray_tools: tuple[str, ...]
    assist_tray_tools: tuple[str, ...]

    def __post_init__(self) -> None:
        if len(set(self.frame_sequences)) != 3:
            raise ValueError("관측에는 서로 다른 3개 프레임이 필요합니다.")
        if tuple(sorted(self.frame_sequences)) != self.frame_sequences:
            raise ValueError("프레임 sequence는 증가해야 합니다.")
        overlap = set(self.main_tray_tools) & set(self.assist_tray_tools)
        if overlap:
            raise ValueError("한 물품은 두 트레이에 동시에 있을 수 없습니다.")

