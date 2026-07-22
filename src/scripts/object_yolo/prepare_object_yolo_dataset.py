#!/usr/bin/env python3
"""Re-split Roboflow images by LeRobot episode to prevent adjacent-frame leakage."""

import argparse
import random
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import yaml


EPISODE_RE = re.compile(r"^ep(\d{3})_")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("datasets/objects"))
    parser.add_argument("--output", type=Path, default=Path("datasets/objects_grouped"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def build_episode_split(episodes: set[int], seed: int) -> dict[int, str]:
    """Seeded 8:1:1 episode split, stratified by syringe/pill task blocks."""
    groups = {
        "syringe": sorted(episode for episode in episodes if episode < 40),
        "pill": sorted(episode for episode in episodes if episode >= 40),
    }
    split_by_episode: dict[int, str] = {}
    rng = random.Random(seed)
    for name, group in groups.items():
        if len(group) != 40:
            raise ValueError(f"Expected 40 {name} episodes, found {len(group)}: {group}")
        rng.shuffle(group)
        train_end = int(len(group) * 0.8)
        valid_end = train_end + int(len(group) * 0.1)
        for episode in group[:train_end]:
            split_by_episode[episode] = "train"
        for episode in group[train_end:valid_end]:
            split_by_episode[episode] = "valid"
        for episode in group[valid_end:]:
            split_by_episode[episode] = "test"
    return split_by_episode


def main() -> None:
    args = parse_args()
    source = args.source.resolve()
    output = args.output.resolve()
    if output.exists():
        if not args.overwrite:
            raise FileExistsError(f"Output already exists: {output}. Use --overwrite to rebuild it.")
        shutil.rmtree(output)

    data = yaml.safe_load((source / "data.yaml").read_text())
    if data.get("names") != ["pill", "syringe"]:
        raise ValueError(f"Expected class order ['pill', 'syringe'], got {data.get('names')}")

    records: list[tuple[Path, Path, int]] = []
    for original_split in ("train", "valid", "test"):
        for image_path in (source / original_split / "images").iterdir():
            if not image_path.is_file():
                continue
            match = EPISODE_RE.match(image_path.stem)
            if match is None:
                raise ValueError(f"Cannot parse episode from filename: {image_path.name}")
            episode = int(match.group(1))
            label_path = source / original_split / "labels" / f"{image_path.stem}.txt"
            if not label_path.is_file():
                raise FileNotFoundError(f"Missing label: {label_path}")
            records.append((image_path, label_path, episode))

    split_by_episode = build_episode_split({record[2] for record in records}, args.seed)
    image_counts: Counter[str] = Counter()
    episode_counts: defaultdict[str, set[int]] = defaultdict(set)
    for image_path, label_path, episode in records:
        split = split_by_episode[episode]
        image_out = output / split / "images" / image_path.name
        label_out = output / split / "labels" / label_path.name
        image_out.parent.mkdir(parents=True, exist_ok=True)
        label_out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image_path, image_out)
        shutil.copy2(label_path, label_out)
        image_counts[split] += 1
        episode_counts[split].add(episode)

    (output / "data.yaml").write_text(
        "path: " + str(output) + "\n"
        "train: train/images\n"
        "val: valid/images\n"
        "test: test/images\n\n"
        "nc: 2\n"
        "names: ['pill', 'syringe']\n"
    )
    print(f"Created episode-grouped dataset: {output}")
    print(f"Seed: {args.seed}")
    for split in ("train", "valid", "test"):
        syringe_count = sum(episode < 40 for episode in episode_counts[split])
        pill_count = sum(episode >= 40 for episode in episode_counts[split])
        print(
            f"  {split}: {image_counts[split]} images, {len(episode_counts[split])} episodes "
            f"(syringe={syringe_count}, pill={pill_count})"
        )


if __name__ == "__main__":
    main()
