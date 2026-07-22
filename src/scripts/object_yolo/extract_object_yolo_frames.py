#!/usr/bin/env python3
"""Extract evenly spaced front-camera frames from a LeRobot dataset for bbox labeling."""

import argparse
import csv
import os
from pathlib import Path

import cv2
import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-id", default="1unasy/pick_and_place_v2")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("datasets/objects/yolo_v1/unlabeled"),
    )
    parser.add_argument("--samples-per-episode", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.samples_per_episode < 2:
        raise ValueError("--samples-per-episode must be at least 2")

    # Hugging Face datasets writes lock files even when the LeRobot data is read-only.
    os.environ.setdefault("HF_DATASETS_CACHE", "/tmp/hf_datasets_cache")
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.csv"
    if manifest_path.exists() or any(output_dir.glob("*.jpg")):
        raise FileExistsError(
            f"Output is not empty: {output_dir}. Move or remove it before extracting again."
        )

    dataset = LeRobotDataset(args.repo_id)
    fractions = np.linspace(0.08, 0.92, args.samples_per_episode)
    manifest_rows: list[dict[str, str | int | float]] = []

    for episode in dataset.meta.episodes:
        episode_index = int(episode["episode_index"])
        start = int(episode["dataset_from_index"])
        end = int(episode["dataset_to_index"])
        length = end - start
        task = str(episode["tasks"][0])
        target = "syringe" if "syringe" in task.lower() else "pill"

        for sample_index, fraction in enumerate(fractions):
            dataset_index = start + min(length - 1, round((length - 1) * float(fraction)))
            row = dataset[dataset_index]
            image_rgb = row["observation.images.front"].permute(1, 2, 0).numpy()
            image_bgr = cv2.cvtColor((image_rgb * 255).clip(0, 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
            filename = f"ep{episode_index:03d}_{target}_s{sample_index:02d}_idx{dataset_index:06d}.jpg"
            if not cv2.imwrite(str(output_dir / filename), image_bgr):
                raise RuntimeError(f"Failed to write {output_dir / filename}")
            manifest_rows.append(
                {
                    "filename": filename,
                    "episode_index": episode_index,
                    "dataset_index": dataset_index,
                    "episode_fraction": round(float(fraction), 3),
                    "task": task,
                }
            )

    with manifest_path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(manifest_rows[0].keys()))
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"Extracted {len(manifest_rows)} images to {output_dir}")
    print(f"Manifest: {manifest_path}")
    print("Next: label every visible syringe and pill bbox, then export YOLO format.")


if __name__ == "__main__":
    main()
