import json
import unittest
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from expert_surgical_mentor.case_validation import CaseInput
from expert_surgical_mentor.vlm.backend import QwenVisionInventoryBackend
from expert_surgical_mentor.vlm.inventory import (
    InventoryContractError,
    InventoryResult,
    VisualInventoryAssessment,
)
from expert_surgical_mentor.vlm.model_loader import ModelCatalog, QuantizedVlmLoader
from expert_surgical_mentor.vlm.prompt import InventoryPromptBuilder
from expert_surgical_mentor.scenario_registry import Scenario


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_CONFIG_PATH = PROJECT_ROOT / "config" / "vlm_models.json"
PROMPT_PATH = PROJECT_ROOT / "config" / "vlm_inventory_prompt.txt"


class InventorySchemaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.case = CaseInput("PT7A21B", "CASE_2026_001", "폐렴")
        self.scenario = Scenario(
            "SIM_PNEUMONIA",
            "폐렴",
            ("XRay", "Pill", "Syringe"),
        )

    def test_builds_authoritative_result_in_required_order(self) -> None:
        assessment = VisualInventoryAssessment.from_model_text(
            '```json\n{"present_required_tools":["Syringe","XRay"],'
            '"missing_tools":["Pill"],"assist_tray_tools":["XRay"]}\n```'
        )

        result = InventoryResult.from_assessment(
            case=self.case,
            scenario=self.scenario,
            assessment=assessment,
            moved_tools=("XRay",),
            verification_tool="XRay",
        )

        self.assertEqual(result.present_required_tools, ("XRay", "Syringe"))
        self.assertEqual(result.missing_tools, ("Pill",))
        self.assertEqual(result.move_queue, ("Syringe",))
        self.assertEqual(result.moved_tools, ("XRay",))
        self.assertEqual(result.status, "ready_with_missing_tools")

    def test_rejects_incomplete_partition(self) -> None:
        assessment = VisualInventoryAssessment(
            present_required_tools=("XRay",),
            missing_tools=("Pill",),
            assist_tray_tools=(),
        )

        with self.assertRaisesRegex(InventoryContractError, "모든 필요 물품"):
            InventoryResult.from_assessment(
                case=self.case,
                scenario=self.scenario,
                assessment=assessment,
            )

    def test_rejects_unregistered_tool_from_model(self) -> None:
        assessment = VisualInventoryAssessment.from_model_text(
            '{"present_required_tools":["XRay","UnknownTool"],'
            '"missing_tools":["Pill","Syringe"],"assist_tray_tools":[]}'
        )
        with self.assertRaisesRegex(InventoryContractError, "UnknownTool"):
            InventoryResult.from_assessment(
                case=self.case,
                scenario=self.scenario,
                assessment=assessment,
            )

    def test_serialized_result_matches_output_contract(self) -> None:
        assessment = VisualInventoryAssessment(
            present_required_tools=("XRay", "Syringe"),
            missing_tools=("Pill",),
            assist_tray_tools=(),
        )
        result = InventoryResult.from_assessment(
            case=self.case,
            scenario=self.scenario,
            assessment=assessment,
        )

        self.assertEqual(
            result.as_dict(),
            {
                "status": "ready_with_missing_tools",
                "patient_id": "PT7A21B",
                "case_id": "CASE_2026_001",
                "scenario_id": "SIM_PNEUMONIA",
                "required_tools": ["XRay", "Pill", "Syringe"],
                "present_required_tools": ["XRay", "Syringe"],
                "missing_tools": ["Pill"],
                "move_queue": ["XRay", "Syringe"],
                "moved_tools": [],
            },
        )

    def test_assist_tray_tool_is_not_added_to_move_queue(self) -> None:
        assessment = VisualInventoryAssessment(
            present_required_tools=("XRay", "Pill", "Syringe"),
            missing_tools=(),
            assist_tray_tools=("XRay",),
        )

        result = InventoryResult.from_assessment(self.case, self.scenario, assessment)

        self.assertEqual(result.move_queue, ("Pill", "Syringe"))

    def test_partial_assist_inventory_is_not_reported_as_empty(self) -> None:
        assessment = VisualInventoryAssessment(
            present_required_tools=("XRay",),
            missing_tools=("Pill", "Syringe"),
            assist_tray_tools=("XRay",),
        )

        result = InventoryResult.from_assessment(self.case, self.scenario, assessment)

        self.assertEqual(result.status, "ready_with_missing_tools")
        self.assertEqual(result.move_queue, ())

    def test_previously_delivered_tool_may_leave_assist_tray(self) -> None:
        assessment = VisualInventoryAssessment(
            present_required_tools=("Pill", "Syringe"),
            missing_tools=("XRay",),
            assist_tray_tools=("Pill",),
        )

        result = InventoryResult.from_assessment(
            self.case,
            self.scenario,
            assessment,
            moved_tools=("XRay", "Pill"),
            verification_tool="Pill",
        )

        self.assertEqual(result.missing_tools, ())
        self.assertEqual(result.move_queue, ("Syringe",))
        self.assertEqual(result.moved_tools, ("XRay", "Pill"))


