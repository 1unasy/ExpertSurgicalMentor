"""Idempotent semantic-command router for object-specific ACT policies."""

from threading import Event, Lock

from .policy_registry import RobotPolicyRegistry
from .policy_runner import PolicyRuntime
from ..system.contracts import MoveCommand, RobotResult, RobotStatus, Tray


class RobotPolicyRouter:
    def __init__(self, registry: RobotPolicyRegistry, runtime: PolicyRuntime) -> None:
        self._registry = registry
        self._runtime = runtime
        self._results: dict[str, RobotResult] = {}
        self._result_lock = Lock()
        self._execution_lock = Lock()
        self._active_command: MoveCommand | None = None
        self._stop_requested: set[str] = set()
        self._inflight: dict[str, Event] = {}
        self._commands: dict[str, MoveCommand] = {}
        self._cancel_requested: dict[str, Event] = {}
        self._stop_acknowledged: dict[str, Event] = {}

    def execute(self, command: MoveCommand) -> RobotResult:
        if command.source_tray is not Tray.MAIN or command.target_tray is not Tray.ASSIST:
            raise ValueError("로봇은 MainToolTray에서 AssistTray로만 이동합니다.")
        policy = self._registry.require(command.tool_id)
        with self._result_lock:
            cached = self._results.get(command.command_id)
            wait_for = self._inflight.get(command.command_id)
            registered = self._commands.get(command.command_id)
            if registered is not None and registered != command:
                raise ValueError("같은 command_id에 다른 명령 내용이 전달되었습니다.")
            if cached is not None:
                return cached
            if wait_for is None and self._active_command is not None:
                raise RuntimeError("다른 로봇 명령이 실행 중입니다.")
            if wait_for is None:
                self._active_command = command
                wait_for = Event()
                self._inflight[command.command_id] = wait_for
                self._commands[command.command_id] = command
                self._cancel_requested[command.command_id] = Event()
                self._stop_acknowledged[command.command_id] = Event()
                owns_execution = True
            else:
                owns_execution = False
        if not owns_execution:
            wait_for.wait()
            with self._result_lock:
                return self._results[command.command_id]
        with self._execution_lock:
            try:
                cancel_requested = self._cancel_requested[command.command_id]
                self._runtime.run(policy, cancel_requested)
                stopped = cancel_requested.is_set()
                if stopped:
                    self._stop_acknowledged[command.command_id].wait()
                status = (
                    RobotStatus.STOPPED_SAFE
                    if stopped
                    else RobotStatus.EXECUTION_COMPLETED
                )
            except TimeoutError:
                status = RobotStatus.TIMEOUT
            except Exception:
                status = RobotStatus.FAILED
            result = RobotResult(
                command.session_id,
                command.command_id,
                command.safety_epoch,
                command.tool_id,
                status,
            )
            with self._result_lock:
                if command.command_id in self._stop_requested:
                    result = RobotResult(
                        command.session_id,
                        command.command_id,
                        command.safety_epoch,
                        command.tool_id,
                        RobotStatus.STOPPED_SAFE,
                    )
                self._results[command.command_id] = result
                self._active_command = None
                self._stop_requested.discard(command.command_id)
                self._cancel_requested.pop(command.command_id, None)
                self._stop_acknowledged.pop(command.command_id, None)
                self._inflight.pop(command.command_id).set()
            return result

    def stop(self) -> None:
        with self._result_lock:
            active = self._active_command
            if active is not None:
                self._stop_requested.add(active.command_id)
                self._cancel_requested[active.command_id].set()
                acknowledgement = self._stop_acknowledged[active.command_id]
            else:
                acknowledgement = None
        try:
            self._runtime.stop()
        finally:
            if acknowledgement is not None:
                acknowledgement.set()

    def close_session(self, session_id: str) -> None:
        with self._result_lock:
            self._results = {
                command_id: result
                for command_id, result in self._results.items()
                if result.session_id != session_id
            }
            self._commands = {
                command_id: command
                for command_id, command in self._commands.items()
                if command.session_id != session_id
            }
