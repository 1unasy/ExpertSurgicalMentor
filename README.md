# ExpertSurgicalMentor

감기·폐렴·골절 가상 케이스를 입력받아 MainToolTray의 필요 물품을 확인하고, 실제로 존재하는 물품만 AssistTray로 전달하기 위한 교육용 Physical AI 프로젝트다.

현재 저장소에는 VLM 인벤토리 모듈과 ACT 데이터 수집·학습 보조 파일이 들어 있다. YOLO 손 감지 모듈, 물체별 ACT 정책 로더, 전체 시스템 통합 실행기는 이후 별도 모듈로 추가한다.

기본 시연은 `data/demo_cases_syringe_pill.json`의 감기 입력 하나를 사용한다. 입력에는 환자·케이스·질환만 있으며, 실행 시 Scenario Registry에서 `Syringe`, `Pill` 순서가 결정된다.

## 목표 처리 흐름

```text
환자 ID·질환 입력
        -> Scenario Registry에서 required_tools 확정
        -> YOLO Safety Controller가 트레이 영역의 손 감지
        -> VLM이 최초 3프레임에서 MainToolTray·AssistTray의 물품 확인
        -> 규칙 기반 코드가 move_queue 생성
        -> 대기열 첫 물품이 MainToolTray에 있는지 새 3프레임으로 재확인
        -> 3회 판단이 모두 일치한 경우에만 로봇 이동 명령 발행
        -> 로봇이 MainToolTray에서 AssistTray로 물품 이동
        -> 이동 완료 이벤트 이후 새 3프레임에서 AssistTray 이동 결과 확인
        -> 3회 판단이 모두 일치한 경우에만 moved 갱신
        -> 다음 물품에 대해 수행 전·후 확인 반복
        -> 필요한 물품·옮긴 물품·없는 물품 리포트 생성
```

YOLO는 현재 물품을 인식하지 않고 손의 트레이 진입 여부만 감지한다. VLM은 물품과 트레이 위치를 판정하지만 로봇 좌표나 파지점을 생성하지 않는다. `move_queue`와 이동 이력은 모델 출력에 맡기지 않고 코드에서 검증해 관리한다.

각 확인 단계는 해당 단계가 시작된 뒤 촬영된 대표 프레임 3장만 사용한다. 세 VLM 결과의 존재·누락·트레이 위치가 모두 일치해야 다음 상태로 진행한다. 불일치하거나 현재 물품을 수행 전 MainToolTray 또는 수행 후 AssistTray에서 확인하지 못하면 프레임 묶음을 폐기하고 같은 단계에서 다시 3장을 받는다. 손이 감지되면 수집 중인 프레임도 즉시 폐기한다.

## 저장소 구조

```text
ExpertSurgicalMentor/
├── config/                       입력·출력·시나리오·VLM 설정
├── data/                         VLM 평가용 가상 케이스
├── docs/                         프로젝트 계획과 ACT 작업 문서
├── expert_surgical_mentor/       재사용 가능한 Python 패키지
│   └── vlm/                      VLM 전용 추론·인벤토리 모듈
├── scripts/                      평가와 ACT 학습 실행 스크립트
├── src/                          로봇 하드웨어 보조 실행 파일
├── tests/                        외부 모델 없이 실행되는 단위 테스트
└── requirements-vlm.txt          VLM 추론 의존성
```

### 루트 파일

| 파일 | 역할 |
|---|---|
| `.gitignore` | Python 캐시, 로컬 가상환경, 모델·학습 출력처럼 저장소에 올리지 않을 파일을 제외한다. |
| `README.md` | 프로젝트 구조, 실행 흐름, 사용 방법을 설명한다. |
| `requirements-vlm.txt` | Qwen VLM 4-bit 추론에 필요한 PyTorch, Transformers, bitsandbytes 등의 버전 범위를 정의한다. |

### `config/`

| 파일 | 역할 |
|---|---|
| `case_input.schema.json` | `patient_id`, `case_id`, `disease_name` 입력 JSON 형식을 정의한다. |
| `inventory_output.schema.json` | 상태, 필요 물품, 존재 물품, 누락 물품, 이동 대기열, 이동 이력의 출력 형식을 정의한다. |
| `scenario_registry.json` | 감기·폐렴·골절과 질환별 `required_tools` 순서를 관리한다. 미등록 질환 고정 응답도 여기에서 관리한다. |
| `vlm_inventory_prompt.txt` | Qwen에 전달하는 역할, 해야 할 것, 하지 말아야 할 것, JSON 출력 규칙을 정의한다. |
| `vlm_models.json` | Qwen3-VL 2B, Qwen2.5-VL 3B, Qwen3-VL 4B의 우선순위와 NF4 4-bit 설정을 관리한다. |