class ModelLoaderTest(unittest.TestCase):
    def test_every_model_is_configured_for_four_bit_loading(self) -> None:
        catalog = ModelCatalog.from_file(MODEL_CONFIG_PATH)

        self.assertEqual(
            [spec.key for spec in catalog.models],
            ["qwen3_vl_2b", "qwen2_5_vl_3b", "qwen3_vl_4b"],
        )
        for spec in catalog.models:
            with self.subTest(model=spec.key):
                self.assertTrue(spec.quantization.load_in_4bit)
                self.assertEqual(spec.quantization.quant_type, "nf4")
                self.assertTrue(spec.quantization.use_double_quant)

    def test_loader_passes_quantization_config_without_downloading_in_test(self) -> None:
        catalog = ModelCatalog.from_file(MODEL_CONFIG_PATH)
        calls: dict[str, object] = {}

        class FakeBitsAndBytesConfig:
            def __init__(self, **kwargs: object) -> None:
                calls["quantization"] = kwargs

        class FakeModelType:
            @classmethod
            def from_pretrained(cls, model_id: str, **kwargs: object) -> object:
                calls["model_id"] = model_id
                calls["model_kwargs"] = kwargs
                return object()

        class FakeProcessorType:
            @classmethod
            def from_pretrained(cls, model_id: str) -> object:
                calls["processor_id"] = model_id
                return object()

        fake_torch = SimpleNamespace(bfloat16="bfloat16")
        fake_transformers = SimpleNamespace(
            AutoProcessor=FakeProcessorType,
            BitsAndBytesConfig=FakeBitsAndBytesConfig,
            Qwen3VLForConditionalGeneration=FakeModelType,
            Qwen2_5_VLForConditionalGeneration=FakeModelType,
        )

        def fake_import(module_name: str) -> object:
            return {"torch": fake_torch, "transformers": fake_transformers}[module_name]

        with patch(
            "expert_surgical_mentor.vlm.model_loader.importlib.import_module",
            side_effect=fake_import,
        ):
            QuantizedVlmLoader(catalog).load("qwen3_vl_2b")

        quantization = calls["quantization"]
        self.assertIsInstance(quantization, dict)
        self.assertTrue(quantization["load_in_4bit"])
        self.assertEqual(quantization["bnb_4bit_quant_type"], "nf4")
        self.assertTrue(quantization["bnb_4bit_use_double_quant"])
        self.assertEqual(quantization["bnb_4bit_compute_dtype"], "bfloat16")
        self.assertEqual(calls["model_id"], "Qwen/Qwen3-VL-2B-Instruct")


class PromptBuilderTest(unittest.TestCase):
    def test_prompt_contains_only_runtime_context_and_fixed_rules(self) -> None:
        builder = InventoryPromptBuilder.from_file(PROMPT_PATH)
        prompt = builder.build(
            patient_id="PT7A21B",
            case_id="CASE_2026_001",
            disease_name="폐렴",
            required_tools=("XRay", "Pill", "Syringe"),
        )

        self.assertIn("[해야 할 것]", prompt.system_text)
        self.assertIn("[하지 말아야 할 것]", prompt.system_text)
        self.assertIn("물품을 인식하지 않는다", prompt.system_text)
        runtime = json.loads(prompt.user_text)
        self.assertEqual(runtime["required_tools"], ["XRay", "Pill", "Syringe"])
        self.assertIsNone(runtime["verification_tool"])
        self.assertNotIn("safety_state", runtime)
        self.assertNotIn("yolo_detections", runtime)
        self.assertNotIn("scene_tools", runtime)


class QwenVisionInventoryBackendTest(unittest.TestCase):
    def test_assess_builds_deterministic_request_and_parses_output(self) -> None:
        calls: dict[str, object] = {}

        class FakeInputs(dict):
            def to(self, device: str) -> "FakeInputs":
                calls["device"] = device
                return self

        class FakeOutput:
            def __getitem__(self, key: object) -> str:
                calls["output_slice"] = key
                return "generated"

        class FakeProcessor:
            def apply_chat_template(self, messages: object, **kwargs: object) -> str:
                calls["messages"] = messages
                calls["template_kwargs"] = kwargs
                return "rendered"

            def __call__(self, **kwargs: object) -> FakeInputs:
                calls["processor_kwargs"] = kwargs
                return FakeInputs(input_ids=SimpleNamespace(shape=(1, 2)))

            def batch_decode(self, generated: object, **kwargs: object) -> list[str]:
                calls["decoded"] = generated
                calls["decode_kwargs"] = kwargs
                return [
                    '{"present_required_tools":["XRay"],"missing_tools":["Pill"],'
                    '"assist_tray_tools":[]}'
                ]

        class FakeModel:
            device = "cuda:0"

            def generate(self, **kwargs: object) -> FakeOutput:
                calls["generate_kwargs"] = kwargs
                return FakeOutput()

        fake_torch = SimpleNamespace(inference_mode=nullcontext)
        fake_qwen_utils = SimpleNamespace(
            process_vision_info=lambda messages: (["image-input"], None)
        )

        def fake_import(module_name: str) -> object:
            return {"torch": fake_torch, "qwen_vl_utils": fake_qwen_utils}[module_name]

        loaded = SimpleNamespace(model=FakeModel(), processor=FakeProcessor())
        backend = QwenVisionInventoryBackend(loaded)
        with patch(
            "expert_surgical_mentor.vlm.backend.importlib.import_module",
            side_effect=fake_import,
        ):
            assessment = backend.assess(
                "image",
                SimpleNamespace(system_text="system", user_text="user"),
            )

        self.assertEqual(assessment.present_required_tools, ("XRay",))
        self.assertEqual(assessment.missing_tools, ("Pill",))
        self.assertEqual(calls["device"], "cuda:0")
        self.assertFalse(calls["generate_kwargs"]["do_sample"])
        self.assertEqual(calls["generate_kwargs"]["max_new_tokens"], 128)


if __name__ == "__main__":
    unittest.main()
