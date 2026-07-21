# ExpertSurgicalMentor 기획안

## 1. 프로젝트 주제

**프로젝트명:** 숙련 수술 멘토 (**ExpertSurgicalMentor**)

**프로젝트 한 줄 정의:**  
질환명이 포함된 비식별 가상 케이스를 입력하면 VLM이 등록된 시나리오에서 필요한 물품 순서를 조회하고, 카메라 영상에서 현재 트레이에 있는 물품과 없는 물품을 구분한다. OMX-AI 기반 모방학습 로봇팔은 실제로 존재하는 필요 물품만 큰 트레이에서 작은 보조 트레이로 옮기며, 시스템은 필요한 물품·옮긴 물품·없는 물품을 정리해 알려준다.

> 본 프로젝트는 실제 환자를 진단하거나 의료행위를 지시하는 시스템이 아니다. 실제 환자와 연결되지 않는 임의의 환자 ID, 장난감 도구, 가상 질환 시나리오를 사용하는 교육용 MVP이다.

---

## 2. MVP 범위와 핵심 결정

### 2.1 등록 질환

MVP에서 허용하는 질환은 다음 세 가지로 한정한다.

| Scenario ID | 질환 | 필요한 물품 순서 |
|---|---|---|
| `SIM_COLD` | 감기 | `Syringe → Pill` |
| `SIM_PNEUMONIA` | 폐렴 | `XRay → Pill → Syringe` |
| `SIM_FRACTURE` | 골절 | `Glasses → XRay → Pill` |

위 순서는 실제 임상 지침이 아니라 프로젝트에서 정의한 교육용 가상 순서다.

등록되지 않은 질환이 입력되면 VLM이 유사 질환이나 새로운 도구 순서를 임의로 생성하지 않고 다음 문장만 반환한다.

> 등록되지 않은 질환입니다.

```json
{
  "status": "unsupported_disease",
  "message": "등록되지 않은 질환입니다."
}
```

### 2.2 사용 물품

| ID | 한글명 | 시스템 ID | 물리 객체 정의 |
|---|---|---|---|
| T01 | 장난감 주사기 | `Syringe` | 바늘이 없는 장난감 주사기 |
| T02 | 안경 | `Glasses` | 교육용 안경 또는 보호안경 모형 |
| T03 | 알약 | `Pill` | 복용할 수 없는 알약 모형 |
| T04 | X-ray | `XRay` | X-ray 이미지 카드 또는 필름 모형 |

### 2.3 범위 밖 항목

- 실제 환자 개인정보 입력
- 실제 진단, 처방, 투약, 약물명 또는 용량 생성
- 등록되지 않은 질환에 대한 의료 추론
- VLM 판단만으로 로봇을 직접 실행하거나 안전정지를 해제하는 기능
- 로봇이 사람 손에 직접 물품을 건네는 동작

---

## 3. 가상 케이스 입력 계약

환자정보는 `patient_id` 하나만 사용한다. `patient_id`는 실제 환자와 연결되지 않는 임의의 영문·숫자 조합으로 생성한다.

```json
{
  "patient_id": "PT7A21B",
  "case_id": "CASE_2026_001",
  "disease_name": "폐렴"
}
```

### 3.1 입력 검증 규칙

- `patient_id`는 영문과 숫자로만 구성한다.
- 영문과 숫자를 각각 하나 이상 포함한다.
- 이름, 생년월일, 전화번호, 이메일, 병원 등록번호는 입력하지 않는다.
- 한 케이스에는 질환 하나만 입력한다.
- 허용 질환은 `감기`, `폐렴`, `골절` 세 가지뿐이다.
- 실제 환자와 연결되는 별도 대응표를 만들지 않는다.

질환이 두 개 이상이면 `질환은 하나만 입력해 주세요.`를 반환하고, 등록되지 않은 질환이면 `등록되지 않은 질환입니다.`를 반환한다.

---

## 4. VLM 활용 방향

### 4.1 VLM을 사용하는 이유

이 프로젝트에서 LLM 대신 VLM을 사용하는 선택은 타당하다. 텍스트 케이스만 해석하는 것이 아니라 카메라 영상을 함께 받아 다음 정보를 판단해야 하기 때문이다.

