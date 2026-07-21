from __future__ import annotations

import argparse
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import evaluate_vlm_inventory


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class EvaluateVlmInventoryTest(unittest.TestCase):
    def test_all_models_continue_after_failure_and_always_release_cache(self) -> None:
        args = argparse.Namespace(
            image_dir=PROJECT_ROOT / "data" / "evaluation_images",
            project_root=PROJECT_ROOT,
            model="all",
        )
        evaluated: list[str] = []

        def fake_evaluate_model(**kwargs: object) -> dict[str, object]:
            model_key = str(kwargs["model_key"])
            evaluated.append(model_key)
            if model_key == "qwen3_vl_2b":
                raise RuntimeError("load failed")
            return {"model_key": model_key, "status": "complete"}

        with (
            patch.object(evaluate_vlm_inventory, "parse_args", return_value=args),
            patch.object(
                evaluate_vlm_inventory,
                "evaluate_model",
                side_effect=fake_evaluate_model,
            ),
            patch.object(evaluate_vlm_inventory, "release_cuda_cache") as release,
            patch("builtins.print"),
        ):
            exit_code = evaluate_vlm_inventory.main()

        self.assertEqual(
            evaluated,
            ["qwen3_vl_2b", "qwen2_5_vl_3b", "qwen3_vl_4b"],
        )
        self.assertEqual(release.call_count, 3)
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
