import json
import unittest
from pathlib import Path

from expert_surgical_mentor.case_validation import validate_case_payload
from expert_surgical_mentor.scenario_registry import ScenarioRegistry


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DemoCaseTest(unittest.TestCase):
    def test_demo_case_contains_only_input_fields_and_resolves_two_tools(self) -> None:
        payload = json.loads(
            (PROJECT_ROOT / "data" / "demo_cases_syringe_pill.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(set(payload), {"case_id", "patient_id", "disease_name"})

        registry = ScenarioRegistry.from_file(
            PROJECT_ROOT / "config" / "scenario_registry.json"
        )
        _, scenario = validate_case_payload(payload, registry)

        self.assertEqual(scenario.scenario_id, "SIM_COLD")
        self.assertEqual(scenario.required_tools, ("Syringe", "Pill"))


if __name__ == "__main__":
    unittest.main()