1. 질환에 필요한 물품 목록은 무엇인가
2. 큰 트레이에 필요한 물품이 실제로 있는가
3. 필요한 물품 중 없는 것은 무엇인가
4. 현재 옮길 수 있는 물품은 무엇인가
5. 이동 후 어떤 물품이 보조 트레이에 놓였는가

다만 VLM을 매 카메라 프레임마다 실행하는 방식은 사용하지 않는다. VLM은 지연이 크고 출력이 매번 달라질 수 있으며, 현재 PC의 8GB VRAM을 ACT 정책과 공유해야 한다. 따라서 다음과 같이 역할을 분리한다.

| 기능 | 담당 | 실행 주기 |
|---|---|---|
| 트레이 영역의 손 감지 | YOLO | 실시간, 목표 10~30 FPS |
| 필요 물품과 현재 장면의 의미 비교 | VLM | 세션 시작·장면 변경·이동 직후 |
| 이동 대상 목록 계산 | 규칙 기반 Inventory Manager | VLM 결과 수신 시 |
| 로봇 실행 허가·정지 | Safety Controller | 실시간 |
| 사용자용 결과 요약 | VLM | 단계 종료·세션 종료 |

VLM은 영상 전체를 계속 스트리밍받는 대신 이벤트가 발생했을 때 선명한 대표 프레임 또는 짧은 프레임 묶음을 받는다.

### 4.2 VLM의 입력

```json
{
  "patient_id": "PT7A21B",
  "case_id": "CASE_2026_001",
  "disease_name": "폐렴",
  "required_tools": ["XRay", "Pill", "Syringe"],
  "image": "MainToolTray와 AssistTray가 함께 보이는 최신 대표 프레임"
}
```

VLM에는 환자 ID, 질환명, 시나리오 Registry에서 가져온 필요 물품 목록과 최신 카메라 프레임을 제공한다. YOLO 손 감지 상태는 VLM 입력이 아니라 별도 Safety Controller에서 사용한다. YOLO는 현재 물품을 인식하지 않으며, VLM이 두 트레이의 물품 종류와 위치를 판정한다. `hand_detected=true`이면 VLM 추론과 로봇 실행을 시작하지 않는다.

### 4.3 VLM의 출력

```json
{
  "status": "ready_with_missing_tools",
  "patient_id": "PT7A21B",
  "case_id": "CASE_2026_001",
  "scenario_id": "SIM_PNEUMONIA",
  "required_tools": ["XRay", "Pill", "Syringe"],
  "present_required_tools": ["XRay", "Syringe"],
  "missing_tools": ["Pill"],
  "move_queue": ["XRay", "Syringe"],
  "moved_tools": []
}
```

`move_queue`는 다음 규칙으로 결정한다.

```text
move_queue = required_tools 순서의 present_required_tools
             - assist_tray_tools - moved_tools
순서는 required_tools의 기존 순서를 유지
```

없는 물품은 건너뛰되 `missing_tools`에 반드시 기록한다. VLM이 물품 또는 트레이 위치를 확신하지 못하면 로봇을 실행하지 않고 프레임을 다시 획득한다.

VLM의 원시 판정에는 `assist_tray_tools`를 추가한다. 로봇의 이동 완료 이벤트를 받은 뒤 `verification_tool`로 지정된 이번 물품이 후속 프레임의 `AssistTray`에서 확인된 경우에만 `moved_tools`에 반영한다. 단순히 작업 공간 어딘가에 보이는 것만으로 이동 성공으로 처리하지 않는다. 이전에 확인된 `moved_tools`는 코드가 전달 이력으로 유지하므로 의료진이 AssistTray에서 가져간 뒤 다음 프레임에 보이지 않아도 성공 기록을 취소하지 않는다.

### 4.4 최종 사용자 출력

```json
{
  "patient_id": "PT7A21B",
  "disease_name": "폐렴",
  "required_tools": ["XRay", "Pill", "Syringe"],
  "moved_tools": ["XRay", "Syringe"],
  "missing_tools": ["Pill"],
  "message": "필요한 물품은 X-ray, 알약, 주사기입니다. X-ray와 주사기를 옮겼으며 알약은 트레이에 없어 건너뛰었습니다."
}
```

---

## 5. 시스템 아키텍처

