"""Utilities for evaluating inventory VLMs on LeRobot pick-and-place episodes."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from statistics import quantiles
from typing import Iterable, Mapping, Sequence


TASK_TO_TOOL = {
    "Pick up syringe": "Syringe",
    "Pick up a pill": "Pill",
}


@dataclass(frozen=True, slots=True)
class PickPlaceEpisode:
    episode_index: int
    task: str
    tool_id: str
    video_file_index: int
    from_timestamp: float
    to_timestamp: float


def load_pick_place_episodes(paths: Sequence[str | Path]) -> tuple[PickPlaceEpisode, ...]:
    """Read only the columns needed from LeRobot v3 episode parquet files."""

    try:
        import pyarrow.parquet as parquet
    except ImportError as error:
        raise RuntimeError("pyarrow가 필요합니다. requirements-vlm.txt를 설치하세요.") from error

    columns = [
        "episode_index",
        "tasks",
        "videos/observation.images.front/file_index",
        "videos/observation.images.front/from_timestamp",
        "videos/observation.images.front/to_timestamp",
    ]
    episodes: list[PickPlaceEpisode] = []
    for path in paths:
        rows = parquet.read_table(path, columns=columns).to_pylist()
        for row in rows:
            tasks = row["tasks"]
            if not isinstance(tasks, list) or len(tasks) != 1 or tasks[0] not in TASK_TO_TOOL:
                raise ValueError(f"지원하지 않는 에피소드 작업입니다: {tasks}")
            task = tasks[0]
            episodes.append(
                PickPlaceEpisode(
                    episode_index=int(row["episode_index"]),
                    task=task,
                    tool_id=TASK_TO_TOOL[task],
                    video_file_index=int(
                        row["videos/observation.images.front/file_index"]
                    ),
                    from_timestamp=float(
                        row["videos/observation.images.front/from_timestamp"]
                    ),
                    to_timestamp=float(
                        row["videos/observation.images.front/to_timestamp"]
                    ),
                )
            )
    ordered = tuple(sorted(episodes, key=lambda item: item.episode_index))
    if len({item.episode_index for item in ordered}) != len(ordered):
        raise ValueError("episode_index가 중복되었습니다.")
    return ordered


def select_balanced_episodes(
    episodes: Sequence[PickPlaceEpisode],
    per_tool: int | None,
) -> tuple[PickPlaceEpisode, ...]:
    """Select the same number of deterministic, low-index episodes per tool."""

    by_tool: dict[str, list[PickPlaceEpisode]] = {}
    for episode in episodes:
        by_tool.setdefault(episode.tool_id, []).append(episode)
    if set(by_tool) != set(TASK_TO_TOOL.values()):
        raise ValueError("Syringe와 Pill 에피소드가 모두 필요합니다.")
    available = min(len(items) for items in by_tool.values())
    count = available if per_tool is None else per_tool
    if count <= 0 or count > available:
        raise ValueError(f"episodes-per-tool은 1-{available} 범위여야 합니다.")
    selected = [episode for tool in sorted(by_tool) for episode in by_tool[tool][:count]]
    return tuple(sorted(selected, key=lambda item: item.episode_index))


def phase_timestamps(
    episode: PickPlaceEpisode,
    *,
    edge_offset_seconds: float,
    frames_per_phase: int,
    frame_spacing_seconds: float,
) -> Mapping[str, tuple[float, ...]]:
    """Choose symmetric pre/post timestamps away from episode boundaries."""

    if frames_per_phase <= 0 or frames_per_phase % 2 == 0:
        raise ValueError("frames_per_phase는 양의 홀수여야 합니다.")
    if edge_offset_seconds <= 0 or frame_spacing_seconds <= 0:
        raise ValueError("프레임 시간 간격은 양수여야 합니다.")
    radius = frames_per_phase // 2
    offsets = tuple(index * frame_spacing_seconds for index in range(-radius, radius + 1))
    before_center = episode.from_timestamp + edge_offset_seconds
    after_center = episode.to_timestamp - edge_offset_seconds
    before = tuple(before_center + offset for offset in offsets)
    after = tuple(after_center + offset for offset in offsets)
    if before[0] < episode.from_timestamp or after[-1] >= episode.to_timestamp:
        raise ValueError(f"episode {episode.episode_index}의 추출 시각이 범위를 벗어났습니다.")
    if before[-1] >= after[0]:
        raise ValueError(f"episode {episode.episode_index}가 전·후 프레임 추출에 너무 짧습니다.")
    return {"pre": before, "post": after}


def summarize_model_records(
    *,
    model_key: str,
    model_id: str,
    records: Sequence[Mapping[str, object]],
    peak_vram_bytes: int | None,
) -> dict[str, object]:
    """Aggregate target-only observations into one comparable model row."""

    total = len(records)
    valid = [record for record in records if bool(record["schema_valid"])]
    pre = [record for record in valid if record["phase"] == "pre"]
    post = [record for record in valid if record["phase"] == "post"]
    grouped: dict[int, list[Mapping[str, object]]] = {}
    for record in records:
        grouped.setdefault(int(record["episode_index"]), []).append(record)
    episode_successes = sum(
        bool(values)
        and all(bool(value["schema_valid"]) and bool(value["target_correct"]) for value in values)
        for values in grouped.values()
    )
    consensus_groups: dict[tuple[int, str], list[Mapping[str, object]]] = {}
    for record in valid:
        consensus_groups.setdefault(
            (int(record["episode_index"]), str(record["phase"])), []
        ).append(record)
    consensus_matches = sum(
        len({str(value["prediction_signature"]) for value in values}) == 1
        for values in consensus_groups.values()
    )
    latencies = [float(record["latency_seconds"]) for record in valid]
    p95 = quantiles(latencies, n=20)[18] if len(latencies) >= 2 else (latencies[0] if latencies else math.nan)
    return {
        "model_key": model_key,
        "model_id": model_id,
        "schema_valid_rate": len(valid) / total if total else 0.0,
        "pre_presence_accuracy": _accuracy(pre),
        "post_transfer_accuracy": _accuracy(post),
        "episode_success_rate": episode_successes / len(grouped) if grouped else 0.0,
        "phase_consensus_rate": (
            consensus_matches / len(consensus_groups) if consensus_groups else 0.0
        ),
        "unsafe_pre_assist_false_positive_count": sum(
            bool(record["unsafe_false_positive"]) for record in pre
        ),
        "p95_latency_seconds": round(p95, 4) if not math.isnan(p95) else None,
        "peak_vram_gib": (
            round(peak_vram_bytes / (1024 ** 3), 3) if peak_vram_bytes is not None else None
        ),
        "evaluated_episodes": len(grouped),
        "evaluated_frames": total,
    }


def comparison_markdown(rows: Iterable[Mapping[str, object]]) -> str:
    """Render all model summaries as one Markdown comparison table."""

    headers = (
        "모델", "프롬프트", "Schema 유효율", "수행 전 존재 정확도", "수행 후 이동 정확도",
        "에피소드 성공률", "3프레임 합의율", "위험 FP", "P95 지연(s)",
        "Peak VRAM(GiB)", "에피소드/프레임",
    )
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join((
            str(row["model_key"]),
            str(row.get("prompt_language", "-")),
            _percent(row["schema_valid_rate"]),
            _percent(row["pre_presence_accuracy"]),
            _percent(row["post_transfer_accuracy"]),
            _percent(row["episode_success_rate"]),
            _percent(row["phase_consensus_rate"]),
            str(row["unsafe_pre_assist_false_positive_count"]),
            _display(row["p95_latency_seconds"]),
            _display(row["peak_vram_gib"]),
            f'{row["evaluated_episodes"]}/{row["evaluated_frames"]}',
        )) + " |")
    return "\n".join(lines) + "\n"


def _accuracy(records: Sequence[Mapping[str, object]]) -> float:
    return (
        sum(bool(record["target_correct"]) for record in records) / len(records)
        if records else 0.0
    )


def _percent(value: object) -> str:
    return f"{float(value) * 100:.2f}%"


def _display(value: object) -> str:
    return "N/A" if value is None else str(value)
