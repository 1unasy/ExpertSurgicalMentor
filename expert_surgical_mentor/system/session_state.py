"""Pure reducer for the Syringe/Pill demonstration session."""

from dataclasses import dataclass, replace
from enum import Enum
from uuid import uuid4

from .contracts import InventoryObservation, MoveCommand, RobotResult, RobotStatus


class SessionPhase(str, Enum):
    INITIAL_CHECK = "initial_check"
    PRE_MOVE_CHECK = "pre_move_check"
    COMMAND_PENDING = "command_pending"
    MOVING = "moving"
    POST_MOVE_CHECK = "post_move_check"
    COMPLETED = "completed"
    PARTIAL_COMPLETED = "partial_completed"
    SETUP_INVALID = "setup_invalid"
    RECOVERY_REQUIRED = "recovery_required"
    ABORTED = "aborted"


@dataclass(frozen=True, slots=True)
class SessionState:
    session_id: str
    case_id: str
    required_tools: tuple[str, ...]
    phase: SessionPhase = SessionPhase.INITIAL_CHECK
    phase_generation: int = 0
    move_queue: tuple[str, ...] = ()
    moved_tools: tuple[str, ...] = ()
    missing_tools: tuple[str, ...] = ()
    active_command: MoveCommand | None = None


def accept_observation(
    state: SessionState,
    observation: InventoryObservation,
    safety_epoch: int,
) -> tuple[SessionState, MoveCommand | None]:
    _require_observation_scope(state, observation)
    main = set(observation.main_tray_tools)
    assist = set(observation.assist_tray_tools)

    if state.phase is SessionPhase.INITIAL_CHECK:
        missing = tuple(tool for tool in state.required_tools if tool not in main | assist)
        queue = tuple(tool for tool in state.required_tools if tool in main)
        if assist:
            phase = SessionPhase.SETUP_INVALID
            queue = ()
        elif not queue:
            phase = SessionPhase.COMPLETED if not missing else SessionPhase.PARTIAL_COMPLETED
        else:
            phase = SessionPhase.PRE_MOVE_CHECK
        return replace(
            state,
            phase=phase,
            phase_generation=state.phase_generation + 1,
            move_queue=queue,
            moved_tools=(),
            missing_tools=missing,
        ), None

    if state.phase is SessionPhase.PRE_MOVE_CHECK:
        if not state.move_queue or state.move_queue[0] not in main:
            return state, None
        command = MoveCommand(
            session_id=state.session_id,
            command_id=uuid4().hex,
            safety_epoch=safety_epoch,
            tool_id=state.move_queue[0],
        )
        return replace(state, phase=SessionPhase.COMMAND_PENDING, active_command=command), command

    if state.phase is SessionPhase.POST_MOVE_CHECK:
        command = _require_active_command(state)
        expected_assist = set(state.moved_tools) | {command.tool_id}
        if not expected_assist.issubset(assist):
            return state, None
        moved = tuple(tool for tool in state.required_tools if tool in expected_assist)
        queue = tuple(tool for tool in state.move_queue if tool != command.tool_id)
        if queue:
            phase = SessionPhase.PRE_MOVE_CHECK
        else:
            phase = SessionPhase.PARTIAL_COMPLETED if state.missing_tools else SessionPhase.COMPLETED
        return replace(
            state,
            phase=phase,
            phase_generation=state.phase_generation + 1,
            move_queue=queue,
            moved_tools=moved,
            active_command=None,
        ), None

    raise ValueError(f"현재 단계에서는 VLM 관측을 받을 수 없습니다: {state.phase.value}")


def accept_robot_result(state: SessionState, result: RobotResult) -> SessionState:
    if state.phase in {
        SessionPhase.COMPLETED,
        SessionPhase.PARTIAL_COMPLETED,
        SessionPhase.SETUP_INVALID,
        SessionPhase.RECOVERY_REQUIRED,
        SessionPhase.ABORTED,
    }:
        return state
    command = _require_active_command(state)
    if (result.session_id, result.command_id, result.tool_id) != (
        command.session_id,
        command.command_id,
        command.tool_id,
    ):
        raise ValueError("현재 활성 명령과 일치하지 않는 로봇 결과입니다.")
    if result.safety_epoch != command.safety_epoch:
        return replace(state, phase=SessionPhase.RECOVERY_REQUIRED)
    if result.status in {RobotStatus.ACCEPTED, RobotStatus.RUNNING}:
        if state.phase not in {SessionPhase.COMMAND_PENDING, SessionPhase.MOVING}:
            raise ValueError("현재 단계에서 진행 상태를 받을 수 없습니다.")
        return replace(state, phase=SessionPhase.MOVING)
    if result.status is RobotStatus.EXECUTION_COMPLETED:
        if state.phase not in {SessionPhase.COMMAND_PENDING, SessionPhase.MOVING}:
            raise ValueError("현재 단계에서 실행 완료를 받을 수 없습니다.")
        return replace(
            state,
            phase=SessionPhase.POST_MOVE_CHECK,
            phase_generation=state.phase_generation + 1,
        )
    return replace(state, phase=SessionPhase.RECOVERY_REQUIRED)


def _require_observation_scope(
    state: SessionState, observation: InventoryObservation
) -> None:
    if observation.session_id != state.session_id:
        raise ValueError("다른 세션의 VLM 관측입니다.")
    if observation.phase_generation != state.phase_generation:
        raise ValueError("현재 단계와 일치하지 않는 VLM 관측입니다.")


def _require_active_command(state: SessionState) -> MoveCommand:
    if state.active_command is None:
        raise ValueError("활성 로봇 명령이 없습니다.")
    return state.active_command