```text
가상 케이스 입력
    ↓
Case Validator
    ├─ 미등록 질환 → "등록되지 않은 질환입니다."
    └─ 등록 질환
          ↓
Scenario Registry
          ↓ required_tools
Camera Frame Buffer ← 상단 카메라
          ↓ 대표 프레임
YOLO Hand Detection ──────────┐
          ↓                   │
VLM Inventory Checker         │
          ↓                   │
Inventory Manager             │
          ↓ move_queue        │
Safety Controller ←───────────┘
          ↓ SAFE
Robot Task Router
          ↓
물체별 ACT Policy / Trajectory Replay
          ↓
이동 후 VLM 재확인
          ↓
필요한 물품 / 옮긴 물품 / 없는 물품 리포트
```

### 5.1 ROS 2 노드 제안

| 노드 | 역할 |
|---|---|
| `case_input_node` | 환자 ID와 질환명이 포함된 가상 케이스 수신 |
| `case_validator_node` | 환자 ID 형식과 등록 질환 검증 |
| `scenario_registry_node` | 질환별 고정 물품 순서 제공 |
| `camera_buffer_node` | 카메라 프레임을 유지하고 이벤트 시 대표 프레임 제공 |
| `yolo_detection_node` | MainToolTray·AssistTray 영역의 손 감지 |
| `vlm_inventory_node` | 영상과 필요 물품을 비교해 존재·누락 물품 JSON 생성 |
| `inventory_manager_node` | `move_queue`, `moved_tools`, `missing_tools` 상태 관리 |
| `safety_controller_node` | 손 감지 시 로봇 정지 |
| `robot_task_router_node` | 물체별 ACT 정책 또는 replay 선택 |
| `session_report_node` | 최종 결과를 자연어와 JSON으로 출력 |

### 5.2 주요 토픽

| 토픽 | 데이터 |
|---|---|
| `/case/input` | `patient_id`, `case_id`, `disease_name` |
| `/scenario/required_tools` | 질환별 필요 물품 순서 |
| `/camera/keyframe` | VLM 검사용 대표 프레임 |
| `/safety/hand_state` | YOLO 손 감지 여부 `hand_detected` |
| `/inventory/state` | 필요·존재·누락·이동 완료 물품 |

`/robot/move_completed`는 이전 케이스의 지연 이벤트를 차단할 수 있도록 `case_id`와 `tool_id`를 포함한 JSON으로 전달한다.
| `/robot/move_queue` | 실행할 물품 ID 배열 |
| `/safety/state` | `READY`, `STOPPED`, `ERROR` |
| `/session/report` | 필요한 물품·옮긴 물품·없는 물품 |

---

## 6. VLM 모델 후보와 권장 순서

첨부된 실행 환경은 **NVIDIA GeForce RTX 4060 Laptop GPU, VRAM 8GB**다. ACT 정책과 같은 GPU를 사용할 가능성을 고려해 작은 로컬 모델부터 검증한다.

