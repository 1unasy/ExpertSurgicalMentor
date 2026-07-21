import unittest
from collections import deque
from pathlib import Path

from expert_surgical_mentor.case_validation import validate_case_payload
from expert_surgical_mentor.vlm.inventory import (
    InventoryContractError,
    InventoryResult,
    VisualInventoryAssessment,
)
from expert_surgical_mentor.vlm.node import (
    InventoryConsensusError,
    InventoryWorkflow,
    InventoryWorkflowError,
    VlmInventoryController,
)
from expert_surgical_mentor.vlm.prompt import InventoryPrompt
from expert_surgical_mentor.scenario_registry import ScenarioRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "config" / "scenario_registry.json"
COLD_CASE = {
    "patient_id": "P1COLD01",
    "case_id": "COLD_001",
    "disease_name": "감기",
}
PNEUMONIA_CASE = {
    "patient_id": "PT7A21B",
    "case_id": "CASE_2026_001",
    "disease_name": "폐렴",
}


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


def repeated(
    assessment: VisualInventoryAssessment,
    count: int = 3,
) -> list[VisualInventoryAssessment]:
    return [assessment] * count


class InventoryWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ScenarioRegistry.from_file(REGISTRY_PATH)

    def build_controller(
        self,
        assessments: list[VisualInventoryAssessment],
    ) -> tuple[VlmInventoryController, StubVisionBackend]:
        backend = StubVisionBackend(assessments)
        workflow = InventoryWorkflow(self.registry, StubPromptBuilder(), backend)
        return VlmInventoryController(workflow), backend

    def feed_three_frames(
        self,
        controller: VlmInventoryController,
        prefix: str,
        start_time_ns: int,
    ):
        self.assertIsNone(controller.update_keyframe(f"{prefix}-1", start_time_ns))
        self.assertIsNone(controller.update_keyframe(f"{prefix}-2", start_time_ns + 1))
        return controller.update_keyframe(f"{prefix}-3", start_time_ns + 2)

    def test_each_phase_requires_three_matching_frames(self) -> None:
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
        controller, backend = self.build_controller(
            repeated(all_present, 6) + repeated(after_xray)
        )

        controller.handle_case_input(PNEUMONIA_CASE, event_time_ns=100)
        self.assertEqual(len(backend.calls), 0)

        initial = self.feed_three_frames(controller, "initial", 101)
        self.assertEqual(initial.kind, "initial_inventory_confirmed")
        self.assertEqual(initial.result.move_queue, ("XRay", "Pill", "Syringe"))
        self.assertEqual(len(backend.calls), 3)

        command = self.feed_three_frames(controller, "before-xray", 104)
        self.assertEqual(command.kind, "move_command")
        self.assertEqual(command.tool_id, "XRay")
        self.assertEqual(len(backend.calls), 6)

        controller.handle_move_completed(
            "XRay",
            case_id="CASE_2026_001",
            event_time_ns=200,
        )
        verified = self.feed_three_frames(controller, "after-xray", 201)
        self.assertEqual(verified.kind, "move_verified")
        self.assertEqual(verified.result.moved_tools, ("XRay",))
        self.assertEqual(verified.result.move_queue, ("Pill", "Syringe"))
        self.assertEqual(len(backend.calls), 9)

    def test_inconsistent_frames_stop_and_allow_a_new_three_frame_check(self) -> None:
        all_present = VisualInventoryAssessment(("Syringe", "Pill"), (), ())
        pill_missing = VisualInventoryAssessment(("Syringe",), ("Pill",), ())
        controller, backend = self.build_controller(
            [all_present, pill_missing, all_present] + repeated(all_present)
        )
        controller.handle_case_input(COLD_CASE)

        controller.update_keyframe("unstable-1")
        controller.update_keyframe("unstable-2")
        with self.assertRaisesRegex(InventoryConsensusError, "3개 프레임"):
            controller.update_keyframe("unstable-3")

        self.assertEqual(controller.phase, "initial_check")
        confirmed = self.feed_three_frames(controller, "stable", 1)
        self.assertEqual(confirmed.kind, "initial_inventory_confirmed")
        self.assertEqual(len(backend.calls), 6)

    def test_pre_move_check_stops_if_queue_head_disappears(self) -> None:
        all_present = VisualInventoryAssessment(("Syringe", "Pill"), (), ())
        syringe_missing = VisualInventoryAssessment(("Pill",), ("Syringe",), ())
        controller, backend = self.build_controller(
            repeated(all_present)
            + repeated(syringe_missing)
            + repeated(all_present)
        )
        controller.handle_case_input(COLD_CASE)
        self.feed_three_frames(controller, "initial", 1)

        controller.update_keyframe("missing-1")
        controller.update_keyframe("missing-2")
        with self.assertRaisesRegex(InventoryWorkflowError, "MainToolTray"):
            controller.update_keyframe("missing-3")

        self.assertEqual(controller.phase, "pre_move_check")
        self.assertEqual(controller.current_result.move_queue, ("Syringe", "Pill"))

        command = self.feed_three_frames(controller, "recheck", 10)
        self.assertEqual(command.kind, "move_command")
        self.assertEqual(command.tool_id, "Syringe")
        self.assertEqual(len(backend.calls), 9)

    def test_post_move_check_does_not_commit_until_tool_is_on_assist_tray(self) -> None:
        all_present = VisualInventoryAssessment(("Syringe", "Pill"), (), ())
        after_syringe = VisualInventoryAssessment(
            ("Syringe", "Pill"), (), ("Syringe",)
        )
        controller, _ = self.build_controller(
            repeated(all_present, 9) + repeated(after_syringe)
        )
        controller.handle_case_input(COLD_CASE)
        self.feed_three_frames(controller, "initial", 1)
        self.feed_three_frames(controller, "before", 4)
        controller.handle_move_completed("Syringe", case_id="COLD_001")

        controller.update_keyframe("failed-1")
        controller.update_keyframe("failed-2")
        with self.assertRaisesRegex(InventoryContractError, "보조 트레이"):
            controller.update_keyframe("failed-3")

        self.assertEqual(controller.phase, "post_move_check")
        self.assertEqual(controller.current_result.moved_tools, ())
        verified = self.feed_three_frames(controller, "retry", 20)
        self.assertEqual(verified.result.moved_tools, ("Syringe",))

    def test_later_post_check_requires_previous_moved_tool_to_remain_on_assist(self) -> None:
        case, scenario = validate_case_payload(COLD_CASE, self.registry)
        assessment = VisualInventoryAssessment(("Syringe", "Pill"), (), ("Pill",))

        with self.assertRaisesRegex(InventoryContractError, "전체"):
            InventoryResult.from_assessment(
                case,
                scenario,
                assessment,
                moved_tools=("Syringe", "Pill"),
                verification_tool="Pill",
            )

    def test_frames_captured_before_move_completion_are_ignored(self) -> None:
        all_present = VisualInventoryAssessment(("Syringe", "Pill"), (), ())
        after_syringe = VisualInventoryAssessment(
            ("Syringe", "Pill"), (), ("Syringe",)
        )
        controller, backend = self.build_controller(
            repeated(all_present, 6) + repeated(after_syringe)
        )
        controller.handle_case_input(COLD_CASE, event_time_ns=100)
        self.feed_three_frames(controller, "initial", 101)
        self.feed_three_frames(controller, "before", 104)
        controller.handle_move_completed(
            "Syringe",
            case_id="COLD_001",
            event_time_ns=200,
        )

        self.assertIsNone(controller.update_keyframe("stale", captured_at_ns=199))
        self.assertEqual(len(backend.calls), 6)
        self.assertIsNone(controller.update_keyframe("after-1", captured_at_ns=201))
        self.assertIsNone(controller.update_keyframe("after-2", captured_at_ns=202))
        verified = controller.update_keyframe("after-3", captured_at_ns=203)
        self.assertEqual(verified.kind, "move_verified")

    def test_move_completion_requires_the_commanded_tool_and_case(self) -> None:
        all_present = VisualInventoryAssessment(("XRay", "Pill", "Syringe"), (), ())
        controller, backend = self.build_controller(repeated(all_present, 6))
        controller.handle_case_input(PNEUMONIA_CASE)
        self.feed_three_frames(controller, "initial", 1)

        with self.assertRaisesRegex(InventoryWorkflowError, "이동 명령 전"):
            controller.handle_move_completed("XRay", case_id="CASE_2026_001")

        self.feed_three_frames(controller, "before", 4)
        with self.assertRaisesRegex(InventoryWorkflowError, "다른 이동 완료"):
            controller.handle_move_completed("XRay", case_id="OLD_CASE")
        with self.assertRaisesRegex(InventoryWorkflowError, "명령한 물품과 다른"):
            controller.handle_move_completed("Pill", case_id="CASE_2026_001")
        self.assertEqual(len(backend.calls), 6)

    def test_case_cannot_be_replaced_while_a_move_is_unverified(self) -> None:
        all_present = VisualInventoryAssessment(("Syringe", "Pill"), (), ())
        controller, _ = self.build_controller(repeated(all_present, 6))
        controller.handle_case_input(COLD_CASE)
        self.feed_three_frames(controller, "initial", 1)
        self.feed_three_frames(controller, "before", 4)

        with self.assertRaisesRegex(InventoryWorkflowError, "새 케이스"):
            controller.handle_case_input(PNEUMONIA_CASE)

        controller.handle_move_completed("Syringe", case_id="COLD_001")
        with self.assertRaisesRegex(InventoryWorkflowError, "새 케이스"):
            controller.handle_case_input(PNEUMONIA_CASE)

    def test_hand_detection_clears_partial_consensus_and_blocks_inference(self) -> None:
        assessment = VisualInventoryAssessment(("Syringe", "Pill"), (), ())
        controller, backend = self.build_controller(repeated(assessment))
        controller.handle_case_input(COLD_CASE)
        controller.update_keyframe("before-hand")
        controller.update_hand_detection(True)

        with self.assertRaisesRegex(InventoryWorkflowError, "손이 감지"):
            controller.update_keyframe("hand-present")
        self.assertEqual(len(backend.calls), 0)

        controller.update_hand_detection(False)
        self.assertIsNone(controller.update_keyframe("clear-1"))
        self.assertIsNone(controller.update_keyframe("clear-2"))
        event = controller.update_keyframe("clear-3")
        self.assertEqual(event.kind, "initial_inventory_confirmed")

    def test_frames_from_before_hand_clear_are_ignored(self) -> None:
        assessment = VisualInventoryAssessment(("Syringe", "Pill"), (), ())
        controller, backend = self.build_controller(repeated(assessment))
        controller.handle_case_input(COLD_CASE, event_time_ns=100)
        controller.update_hand_detection(True, event_time_ns=110)
        controller.update_hand_detection(False, event_time_ns=120)

        self.assertIsNone(controller.update_keyframe("stale", captured_at_ns=119))
        self.feed_three_frames(controller, "clear", 121)

        self.assertEqual(len(backend.calls), 3)

    def test_completed_session_repeats_pre_and_post_checks_for_each_tool(self) -> None:
        initial = VisualInventoryAssessment(("Syringe", "Pill"), (), ())
        after_syringe = VisualInventoryAssessment(
            ("Syringe", "Pill"), (), ("Syringe",)
        )
        before_pill = VisualInventoryAssessment(
            ("Syringe", "Pill"), (), ("Syringe",)
        )
        after_pill = VisualInventoryAssessment(
            ("Syringe", "Pill"), (), ("Syringe", "Pill")
        )
        controller, backend = self.build_controller(
            repeated(initial, 6)
            + repeated(after_syringe)
            + repeated(before_pill)
            + repeated(after_pill)
        )
        controller.handle_case_input(COLD_CASE)
        self.feed_three_frames(controller, "initial", 1)
        first_command = self.feed_three_frames(controller, "before-syringe", 4)
        self.assertEqual(first_command.tool_id, "Syringe")
        controller.handle_move_completed("Syringe", case_id="COLD_001")
        first_verified = self.feed_three_frames(controller, "after-syringe", 7)
        self.assertEqual(first_verified.result.move_queue, ("Pill",))

        second_command = self.feed_three_frames(controller, "before-pill", 10)
        self.assertEqual(second_command.tool_id, "Pill")
        controller.handle_move_completed("Pill", case_id="COLD_001")
        completed = self.feed_three_frames(controller, "after-pill", 13)

        self.assertEqual(completed.kind, "session_completed")
        self.assertEqual(completed.result.status, "completed")
        self.assertEqual(completed.result.move_queue, ())
        self.assertEqual(completed.result.moved_tools, ("Syringe", "Pill"))
        self.assertEqual(controller.phase, "completed")
        self.assertEqual(len(backend.calls), 15)

    def test_report_uses_last_committed_inventory_state(self) -> None:
        initial = VisualInventoryAssessment(("XRay", "Syringe"), ("Pill",), ())
        controller, _ = self.build_controller(repeated(initial))
        controller.handle_case_input(PNEUMONIA_CASE)
        self.feed_three_frames(controller, "initial", 1)

        report = controller.build_session_report()

        self.assertEqual(report["required_tools"], ["XRay", "Pill", "Syringe"])
        self.assertEqual(report["moved_tools"], [])
        self.assertEqual(report["missing_tools"], ["Pill"])
        self.assertEqual(report["disease_name"], "폐렴")


if __name__ == "__main__":
    unittest.main()
