# ExpertSurgicalMentor

감기·폐렴·골절 가상 케이스와 카메라 영상을 이용해 필요한 물품의 존재 여부를 확인하고, 실제로 있는 물품만 OMX-F 이동 대기열에 넣는 교육용 VLM 인벤토리 시스템이다.

## VLM 인벤토리 구성

- `config/scenario_registry.json`: 질환별 고정 물품 순서
- `data/virtual_cases_15.json`: 감기·폐렴·골절 각 5개 평가 케이스
- `config/vlm_models.json`: Qwen3-VL 2B, Qwen2.5-VL 3B, Qwen3-VL 4B의 4-bit 설정
- `expert_surgical_mentor/vlm_inventory_node.py`: 환자 입력·이동 완료 이벤트 처리
- `scripts/evaluate_vlm_inventory.py`: 15개 이미지로 세 모델을 순차 비교하는 추론 전용 스크립트

VLM은 카메라 프레임마다 실행하지 않는다. 최신 프레임은 계속 갱신하되 다음 두 이벤트에서만 추론한다.

1. 환자 ID와 질환명이 포함된 가상 케이스가 입력될 때
2. 로봇이 물품 하나의 이동 완료를 알릴 때

## 의존성

실행 PC에서 별도 가상환경을 만든 뒤 추론 의존성을 설치한다.

```bash
python3 -m pip install -r requirements-vlm.txt
```

모든 후보는 bitsandbytes NF4 4-bit로만 로드된다. 이 저장소의 VLM 코드는 추론과 비교만 수행하며 모델을 학습하거나 가중치를 수정하지 않는다.

Qwen 계열에는 `system` 역할로 `config/vlm_inventory_prompt.txt`를, `user` 역할로 환자·시나리오 JSON과 최신 이미지를 전달한다. Qwen 전용 chat template 토큰은 코드에 직접 적지 않고 `AutoProcessor.apply_chat_template()`이 모델 버전에 맞게 생성한다. YOLO는 물품을 인식하지 않으며, 별도 Safety Controller가 `hand_detected=true`일 때 VLM 추론과 로봇 실행을 중지한다.

이동 직후에는 `verification_tool` 하나만 AssistTray에서 시각적으로 재확인한다. 확인이 끝난 물품의 전달 이력은 코드가 유지하므로, 의료진이 해당 물품을 AssistTray에서 가져간 뒤 다음 프레임에서 보이지 않아도 이전 성공 기록은 취소되지 않는다.

## 테스트

외부 모델이나 ROS 2 없이 핵심 계약과 상태 전이를 검증할 수 있다.

```bash
python3 -m unittest discover -s tests -v
```

## VLM 후보 비교

먼저 `COLD_001.jpg`처럼 15개 Case ID와 같은 이름으로 평가 이미지를 준비한다. 그다음 세 양자화 모델을 우선순위대로 실행한다.

```bash
python3 scripts/evaluate_vlm_inventory.py --image-dir data/evaluation_images
```

한 모델만 확인하려면 `--model qwen3_vl_2b`처럼 `config/vlm_models.json`의 key를 전달한다. 실제 모델 가중치 다운로드와 GPU 추론은 이 명령을 실행할 때만 발생한다.

## ROS 2 이벤트 연결

ROS 2와 카메라 의존성이 설치된 로봇 PC에서는 다음과 같이 실행한다.

```bash
python3 -m expert_surgical_mentor.vlm_inventory_node --model qwen3_vl_2b
```

사용하는 인터페이스는 다음과 같다.

- 구독 `/camera/keyframe`: VLM에 사용할 최신 `sensor_msgs/Image`
- 구독 `/safety/hand_state`: YOLO 손 감지 상태 `{"hand_detected": true|false}`
- 구독 `/case/input`: 환자 ID·케이스 ID·질환명 JSON
- 구독 `/robot/move_completed`: `case_id`, `tool_id` JSON
- 발행 `/inventory/state`: 필요·존재·누락·이동 대기·이동 완료 물품
- 발행 `/session/report`: 필요한 물품·옮긴 물품·없는 물품 리포트
- 발행 `/inventory/error`: 입력·모델 출력·이벤트 순서 오류

카메라 프레임 수신 자체는 VLM 추론을 발생시키지 않는다. `/case/input` 또는 `/robot/move_completed` 이벤트가 들어올 때만 저장된 최신 프레임으로 추론한다.
