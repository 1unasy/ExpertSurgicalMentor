from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from expert_surgical_mentor.case_validation import (
    CaseValidationError,
    UnsupportedDiseaseError,
    validate_case_payload,
)
from expert_surgical_mentor.scenario_registry import ScenarioRegistry, ScenarioRegistryError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = PROJECT_ROOT / "config" / "scenario_registry.json"


class CaseValidatorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ScenarioRegistry.from_file(REGISTRY_PATH)

    def test_valid_case_resolves_registered_scenario(self) -> None:
        case, scenario = validate_case_payload(
            {
                "patient_id": "PT7A21B",
                "case_id": "CASE_2026_001",
                "disease_name": "폐렴",
            },
            self.registry,
        )

        self.assertEqual(case.patient_id, "PT7A21B")
        self.assertEqual(scenario.scenario_id, "SIM_PNEUMONIA")
        self.assertEqual(scenario.required_tools, ("XRay", "Pill", "Syringe"))

    def test_patient_id_requires_letters_digits_and_safe_length(self) -> None:
        for patient_id in ["123456", "PATIENT", "홍길동01", "A1", "A1-234", ""]:
            with self.subTest(patient_id=patient_id):
                with self.assertRaisesRegex(CaseValidationError, "patient_id"):
                    validate_case_payload(
                        {
                            "patient_id": patient_id,
                            "case_id": "CASE_2026_001",
                            "disease_name": "감기",
                        },
                        self.registry,
                    )

    def test_unknown_fields_are_rejected(self) -> None:
        with self.assertRaisesRegex(CaseValidationError, "허용되지 않은 필드"):
            validate_case_payload(
                {
                    "patient_id": "PT7A21B",
                    "case_id": "CASE_2026_001",
                    "disease_name": "감기",
                    "patient_name": "홍길동",
                },
                self.registry,
            )

    def test_unregistered_disease_uses_fixed_message(self) -> None:
        with self.assertRaises(UnsupportedDiseaseError) as error:
            validate_case_payload(
                {
                    "patient_id": "PT7A21B",
                    "case_id": "CASE_2026_001",
                    "disease_name": "장염",
                },
                self.registry,
            )

        self.assertEqual(str(error.exception), "등록되지 않은 질환입니다.")
        self.assertEqual(
            error.exception.as_dict(),
            {
                "status": "unsupported_disease",
                "message": "등록되지 않은 질환입니다.",
            },
        )

    def test_registry_rejects_unknown_tool(self) -> None:
        raw_registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
        raw_registry["scenarios"][0]["required_tools"].append("UnknownTool")

        with tempfile.TemporaryDirectory() as temp_dir:
            invalid_path = Path(temp_dir) / "invalid_registry.json"
            invalid_path.write_text(json.dumps(raw_registry), encoding="utf-8")
            with self.assertRaisesRegex(ScenarioRegistryError, "UnknownTool"):
                ScenarioRegistry.from_file(invalid_path)

    def test_all_fifteen_virtual_cases_match_registry_expectations(self) -> None:
        case_dataset_path = PROJECT_ROOT / "data" / "virtual_cases_15.json"
        cases = json.loads(case_dataset_path.read_text(encoding="utf-8"))["cases"]

        self.assertEqual(len(cases), 15)
        self.assertEqual(len({case["case_id"] for case in cases}), 15)
        for raw_case in cases:
            with self.subTest(case_id=raw_case["case_id"]):
                _, scenario = validate_case_payload(
                    {
                        "patient_id": raw_case["patient_id"],
                        "case_id": raw_case["case_id"],
                        "disease_name": raw_case["disease_name"],
                    },
                    self.registry,
                )
                scene_tools = set(raw_case["scene_tools"])
                expected_present = [
                    tool for tool in scenario.required_tools if tool in scene_tools
                ]
                expected_missing = [
                    tool for tool in scenario.required_tools if tool not in scene_tools
                ]
                self.assertEqual(
                    raw_case["expected_present_required_tools"],
                    expected_present,
                )
                self.assertEqual(raw_case["expected_missing_tools"], expected_missing)
                self.assertEqual(raw_case["expected_move_queue"], expected_present)


if __name__ == "__main__":
    unittest.main()
