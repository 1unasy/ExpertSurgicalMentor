"""Three-frame inventory workflow for safe, event-driven robot commands."""

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from ..case_validation import CaseInput, UnsupportedDiseaseError, validate_case_payload
from ..scenario_registry import Scenario, ScenarioRegistry
from .backend import QwenVisionInventoryBackend, VisionInventoryBackend
from .consensus import (
    CONSECUTIVE_FRAME_COUNT,
    InventoryConsensusError,
    require_unanimous_assessment,
)
from .inventory import InventoryResult, VisualInventoryAssessment
from .model_loader import ModelCatalog, ModelDependencyError, QuantizedVlmLoader
from .prompt import InventoryPromptBuilder
from .reporting import build_session_report


class InventoryWorkflowError(RuntimeError):
    """Raised when event order or workflow state is invalid."""


class InventoryPhase(str, Enum):
    IDLE = "idle"
    INITIAL_CHECK = "initial_check"
    PRE_MOVE_CHECK = "pre_move_check"
    MOVING = "moving"
    POST_MOVE_CHECK = "post_move_check"
    COMPLETED = "completed"


class InventoryEventKind(str, Enum):
    INITIAL_INVENTORY_CONFIRMED = "initial_inventory_confirmed"
    MOVE_COMMAND = "move_command"
    MOVE_VERIFIED = "move_verified"
    SESSION_COMPLETED = "session_completed"


@dataclass(frozen=True, slots=True)
class InventoryControllerEvent:
    """State or robot-command event emitted after a successful frame check."""

    kind: InventoryEventKind
    result: InventoryResult
    tool_id: str | None = None


class InventoryWorkflow:
    """Pure domain service; transport and camera buffering are kept outside."""

    def __init__(
        self,
        registry: ScenarioRegistry,
        prompt_builder: InventoryPromptBuilder,
        vision_backend: VisionInventoryBackend,
    ) -> None:
        self._registry = registry
        self._prompt_builder = prompt_builder
        self._vision_backend = vision_backend
        self._case: CaseInput | None = None
        self._scenario: Scenario | None = None
        self._current_result: InventoryResult | None = None

    @property
    def current_result(self) -> InventoryResult | None:
        return self._current_result

    def prepare_case(
        self,
        payload: Mapping[str, object],
        hand_detected: bool = False,
    ) -> None:
        self._case = None
        self._scenario = None
        self._current_result = None
        _ensure_hand_clear(hand_detected)
        case, scenario = validate_case_payload(payload, self._registry)
        self._case = case
        self._scenario = scenario

    def confirm_initial_inventory(
        self,
        images: Sequence[object],
        hand_detected: bool = False,
    ) -> InventoryResult:
        _ensure_hand_clear(hand_detected)
        self._require_active_case()
        result = self._assess_consensus(
            images=images,
            moved_tools=(),
            verification_tool=None,
        )
        self._current_result = result
        return result

    def verify_next_move(
        self,
        images: Sequence[object],
        hand_detected: bool = False,
    ) -> tuple[str, InventoryResult]:
        _ensure_hand_clear(hand_detected)
        current_result = self._require_current_result()
        if not current_result.move_queue:
            raise InventoryWorkflowError("이동할 물품이 없습니다.")

        tool_id = current_result.move_queue[0]
        result, assessment = self._assess_consensus_with_assessment(
            images=images,
            moved_tools=current_result.moved_tools,
            verification_tool=None,
        )
        if tool_id not in assessment.main_tray_tools:
            raise InventoryWorkflowError(
                f"수행 전 확인에서 {tool_id} 물품을 "
                "MainToolTray에서 확인하지 못했습니다."
            )
        self._current_result = result
        return tool_id, result

    def complete_move(
        self,
        tool_id: str,
        images: Sequence[object],
        hand_detected: bool = False,
    ) -> InventoryResult:
        _ensure_hand_clear(hand_detected)
        current_result = self._require_current_result()
        if not current_result.move_queue or tool_id != current_result.move_queue[0]:
            raise InventoryWorkflowError(
                f"현재 이동 순서가 아닌 물품입니다: {tool_id}"
            )

        moved_tools = (*current_result.moved_tools, tool_id)
        result = self._assess_consensus(
            images=images,
            moved_tools=moved_tools,
            verification_tool=tool_id,
        )
        self._current_result = result
        return result

    def build_report(self) -> dict[str, object]:
        if self._current_result is None:
            raise InventoryWorkflowError(
                "리포트를 생성할 활성화된 케이스가 없습니다."
            )
        return build_session_report(self._current_result)

    def _assess_consensus(
        self,
        *,
        images: Sequence[object],
        moved_tools: tuple[str, ...],
        verification_tool: str | None,
    ) -> InventoryResult:
        result, _ = self._assess_consensus_with_assessment(
            images=images,
            moved_tools=moved_tools,
            verification_tool=verification_tool,
        )
        return result

    def _assess_consensus_with_assessment(
        self,
        *,
        images: Sequence[object],
        moved_tools: tuple[str, ...],
        verification_tool: str | None,
    ) -> tuple[InventoryResult, VisualInventoryAssessment]:
        case, scenario = self._require_active_case()
        prompt = self._prompt_builder.build(
            patient_id=case.patient_id,
            case_id=case.case_id,
            disease_name=case.disease_name,
            required_tools=scenario.required_tools,
            verification_tool=verification_tool,
        )
        assessments = tuple(
            self._vision_backend.assess(image, prompt) for image in images
        )
        assessment = require_unanimous_assessment(assessments)
        result = InventoryResult.from_assessment(
            case=case,
            scenario=scenario,
            assessment=assessment,
            moved_tools=moved_tools,
            verification_tool=verification_tool,
        )
        return result, assessment

    def _require_active_case(self) -> tuple[CaseInput, Scenario]:
        if self._case is None or self._scenario is None:
            raise InventoryWorkflowError("활성화된 가상 케이스가 없습니다.")
        return self._case, self._scenario

    def _require_current_result(self) -> InventoryResult:
        self._require_active_case()
        if self._current_result is None:
            raise InventoryWorkflowError(
                "최초 인벤토리 확인이 완료되지 않았습니다."
            )
        return self._current_result


