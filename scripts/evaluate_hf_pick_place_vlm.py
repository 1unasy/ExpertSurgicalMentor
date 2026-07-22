#!/usr/bin/env python3
"""Compare configured VLMs on 1unasy/pick_and_place_v2 in one table."""

from __future__ import annotations

import argparse
import gc
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from expert_surgical_mentor.vlm.backend import QwenVisionInventoryBackend
from expert_surgical_mentor.vlm.hf_evaluation import (
    comparison_markdown,
    load_pick_place_episodes,
    phase_timestamps,
    select_balanced_episodes,
    summarize_model_records,
)
from expert_surgical_mentor.vlm.model_loader import ModelCatalog, QuantizedVlmLoader
from expert_surgical_mentor.vlm.prompt import InventoryPromptBuilder


DATASET_ID = "1unasy/pick_and_place_v2"
DATASET_TYPE = "dataset"
REQUIRED_TOOLS = ("Syringe", "Pill")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-id", default=DATASET_ID)
    parser.add_argument("--revision", default="a2851c285a1fbf3d31167c02170acd264f139c27")
    parser.add_argument("--model", default="all")
    parser.add_argument(
        "--prompt-file", type=Path,
        default=PROJECT_ROOT / "config/vlm_inventory_prompt.txt",
    )
    parser.add_argument("--prompt-language", choices=("ko", "en"), default="ko")
    parser.add_argument(
        "--episodes-per-tool", type=int, default=None,
        help="Defaults to all 40 episodes per tool. Use a smaller value for a smoke test.",
    )
    parser.add_argument("--frames-per-phase", type=int, default=3)
    parser.add_argument("--edge-offset-seconds", type=float, default=1.0)
    parser.add_argument("--frame-spacing-seconds", type=float, default=0.15)
    parser.add_argument("--cache-dir", type=Path, default=Path("data/hf_cache"))
    parser.add_argument("--output-dir", type=Path, default=Path("results/vlm_pick_place_v2"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    meta_paths, repo_files = download_metadata(args.repo_id, args.revision, args.cache_dir)
    episodes = select_balanced_episodes(
        load_pick_place_episodes(meta_paths), args.episodes_per_tool
    )
    frame_manifest = prepare_frames(episodes, repo_files, args)

    catalog = ModelCatalog.from_file(PROJECT_ROOT / "config/vlm_models.json")
    prompt_path = args.prompt_file
    if not prompt_path.is_absolute():
        prompt_path = PROJECT_ROOT / prompt_path
    prompt_builder = InventoryPromptBuilder.from_file(prompt_path)
    model_keys = (
        [model.key for model in catalog.models]
        if args.model == "all" else [args.model]
    )
    summaries = []
    all_records: dict[str, list[dict[str, object]]] = {}
    failed = False
    for model_key in model_keys:
        records: list[dict[str, object]] = []
        try:
            reset_cuda_peak_memory()
            loaded = QuantizedVlmLoader(catalog).load(model_key)
            backend = QwenVisionInventoryBackend(loaded)
            records = evaluate_frames(backend, prompt_builder, frame_manifest)
            summary = summarize_model_records(
                model_key=model_key,
                model_id=loaded.spec.model_id,
                records=records,
                peak_vram_bytes=peak_vram_bytes(),
            )
            summary["prompt_language"] = args.prompt_language
        except Exception as error:
            failed = True
            spec = catalog.get(model_key)
            summary = {
                "model_key": model_key,
                "model_id": spec.model_id,
                "status": "failed",
                "error_type": type(error).__name__,
                "message": str(error),
                "schema_valid_rate": 0.0,
                "pre_presence_accuracy": 0.0,
                "post_transfer_accuracy": 0.0,
                "episode_success_rate": 0.0,
                "phase_consensus_rate": 0.0,
                "unsafe_pre_assist_false_positive_count": 0,
                "p95_latency_seconds": None,
                "peak_vram_gib": None,
                "evaluated_episodes": 0,
                "evaluated_frames": 0,
                "prompt_language": args.prompt_language,
            }
        finally:
            release_cuda_cache()
        summaries.append(summary)
        all_records[model_key] = records

    table = comparison_markdown(summaries)
    payload = {
        "dataset_id": args.repo_id,
        "revision": args.revision,
        "label_scope": "target tool only; pre=MainToolTray, post=AssistTray",
        "prompt_language": args.prompt_language,
        "prompt_file": str(prompt_path),
        "models": summaries,
        "frame_predictions": all_records,
    }
    (args.output_dir / "comparison.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (args.output_dir / "comparison.md").write_text(table, encoding="utf-8")
    print(table, end="")
    print(f"\nJSON: {args.output_dir / 'comparison.json'}")
    print(f"표: {args.output_dir / 'comparison.md'}")
    return 1 if failed else 0


def download_metadata(repo_id: str, revision: str, cache_dir: Path):
    try:
        from huggingface_hub import HfApi, hf_hub_download
    except ImportError as error:
        raise RuntimeError("huggingface-hub가 필요합니다. requirements-vlm.txt를 설치하세요.") from error
    repo_files = HfApi().list_repo_files(
        repo_id=repo_id, repo_type=DATASET_TYPE, revision=revision
    )
    episode_files = sorted(
        name for name in repo_files
        if name.startswith("meta/episodes/") and name.endswith(".parquet")
    )
    if not episode_files:
        raise RuntimeError("LeRobot episode metadata를 찾지 못했습니다.")
    paths = [
        hf_hub_download(
            repo_id=repo_id, filename=name, repo_type=DATASET_TYPE,
            revision=revision, cache_dir=cache_dir,
        )
        for name in episode_files
    ]
    return paths, repo_files


def prepare_frames(episodes, repo_files, args):
    try:
        import av
        from huggingface_hub import hf_hub_download
    except ImportError as error:
        raise RuntimeError("av와 huggingface-hub가 필요합니다.") from error

    requested: dict[int, list[dict[str, object]]] = defaultdict(list)
    for episode in episodes:
        phases = phase_timestamps(
            episode,
            edge_offset_seconds=args.edge_offset_seconds,
            frames_per_phase=args.frames_per_phase,
            frame_spacing_seconds=args.frame_spacing_seconds,
        )
        for phase, timestamps in phases.items():
            for sequence, timestamp in enumerate(timestamps, start=1):
                requested[episode.video_file_index].append({
                    "episode_index": episode.episode_index,
                    "tool_id": episode.tool_id,
                    "phase": phase,
                    "sequence": sequence,
                    "timestamp": timestamp,
                })

    frames_dir = args.output_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    for file_index, requests in sorted(requested.items()):
        remote_name = (
            "videos/observation.images.front/chunk-000/"
            f"file-{file_index:03d}.mp4"
        )
        if remote_name not in repo_files:
            raise FileNotFoundError(f"데이터셋 비디오가 없습니다: {remote_name}")
        video_path = hf_hub_download(
            repo_id=args.repo_id, filename=remote_name, repo_type=DATASET_TYPE,
            revision=args.revision, cache_dir=args.cache_dir,
        )
        pending = sorted(requests, key=lambda item: float(item["timestamp"]))
        next_index = 0
        with av.open(video_path) as container:
            stream = container.streams.video[0]
            for frame in container.decode(stream):
                if next_index >= len(pending):
                    break
                frame_time = float(frame.pts * stream.time_base)
                while next_index < len(pending) and frame_time >= float(pending[next_index]["timestamp"]):
                    item = pending[next_index]
                    image_name = (
                        f'e{item["episode_index"]:03d}_{item["tool_id"]}_'
                        f'{item["phase"]}_{item["sequence"]}.jpg'
                    )
                    image_path = frames_dir / image_name
                    frame.to_image().save(image_path, quality=95)
                    manifest.append({**item, "image_path": str(image_path)})
                    next_index += 1
        if next_index != len(pending):
            raise RuntimeError(f"{remote_name}에서 요청 프레임을 모두 추출하지 못했습니다.")
    return sorted(
        manifest,
        key=lambda item: (int(item["episode_index"]), str(item["phase"]), int(item["sequence"])),
    )


def evaluate_frames(backend, prompt_builder, frame_manifest):
    from PIL import Image
    records = []
    for item in frame_manifest:
        verification_tool = item["tool_id"] if item["phase"] == "post" else None
        prompt = prompt_builder.build(
            patient_id="HF_DATASET",
            case_id=f'HF_EP_{item["episode_index"]:03d}',
            disease_name="감기",
            required_tools=REQUIRED_TOOLS,
            verification_tool=verification_tool,
        )
        started = time.perf_counter()
        try:
            with Image.open(item["image_path"]) as source:
                assessment = backend.assess(source.convert("RGB"), prompt)
            latency = time.perf_counter() - started
            if item["phase"] == "pre":
                correct = item["tool_id"] in assessment.main_tray_tools
                unsafe = item["tool_id"] in assessment.assist_tray_tools
            else:
                correct = item["tool_id"] in assessment.assist_tray_tools
                unsafe = False
            signature = json.dumps({
                "present": assessment.present_required_tools,
                "missing": assessment.missing_tools,
                "assist": assessment.assist_tray_tools,
            })
            record = {
                **item, "schema_valid": True, "target_correct": correct,
                "unsafe_false_positive": unsafe, "prediction_signature": signature,
                "latency_seconds": round(latency, 4),
            }
        except Exception as error:
            record = {
                **item, "schema_valid": False, "target_correct": False,
                "unsafe_false_positive": False, "prediction_signature": "INVALID",
                "latency_seconds": round(time.perf_counter() - started, 4),
                "error_type": type(error).__name__, "message": str(error),
            }
        records.append(record)
    return records


def reset_cuda_peak_memory():
    import torch
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()


def peak_vram_bytes():
    import torch
    return int(torch.cuda.max_memory_allocated()) if torch.cuda.is_available() else None


def release_cuda_cache():
    gc.collect()
    try:
        import torch
    except ImportError:
        return
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


if __name__ == "__main__":
    raise SystemExit(main())
