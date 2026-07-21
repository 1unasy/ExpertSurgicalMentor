"""Validation for de-identified virtual case input."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from .scenario_registry import Scenario, ScenarioRegistry


_PATIENT_ID_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*[0-9])[A-Za-z0-9]{4,32}$")
_CASE_ID_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*[0-9])[A-Za-z0-9_]{4,64}$")
_REQUIRED_FIELDS = frozenset({"patient_id", "case_id", "disease_name"})


class CaseValidationError(ValueError):
    """Raised when a virtual case violates the input contract."""


class UnsupportedDiseaseError(CaseValidationError):
    """Raised when a case requests a disease outside the fixed MVP registry."""

    def as_dict(self) -> dict[str, str]:
        return {"status": "unsupported_disease", "message": str(self)}


@dataclass(frozen=True, slots=True)
class CaseInput:
    patient_id: str
    case_id: str
    disease_name: str


def validate_case_payload(
    payload: Mapping[str, object],
    registry: ScenarioRegistry,
) -> tuple[CaseInput, Scenario]:
    """Validate a case payload and resolve its approved scenario."""

    actual_fields = set(payload)
    missing_fields = _REQUIRED_FIELDS - actual_fields
    if missing_fields:
        fields = ", ".join(sorted(missing_fields))
        raise CaseValidationError(f"필수 필드가 없습니다: {fields}")

    unknown_fields = actual_fields - _REQUIRED_FIELDS
    if unknown_fields:
        fields = ", ".join(sorted(unknown_fields))
        raise CaseValidationError(f"허용되지 않은 필드입니다: {fields}")

    patient_id = _require_string(payload, "patient_id")
    case_id = _require_string(payload, "case_id")
    disease_name = _require_string(payload, "disease_name")

    if _PATIENT_ID_PATTERN.fullmatch(patient_id) is None:
        raise CaseValidationError(
            "patient_id는 영문과 숫자를 각각 포함한 4~32자 조합이어야 합니다."
        )
    if _CASE_ID_PATTERN.fullmatch(case_id) is None:
        raise CaseValidationError(
            "case_id는 영문과 숫자를 포함한 4~64자 영문·숫자·밑줄 조합이어야 합니다."
        )

    scenario = registry.get_by_disease(disease_name)
    if scenario is None:
        raise UnsupportedDiseaseError(registry.unsupported_disease_message)

    return CaseInput(patient_id, case_id, disease_name), scenario


def _require_string(payload: Mapping[str, object], field: str) -> str:
    value = payload[field]
    if not isinstance(value, str) or not value:
        raise CaseValidationError(f"{field}는 비어 있지 않은 문자열이어야 합니다.")
    return value
