import unittest

from expert_surgical_mentor.vlm.hf_evaluation import (
    PickPlaceEpisode,
    comparison_markdown,
    phase_timestamps,
    select_balanced_episodes,
    summarize_model_records,
)


class HfVlmEvaluationTest(unittest.TestCase):
    def test_balanced_selection_and_phase_timestamps(self):
        episodes = tuple(
            PickPlaceEpisode(index, task, tool, 0, index * 20.0, index * 20.0 + 10.0)
            for index, task, tool in (
                (0, "Pick up syringe", "Syringe"),
                (1, "Pick up syringe", "Syringe"),
                (2, "Pick up a pill", "Pill"),
                (3, "Pick up a pill", "Pill"),
            )
        )
        selected = select_balanced_episodes(episodes, 1)
        self.assertEqual([item.episode_index for item in selected], [0, 2])
        timestamps = phase_timestamps(
            selected[0], edge_offset_seconds=1.0,
            frames_per_phase=3, frame_spacing_seconds=0.1,
        )
        self.assertEqual(timestamps["pre"], (0.9, 1.0, 1.1))
        self.assertEqual(timestamps["post"], (8.9, 9.0, 9.1))

    def test_summary_and_single_markdown_table(self):
        records = []
        for phase, predictions in (("pre", (True, True, True)), ("post", (True, True, False))):
            for sequence, correct in enumerate(predictions, start=1):
                records.append({
                    "episode_index": 0, "phase": phase, "schema_valid": True,
                    "target_correct": correct, "unsafe_false_positive": False,
                    "prediction_signature": str(correct), "latency_seconds": 1.0,
                })
        summary = summarize_model_records(
            model_key="test", model_id="test/model", records=records,
            peak_vram_bytes=1024 ** 3,
        )
        self.assertEqual(summary["pre_presence_accuracy"], 1.0)
        self.assertAlmostEqual(summary["post_transfer_accuracy"], 2 / 3)
        self.assertEqual(summary["episode_success_rate"], 0.0)
        table = comparison_markdown([summary])
        self.assertEqual(table.count("| 모델 |"), 1)
        self.assertIn("66.67%", table)


if __name__ == "__main__":
    unittest.main()