### `data/`

| 파일 | 역할 |
|---|---|
| `virtual_cases_15.json` | 감기·폐렴·골절 각 5개씩 총 15개 비식별 가상 케이스와 평가 기대값을 제공한다. 학습 데이터가 아니라 VLM 비교 평가용 데이터다. |

### `docs/`

| 파일 | 역할 |
|---|---|
| `ExpertSurgicalMentor_plan.md` | VLM, YOLO 안전정지, ACT, ROS 2 연결을 포함한 기준 기획안이다. |
| `ExpertSurgicalMentor_plan.html` | 기획안을 브라우저에서 확인하기 위한 HTML 문서다. |
| `ExpertSurgicalMentor_imitation_episodes_60.md` | 초기 모방학습 에피소드 60개의 작업·변형·분할 정의를 설명한다. |
| `ExpertSurgicalMentor_imitation_episodes_60.jsonl` | 위 60개 에피소드를 프로그램에서 읽을 수 있는 JSONL 형식으로 제공한다. |
| `command.md` | LeRobot 데이터 추가 수집, 물체별 데이터 분할, ACT 학습·추론 명령을 정리한다. |

### `expert_surgical_mentor/`

VLM·YOLO·로봇이 공통으로 사용할 도메인 계약과 각 기능 모듈을 두는 Python 패키지다.

| 파일/폴더 | 역할 |
|---|---|
| `__init__.py` | 공용 케이스와 시나리오 타입을 패키지 외부에 노출한다. |
| `case_validation.py` | 환자 ID·케이스 ID 형식을 검사하고 미등록 질환을 거부한다. |
| `scenario_registry.py` | Scenario Registry를 읽고 질환별 필요 물품을 불변 조회 객체로 제공한다. |
| `vlm/` | 모델 로딩부터 ROS 2 이벤트 처리까지 VLM 관련 코드만 모아 둔다. |

### `expert_surgical_mentor/vlm/`

| 파일 | 역할 |
|---|---|
| `__init__.py` | VLM 하위 패키지를 선언한다. |
| `model_loader.py` | 선택한 Qwen 모델 하나를 bitsandbytes NF4 4-bit로 지연 로딩한다. 학습이나 가중치 변경은 수행하지 않는다. |
| `prompt.py` | 고정 system prompt와 환자·시나리오·`verification_tool` JSON을 Qwen 입력으로 조립한다. |
| `backend.py` | 이미지와 프롬프트를 Qwen chat template에 넣고 모델의 JSON 텍스트를 파싱한다. |
| `consensus.py` | 연속 3프레임의 물품 존재·누락·트레이 위치가 모두 일치하는지 검증한다. |
| `inventory.py` | VLM 원시 출력의 필드·물품 목록을 검증하고 `move_queue`, `missing_tools`, `moved_tools`를 결정한다. |
| `reporting.py` | 최종 인벤토리 상태를 한국어 세션 리포트와 JSON으로 변환한다. |
| `node.py` | 최초 확인·수행 전 확인·수행 후 확인의 3프레임 합의 상태 머신과 선택적 ROS 2 노드를 제공한다. |

### `scripts/`

| 파일 | 역할 |
|---|---|
| `evaluate_vlm_inventory.py` | 15개 케이스 이미지로 세 양자화 VLM을 순차 비교하고 정확도와 지연 시간을 출력한다. |
| `train_act_objects.sh` | syringe, glasses, pill, xray_image용 ACT 정책을 순서대로 학습한다. 이미 완료된 모델은 건너뛴다. |

### `src/`

| 파일 | 역할 |
|---|---|
| `omx_f_keyboard_teleop.py` | OMX-Follower 관절과 그리퍼를 키보드로 시험 조작하는 하드웨어 보조 도구다. ACT 정책 실행기는 아니다. |

`scripts/train_act_objects.sh`와 `docs/command.md`는 실행 환경의 `src/lerobot`을 사용하도록 작성되어 있다. LeRobot 소스와 학습 데이터·체크포인트는 이 저장소에 포함하지 않는다.

### `tests/`

