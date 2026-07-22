#!/usr/bin/env python3
"""Merge per-model pick-and-place evaluation outputs into one comparison table."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from expert_surgical_mentor.vlm.hf_evaluation import comparison_markdown


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    summaries = []
    predictions = {}
    dataset_id = None
    revision = None
    for path in args.inputs:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if dataset_id is None:
            dataset_id = payload["dataset_id"]
            revision = payload["revision"]
        elif (payload["dataset_id"], payload["revision"]) != (dataset_id, revision):
            raise ValueError("서로 다른 데이터셋 또는 revision 결과는 병합할 수 없습니다.")
        if len(payload["models"]) != 1:
            raise ValueError(f"모델별 결과 파일이 아닙니다: {path}")
        summary = payload["models"][0]
        summaries.append(summary)
        language = payload.get("prompt_language", summary.get("prompt_language", "unknown"))
        summary["prompt_language"] = language
        for model_key, records in payload["frame_predictions"].items():
            predictions[f"{language}:{model_key}"] = records

    summaries.sort(key=lambda item: (item["prompt_language"], item["model_key"]))
    table = comparison_markdown(summaries)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "comparison.md").write_text(table, encoding="utf-8")
    (args.output_dir / "comparison.json").write_text(
        json.dumps(
            {
                "dataset_id": dataset_id,
                "revision": revision,
                "label_scope": "target tool only; pre=MainToolTray, post=AssistTray",
                "models": summaries,
                "frame_predictions": predictions,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(table, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
