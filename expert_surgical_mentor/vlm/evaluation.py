"""Manifest validation and model-independent VLM evaluation metrics."""

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import quantiles


STATE_LABELS = {
    "S0": (("Syringe", "Pill"), ()),
    "S1": (("Pill",), ("Syringe",)),
    "S2": ((), ("Syringe", "Pill")),
    "S3": (("Pill",), ()),
    "S4": (("Syringe",), ()),
    "S5": ((), ()),
}
EXPECTED_STATES = frozenset(STATE_LABELS)
ALLOWED_TOOLS = frozenset(tool for trays in STATE_LABELS.values() for tray in trays for tool in tray)


@dataclass(frozen=True, slots=True)
class EvalFrame:
    image_path: str
    state_id: str
    trial_id: int
    split: str
    frame_sequence: int
    captured_at_ns: int
    main_tray_tools: tuple[str, ...]
    assist_tray_tools: tuple[str, ...]


def load_manifest(path: str | Path, require_complete: bool = True) -> tuple[EvalFrame, ...]:
    records = tuple(
        _parse_record(json.loads(line))
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip()
    )
    batches: dict[tuple[str, int], list[EvalFrame]] = {}
    for record in records:
        batches.setdefault((record.state_id, record.trial_id), []).append(record)
    for key, frames in batches.items():
        if sorted(frame.frame_sequence for frame in frames) != [1, 2, 3]:
            raise ValueError(f"{key} 시행은 frame_sequence 1, 2, 3이 필요합니다.")
        timestamps = [frame.captured_at_ns for frame in frames]
        if len(set(timestamps)) != 3:
            raise ValueError(f"{key} 시행의 촬영 시각이 중복되었습니다.")
    if require_complete:
        expected = {(state, trial) for state in EXPECTED_STATES for trial in range(1, 6)}
        if set(batches) != expected or len(records) != 90:
            raise ValueError("완성된 평가 manifest는 S0-S5 각 5회, 회당 3장이어야 합니다.")
    return records


def summarize_predictions(predictions: list[dict[str, object]]) -> dict[str, object]:
    total = len(predictions)
    exact = sum(bool(item["exact_match"]) for item in predictions)
    false_ready = sum(bool(item["false_ready"]) for item in predictions)
    consensus = sum(bool(item["consensus_match"]) for item in predictions)
    latencies = [float(item["latency_seconds"]) for item in predictions]
    p95 = quantiles(latencies, n=20)[18] if len(latencies) >= 2 else (latencies[0] if latencies else 0)
    return {
        "total_batches": total,
        "exact_match_rate": exact / total if total else 0,
        "consensus_rate": consensus / total if total else 0,
        "false_ready_count": false_ready,
        "p95_latency_seconds": round(p95, 4),
    }


def _parse_record(payload: dict[str, object]) -> EvalFrame:
    expected = {
        "image_path", "state_id", "trial_id", "split", "frame_sequence",
        "captured_at_ns", "main_tray_tools", "assist_tray_tools",
    }
    if set(payload) != expected:
        raise ValueError("평가 manifest 필드가 계약과 일치하지 않습니다.")
    state_id = str(payload["state_id"])
    if state_id not in EXPECTED_STATES:
        raise ValueError(f"등록되지 않은 평가 상태입니다: {state_id}")
    main = tuple(payload["main_tray_tools"])
    assist = tuple(payload["assist_tray_tools"])
    if (set(main) | set(assist)) - ALLOWED_TOOLS:
        raise ValueError("평가 manifest에는 Syringe와 Pill만 허용됩니다.")
    if set(main) & set(assist):
        raise ValueError("물품을 두 트레이에 동시에 기록할 수 없습니다.")
    if (main, assist) != STATE_LABELS[state_id]:
        raise ValueError(f"{state_id}의 트레이 정답이 상태 정의와 일치하지 않습니다.")
    return EvalFrame(
        str(payload["image_path"]), state_id, int(payload["trial_id"]),
        str(payload["split"]), int(payload["frame_sequence"]),
        int(payload["captured_at_ns"]), main, assist,
    )
