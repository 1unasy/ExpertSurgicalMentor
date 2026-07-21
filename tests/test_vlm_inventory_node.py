import unittest
from collections import deque
from pathlib import Path

from expert_surgical_mentor.vlm.inventory import (
    InventoryContractError,
    VisualInventoryAssessment,
)
from expert_surgical_mentor.vlm.node import (
    InventoryWorkflow,
    InventoryWorkflowError,
    VlmInventoryController,
)
from expert_surgical_mentor.vlm.prompt import InventoryPrompt
from expert_surgical_mentor.scenario_registry import ScenarioRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "config" / "scenario_registry.json"


class StubPromptBuilder:
    def build(self, **_: object) -> InventoryPrompt:
        return InventoryPrompt("system", "user")


class StubVisionBackend:
    def __init__(self, assessments: list[VisualInventoryAssessment]) -> None:
        self._assessments = deque(assessments)
        self.calls: list[tuple[object, InventoryPrompt]] = []

    def assess(self, image: object, prompt: InventoryPrompt) -> VisualInventoryAssessment:
        self.calls.append((image, prompt))
        return self._assessments.popleft()


class InventoryWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ScenarioRegistry.from_file(REGISTRY_PATH)

    def test_vlm_runs_only_on_case_input_and_move_completion(self) -> None:
        all_present = VisualInventoryAssessment(
            present_required_tools=("XRay", "Pill", "Syringe"),
            missing_tools=(),
            assist_tray_tools=(),
        )
        after_xray = VisualInventoryAssessment(
            present_required_tools=("XRay", "Pill", "Syringe"),
            missing_tools=(),
            assist_tray_tools=("XRay",),
        )
        backend = StubVisionBackend([all_present, after_xray])
        workflow = InventoryWorkflow(self.registry, StubPromptBuilder(), backend)
        controller = VlmInventoryController(workflow)

        controller.update_keyframe("frame-before-case")
        self.assertEqual(len(backend.calls), 0)

        initial = controller.handle_case_input(
            {
                "patient_id": "PT7A21B",
                "case_id": "CASE_2026_001",
                "disease_name": "폐렴",
            }
        )
        self.assertEqual(initial.move_queue, ("XRay", "Pill", "Syringe"))
        self.assertEqual(len(backend.calls), 1)

        controller.update_keyframe("frame-after-move")
        self.assertEqual(len(backend.calls), 1)

        after_move = controller.handle_move_completed("XRay")
        self.assertEqual(after_move.moved_tools, ("XRay",))
        self.assertEqual(after_move.move_queue, ("Pill", "Syringe"))
        self.assertEqual(len(backend.calls), 2)
        self.assertEqual(backend.calls[1][0], "frame-after-move")

    def test_missing_tool_is_skipped_in_move_queue(self) -> None:
        backend = StubVisionBackend(
            [
                VisualInventoryAssessment(
                    present_required_tools=("XRay", "Syringe"),
                    missing_tools=("Pill",),
                    assist_tray_tools=(),
                )
            ]
        )
        controller = VlmInventoryController(
            InventoryWorkflow(self.registry, StubPromptBuilder(), backend)
        )
        controller.update_keyframe("frame")

        result = controller.handle_case_input(
            {
                "patient_id": "PT7A21B",
                "case_id": "CASE_2026_001",
                "disease_name": "폐렴",
            }
        )

        self.assertEqual(result.move_queue, ("XRay", "Syringe"))
        self.assertEqual(result.missing_tools, ("Pill",))

    def test_hand_detection_stops_inventory_inference(self) -> None:
        assessment = VisualInventoryAssessment(("Syringe", "Pill"), (), ())
        backend = StubVisionBackend([assessment])
        controller = VlmInventoryController(
            InventoryWorkflow(self.registry, StubPromptBuilder(), backend)
        )
        controller.update_keyframe("frame")
        controller.update_hand_detection(True)

        with self.assertRaisesRegex(InventoryWorkflowError, "손이 감지"):
            controller.handle_case_input(
                {
                    "patient_id": "P1COLD01",
                    "case_id": "COLD_001",
                    "disease_name": "감기",
                }
            )
        self.assertEqual(len(backend.calls), 0)

    def test_move_completion_requires_latest_keyframe_and_queued_tool(self) -> None:
        all_present = VisualInventoryAssessment(
            present_required_tools=("Syringe", "Pill"),
            missing_tools=(),
            assist_tray_tools=(),
        )
        controller = VlmInventoryController(
            InventoryWorkflow(
                self.registry,
                StubPromptBuilder(),
                StubVisionBackend([all_present]),
            )
        )

        with self.assertRaisesRegex(InventoryWorkflowError, "대표 프레임"):
            controller.handle_case_input(
                {
                    "patient_id": "P1COLD01",
                    "case_id": "COLD_001",
                    "disease_name": "감기",
                }
            )

        controller.update_keyframe("frame")
        controller.handle_case_input(
            {
                "patient_id": "P1COLD01",
                "case_id": "COLD_001",
                "disease_name": "감기",
            }
        )
        with self.assertRaisesRegex(InventoryWorkflowError, "새로운 대표 프레임"):
            controller.handle_move_completed("Syringe")

        controller.update_keyframe("frame-after-invalid-move")
        with self.assertRaisesRegex(InventoryWorkflowError, "이동 순서"):
            controller.handle_move_completed("XRay")

    def test_move_completion_rejects_a_later_queue_item(self) -> None:
        assessment = VisualInventoryAssessment(("XRay", "Pill", "Syringe"), (), ())
        backend = StubVisionBackend([assessment])
        controller = VlmInventoryController(
            InventoryWorkflow(self.registry, StubPromptBuilder(), backend)
        )
        controller.update_keyframe("initial")
        controller.handle_case_input(
            {
                "patient_id": "PT7A21B",
                "case_id": "CASE_2026_001",
                "disease_name": "폐렴",
            }
        )
        controller.update_keyframe("after-wrong-move")

        with self.assertRaisesRegex(InventoryWorkflowError, "이동 순서"):
            controller.handle_move_completed("Pill", case_id="CASE_2026_001")
        self.assertEqual(len(backend.calls), 1)

    def test_report_lists_required_moved_and_missing_tools(self) -> None:
        initial_assessment = VisualInventoryAssessment(
            present_required_tools=("XRay", "Syringe"),
            missing_tools=("Pill",),
            assist_tray_tools=(),
        )
        moved_assessment = VisualInventoryAssessment(
            present_required_tools=("XRay", "Syringe"),
            missing_tools=("Pill",),
            assist_tray_tools=("XRay",),
        )
        controller = VlmInventoryController(
            InventoryWorkflow(
                self.registry,
                StubPromptBuilder(),
                StubVisionBackend([initial_assessment, moved_assessment]),
            )
        )
        controller.update_keyframe("initial")
        controller.handle_case_input(
            {
                "patient_id": "PT7A21B",
                "case_id": "CASE_2026_001",
                "disease_name": "폐렴",
            }
        )
        controller.update_keyframe("after-xray")
        controller.handle_move_completed("XRay")

        report = controller.build_session_report()

        self.assertEqual(report["required_tools"], ["XRay", "Pill", "Syringe"])
        self.assertEqual(report["moved_tools"], ["XRay"])
        self.assertEqual(report["missing_tools"], ["Pill"])
        self.assertEqual(report["disease_name"], "폐렴")
        self.assertIn("X-ray를 옮겼으며", report["message"])
        self.assertIn("알약은 트레이에 없어", report["message"])

    def test_move_is_rejected_when_tool_remains_on_main_tray(self) -> None:
        assessment = VisualInventoryAssessment(("Syringe", "Pill"), (), ())
        backend = StubVisionBackend([assessment, assessment])
        controller = VlmInventoryController(
            InventoryWorkflow(self.registry, StubPromptBuilder(), backend)
        )
        controller.update_keyframe("initial")
        controller.handle_case_input(
            {"patient_id": "P1COLD01", "case_id": "COLD_001", "disease_name": "감기"}
        )
        controller.update_keyframe("failed-move")

        with self.assertRaisesRegex(InventoryContractError, "보조 트레이"):
            controller.handle_move_completed("Syringe")

    def test_failed_replacement_clears_previous_case(self) -> None:
        assessment = VisualInventoryAssessment(("Syringe", "Pill"), (), ())
        workflow = InventoryWorkflow(
            self.registry,
            StubPromptBuilder(),
            StubVisionBackend([assessment]),
        )
        workflow.start_case(
            {"patient_id": "P1COLD01", "case_id": "COLD_001", "disease_name": "감기"},
            "frame",
        )

        with self.assertRaises(ValueError):
            workflow.start_case(
                {"patient_id": "P2COLD02", "case_id": "COLD_002", "disease_name": "장염"},
                "frame",
            )
        with self.assertRaisesRegex(InventoryWorkflowError, "활성화된"):
            workflow.complete_move("Syringe", "frame")

    def test_delayed_completion_from_another_case_is_rejected(self) -> None:
        assessment = VisualInventoryAssessment(("Syringe", "Pill"), (), ())
        controller = VlmInventoryController(
            InventoryWorkflow(self.registry, StubPromptBuilder(), StubVisionBackend([assessment]))
        )
        controller.update_keyframe("initial")
        controller.handle_case_input(
            {"patient_id": "P1COLD01", "case_id": "COLD_001", "disease_name": "감기"}
        )
        controller.update_keyframe("after-move")

        with self.assertRaisesRegex(InventoryWorkflowError, "다른 이동 완료"):
            controller.handle_move_completed("Syringe", case_id="COLD_OLD")

    def test_completed_session_keeps_ordered_moved_tools(self) -> None:
        initial = VisualInventoryAssessment(("Syringe", "Pill"), (), ())
        after_syringe = VisualInventoryAssessment(
            ("Syringe", "Pill"), (), ("Syringe",)
        )
        after_pill = VisualInventoryAssessment(
            ("Pill",), ("Syringe",), ("Pill",)
        )
        backend = StubVisionBackend([initial, after_syringe, after_pill])
        controller = VlmInventoryController(
            InventoryWorkflow(self.registry, StubPromptBuilder(), backend)
        )
        controller.update_keyframe("initial")
        controller.handle_case_input(
            {"patient_id": "P1COLD01", "case_id": "COLD_001", "disease_name": "감기"}
        )
        controller.update_keyframe("after-syringe")
        controller.handle_move_completed("Syringe", case_id="COLD_001")
        controller.update_keyframe("after-pill")
        result = controller.handle_move_completed("Pill", case_id="COLD_001")

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.move_queue, ())
        self.assertEqual(result.moved_tools, ("Syringe", "Pill"))
        self.assertEqual(len(backend.calls), 3)


if __name__ == "__main__":
    unittest.main()
