import json
import tempfile
import unittest
from pathlib import Path

from expert_surgical_mentor.vlm.evaluation import load_manifest, summarize_predictions


class VlmEvalManifestTest(unittest.TestCase):
    def test_three_frame_trial_and_metrics(self) -> None:
        rows = []
        for sequence in range(1, 4):
            rows.append({
                "image_path": f"images/S0_1_{sequence}.jpg", "state_id": "S0",
                "trial_id": 1, "split": "development", "frame_sequence": sequence,
                "captured_at_ns": sequence, "main_tray_tools": ["Syringe", "Pill"],
                "assist_tray_tools": [],
            })
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.jsonl"
            path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            self.assertEqual(len(load_manifest(path, require_complete=False)), 3)
        summary = summarize_predictions([{
            "exact_match": True, "false_ready": False,
            "consensus_match": True, "latency_seconds": 0.5,
        }])
        self.assertEqual(summary["exact_match_rate"], 1)
        self.assertEqual(summary["false_ready_count"], 0)

    def test_state_label_drift_is_rejected(self) -> None:
        row = {
            "image_path": "images/S3.jpg", "state_id": "S3", "trial_id": 1,
            "split": "development", "frame_sequence": 1, "captured_at_ns": 1,
            "main_tray_tools": ["Syringe"], "assist_tray_tools": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.jsonl"
            path.write_text(json.dumps(row), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "S3"):
                load_manifest(path, require_complete=False)


if __name__ == "__main__":
    unittest.main()
