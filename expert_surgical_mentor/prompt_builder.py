"""Prompt assembly for deterministic VLM inventory assessment."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


@dataclass(frozen=True, slots=True)
class InventoryPrompt:
    system_text: str
    user_text: str


class InventoryPromptBuilder:
    def __init__(self, system_text: str) -> None:
        if not system_text.strip():
            raise ValueError("VLM Inventory Prompt는 비어 있을 수 없습니다.")
        self._system_text = system_text.strip()

    @classmethod
    def from_file(cls, path: str | Path) -> "InventoryPromptBuilder":
        return cls(Path(path).read_text(encoding="utf-8"))

    def build(
        self,
        *,
        patient_id: str,
        case_id: str,
        disease_name: str,
        required_tools: Iterable[str],
        yolo_detections: Iterable[Mapping[str, object]] = (),
        moved_tools: Iterable[str] = (),
    ) -> InventoryPrompt:
        runtime_context = {
            "patient_id": patient_id,
            "case_id": case_id,
            "disease_name": disease_name,
            "required_tools": list(required_tools),
            "moved_tools": list(moved_tools),
            "yolo_detections": [dict(detection) for detection in yolo_detections],
            "instruction": "첨부된 최신 작업 공간 이미지에서 필요 물품의 존재 여부를 판정하세요.",
        }
        return InventoryPrompt(
            system_text=self._system_text,
            user_text=json.dumps(runtime_context, ensure_ascii=False, separators=(",", ":")),
        )
