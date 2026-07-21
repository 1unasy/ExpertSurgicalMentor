import unittest

from expert_surgical_mentor.system.contracts import (
    InventoryObservation,
    RobotResult,
    RobotStatus,
)
from expert_surgical_mentor.system.session_state import (
    SessionPhase,
    SessionState,
    accept_observation,
    accept_robot_result,
)


def observation(state, main, assist=()):
    return InventoryObservation(
        state.session_id,
        state.phase_generation,
        (1, 2, 3),
        tuple(main),
        tuple(assist),
    )


class SessionStateTest(unittest.TestCase):
    def test_two_tools_require_robot_and_post_check_in_order(self) -> None:
        state = SessionState("session-1", "DEMO_COLD_001", ("Syringe", "Pill"))
        state, command = accept_observation(
            state, observation(state, ("Syringe", "Pill")), safety_epoch=4
        )
        self.assertIsNone(command)
        self.assertEqual(state.phase, SessionPhase.PRE_MOVE_CHECK)

        state, command = accept_observation(
            state, observation(state, ("Syringe", "Pill")), safety_epoch=4
        )
        self.assertEqual(command.tool_id, "Syringe")
        self.assertEqual(state.phase, SessionPhase.COMMAND_PENDING)

        completed = RobotResult(
            state.session_id,
            command.command_id,
            4,
            "Syringe",
            RobotStatus.EXECUTION_COMPLETED,
        )
        state = accept_robot_result(state, completed)
        state, next_command = accept_observation(
            state, observation(state, ("Pill",), ("Syringe",)), safety_epoch=4
        )
        self.assertIsNone(next_command)
        self.assertEqual(state.moved_tools, ("Syringe",))
        self.assertEqual(state.move_queue, ("Pill",))

    def test_post_check_keeps_state_when_current_or_previous_tool_is_absent(self) -> None:
        state = SessionState("session-1", "case-1", ("Syringe", "Pill"))
        state, _ = accept_observation(state, observation(state, ("Syringe", "Pill")), 1)
        state, command = accept_observation(state, observation(state, ("Syringe", "Pill")), 1)
        state = accept_robot_result(
            state,
            RobotResult("session-1", command.command_id, 1, "Syringe", RobotStatus.EXECUTION_COMPLETED),
        )
        unchanged, _ = accept_observation(state, observation(state, ("Pill",), ()), 1)
        self.assertEqual(unchanged, state)
        self.assertEqual(unchanged.moved_tools, ())

    def test_late_running_cannot_regress_post_move_check(self) -> None:
        state = SessionState("session-1", "case-1", ("Syringe", "Pill"))
        state, _ = accept_observation(state, observation(state, ("Syringe", "Pill")), 1)
        state, command = accept_observation(state, observation(state, ("Syringe", "Pill")), 1)
        state = accept_robot_result(
            state,
            RobotResult("session-1", command.command_id, 1, "Syringe", RobotStatus.EXECUTION_COMPLETED),
        )
        with self.assertRaises(ValueError):
            accept_robot_result(
                state,
                RobotResult("session-1", command.command_id, 1, "Syringe", RobotStatus.RUNNING),
            )

    def test_initial_assist_contents_are_invalid_not_moved(self) -> None:
        state = SessionState("session-1", "case-1", ("Syringe", "Pill"))
        state, command = accept_observation(
            state,
            observation(state, (), ("Syringe", "Pill")),
            1,
        )
        self.assertIsNone(command)
        self.assertEqual(state.phase, SessionPhase.SETUP_INVALID)
        self.assertEqual(state.moved_tools, ())


if __name__ == "__main__":
    unittest.main()