| 파일 | 역할 |
|---|---|
| `test_case_validator.py` | 환자 입력, 질환 Registry, 미등록 질환 응답을 검증한다. |
| `test_vlm_inventory_schema.py` | VLM JSON 계약, 이동 대기열, 양자화 설정, Qwen 요청 구성을 검증한다. |
| `test_vlm_inventory_node.py` | 케이스 시작, 손 감지 정지, 물품별 이동 완료 검증, 리포트 상태 전이를 검증한다. |
| `test_evaluate_vlm_inventory.py` | 모델 하나가 실패해도 다음 후보 평가와 GPU 캐시 해제가 계속되는지 검증한다. |

## VLM 실행

Python 3.10 이상 환경에서 VLM 의존성을 설치한다.

```bash
python3 -m pip install -r requirements-vlm.txt
```

모든 후보는 4-bit 추론만 수행하며 모델을 학습하지 않는다. 실제 가중치 다운로드와 GPU 사용은 다음 평가 또는 ROS 2 실행 명령을 호출할 때 발생한다.

```bash
python3 scripts/evaluate_vlm_inventory.py \
  --image-dir data/evaluation_images
```

한 모델만 평가하려면 `--model qwen3_vl_2b`처럼 `config/vlm_models.json`의 key를 지정한다.

```bash
python3 -m expert_surgical_mentor.vlm.node \
  --model qwen3_vl_2b
```

ROS 2 노드는 다음 인터페이스를 사용한다.

| 방향 | 토픽 | 데이터 |
|---|---|---|
| 구독 | `/camera/keyframe` | VLM에 사용할 최신 `sensor_msgs/Image` |
| 구독 | `/safety/hand_state` | `{"hand_detected": true\|false}` |
| 구독 | `/case/input` | `patient_id`, `case_id`, `disease_name` JSON |
| 구독 | `/robot/move_completed` | `case_id`, `tool_id` JSON |
| 발행 | `/inventory/state` | 필요·존재·누락·이동 대기·이동 완료 물품 |
| 발행 | `/robot/move_command` | 수행 전 3프레임 확인을 통과한 `case_id`, `tool_id` JSON |
| 발행 | `/session/report` | 최종 세션 리포트 |
| 발행 | `/inventory/error` | 입력·모델 출력·이벤트 순서 오류 |

ROS 2 실행 순서는 다음과 같다.

1. `/case/input`을 수신하면 이전 프레임을 폐기하고 `initial_check`를 시작한다.
2. 이후 `/camera/keyframe` 3장의 결과가 일치하면 초기 `move_queue`를 발행한다.
3. 새 프레임 3장에서 대기열 첫 물품이 MainToolTray에 있으면 `/robot/move_command`를 발행한다.
4. 로봇은 이동을 마친 뒤 `/robot/move_completed`를 발행한다.
5. 완료 이벤트 이후 촬영된 새 프레임 3장에서 물품이 AssistTray에 있으면 `moved_tools`와 `move_queue`를 갱신한다.
6. 대기열이 남아 있으면 3번부터 반복하고, 없으면 `/session/report`를 발행한다.

## 테스트

테스트에서는 모델 가중치를 다운로드하거나 ROS 2를 실행하지 않는다.

```bash
python3 -m unittest discover -s tests -v
```

## 향후 통합 구조

향후에는 각 기능을 다음과 같이 분리한다.

```text
expert_surgical_mentor/
├── vlm/       필요 물품과 MainToolTray·AssistTray 상태 판정
├── yolo/      손 감지, 트레이 ROI 판정, Safety Controller 입력
├── robot/     물체별 ACT 체크포인트 로딩과 정책 실행
└── system/    위 세 모듈의 시작·종료·이벤트 순서를 관리하는 통합 실행기
```

통합 실행기는 모델을 서로 직접 호출하게 만들지 않고 다음 순서를 조정한다.

1. YOLO 손 감지가 안전 상태인지 확인한다.
2. 최초 VLM 3프레임 합의로 코드가 `move_queue`를 생성한다.
3. 다음 물품을 새 3프레임에서 MainToolTray에 확인한 뒤에만 이동 명령을 발행한다.
4. `robot/`의 정책 라우터가 해당 물품의 ACT 모델을 불러와 한 번 이동한다.
5. 이동 완료 이벤트 이후 새 3프레임에서 AssistTray 이동 결과를 확인한다.
6. 성공한 경우에만 `moved_tools`에 추가하고 다음 물품으로 진행한다.

물체별 30개 모방학습 평가에서 파지 정확도가 부족하면 확장 단계에서만 물품 검출용 YOLO를 추가하고, 그 위치 결과를 ACT 정책 입력 보정에 사용한다.