class VlmInventoryController:
    """Collect three fresh frames for every initial, pre-, and post-move check."""

    def __init__(self, workflow: InventoryWorkflow) -> None:
        self._workflow = workflow
        self._phase = InventoryPhase.IDLE
        self._frame_buffer: list[object] = []
        self._phase_started_at_ns: int | None = None
        self._commanded_tool: str | None = None
        self._hand_detected = False

    @property
    def phase(self) -> str:
        return self._phase.value

    @property
    def current_result(self) -> InventoryResult | None:
        return self._workflow.current_result

    def update_keyframe(
        self,
        image: object,
        captured_at_ns: int | None = None,
    ) -> InventoryControllerEvent | None:
        if self._phase not in (
            InventoryPhase.INITIAL_CHECK,
            InventoryPhase.PRE_MOVE_CHECK,
            InventoryPhase.POST_MOVE_CHECK,
        ):
            return None
        _ensure_hand_clear(self._hand_detected)
        if (
            captured_at_ns is not None
            and self._phase_started_at_ns is not None
            and captured_at_ns <= self._phase_started_at_ns
        ):
            return None

        self._frame_buffer.append(image)
        if len(self._frame_buffer) < CONSECUTIVE_FRAME_COUNT:
            return None

        images = tuple(self._frame_buffer)
        self._frame_buffer.clear()
        if self._phase is InventoryPhase.INITIAL_CHECK:
            result = self._workflow.confirm_initial_inventory(images, self._hand_detected)
            next_phase = (
                InventoryPhase.PRE_MOVE_CHECK
                if result.move_queue
                else InventoryPhase.COMPLETED
            )
            self._begin_phase(next_phase, captured_at_ns)
            return InventoryControllerEvent(
                InventoryEventKind.INITIAL_INVENTORY_CONFIRMED,
                result,
            )
        if self._phase is InventoryPhase.PRE_MOVE_CHECK:
            tool_id, result = self._workflow.verify_next_move(images, self._hand_detected)
            self._commanded_tool = tool_id
            self._begin_phase(InventoryPhase.MOVING, captured_at_ns)
            return InventoryControllerEvent(InventoryEventKind.MOVE_COMMAND, result, tool_id)

        if self._commanded_tool is None:
            raise InventoryWorkflowError("검증할 이동 명령이 없습니다.")
        tool_id = self._commanded_tool
        result = self._workflow.complete_move(tool_id, images, self._hand_detected)
        self._commanded_tool = None
        if result.move_queue:
            self._begin_phase(InventoryPhase.PRE_MOVE_CHECK, captured_at_ns)
            return InventoryControllerEvent(
                InventoryEventKind.MOVE_VERIFIED,
                result,
                tool_id,
            )
        self._begin_phase(InventoryPhase.COMPLETED, captured_at_ns)
        return InventoryControllerEvent(
            InventoryEventKind.SESSION_COMPLETED,
            result,
            tool_id,
        )

    def update_hand_detection(
        self,
        hand_detected: bool,
        event_time_ns: int | None = None,
    ) -> None:
        state_changed = hand_detected != self._hand_detected
        self._hand_detected = hand_detected
        if state_changed:
            self._frame_buffer.clear()
            if event_time_ns is not None:
                self._phase_started_at_ns = event_time_ns

    def handle_case_input(
        self,
        payload: Mapping[str, object],
        event_time_ns: int | None = None,
    ) -> None:
        if self._phase in {InventoryPhase.MOVING, InventoryPhase.POST_MOVE_CHECK}:
            raise InventoryWorkflowError(
                "이동 명령 발행 후 수행 결과 확인 전에는 "
                "새 케이스를 시작할 수 없습니다."
            )
        self._workflow.prepare_case(payload, self._hand_detected)
        self._commanded_tool = None
        self._begin_phase(InventoryPhase.INITIAL_CHECK, event_time_ns)

    def handle_move_completed(
        self,
        tool_id: str,
        case_id: str | None = None,
        event_time_ns: int | None = None,
    ) -> None:
        current_result = self._workflow.current_result
        if case_id is not None and (
            current_result is None or current_result.case_id != case_id
        ):
            raise InventoryWorkflowError(
                f"현재 케이스와 다른 이동 완료 이벤트입니다: {case_id}"
            )
        if self._phase is not InventoryPhase.MOVING or self._commanded_tool is None:
            raise InventoryWorkflowError(
                "로봇 이동 명령 전에는 이동 완료를 처리할 수 없습니다."
            )
        if tool_id != self._commanded_tool:
            raise InventoryWorkflowError(
                f"명령한 물품과 다른 이동 완료 이벤트입니다: {tool_id}"
            )
        _ensure_hand_clear(self._hand_detected)
        self._begin_phase(InventoryPhase.POST_MOVE_CHECK, event_time_ns)

    def build_session_report(self) -> dict[str, object]:
        return self._workflow.build_report()

    def _begin_phase(
        self,
        phase: InventoryPhase,
        started_at_ns: int | None,
    ) -> None:
        self._phase = phase
        self._phase_started_at_ns = started_at_ns
        self._frame_buffer.clear()


