import unittest
from pathlib import Path

from expert_surgical_mentor.safety.controller import SafetyController
from expert_surgical_mentor.scenario_registry import ScenarioRegistry
from expert_surgical_mentor.system.contracts import InventoryObservation
from expert_surgical_mentor.system.orchestrator import DemoOrchestrator


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class SystemOrchestratorTest(unittest.TestCase):
    def test_requires_fresh_safe_before_creating_robot_command(self) -> None:
        safety = SafetyController(ttl_ns=100)
        orchestrator = DemoOrchestrator(
            ScenarioRegistry.from_file(PROJECT_ROOT / "config" / "scenario_registry.json"),
            safety,
        )
        state = orchestrator.start_case(
            {"case_id": "DEMO_001", "patient_id": "PT77AA", "disease_name": "감기"}
        )
        initial = InventoryObservation(
            state.session_id, 0, (1, 2, 3), ("Syringe", "Pill"), ()
        )
        with self.assertRaises(RuntimeError):
            orchestrator.accept_observation(initial, 10)

        safety.observe(False, 10)
        self.assertIsNone(orchestrator.accept_observation(initial, 11))
        state = orchestrator.state
        pre = InventoryObservation(
            state.session_id, state.phase_generation, (4, 5, 6), ("Syringe", "Pill"), ()
        )
        command = orchestrator.accept_observation(pre, 12)
        self.assertEqual(command.tool_id, "Syringe")
        with self.assertRaises(RuntimeError):
            orchestrator.start_case(
                {"case_id": "DEMO_002", "patient_id": "PT88BB", "disease_name": "감기"}
            )
        orchestrator.validate_dispatch(command, 13)
        safety.observe(True, 14)
        with self.assertRaises(RuntimeError):
            orchestrator.validate_dispatch(command, 14)


if __name__ == "__main__":
    unittest.main()
