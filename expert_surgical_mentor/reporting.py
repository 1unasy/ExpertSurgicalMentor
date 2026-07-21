"""Deterministic Korean session reporting for inventory outcomes."""

from __future__ import annotations

from .inventory_schema import InventoryResult


_KOREAN_TOOL_NAMES = {
    "Syringe": "주사기",
    "Glasses": "안경",
    "Pill": "알약",
    "XRay": "X-ray",
}
_OBJECT_FORMS = {
    "Syringe": "주사기를",
    "Glasses": "안경을",
    "Pill": "알약을",
    "XRay": "X-ray를",
}
_TOPIC_FORMS = {
    "Syringe": "주사기는",
    "Glasses": "안경은",
    "Pill": "알약은",
    "XRay": "X-ray는",
}


def build_session_report(result: InventoryResult) -> dict[str, object]:
    required_text = _join_tools(result.required_tools)
    moved_text = _join_tools_with_final_form(result.moved_tools, _OBJECT_FORMS)
    missing_text = _join_tools_with_final_form(result.missing_tools, _TOPIC_FORMS)

    clauses = [f"필요한 물품은 {required_text}입니다."]
    if result.moved_tools:
        clauses.append(f"{moved_text} 옮겼으며")
    else:
        clauses.append("옮긴 물품은 없으며")
    if result.missing_tools:
        clauses.append(f"{missing_text} 트레이에 없어 건너뛰었습니다.")
    else:
        clauses.append("없는 물품은 없습니다.")

    return {
        "patient_id": result.patient_id,
        "case_id": result.case_id,
        "scenario_id": result.scenario_id,
        "disease_name": result.disease_name,
        "required_tools": list(result.required_tools),
        "moved_tools": list(result.moved_tools),
        "missing_tools": list(result.missing_tools),
        "message": " ".join(clauses),
    }


def _join_tools(tools: tuple[str, ...]) -> str:
    return ", ".join(_KOREAN_TOOL_NAMES[tool] for tool in tools)


def _join_tools_with_final_form(
    tools: tuple[str, ...],
    final_forms: dict[str, str],
) -> str:
    if not tools:
        return ""
    leading = [_KOREAN_TOOL_NAMES[tool] for tool in tools[:-1]]
    return ", ".join([*leading, final_forms[tools[-1]]])