def _ensure_hand_clear(hand_detected: bool) -> None:
    if hand_detected:
        raise InventoryWorkflowError(
            "트레이 영역에서 손이 감지되어 로봇 동작을 중지합니다."
        )


def build_quantized_controller(
    project_root: str | Path,
    model_key: str | None = None,
) -> VlmInventoryController:
    """Compose the production controller; this is the only weight-loading entrypoint."""

    root = Path(project_root)
    registry = ScenarioRegistry.from_file(root / "config" / "scenario_registry.json")
    prompt_builder = InventoryPromptBuilder.from_file(
        root / "config" / "vlm_inventory_prompt.txt"
    )
    catalog = ModelCatalog.from_file(root / "config" / "vlm_models.json")
    loaded_vlm = QuantizedVlmLoader(catalog).load(model_key)
    backend = QwenVisionInventoryBackend(loaded_vlm)
    return VlmInventoryController(InventoryWorkflow(registry, prompt_builder, backend))


def run_ros_node(
    project_root: str | Path,
    model_key: str | None = None,
    ros_args: list[str] | None = None,
) -> None:
    """Run the optional ROS 2 transport around the tested domain controller."""

    try:
        import rclpy
        from cv_bridge import CvBridge
        from PIL import Image
        from rclpy.node import Node
        from sensor_msgs.msg import Image as RosImage
        from std_msgs.msg import String
    except ImportError as error:
        raise ModelDependencyError(
            "ROS 2 실행에는 rclpy, cv_bridge, sensor_msgs, std_msgs, Pillow가 필요합니다."
        ) from error

    controller = build_quantized_controller(project_root, model_key)

    class RosVlmInventoryNode(Node):
        def __init__(self) -> None:
            super().__init__("vlm_inventory_node")
            self._controller = controller
            self._bridge = CvBridge()
            self._state_publisher = self.create_publisher(String, "/inventory/state", 10)
            self._move_publisher = self.create_publisher(String, "/robot/move_command", 10)
            self._report_publisher = self.create_publisher(String, "/session/report", 10)
            self._error_publisher = self.create_publisher(String, "/inventory/error", 10)
            self.create_subscription(RosImage, "/camera/keyframe", self._on_keyframe, 10)
            self.create_subscription(String, "/safety/hand_state", self._on_hand_state, 10)
            self.create_subscription(String, "/case/input", self._on_case_input, 10)
            self.create_subscription(
                String,
                "/robot/move_completed",
                self._on_move_completed,
                10,
            )

        def _on_keyframe(self, message: RosImage) -> None:
            try:
                rgb_array = self._bridge.imgmsg_to_cv2(message, desired_encoding="rgb8")
                captured_at_ns = self._image_timestamp_ns(message)
                event = self._controller.update_keyframe(
                    Image.fromarray(rgb_array),
                    captured_at_ns,
                )
                if event is not None:
                    self._publish_controller_event(event)
            except Exception as error:
                self._publish_error(error)

        def _on_hand_state(self, message: String) -> None:
            try:
                payload = json.loads(message.data)
                if not isinstance(payload, dict) or set(payload) != {"hand_detected"}:
                    raise ValueError("hand_state는 hand_detected만 포함해야 합니다.")
                hand_detected = payload["hand_detected"]
                if not isinstance(hand_detected, bool):
                    raise TypeError("hand_detected는 boolean이어야 합니다.")
                self._controller.update_hand_detection(
                    hand_detected,
                    event_time_ns=self.get_clock().now().nanoseconds,
                )
            except (TypeError, ValueError) as error:
                self._publish_error(error)

        def _on_case_input(self, message: String) -> None:
            try:
                payload = json.loads(message.data)
                if not isinstance(payload, dict):
                    raise ValueError("case input은 JSON 객체여야 합니다.")
                self._controller.handle_case_input(
                    payload,
                    event_time_ns=self.get_clock().now().nanoseconds,
                )
            except UnsupportedDiseaseError as error:
                self._publish_json(self._error_publisher, error.as_dict())
            except Exception as error:
                self._publish_error(error)

        def _on_move_completed(self, message: String) -> None:
            try:
                payload = json.loads(message.data)
                if not isinstance(payload, dict) or set(payload) != {"case_id", "tool_id"}:
                    raise ValueError(
                        "move_completed는 case_id와 tool_id만 포함해야 합니다."
                    )
                case_id = payload["case_id"]
                tool_id = payload["tool_id"]
                if not isinstance(case_id, str) or not isinstance(tool_id, str):
                    raise TypeError("case_id와 tool_id는 문자열이어야 합니다.")
                self._controller.handle_move_completed(
                    tool_id,
                    case_id,
                    event_time_ns=self.get_clock().now().nanoseconds,
                )
            except Exception as error:
                self._publish_error(error)

        def _publish_controller_event(self, event: InventoryControllerEvent) -> None:
            self._publish_json(self._state_publisher, event.result.as_dict())
            if event.kind is InventoryEventKind.MOVE_COMMAND:
                if event.tool_id is None:
                    raise InventoryWorkflowError("이동 명령에 물품 ID가 없습니다.")
                self._publish_json(
                    self._move_publisher,
                    {
                        "case_id": event.result.case_id,
                        "tool_id": event.tool_id,
                    },
                )
            if self._controller.phase == InventoryPhase.COMPLETED.value:
                self._publish_report()

        def _image_timestamp_ns(self, message: RosImage) -> int:
            stamp = message.header.stamp
            timestamp_ns = stamp.sec * 1_000_000_000 + stamp.nanosec
            if timestamp_ns > 0:
                return timestamp_ns
            return self.get_clock().now().nanoseconds

        def _publish_report(self) -> None:
            self._publish_json(
                self._report_publisher,
                self._controller.build_session_report(),
            )

        def _publish_error(self, error: Exception) -> None:
            payload = {
                "status": "error",
                "error_type": type(error).__name__,
                "message": str(error),
            }
            self._publish_json(self._error_publisher, payload)
            self.get_logger().error(str(error))

        @staticmethod
        def _publish_json(publisher: object, payload: Mapping[str, object]) -> None:
            message = String()
            message.data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            publisher.publish(message)

    rclpy.init(args=ros_args)
    node = None
    try:
        node = RosVlmInventoryNode()
        rclpy.spin(node)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the quantized VLM inventory ROS 2 node.")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--model", default=None, help="Model key from config/vlm_models.json")
    args, ros_args = parser.parse_known_args(argv)
    run_ros_node(args.project_root, args.model, ros_args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
