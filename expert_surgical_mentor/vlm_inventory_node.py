"""Event-driven inventory workflow invoked at case start and move completion."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Mapping
from pathlib import Path

from .case_validation import CaseInput, UnsupportedDiseaseError, validate_case_payload
from .inventory_schema import InventoryResult
from .model_loader import ModelCatalog, ModelDependencyError, QuantizedVlmLoader
from .prompt_builder import InventoryPromptBuilder
from .reporting import build_session_report
from .scenario_registry import Scenario, ScenarioRegistry
from .vlm_backend import QwenVisionInventoryBackend, VisionInventoryBackend


class InventoryWorkflowError(RuntimeError):
    """Raised when event order or workflow state is invalid."""


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

    def start_case(
        self,
        payload: Mapping[str, object],
        image: object,
        yolo_detections: Iterable[Mapping[str, object]] = (),
    ) -> InventoryResult:
        self._case = None
        self._scenario = None
        self._current_result = None
        case, scenario = validate_case_payload(payload, self._registry)
        result = self._assess(
            case=case,
            scenario=scenario,
            image=image,
            yolo_detections=yolo_detections,
            moved_tools=(),
        )
        self._case = case
        self._scenario = scenario
        self._current_result = result
        return result

    def complete_move(
        self,
        tool_id: str,
        image: object,
        yolo_detections: Iterable[Mapping[str, object]] = (),
    ) -> InventoryResult:
        if self._case is None or self._scenario is None or self._current_result is None:
            raise InventoryWorkflowError("활성화된 가상 케이스가 없습니다.")
        if not self._current_result.move_queue or tool_id != self._current_result.move_queue[0]:
            raise InventoryWorkflowError(f"현재 이동 순서가 아닌 물품입니다: {tool_id}")

        moved_tools = (*self._current_result.moved_tools, tool_id)
        result = self._assess(
            case=self._case,
            scenario=self._scenario,
            image=image,
            yolo_detections=yolo_detections,
            moved_tools=moved_tools,
        )
        self._current_result = result
        return result

    def build_report(self) -> dict[str, object]:
        if self._current_result is None:
            raise InventoryWorkflowError("리포트를 생성할 활성화된 케이스가 없습니다.")
        return build_session_report(self._current_result)

    def _assess(
        self,
        *,
        case: CaseInput,
        scenario: Scenario,
        image: object,
        yolo_detections: Iterable[Mapping[str, object]],
        moved_tools: tuple[str, ...],
    ) -> InventoryResult:
        prompt = self._prompt_builder.build(
            patient_id=case.patient_id,
            case_id=case.case_id,
            disease_name=case.disease_name,
            required_tools=scenario.required_tools,
            yolo_detections=yolo_detections,
            moved_tools=moved_tools,
        )
        assessment = self._vision_backend.assess(image, prompt)
        return InventoryResult.from_assessment(
            case=case,
            scenario=scenario,
            assessment=assessment,
            moved_tools=moved_tools,
        )


class VlmInventoryController:
    """Camera/event adapter that prevents continuous per-frame VLM calls."""

    def __init__(self, workflow: InventoryWorkflow) -> None:
        self._workflow = workflow
        self._latest_keyframe: object | None = None
        self._keyframe_version = 0
        self._last_analysis_version = -1
        self._yolo_detections: tuple[Mapping[str, object], ...] = ()

    def update_keyframe(self, image: object) -> None:
        self._latest_keyframe = image
        self._keyframe_version += 1

    def update_yolo_detections(
        self,
        detections: Iterable[Mapping[str, object]],
    ) -> None:
        self._yolo_detections = tuple(dict(detection) for detection in detections)

    def handle_case_input(self, payload: Mapping[str, object]) -> InventoryResult:
        image, keyframe_version = self._require_keyframe(require_fresh=False)
        result = self._workflow.start_case(payload, image, self._yolo_detections)
        self._last_analysis_version = keyframe_version
        return result

    def handle_move_completed(
        self,
        tool_id: str,
        case_id: str | None = None,
    ) -> InventoryResult:
        current_result = self._workflow.current_result
        if case_id is not None and (
            current_result is None or current_result.case_id != case_id
        ):
            raise InventoryWorkflowError(f"현재 케이스와 다른 이동 완료 이벤트입니다: {case_id}")
        image, keyframe_version = self._require_keyframe(require_fresh=True)
        result = self._workflow.complete_move(tool_id, image, self._yolo_detections)
        self._last_analysis_version = keyframe_version
        return result

    def build_session_report(self) -> dict[str, object]:
        return self._workflow.build_report()

    def _require_keyframe(self, *, require_fresh: bool) -> tuple[object, int]:
        if self._latest_keyframe is None:
            raise InventoryWorkflowError("VLM 분석에 사용할 대표 프레임이 없습니다.")
        if require_fresh and self._keyframe_version <= self._last_analysis_version:
            raise InventoryWorkflowError("이동 완료 후의 새로운 대표 프레임이 필요합니다.")
        return self._latest_keyframe, self._keyframe_version


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
            self._report_publisher = self.create_publisher(String, "/session/report", 10)
            self._error_publisher = self.create_publisher(String, "/inventory/error", 10)
            self.create_subscription(RosImage, "/camera/keyframe", self._on_keyframe, 10)
            self.create_subscription(String, "/perception/detections", self._on_detections, 10)
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
                self._controller.update_keyframe(Image.fromarray(rgb_array))
            except Exception as error:
                self._publish_error(error)

        def _on_detections(self, message: String) -> None:
            try:
                detections = json.loads(message.data)
                if not isinstance(detections, list):
                    raise ValueError("detections는 배열이어야 합니다.")
                self._controller.update_yolo_detections(detections)
            except (TypeError, ValueError) as error:
                self._publish_error(error)

        def _on_case_input(self, message: String) -> None:
            try:
                payload = json.loads(message.data)
                if not isinstance(payload, dict):
                    raise ValueError("case input은 JSON 객체여야 합니다.")
                result = self._controller.handle_case_input(payload)
                self._publish_json(self._state_publisher, result.as_dict())
                if not result.move_queue:
                    self._publish_report()
            except UnsupportedDiseaseError as error:
                self._publish_json(self._error_publisher, error.as_dict())
            except Exception as error:
                self._publish_error(error)

        def _on_move_completed(self, message: String) -> None:
            try:
                payload = json.loads(message.data)
                if not isinstance(payload, dict) or set(payload) != {"case_id", "tool_id"}:
                    raise ValueError("move_completed는 case_id와 tool_id만 포함해야 합니다.")
                case_id = payload["case_id"]
                tool_id = payload["tool_id"]
                if not isinstance(case_id, str) or not isinstance(tool_id, str):
                    raise TypeError("case_id와 tool_id는 문자열이어야 합니다.")
                result = self._controller.handle_move_completed(tool_id, case_id)
                self._publish_json(self._state_publisher, result.as_dict())
                if not result.move_queue:
                    self._publish_report()
            except Exception as error:
                self._publish_error(error)

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
