"""Validated inventory contracts shared by VLM and robot orchestration layers."""

import json
import re
from dataclasses import dataclass
from typing import Iterable

from ..case_validation import CaseInput
from ..scenario_registry import Scenario


_JSON_FENCE = re.compile(r"^```(?:json)?\s*(\{.*\})\s*```$", re.DOTALL)


class InventoryContractError(ValueError):
    """Raised when a VLM inventory response violates the deterministic contract."""


@dataclass(frozen=True, slots=True)
class VisualInventoryAssessment:
    """Minimal visual observation returned by the VLM."""

    present_required_tools: tuple[str, ...]
    missing_tools: tuple[str, ...]
    assist_tray_tools: tuple[str, ...]

    @property
    def main_tray_tools(self) -> tuple[str, ...]:
        """Tools seen on MainToolTray, derived from the exclusive tray contract."""

        assist = set(self.assist_tray_tools)
        return tuple(tool for tool in self.present_required_tools if tool not in assist)

    @classmethod
    def from_model_text(cls, model_text: str) -> "VisualInventoryAssessment":
        text = model_text.strip()
        fenced = _JSON_FENCE.fullmatch(text)
        if fenced:
            text = fenced.group(1)

        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            raise InventoryContractError("VLM 출력이 유효한 JSON 객체가 아닙니다.") from error

        if not isinstance(payload, dict):
            raise InventoryContractError("VLM 출력의 최상위 값은 JSON 객체여야 합니다.")

        expected_fields = {
            "present_required_tools",
            "missing_tools",
            "assist_tray_tools",
        }
        if set(payload) != expected_fields:
            raise InventoryContractError(
                "VLM 출력은 present_required_tools, missing_tools, assist_tray_tools만 포함해야 합니다."
            )

        present = _validate_tool_list(payload["present_required_tools"], "present_required_tools")
        missing = _validate_tool_list(payload["missing_tools"], "missing_tools")
        assist = _validate_tool_list(payload["assist_tray_tools"], "assist_tray_tools")
        return cls(present, missing, assist)


@dataclass(frozen=True, slots=True)
class InventoryResult:
    status: str
    patient_id: str
    case_id: str
    scenario_id: str
    disease_name: str
    required_tools: tuple[str, ...]
    present_required_tools: tuple[str, ...]
    missing_tools: tuple[str, ...]
    move_queue: tuple[str, ...]
    moved_tools: tuple[str, ...]

    @classmethod
    def from_assessment(
        cls,
        case: CaseInput,
        scenario: Scenario,
        assessment: VisualInventoryAssessment,
        moved_tools: Iterable[str] = (),
        verification_tool: str | None = None,
    ) -> "InventoryResult":
        required = scenario.required_tools
        required_set = set(required)
        present_set = set(assessment.present_required_tools)
        missing_set = set(assessment.missing_tools)
        assist_set = set(assessment.assist_tray_tools)
        moved = tuple(moved_tools)
        moved_set = set(moved)

        reported_tools = present_set | missing_set | assist_set | moved_set
        if verification_tool is not None:
            reported_tools.add(verification_tool)
        unexpected = reported_tools - required_set
        if unexpected:
            names = ", ".join(sorted(unexpected))
            raise InventoryContractError(f"현재 시나리오에 없는 물품입니다: {names}")
        if present_set & missing_set:
            names = ", ".join(sorted(present_set & missing_set))
            raise InventoryContractError(f"존재·누락 목록에 중복된 물품입니다: {names}")
        if present_set | missing_set != required_set:
            raise InventoryContractError("모든 필요 물품을 존재 또는 누락으로 분류해야 합니다.")
        if not assist_set.issubset(present_set):
            raise InventoryContractError("보조 트레이 물품은 존재 물품에 포함되어야 합니다.")
        if verification_tool is not None:
            if verification_tool not in moved_set:
                raise InventoryContractError("검증 대상 물품은 이동 이력에 포함되어야 합니다.")
            if verification_tool not in assist_set:
                raise InventoryContractError("이번 이동 물품은 보조 트레이에서 확인되어야 합니다.")
            if not moved_set.issubset(assist_set):
                raise InventoryContractError(
                    "이동 완료 물품 전체가 보조 트레이에 유지되어야 합니다."
                )

        present = tuple(tool for tool in required if tool in present_set)
        missing = tuple(
            tool
            for tool in required
            if tool in missing_set and tool not in moved_set
        )
        moved_in_order = tuple(tool for tool in required if tool in moved_set)
        move_queue = tuple(
            tool
            for tool in present
            if tool not in assist_set and tool not in moved_set
        )
        status = _resolve_status(
            missing,
            move_queue,
            moved_in_order,
            required,
            assist_set,
        )

        return cls(
            status=status,
            patient_id=case.patient_id,
            case_id=case.case_id,
            scenario_id=scenario.scenario_id,
            disease_name=case.disease_name,
            required_tools=required,
            present_required_tools=present,
            missing_tools=missing,
            move_queue=move_queue,
            moved_tools=moved_in_order,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "patient_id": self.patient_id,
            "case_id": self.case_id,
            "scenario_id": self.scenario_id,
            "required_tools": list(self.required_tools),
            "present_required_tools": list(self.present_required_tools),
            "missing_tools": list(self.missing_tools),
            "move_queue": list(self.move_queue),
            "moved_tools": list(self.moved_tools),
        }


def _validate_tool_list(value: object, field: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise InventoryContractError(f"{field}는 물품 ID 문자열 배열이어야 합니다.")
    if len(set(value)) != len(value):
        raise InventoryContractError(f"{field}에는 중복 물품이 없어야 합니다.")
    return tuple(value)


def _resolve_status(
    missing: tuple[str, ...],
    move_queue: tuple[str, ...],
    moved: tuple[str, ...],
    required: tuple[str, ...],
    assist: set[str],
) -> str:
    if len(set(moved) | assist) == len(required):
        return "completed"
    if not move_queue and not moved and not assist:
        return "no_required_tools_present"
    if missing:
        return "ready_with_missing_tools"
    return "ready"
