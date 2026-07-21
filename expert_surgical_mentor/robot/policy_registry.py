"""Validated tool-to-ACT policy configuration."""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RobotPolicy:
    tool_id: str
    checkpoint: str
    timeout_seconds: float


class RobotPolicyRegistry:
    def __init__(self, policies: tuple[RobotPolicy, ...]) -> None:
        if len({policy.tool_id for policy in policies}) != len(policies):
            raise ValueError("tool_id별 정책은 하나만 등록할 수 있습니다.")
        self._by_tool = {policy.tool_id: policy for policy in policies}

    @classmethod
    def from_file(cls, path: str | Path) -> "RobotPolicyRegistry":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            tuple(
                RobotPolicy(item["tool_id"], item["checkpoint"], item["timeout_seconds"])
                for item in payload["policies"]
            )
        )

    def require(self, tool_id: str) -> RobotPolicy:
        try:
            return self._by_tool[tool_id]
        except KeyError as error:
            raise ValueError(f"등록되지 않은 로봇 물품 정책입니다: {tool_id}") from error

