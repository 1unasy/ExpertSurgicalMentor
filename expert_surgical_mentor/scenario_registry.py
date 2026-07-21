"""Load and validate the fixed disease-to-tool scenario registry."""

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping


class ScenarioRegistryError(ValueError):
    """Raised when the scenario registry is malformed or internally inconsistent."""


@dataclass(frozen=True, slots=True)
class Scenario:
    scenario_id: str
    disease_name: str
    required_tools: tuple[str, ...]


class ScenarioRegistry:
    """Immutable lookup for the project's approved virtual disease scenarios."""

    def __init__(
        self,
        scenarios: tuple[Scenario, ...],
        allowed_tools: tuple[str, ...],
        unsupported_disease_message: str,
    ) -> None:
        self._validate(scenarios, allowed_tools, unsupported_disease_message)
        self._scenarios = scenarios
        self._allowed_tools = allowed_tools
        self._unsupported_disease_message = unsupported_disease_message
        self._by_disease: Mapping[str, Scenario] = MappingProxyType(
            {scenario.disease_name: scenario for scenario in scenarios}
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "ScenarioRegistry":
        registry_path = Path(path)
        try:
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ScenarioRegistryError(
                f"Scenario Registry를 읽을 수 없습니다: {registry_path}"
            ) from error

        if not isinstance(payload, dict):
            raise ScenarioRegistryError("Scenario Registry 최상위 값은 객체여야 합니다.")

        try:
            raw_scenarios = payload["scenarios"]
            raw_allowed_tools = payload["allowed_tools"]
            unsupported_message = payload["unsupported_disease_message"]
        except KeyError as error:
            raise ScenarioRegistryError(f"필수 Registry 필드가 없습니다: {error.args[0]}") from error

        if not isinstance(raw_scenarios, list) or not isinstance(raw_allowed_tools, list):
            raise ScenarioRegistryError("scenarios와 allowed_tools는 배열이어야 합니다.")

        scenarios: list[Scenario] = []
        for raw_scenario in raw_scenarios:
            if not isinstance(raw_scenario, dict):
                raise ScenarioRegistryError("각 scenario는 객체여야 합니다.")
            try:
                scenario_id = raw_scenario["scenario_id"]
                disease_name = raw_scenario["disease_name"]
                required_tools = raw_scenario["required_tools"]
            except KeyError as error:
                raise ScenarioRegistryError(
                    f"scenario 필드가 없습니다: {error.args[0]}"
                ) from error
            if not all(isinstance(value, str) for value in (scenario_id, disease_name)):
                raise ScenarioRegistryError("scenario_id와 disease_name은 문자열이어야 합니다.")
            if not isinstance(required_tools, list) or not all(
                isinstance(tool, str) for tool in required_tools
            ):
                raise ScenarioRegistryError("required_tools는 문자열 배열이어야 합니다.")
            scenarios.append(Scenario(scenario_id, disease_name, tuple(required_tools)))

        if not all(isinstance(tool, str) for tool in raw_allowed_tools):
            raise ScenarioRegistryError("allowed_tools는 문자열 배열이어야 합니다.")
        if not isinstance(unsupported_message, str):
            raise ScenarioRegistryError("unsupported_disease_message는 문자열이어야 합니다.")

        return cls(tuple(scenarios), tuple(raw_allowed_tools), unsupported_message)

    @staticmethod
    def _validate(
        scenarios: tuple[Scenario, ...],
        allowed_tools: tuple[str, ...],
        unsupported_message: str,
    ) -> None:
        if not scenarios:
            raise ScenarioRegistryError("최소 한 개의 scenario가 필요합니다.")
        if not allowed_tools or len(set(allowed_tools)) != len(allowed_tools):
            raise ScenarioRegistryError("allowed_tools는 비어 있지 않은 고유 목록이어야 합니다.")
        if not unsupported_message.strip():
            raise ScenarioRegistryError("미등록 질환 응답은 비어 있을 수 없습니다.")

        scenario_ids = [scenario.scenario_id for scenario in scenarios]
        disease_names = [scenario.disease_name for scenario in scenarios]
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ScenarioRegistryError("scenario_id가 중복되었습니다.")
        if len(set(disease_names)) != len(disease_names):
            raise ScenarioRegistryError("disease_name이 중복되었습니다.")

        allowed = set(allowed_tools)
        for scenario in scenarios:
            if not scenario.required_tools:
                raise ScenarioRegistryError(
                    f"{scenario.scenario_id}에 required_tools가 없습니다."
                )
            if len(set(scenario.required_tools)) != len(scenario.required_tools):
                raise ScenarioRegistryError(
                    f"{scenario.scenario_id}의 required_tools가 중복되었습니다."
                )
            unknown_tools = set(scenario.required_tools) - allowed
            if unknown_tools:
                names = ", ".join(sorted(unknown_tools))
                raise ScenarioRegistryError(f"등록되지 않은 물품입니다: {names}")

    @property
    def scenarios(self) -> tuple[Scenario, ...]:
        return self._scenarios

    @property
    def allowed_tools(self) -> tuple[str, ...]:
        return self._allowed_tools

    @property
    def unsupported_disease_message(self) -> str:
        return self._unsupported_disease_message

    def get_by_disease(self, disease_name: str) -> Scenario | None:
        return self._by_disease.get(disease_name)
