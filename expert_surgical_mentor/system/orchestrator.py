"""Transport-neutral coordinator for VLM observations and robot commands."""

from dataclasses import replace
from threading import Lock
from uuid import uuid4

from ..case_validation import validate_case_payload
from ..scenario_registry import ScenarioRegistry
from ..safety.controller import SafetyController
from .contracts import InventoryObservation, MoveCommand, RobotResult
from .session_state import SessionState, accept_observation, accept_robot_result
from .session_state import SessionPhase


class DemoOrchestrator:
    def __init__(self, registry: ScenarioRegistry, safety: SafetyController) -> None:
        self._registry = registry
        self._safety = safety
        self._state: SessionState | None = None
        self._state_lock = Lock()

    @property
    def state(self) -> SessionState | None:
        return self._state

    def start_case(self, payload) -> SessionState:
        if self._state is not None and self._state.phase not in {
            SessionPhase.COMPLETED,
            SessionPhase.PARTIAL_COMPLETED,
            SessionPhase.ABORTED,
        }:
            raise RuntimeError("활성 세션은 명시적으로 종료하기 전 교체할 수 없습니다.")
        case, scenario = validate_case_payload(payload, self._registry)
        self._state = SessionState(uuid4().hex, case.case_id, scenario.required_tools)
        return self._state

    def accept_observation(
        self, observation: InventoryObservation, now_ns: int
    ) -> MoveCommand | None:
        state = self._require_state()
        epoch = self._safety.require_safe(now_ns)
        next_state, command = accept_observation(state, observation, epoch)
        self._state = next_state
        return command

    def accept_robot_result(self, result: RobotResult) -> SessionState:
        with self._state_lock:
            self._state = accept_robot_result(self._require_state(), result)
            return self._state

    def validate_dispatch(self, command: MoveCommand, now_ns: int) -> None:
        state = self._require_state()
        if state.active_command != command:
            raise RuntimeError("현재 활성 명령이 아니므로 실행할 수 없습니다.")
        self._safety.validate_epoch(command.safety_epoch, now_ns)

    def latch_safety_stop(self) -> SessionState | None:
        with self._state_lock:
            if self._state is not None and self._state.active_command is not None:
                self._state = replace(self._state, phase=SessionPhase.RECOVERY_REQUIRED)
            return self._state

    def _require_state(self) -> SessionState:
        if self._state is None:
            raise RuntimeError("활성 시연 세션이 없습니다.")
        return self._state