| 우선순위 | 모델 | 선정 이유 | 주의점 |
|---:|---|---|---|
| 1 | [`Qwen/Qwen3-VL-2B-Instruct`](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct) | 2B 규모, 이미지·영상 이해와 공간 인식 지원, Apache-2.0, 8GB GPU에서 가장 먼저 시험하기 적합 | 양자화 여부와 ACT 동시 실행 시 VRAM을 실제 측정해야 함 |
| 2 | [`Qwen/Qwen2.5-VL-3B-Instruct`](https://huggingface.co/Qwen/Qwen2.5-VL-3B-Instruct) | 객체 bbox·point localization과 안정적인 JSON 출력이 명시되어 있어 재고 판정 형식에 적합 | Qwen3-VL보다 이전 세대이며 3B라 추론 부하가 조금 큼 |
| 3 | [`Qwen/Qwen3-VL-4B-Instruct`](https://huggingface.co/Qwen/Qwen3-VL-4B-Instruct) | 2B 모델의 물품 판별 정확도가 부족할 때 사용할 정확도 우선 후보 | 8GB에서 ACT와 동시 상주는 빠듯할 수 있어 4-bit 양자화와 직렬 실행 필요 |
| 4 | [`openbmb/MiniCPM-V-4`](https://huggingface.co/openbmb/MiniCPM-V-4) | 4.1B 규모의 이미지·다중 이미지·영상 이해 모델로 효율성 대안 | 커스텀 코드 의존성과 출력 JSON 안정성을 별도 검증해야 함 |

### 6.1 최종 추천

1. `Qwen3-VL-2B-Instruct`로 로컬 기준선을 만든다.
2. 15개 가상 케이스의 정지 이미지 테스트에서 물품 존재·누락 판정 정확도를 측정한다.
3. JSON 파싱 성공률과 누락 물품 정확도가 부족하면 `Qwen2.5-VL-3B-Instruct`를 비교한다.
4. 2B·3B 모두 시각 판별이 부족할 때만 `Qwen3-VL-4B-Instruct` 양자화 모델을 시험한다.
5. 모든 모델은 ACT와 동시에 GPU를 사용하지 않고 먼저 직렬 실행한다. 동시 실행은 VRAM 사용량과 지연을 확인한 뒤 결정한다.

VLM 선택 기준은 일반 벤치마크 점수보다 다음 프로젝트 지표를 우선한다.

- 네 물품별 존재 여부 정확도
- 없는 물품을 있다고 판단하는 False Positive 비율
- `required_tools`, `present_required_tools`, `missing_tools` JSON 파싱 성공률
- 한 번의 인벤토리 추론 지연
- VLM과 ACT를 번갈아 실행할 때 최대 VRAM 사용량

---

## 7. 가상 케이스 15종

각 케이스에서 사용자 입력은 `patient_id`, `case_id`, `disease_name`만 포함한다. 아래의 `카메라 장면 정답`은 VLM에 텍스트로 제공하는 값이 아니라 테스트를 위해 실제 트레이에 배치할 물품과 기대 결과를 의미한다.

### 7.1 감기 5종

필요 물품 순서: `Syringe → Pill`

| Case ID | Patient ID | 카메라 장면 정답 | 옮길 물품 | 없는 물품 | 테스트 목적 |
|---|---|---|---|---|---|
| `COLD_001` | `P1COLD01` | Syringe, Pill | Syringe, Pill | 없음 | 정상 전체 수행 |
| `COLD_002` | `P2COLD02` | Syringe | Syringe | Pill | 두 번째 물품 누락 |
| `COLD_003` | `P3COLD03` | Pill | Pill | Syringe | 첫 번째 물품을 건너뛰고 다음 물품 수행 |
| `COLD_004` | `P4COLD04` | 없음 | 없음 | Syringe, Pill | 필요한 물품 전체 누락 |
| `COLD_005` | `P5COLD05` | Syringe, Pill, Glasses, XRay | Syringe, Pill | 없음 | 불필요한 물품이 함께 있을 때 선택 정확도 |

### 7.2 폐렴 5종

필요 물품 순서: `XRay → Pill → Syringe`

| Case ID | Patient ID | 카메라 장면 정답 | 옮길 물품 | 없는 물품 | 테스트 목적 |
|---|---|---|---|---|---|
| `PNEUMONIA_001` | `P1PNEU01` | XRay, Pill, Syringe | XRay, Pill, Syringe | 없음 | 정상 전체 수행 |
| `PNEUMONIA_002` | `P2PNEU02` | Pill, Syringe | Pill, Syringe | XRay | 첫 번째 물품 누락 |
| `PNEUMONIA_003` | `P3PNEU03` | XRay, Syringe | XRay, Syringe | Pill | 중간 물품 누락 |
| `PNEUMONIA_004` | `P4PNEU04` | XRay, Pill | XRay, Pill | Syringe | 마지막 물품 누락 |
| `PNEUMONIA_005` | `P5PNEU05` | XRay, Syringe, Glasses | XRay, Syringe | Pill | 누락 물품과 방해 물품 동시 존재 |

### 7.3 골절 5종

필요 물품 순서: `Glasses → XRay → Pill`

| Case ID | Patient ID | 카메라 장면 정답 | 옮길 물품 | 없는 물품 | 테스트 목적 |
|---|---|---|---|---|---|
| `FRACTURE_001` | `P1FRAC01` | Glasses, XRay, Pill | Glasses, XRay, Pill | 없음 | 정상 전체 수행 |
| `FRACTURE_002` | `P2FRAC02` | XRay, Pill | XRay, Pill | Glasses | 첫 번째 물품 누락 |
| `FRACTURE_003` | `P3FRAC03` | Glasses, Pill | Glasses, Pill | XRay | 중간 물품 누락 |
| `FRACTURE_004` | `P4FRAC04` | Glasses, XRay | Glasses, XRay | Pill | 마지막 물품 누락 |
| `FRACTURE_005` | `P5FRAC05` | Glasses, Pill, Syringe | Glasses, Pill | XRay | 누락 물품과 방해 물품 동시 존재 |

---

## 8. 실시간 인벤토리 확인 구현 순서

### 8.1 1단계: 정적 이미지 기준선

1. 네 물품을 단독·혼합·누락 조건으로 촬영한다.
2. Scenario Registry가 질환별 `required_tools`를 반환한다.
3. VLM에 이미지 한 장과 `required_tools`를 입력한다.
4. `present_required_tools`, `missing_tools`, `assist_tray_tools`, `move_queue` JSON을 생성한다.
5. 15개 가상 케이스의 정답과 비교한다.
6. 미등록 질환 입력 시 `등록되지 않은 질환입니다.`가 정확히 출력되는지 확인한다.

### 8.2 2단계: 이벤트 기반 카메라 연결

1. 카메라는 계속 프레임을 수집한다.
2. YOLO는 실시간으로 두 트레이 영역의 손 진입 여부만 검출한다.
3. 세션 시작, 물품 변화, 로봇 이동 완료 이벤트가 발생하면 대표 프레임을 선택한다.
4. 손이 감지되지 않은 경우에만 VLM이 대표 프레임에서 물품과 트레이 위치를 검토한다.
5. Inventory Manager가 `move_queue`를 확정한다.
6. 없는 물품은 건너뛰고 존재하는 물품만 로봇 라우터에 전달한다.

### 8.3 3단계: 이동 후 재검증

1. 물품 하나를 보조 트레이로 이동한다.
2. MainToolTray와 AssistTray의 대표 프레임을 다시 획득한다.
3. VLM이 목표 물품이 MainToolTray에서 AssistTray로 이동했는지 확인한다.
4. VLM이 현재 재고 상태를 다시 요약한다.
5. 성공한 물품을 `moved_tools`에 추가한다.
6. 실패하면 다음 물품으로 진행하지 않고 `MOVE_VERIFICATION_FAILED`를 출력한다.

### 8.4 4단계: 최종 리포트

세션 종료 시 다음 세 목록을 반드시 출력한다.

- 필요한 물품: `required_tools`
- 옮긴 물품: `moved_tools`
- 없는 물품: `missing_tools`

---

## 9. YOLO 안전정지

로봇과 트레이는 무균 영역으로 가정한다. 현재 YOLO는 큰 트레이 또는 작은 보조 트레이에 사람 손이 진입했는지만 감지하며, 손이 감지되면 로봇을 정지한다.

### 9.1 검출 대상

```text
등록 클래스:
- hand
```

### 9.2 정지 규칙

- 손이 `MainToolTray` 또는 `AssistTray` ROI에 진입하면 즉시 정지한다.
- 안전 상태가 정상으로 돌아와도 자동 재개하지 않고 사용자가 확인한 뒤 재개한다.

VLM은 안전정지 여부를 결정하거나 정지를 해제할 권한을 갖지 않는다.

---

## 10. 모방학습 기준선과 YOLO+ACT 확장안

### 10.1 현재 기준선

- `Syringe`, `Glasses`, `Pill`, `XRay`별 30개 에피소드를 수집한다.
- 카메라 영상, joint position, joint velocity, gripper position, task ID, 성공 여부를 동기화한다.
- 위치, 회전, 주변 물품 배치를 변화시킨다.
- 실패한 교시는 기본 학습셋에서 제외하고 오류 분석용으로 보관한다.
- 먼저 물체별 ACT 정책의 목표 선택·파지·이동·배치 성공률을 각각 10회 이상 평가한다.

### 10.2 확장 전환 조건

30개 학습을 완료한 뒤 다음 중 하나라도 발생하면 YOLO+ACT 결합 구조로 확장한다.

- 목표 물체 근처까지 가지만 파지가 반복적으로 빗나감
- 시작 위치를 조금 바꾸면 파지 성공률이 크게 하락함
- 물체의 회전 각도 변화에 취약함
- 목표 물체와 다른 물체가 가까울 때 잘못 집음
- 물체별 10회 평가에서 파지 성공률이 사전에 정한 기준에 미달함

이 확장은 30개 학습 전에는 필수 범위로 넣지 않는다. 먼저 현재 ACT 기준선을 평가하고 실패 원인이 확인된 경우에만 진행한다.

### 10.3 확장 구조

```text
VLM: 이동할 물체 ID 결정
    ↓
YOLO: 목표 물체 bbox·중심·방향 검출
    ↓
Pixel-to-Robot 좌표 변환
    ↓
기준 파지 궤적에 Δx·Δy·Δyaw 보정
    ↓
ACT 또는 파지 primitive 실행
    ↓
YOLO: 파지 및 이동 성공 재확인
```

YOLO 검출 예시는 다음과 같다.

```json
{
  "class_id": "Syringe",
  "confidence": 0.94,
  "bbox": [220, 145, 310, 280],
  "center_px": [265, 212],
  "orientation_deg": 18.5
}
```

고정 상단 카메라와 평평한 트레이에서는 Homography 또는 카메라-로봇 캘리브레이션을 이용해 중심 픽셀을 로봇 기준 `x`, `y`로 변환한다. 물체 높이는 물체별 고정 `grasp_z`를 사용한다.

기존 ACT 정책을 임의의 중간 상태에서 시작하지 않는다. 다음 순서로 확장한다.

1. 교시 데이터의 기준 물체 위치 `nominal_xy`를 저장한다.
2. YOLO가 현재 물체 위치 `detected_xy`를 계산한다.
3. `offset_xy = detected_xy - nominal_xy`를 구한다.
4. 기존 전체 궤적 또는 접근 waypoint에 위치 오프셋을 적용한다.
5. 물체 상단 안전 높이에서 한 번 더 위치를 확인한다.
6. 오차가 허용 범위 안일 때만 하강하고 파지한다.
7. 들어 올린 뒤 원래 위치에서 물체가 사라졌는지 확인한다.

---

## 11. 3인 기능별 To Do List

### 11.1 팀원 1 — VLM·시나리오·인벤토리 담당

- [ ] 환자 ID와 질환 입력 JSON Schema 확정
- [ ] 감기·폐렴·골절 Scenario Registry 작성
- [ ] 15개 가상 케이스를 Case–Plan Dataset으로 변환
- [ ] 미등록 질환 고정 응답 구현
- [ ] VLM Inventory Prompt 작성
- [ ] `required/present/missing/move_queue/moved` JSON 검증 구현
- [ ] Qwen3-VL 2B → Qwen2.5-VL 3B → Qwen3-VL 4B 순으로 비교
- [ ] 최종 세션 리포트 생성

**주요 산출물**

- `config/scenario_registry.json`
- `data/virtual_cases_15.json`
- `config/vlm_inventory_prompt.txt`
- `expert_surgical_mentor/vlm/node.py`
- `tests/test_case_validator.py`
- `tests/test_vlm_inventory_schema.py`

### 11.2 팀원 2 — 모방학습·ACT 담당

- [ ] 네 물체별 30개 에피소드 수집 완료
- [ ] 위치·회전·방해 물품 조건 분포 확인
- [ ] 물체별 ACT 정책 학습
- [ ] 목표 선택·파지·이동·배치 성공률 분리 측정
- [ ] 물체별 10회 이상 평가
- [ ] 30개 학습 후 파지 실패 패턴 분석
- [ ] 전환 조건 충족 시 YOLO 위치 오프셋 적용 구조 구현

**주요 산출물**

- `lerobot_dataset/`
- `imitation_policy/`
- `evaluation_results.csv`
- `tests/test_policy_router.py`
- 확장 시 `expert_surgical_mentor/grasp_offset_controller.py`

### 11.3 팀원 3 — ROS 2·YOLO·로봇 통합 담당

- [ ] 상단 카메라와 트레이 ROI 고정
- [ ] 손 YOLO 검출과 트레이 ROI 진입 판정 구현
- [ ] Camera Frame Buffer와 이벤트 트리거 구현
- [ ] Inventory Manager 상태 전이 구현
- [ ] Safety Controller와 수동 재개 구현
- [ ] 물체별 ACT Policy Router 연결
- [ ] 이동 전·후 검증과 최종 리포트 연결
- [ ] 확장 시 픽셀-로봇 좌표 변환 캘리브레이션
- [ ] 확장 시 네 물품 YOLO 검출 구현

**주요 산출물**

- `expert_surgical_mentor/yolo_detection_node.py`
- `expert_surgical_mentor/inventory_manager_node.py`
- `expert_surgical_mentor/safety_controller_node.py`
- `config/workspace_config.yaml`
- `config/robot_waypoints.yaml`
- `launch/expert_surgical_mentor.launch.py`
- `tests/test_inventory_manager.py`
- `tests/test_safety_controller.py`

---

## 12. 구현 우선순위

### Phase 1 — 입력과 정적 VLM 검증

1. 환자 ID·질환 입력 Schema를 확정한다.
2. 세 질환 Registry와 15개 케이스를 작성한다.
3. Qwen3-VL 2B를 이용해 정적 이미지 인벤토리 JSON을 생성한다.
4. 미등록 질환과 JSON Schema 실패 처리를 검증한다.

### Phase 2 — 실시간 인식과 상태 관리

1. YOLO 손 감지를 연결한다.
2. 카메라 대표 프레임 이벤트를 정의한다.
3. VLM 결과와 YOLO 손 감지 안전 상태를 Inventory Manager에서 합친다.
4. 없는 물품을 건너뛰고 존재하는 물품만 `move_queue`에 넣는다.

### Phase 3 — ACT 연결

1. 물체별 30개 ACT 학습 결과를 평가한다.
2. VLM의 `move_queue` 순서대로 물체별 정책을 호출한다.
3. 이동 후 VLM으로 성공 여부를 재확인한다.
4. 필요한 물품·옮긴 물품·없는 물품 리포트를 출력한다.

### Phase 4 — 조건부 YOLO+ACT 확장

1. 30개 학습 후 파지 성공률을 검토한다.
2. 파지 실패가 반복될 때만 카메라-로봇 캘리브레이션을 수행한다.
3. YOLO 중심·방향을 로봇 좌표로 변환한다.
4. ACT 궤적 또는 접근 waypoint에 위치 오프셋을 적용한다.
5. 동일한 평가 조건으로 확장 전후 파지 성공률을 비교한다.

---

## 13. MVP 성공 기준

| 항목 | 최소 성공 기준 |
|---|---|
| 입력 검증 | 영문·숫자 환자 ID와 세 등록 질환만 허용 |
| 미등록 질환 | `등록되지 않은 질환입니다.` 정확히 출력 |
| VLM 인벤토리 | 15개 케이스에서 존재·누락 물품 JSON 생성 |
| 실행 필터링 | 없는 물품을 건너뛰고 존재하는 필요 물품만 이동 |
| 로봇 전달 | 네 물품 중 데모 대상 물품을 MainToolTray에서 AssistTray로 이동 |
| 이동 검증 | 이동 성공 물품을 `moved_tools`에 기록 |
| 최종 리포트 | 필요한 물품·옮긴 물품·없는 물품을 모두 출력 |
| 안전 | 손이 트레이에 진입하면 즉시 정지 |
| 모방학습 | 물체별 30개 학습 후 파지 성공률을 정량 평가 |
| 조건부 확장 | 기준 미달 시 YOLO+ACT 위치 보정 전후 결과 비교 |

---

## 14. 최종 정의

**ExpertSurgicalMentor**는 감기·폐렴·골절 세 가지 가상 질환 케이스를 입력받아 필요한 물품을 결정하고, VLM으로 트레이에 실제로 존재하는 물품을 확인한 뒤 OMX-F가 존재하는 필요 물품만 보조 트레이로 옮기는 교육용 Physical AI 프로토타입이다.

VLM은 두 트레이의 물품 인식·위치 판정과 재고 요약을 담당하고, YOLO는 실시간 손 감지만 담당한다. 로봇 안전과 실행 여부는 규칙 기반 Safety Controller가 담당한다. 물체별 30개 모방학습을 우선 평가하며, 파지 정확도가 부족한 경우에만 확장 단계에서 물품 검출용 YOLO를 추가해 ACT 위치 보정에 결합한다.
