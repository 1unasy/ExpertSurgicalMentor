"""Temporal consensus rules for VLM inventory assessments."""

from collections.abc import Sequence

from .inventory import VisualInventoryAssessment


CONSECUTIVE_FRAME_COUNT = 3


class InventoryConsensusError(RuntimeError):
    """Raised when a frame batch cannot produce a unanimous assessment."""


def require_unanimous_assessment(
    assessments: Sequence[VisualInventoryAssessment],
) -> VisualInventoryAssessment:
    if len(assessments) != CONSECUTIVE_FRAME_COUNT:
        raise InventoryConsensusError(
            f"VLM 판단에는 연속 {CONSECUTIVE_FRAME_COUNT}개 프레임이 필요합니다."
        )

    signatures = {_assessment_signature(assessment) for assessment in assessments}
    if len(signatures) != 1:
        raise InventoryConsensusError(
            f"연속 {CONSECUTIVE_FRAME_COUNT}개 프레임의 "
            "VLM 판단이 일치하지 않습니다."
        )
    return assessments[-1]


def _assessment_signature(
    assessment: VisualInventoryAssessment,
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    return (
        frozenset(assessment.present_required_tools),
        frozenset(assessment.missing_tools),
        frozenset(assessment.assist_tray_tools),
    )
