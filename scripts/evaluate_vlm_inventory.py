#!/usr/bin/env python3
"""Evaluate all approved quantized VLMs against the 15-case image set.

This script performs inference only. It does not train or modify model weights.
Expected image names are <case_id>.jpg, .jpeg, or .png inside --image-dir.
"""

from __future__ import annotations

import argparse
import gc
import importlib
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from expert_surgical_mentor.case_validation import validate_case_payload
from expert_surgical_mentor.inventory_schema import InventoryResult
from expert_surgical_mentor.model_loader import ModelCatalog, QuantizedVlmLoader
from expert_surgical_mentor.prompt_builder import InventoryPromptBuilder
from expert_surgical_mentor.scenario_registry import ScenarioRegistry
from expert_surgical_mentor.vlm_backend import QwenVisionInventoryBackend


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--model",
        default="all",
        help="Model key from config/vlm_models.json, or 'all' (default).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.project_root.resolve()
    registry = ScenarioRegistry.from_file(root / "config" / "scenario_registry.json")
    prompt_builder = InventoryPromptBuilder.from_file(root / "config" / "vlm_inventory_prompt.txt")
    catalog = ModelCatalog.from_file(root / "config" / "vlm_models.json")
    cases = json.loads(
        (root / "data" / "virtual_cases_15.json").read_text(encoding="utf-8")
    )["cases"]
    model_keys = [model.key for model in catalog.models] if args.model == "all" else [args.model]

    summaries = []
    failed = False
    for model_key in model_keys:
        try:
            summaries.append(
                evaluate_model(
                    model_key=model_key,
                    catalog=catalog,
                    registry=registry,
                    prompt_builder=prompt_builder,
                    cases=cases,
                    image_dir=args.image_dir,
                )
            )
        except Exception as error:
            failed = True
            summaries.append(
                {
                    "model_key": model_key,
                    "status": "failed",
                    "error_type": type(error).__name__,
                    "message": str(error),
                }
            )
        finally:
            release_cuda_cache()

    print(json.dumps({"models": summaries}, ensure_ascii=False, indent=2))
    return 1 if failed else 0


def evaluate_model(
    *,
    model_key: str,
    catalog: ModelCatalog,
    registry: ScenarioRegistry,
    prompt_builder: InventoryPromptBuilder,
    cases: list[dict[str, object]],
    image_dir: Path,
) -> dict[str, object]:
    pillow_image = importlib.import_module("PIL.Image")
    loaded = QuantizedVlmLoader(catalog).load(model_key)
    backend = QwenVisionInventoryBackend(loaded)
    records = []

    for raw_case in cases:
        case_payload = {
            "patient_id": raw_case["patient_id"],
            "case_id": raw_case["case_id"],
            "disease_name": raw_case["disease_name"],
        }
        case, scenario = validate_case_payload(case_payload, registry)
        image_path = find_case_image(image_dir, case.case_id)
        prompt = prompt_builder.build(
            patient_id=case.patient_id,
            case_id=case.case_id,
            disease_name=case.disease_name,
            required_tools=scenario.required_tools,
        )

        started_at = time.perf_counter()
        with pillow_image.open(image_path) as source_image:
            image = source_image.convert("RGB")
            try:
                assessment = backend.assess(image, prompt)
            finally:
                image.close()
        latency_seconds = time.perf_counter() - started_at
        result = InventoryResult.from_assessment(case, scenario, assessment)
        expected_present = raw_case["expected_present_required_tools"]
        expected_missing = raw_case["expected_missing_tools"]
        exact_match = (
            list(result.present_required_tools) == expected_present
            and list(result.missing_tools) == expected_missing
        )
        records.append(
            {
                "case_id": case.case_id,
                "exact_match": exact_match,
                "latency_seconds": round(latency_seconds, 4),
                "present_required_tools": list(result.present_required_tools),
                "missing_tools": list(result.missing_tools),
            }
        )

    exact_matches = sum(record["exact_match"] for record in records)
    return {
        "model_key": model_key,
        "model_id": loaded.spec.model_id,
        "quantization_bits": 4,
        "exact_matches": exact_matches,
        "total_cases": len(records),
        "accuracy": exact_matches / len(records),
        "cases": records,
    }


def find_case_image(image_dir: Path, case_id: str) -> Path:
    for extension in IMAGE_EXTENSIONS:
        candidate = image_dir / f"{case_id}{extension}"
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"{case_id} 이미지를 찾을 수 없습니다: {image_dir}")


def release_cuda_cache() -> None:
    gc.collect()
    try:
        torch = importlib.import_module("torch")
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


if __name__ == "__main__":
    raise SystemExit(main())
