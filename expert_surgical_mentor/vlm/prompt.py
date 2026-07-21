"""Prompt assembly for deterministic VLM inventory assessment."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


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
        verification_tool: str | None = None,
    ) -> InventoryPrompt:
        runtime_context = {
            "patient_id": patient_id,
            "case_id": case_id,
            "disease_name": disease_name,
            "required_tools": list(required_tools),
            "verification_tool": verification_tool,
            "instruction": (
                "첨부된 최신 작업 공간 이미지에서 required_tools의 존재 여부와 "
                "MainToolTray 또는 AssistTray 위치를 판정하세요."
            ),
        }
        return InventoryPrompt(
            system_text=self._system_text,
            user_text=json.dumps(runtime_context, ensure_ascii=False, separators=(",", ":")),
        )
