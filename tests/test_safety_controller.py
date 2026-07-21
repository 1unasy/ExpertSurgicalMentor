import unittest

from expert_surgical_mentor.safety.controller import SafetyController, SafetyState


class SafetyControllerTest(unittest.TestCase):
    def test_unknown_stale_and_latched_states_fail_closed(self) -> None:
        controller = SafetyController(ttl_ns=10)
        with self.assertRaises(RuntimeError):
            controller.require_safe(1)
        controller.observe(False, 10)
        self.assertEqual(controller.require_safe(15), 0)
        with self.assertRaises(RuntimeError):
            controller.require_safe(21)
        controller.observe(True, 22)
        with self.assertRaises(RuntimeError):
            controller.require_safe(22)
        controller.observe(False, 23)
        self.assertEqual(controller.snapshot.state, SafetyState.STOP_LATCHED)
        controller.reset(24)
        with self.assertRaises(RuntimeError):
            controller.require_safe(24)

    def test_fault_cannot_be_cleared_by_a_normal_observation(self) -> None:
        controller = SafetyController()
        controller.fault(1)
        controller.observe(False, 2)
        self.assertEqual(controller.snapshot.state, SafetyState.SAFETY_FAULT)

    def test_pre_reset_observation_cannot_clear_unknown(self) -> None:
        controller = SafetyController()
        controller.observe(True, 10)
        controller.reset(20)
        controller.observe(False, 19)
        self.assertEqual(controller.snapshot.state, SafetyState.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
