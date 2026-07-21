#!/usr/bin/env python3
"""Validate demo configuration before launching transport-specific workers."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from expert_surgical_mentor.case_validation import validate_case_payload
from expert_surgical_mentor.robot.policy_registry import RobotPolicyRegistry
from expert_surgical_mentor.scenario_registry import ScenarioRegistry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    root = args.project_root.resolve()
    payload = json.loads(
        (root / "data" / "demo_cases_syringe_pill.json").read_text(encoding="utf-8")
    )
    registry = ScenarioRegistry.from_file(root / "config" / "scenario_registry.json")
    case, scenario = validate_case_payload(payload, registry)
    policies = RobotPolicyRegistry.from_file(root / "config" / "robot_policies.json")
    for tool_id in scenario.required_tools:
        policies.require(tool_id)
    print(json.dumps({
        "status": "configuration_ready",
        "case_id": case.case_id,
        "required_tools": list(scenario.required_tools),
        "hardware_started": False,
    }, ensure_ascii=False, indent=2))
    if not args.check_only:
        raise RuntimeError(
            "ROS 2 camera, YOLO checkpoint, LeRobot runtime과 OMX-AI stop API를 "
            "연결한 뒤에만 실제 구동할 수 있습니다."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
