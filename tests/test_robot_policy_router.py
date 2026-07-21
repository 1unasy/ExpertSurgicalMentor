import unittest
from threading import Event, Thread
from pathlib import Path

from expert_surgical_mentor.robot.node import RobotPolicyRouter
from expert_surgical_mentor.robot.policy_registry import RobotPolicyRegistry
from expert_surgical_mentor.system.contracts import MoveCommand, RobotStatus


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeRuntime:
    def __init__(self) -> None:
        self.checkpoints = []

    def run(self, policy, cancel_requested) -> None:
        self.checkpoints.append(policy.checkpoint)

    def stop(self) -> None:
        pass


class RobotPolicyRouterTest(unittest.TestCase):
    def test_routes_each_tool_once_and_deduplicates_command(self) -> None:
        registry = RobotPolicyRegistry.from_file(PROJECT_ROOT / "config" / "robot_policies.json")
        runtime = FakeRuntime()
        router = RobotPolicyRouter(registry, runtime)
        command = MoveCommand("session-1", "command-1", 2, "Syringe")

        first = router.execute(command)
        second = router.execute(command)

        self.assertEqual(first.status, RobotStatus.EXECUTION_COMPLETED)
        self.assertEqual(second, first)
        self.assertEqual(len(runtime.checkpoints), 1)
        self.assertIn("act_syringe", runtime.checkpoints[0])

    def test_rejects_a_distinct_command_while_policy_is_running(self) -> None:
        class BlockingRuntime(FakeRuntime):
            def __init__(self) -> None:
                super().__init__()
                self.started = Event()
                self.release = Event()

            def run(self, policy, cancel_requested) -> None:
                self.started.set()
                self.release.wait(timeout=1)

        registry = RobotPolicyRegistry.from_file(PROJECT_ROOT / "config" / "robot_policies.json")
        runtime = BlockingRuntime()
        router = RobotPolicyRouter(registry, runtime)
        thread = Thread(target=router.execute, args=(MoveCommand("s", "c1", 1, "Syringe"),))
        thread.start()
        self.assertTrue(runtime.started.wait(timeout=1))
        with self.assertRaises(RuntimeError):
            router.execute(MoveCommand("s", "c2", 1, "Pill"))
        runtime.release.set()
        thread.join(timeout=1)
        self.assertFalse(thread.is_alive())

    def test_concurrent_duplicate_waits_for_and_reuses_one_result(self) -> None:
        class BlockingRuntime(FakeRuntime):
            def __init__(self) -> None:
                super().__init__()
                self.started = Event()
                self.release = Event()

            def run(self, policy, cancel_requested) -> None:
                self.checkpoints.append(policy.checkpoint)
                self.started.set()
                self.release.wait(timeout=1)

        registry = RobotPolicyRegistry.from_file(PROJECT_ROOT / "config" / "robot_policies.json")
        runtime = BlockingRuntime()
        router = RobotPolicyRouter(registry, runtime)
        command = MoveCommand("s", "same", 1, "Syringe")
        results = []
        first = Thread(target=lambda: results.append(router.execute(command)))
        second = Thread(target=lambda: results.append(router.execute(command)))
        first.start()
        self.assertTrue(runtime.started.wait(timeout=1))
        second.start()
        runtime.release.set()
        first.join(timeout=1)
        second.join(timeout=1)
        self.assertEqual(len(runtime.checkpoints), 1)
        self.assertEqual(results[0], results[1])


if __name__ == "__main__":
    unittest.main()
