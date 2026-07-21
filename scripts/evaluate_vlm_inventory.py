#!/usr/bin/env python3
"""Evaluate all approved quantized VLMs against the 15-case image set.

This script performs inference only. It does not train or modify model weights.
Expected image names are <case_id>.jpg, .jpeg, or .png inside --image-dir.
"""

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
from expert_surgical_mentor.scenario_registry import ScenarioRegistry
from expert_surgical_mentor.vlm.backend import QwenVisionInventoryBackend
from expert_surgical_mentor.vlm.inventory import InventoryResult
from expert_surgical_mentor.vlm.evaluation import load_manifest, summarize_predictions
from expert_surgical_mentor.vlm.model_loader import ModelCatalog, QuantizedVlmLoader
from expert_surgical_mentor.vlm.prompt import InventoryPromptBuilder


IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--image-dir", type=Path)
    source.add_argument("--manifest", type=Path)
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
    manifest_path = getattr(args, "manifest", None)
    cases = json.loads(
        (root / "data" / "virtual_cases_15.json").read_text(encoding="utf-8")
    )["cases"]
    model_keys = [model.key for model in catalog.models] if args.model == "all" else [args.model]

    summaries = []
    failed = False
    for model_key in model_keys:
        try:
            reset_cuda_peak_memory()
            if manifest_path is not None:
                summary = evaluate_manifest_model(
                    model_key=model_key,
                    catalog=catalog,
                    registry=registry,
                    prompt_builder=prompt_builder,
                    manifest_path=manifest_path,
                    project_root=root,
                )
            else:
                summary = evaluate_model(
                    model_key=model_key,
                    catalog=catalog,
                    registry=registry,
                    prompt_builder=prompt_builder,
                    cases=cases,
                    image_dir=args.image_dir,
                )
            summaries.append(summary)
            if manifest_path is not None and not summary.get("passed", False):
                failed = True
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


def evaluate_manifest_model(
    *,
    model_key: str,
    catalog: ModelCatalog,
    registry: ScenarioRegistry,
    prompt_builder: InventoryPromptBuilder,
    manifest_path: Path,
    project_root: Path,
) -> dict[str, object]:
    pillow_image = importlib.import_module("PIL.Image")
    frames = load_manifest(manifest_path)
    demo_payload = json.loads(
        (project_root / "data" / "demo_cases_syringe_pill.json").read_text(encoding="utf-8")
    )
    case, scenario = validate_case_payload(demo_payload, registry)
    prompt = prompt_builder.build(
        patient_id=case.patient_id,
        case_id=case.case_id,
        disease_name=case.disease_name,
        required_tools=scenario.required_tools,
    )
    loaded = QuantizedVlmLoader(catalog).load(model_key)
    backend = QwenVisionInventoryBackend(loaded)
    batches: dict[tuple[str, int, str], list[tuple[object, float, bool, bool]]] = {}
    for frame in frames:
        started_at = time.perf_counter()
        with pillow_image.open(manifest_path.parent / frame.image_path) as source_image:
            image = source_image.convert("RGB")
            try:
                assessment = backend.assess(image, prompt)
            finally:
                image.close()
        latency = time.perf_counter() - started_at
        expected_missing = set(scenario.required_tools) - set(frame.main_tray_tools) - set(frame.assist_tray_tools)
        false_ready = bool(expected_missing & set(assessment.present_required_tools))
        frame_exact = (
            assessment.main_tray_tools == frame.main_tray_tools
            and assessment.assist_tray_tools == frame.assist_tray_tools
        )
        batches.setdefault((frame.state_id, frame.trial_id, frame.split), []).append(
            (assessment, latency, false_ready, frame_exact)
        )

    records = []
    frame_records = []
    for (state_id, trial_id, split), values in batches.items():
        assessments = [value[0] for value in values]
        expected = next(
            frame for frame in frames if frame.state_id == state_id and frame.trial_id == trial_id
        )
        exact = all(
            assessment.main_tray_tools == expected.main_tray_tools
            and assessment.assist_tray_tools == expected.assist_tray_tools
            for assessment in assessments
        )
        records.append({
            "state_id": state_id,
            "trial_id": trial_id,
            "split": split,
            "exact_match": exact,
            "consensus_match": len(set(assessments)) == 1,
            "false_ready": any(value[2] for value in values),
            "latency_seconds": sum(value[1] for value in values) / len(values),
        })
        frame_records.extend({
            "split": split,
            "exact_match": value[3],
            "consensus_match": len(set(assessments)) == 1,
            "false_ready": value[2],
            "latency_seconds": value[1],
        } for value in values)
    locked = [record for record in records if record["split"] == "locked_validation"]
    locked_frames = [record for record in frame_records if record["split"] == "locked_validation"]
    locked_metrics = summarize_predictions(locked_frames)
    normal = [record for record in locked if record["state_id"] in {"S0", "S1", "S2"}]
    normal_metrics = summarize_predictions(normal)
    selection_gates = {
        "schema_valid_rate": 1.0,
        "locked_exact_match_at_least_95_percent": locked_metrics["exact_match_rate"] >= 0.95,
        "normal_consensus_100_percent": normal_metrics["consensus_rate"] == 1.0,
        "false_ready_zero": locked_metrics["false_ready_count"] == 0,
        "p95_latency_at_most_3_seconds": locked_metrics["p95_latency_seconds"] <= 3.0,
    }
    passed = all(selection_gates.values())
    return {
        "model_key": model_key,
        "model_id": loaded.spec.model_id,
        "quantization_bits": 4,
        "all_metrics": summarize_predictions(records),
        "locked_validation_metrics": locked_metrics,
        "normal_state_metrics": normal_metrics,
        "selection_gates": selection_gates,
        "peak_vram_bytes": current_peak_vram_bytes(),
        "passed": passed,
        "batches": records,
    }


def current_peak_vram_bytes() -> int | None:
    try:
        torch = importlib.import_module("torch")
    except ImportError:
        return None
    if not torch.cuda.is_available():
        return None
    return int(torch.cuda.max_memory_allocated())


def reset_cuda_peak_memory() -> None:
    try:
        torch = importlib.import_module("torch")
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()


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
