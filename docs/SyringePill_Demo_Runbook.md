# Syringe/Pill 시연 런북

이 문서는 감기 입력으로 OMX-AI가 `Syringe`, `Pill`을 MainToolTray에서 AssistTray로 순서대로 옮기는 시연 절차다. VLM과 YOLO는 안전 인증 장치가 아니며, 물리 E-stop·속도/힘 제한·접근 차단이 준비되지 않으면 로봇을 움직이지 않는다.

## 1. 사전 준비

- MainToolTray에 Syringe와 Pill을 서로 겹치지 않게 놓고 AssistTray는 비운다.
- 카메라에서 두 트레이 경계와 두 물품이 모두 보이는지 확인한다.
- `config/robot_policies.json`의 두 checkpoint가 실제 LeRobot 출력 경로와 일치하는지 확인한다.
- 손 전용 YOLO checkpoint와 트레이 ROI를 별도 검증한다. 물품 검출용 YOLO를 사용하지 않는다.
- OMX-AI driver stop API와 물리 E-stop을 각각 시험한다.

설정만 확인한다.

```bash
python3 scripts/run_syringe_pill_demo.py --check-only
python3 -m unittest discover -s tests -v
```

## 2. VLM 모델 선택 실험

S0-S5를 각 5회 구성하고 시행마다 서로 다른 프레임 3장을 촬영한다. 1-3회는 개발용, 4-5회는 잠금 검증용이다.

```bash
python3 scripts/capture_vlm_eval_frames.py --state S0 --trial 1 --camera 0
```

위 명령을 S0-S5와 trial 1-5에 반복한다. 프롬프트·구도·조명을 수정할 때는 개발용 결과만 사용하고, 최종 모델 선택은 보지 않은 잠금 검증 시행으로 한다. 세 후보는 모두 `config/vlm_models.json`의 NF4 4-bit 설정으로 추론만 수행한다.

합격 기준은 Schema 유효율 100%, 잠금 검증 exact match 95% 이상, false-ready 0건이다. 조건을 만족한 모델 중 가장 작은 모델을 우선하고, 같은 크기면 P95 지연이 짧은 모델을 선택한다.

## 3. 정상 시연 순서

1. YOLO의 최신 상태가 `SAFE`인지 확인한다.
2. `data/demo_cases_syringe_pill.json`을 입력한다.
3. 초기 새 3프레임에서 Main=`Syringe,Pill`, Assist=빈 상태를 확인한다.
4. Syringe 수행 전 새 3프레임을 확인한 뒤 Syringe ACT 정책을 한 번 실행한다.
5. `execution_completed` 이후 새 3프레임에서 Syringe가 AssistTray에 있는지 확인한다.
6. Pill 수행 전 새 3프레임에서 Syringe가 AssistTray에 유지되고 Pill이 MainToolTray에 있는지 확인한다.
7. Pill ACT 정책을 한 번 실행한다.
8. 사후 새 3프레임에서 Syringe와 Pill이 모두 AssistTray에 있을 때만 `completed`로 끝낸다.

## 4. 실패와 복구

- 3프레임 불일치, 물품 누락 또는 위치 불일치: 로봇을 실행하지 않고 같은 단계의 새 관측을 요청한다.
- ACT `failed`, `timeout`, `stopped_safe`: 자동 재실행하지 않고 `recovery_required`로 둔다.
- 사후 확인 실패: `moved_tools`를 갱신하지 않는다. 장면 재확인은 로봇 명령 없이 수행한다.
- 손 감지: Safety Controller를 래치하고 독립 stop 경로를 호출한다. 손이 사라져도 자동 재개하지 않는다.
- reset 전에는 로봇 정지 확인, 홈/그리퍼 상태 확인, 물품을 MainToolTray에 복구, 새 SAFE 관측이 모두 필요하다.

## 5. 아직 필요한 실제 장비 연결

이 저장소의 `RobotPolicyRouter`는 의미 수준의 물품 명령을 checkpoint로 매핑하지만, 설치된 LeRobot 버전의 정책 실행 함수와 OMX-AI driver stop 함수는 아직 주입해야 한다. `UnconfiguredLeRobotRuntime`은 이 연결 없이 실제 구동을 시도하면 명시적으로 실패한다. 연결 후 Syringe 10회, Pill 10회 단독 평가와 정상 통합 3회 연속 성공을 기록한 뒤 촬영한다.
