# Expert Surgical Mentor 전체 파이프라인 가이드

> 최종 갱신: 2026-07-22  
> 범위: 교육용 팬텀 환경에서 `감기 → 주사기 전달` 시나리오를 실행하기 위한 데이터,
> 학습, 추론, 안전 검증 및 UI 명령

## 1. 시스템 목표와 구성

사용자가 가상 환자 식별자와 질환을 입력하면 허용 목록에서 필요한 의료 장비를 결정하고,
장비 존재 여부를 확인한 다음 로봇이 전달한다. 현재 데모 매핑은 `감기 → syringe`다.

| 단계 | 기술 | 역할 | 최종 모델/파일 |
|---|---|---|---|
| 모방학습 | ACT | 물체별 pick-and-place 동작 생성 | `act_v2_full100k_{object}/checkpoints/050000` |
| 손 안전 | YOLO11n | 작업 영역에 손이 들어오면 로봇 일시정지 | `hand_yolo_n_sweep_stable_v1/weights/best.pt` |
| 장비 확인 | YOLO11s | syringe/pill 검출 및 트레이 위치 확인 | `object_yolo_v1/weights/best.pt` |
| 위치 판정 | Polygon ROI | Main/Assist Tray 내부 여부 판정 | `config/object_tray_rois.json` |
| 통합 실행 | Bash + Flask | 입력, 사전검사, ACT, 사후검사, 재시도 | `src/scripts/pipeline/` |

```text
환자명·질환 입력
  → 질환-장비 허용 목록 매핑
  → Object YOLO Main Tray 사전검사
  → Hand YOLO 안전 감시 + ACT 실행
  → 초기 자세 복귀
  → Object YOLO Assist Tray 사후검사
  → 성공 종료 / 제한적 재시도 / 안전 중단
```

## 2. 공통 환경 확인

```bash
source ~/venv/il/bin/activate
cd ~/ExpertSurgicalMentor

python --version
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
nvidia-smi
```

기준 장비는 NVIDIA GeForce RTX 4060 Laptop GPU 8GB이며, 카메라는 front `/dev/video4`,
wrist `/dev/video2`, follower 로봇 포트는 `/dev/ttyACM0`을 사용한다.

## 3. 모방학습: 데이터 수집, 학습, 추론

### 3.1 데이터 수집

현재 대상은 syringe와 pill이며 각각 40개 시연 에피소드를 사용한다.

```bash
./src/scripts/imitation_learning/record_object_dataset.sh new pick_and_place_v2 syringe 40
./src/scripts/imitation_learning/record_object_dataset.sh more pick_and_place_v2 pill 40
```

Hugging Face 업로드:

```bash
./src/scripts/imitation_learning/upload_lerobot_dataset.sh pick_and_place_v2
```

물체별 ACT 학습 입력은 다음 형식이다.

```text
1unasy/pick_and_place_v2_syringe
1unasy/pick_and_place_v2_pill
```

### 3.2 ACT 학습

```bash
STEPS=100000 \
SAVE_FREQ=10000 \
BATCH_SIZE=8 \
./src/scripts/imitation_learning/train_act_objects.sh syringe pill
```

| 설정 | 값 | 의미 |
|---|---:|---|
| `STEPS` | 100000 | optimizer update 횟수 |
| `SAVE_FREQ` | 10000 | checkpoint 저장 간격 |
| `BATCH_SIZE` | 8 | 한 step에 사용하는 샘플 수 |
| `policy.type` | ACT | Action Chunking Transformer |
| `use_amp` | true | CUDA mixed precision 사용 |

최종 데모는 20k~100k 실제 로봇 비교 중 우선 50,000-step checkpoint를 사용한다.
`last`가 반드시 최적은 아니며 ACT에는 현재 자동 validation 기반 best checkpoint 선정이 없다.

### 3.3 ACT 단독 추론

```bash
MODEL_PREFIX=act_v2_full100k \
./src/scripts/imitation_learning/run_act_object.sh syringe \
  --checkpoint 050000 \
  --episodes 1 \
  --episode-time 30 \
  --action-steps 100
```

이 실행기는 시작 자세 이동, 손 안전 감시, ACT 실행, 시작 자세 복귀를 포함한다.

## 4. Hand YOLO 데이터셋과 모델

### 4.1 목적

사람 손이 로봇 작업 영역에 들어오면 현재 관절 위치를 유지하여 충돌 위험을 낮춘다. 손이
연속 10초 동안 사라지면 정지 전에 계산한 action chunk를 폐기하고 현재 영상에서 재계획한다.

### 4.2 데이터셋

| 항목 | 내용 |
|---|---|
| 경로 | `datasets/hand/yolo_v1/hospital.yolov11` |
| 원본 수집 | 152장 |
| Roboflow 라벨 결과 | 150장 |
| Train / Valid | 120 / 30 |
| 클래스 | `hand` 1개 |
| Positive / Negative | 104 / 46 |
| 핵심 negative | 손 없는 로봇팔·그리퍼 이미지 N3 |
| 카메라 | front 중심 |

Positive는 측면 진입, Assist Tray 접근, 도구 파지, Main Tray 위 손, 근접 손을 포함한다.
Negative에는 빈 장면, 장비·트레이, 로봇팔·그리퍼를 포함하여 자기 로봇을 손으로 오검출하는
문제를 줄였다.

수집 도구:

```bash
python ./src/scripts/hand_yolo/collect_hand_images.py --list-cameras
python ./src/scripts/hand_yolo/collect_hand_images.py --cam 4 --out datasets/hand/raw
```

### 4.3 학습 방법

```bash
MODEL=yolo11n.pt RUN_NAME=hand_yolo_n_sweep_stable_v1 \
  DEVICE=0 BATCH=8 ./src/scripts/hand_yolo/train_hand_yolo.sh
```

| 항목 | 설정 |
|---|---|
| Base model | `yolo11n.pt` |
| Image size | 640 |
| Batch | 8 |
| Max epochs | 100 |
| Early stopping patience | 20 |
| Optimizer | AdamW |
| AMP | true |
| Seed / deterministic | 0 / true |

### 4.4 n/s/m 비교와 선정 모델

동일한 안정화 조건에서 YOLO11n/s/m을 비교했다. 표의 값은 각 `results.csv`에서
`mAP50-95`가 가장 높은 epoch다.

| 모델 | Best epoch | Precision | Recall | mAP50 | mAP50-95 |
|---|---:|---:|---:|---:|---:|
| **YOLO11n** | **35** | **1.0000** | **0.9984** | **0.9950** | **0.7445** |
| YOLO11s | 49 | 0.9448 | 1.0000 | 0.9892 | 0.7799 |
| YOLO11m | 23 | 0.8305 | 0.8889 | 0.9350 | 0.6733 |

YOLO11s가 mAP50-95는 가장 높지만 최종 배포는 YOLO11n을 사용한다. Nano는 약 5.3MB이며
Precision 1.0, Recall 0.9984, mAP50 0.995를 유지하면서 ACT와 동시에 실행할 때 GPU·지연
부담이 더 낮다. 즉 정확도 단일 지표보다 실시간 통합 안정성을 우선한 선택이다.

```text
models/hand_yolo/best.pt
```

Validation이 30장으로 작으므로 위 수치를 실제 안전 보증으로 해석하면 안 된다. 장갑, 조명,
가림, 빠른 손 진입, 로봇팔 근접 조건에 대한 별도 현장 시험이 필요하다.

### 4.5 단독 추론과 통합 설정

```bash
yolo detect predict \
  model=models/hand_yolo/best.pt \
  source=4 imgsz=640 conf=0.15 device=0 show=true save=false
```

통합 파이프라인 기본 설정은 confidence 0.15, 손이 사라진 뒤 재개 시간 10초다.

## 5. Object YOLO 데이터셋과 모델

### 5.1 목적

ACT 실행 전에 목표 장비가 Main Tray에 있는지 확인하고, 실행 후 Assist Tray로 옮겨졌는지
검증한다. 현재 클래스는 `pill`, `syringe` 두 개다.

### 5.2 데이터 생성과 에피소드 단위 분할

LeRobot의 80개 에피소드에서 시간상 균등한 네 프레임을 추출해 Roboflow에서 bbox를
라벨링했다. 다운로드된 기존 split을 합친 다음 seed 42로 다시 분리했다.

```bash
python ./src/scripts/object_yolo/extract_object_yolo_frames.py \
  --repo-id 1unasy/pick_and_place_v2 \
  --samples-per-episode 4

python ./src/scripts/object_yolo/prepare_object_yolo_dataset.py \
  --source datasets/objects \
  --output datasets/objects_grouped \
  --seed 42 --overwrite
```

인접 프레임이 train과 validation에 섞이는 누수를 막기 위해 이미지가 아니라 에피소드
단위로 분리한다. syringe 40개와 pill 40개 에피소드를 각각 8:1:1로 나눈다.

| Split | 에피소드 | 이미지 | pill 이미지 | syringe 이미지 | pill bbox | syringe bbox |
|---|---:|---:|---:|---:|---:|---:|
| Train | 64 | 233 | 113 | 120 | 210 | 153 |
| Valid | 8 | 29 | 13 | 16 | 26 | 19 |
| Test | 8 | 32 | 16 | 16 | 28 | 29 |
| **합계** | **80** | **294** | **142** | **152** | **264** | **201** |

### 5.3 학습 방법

```bash
./src/scripts/object_yolo/train_object_yolo.sh
```

| 항목 | 설정 |
|---|---|
| Base model | `yolo11s.pt` |
| Classes | `pill`, `syringe` |
| Image size | 640 |
| Batch | 8 |
| Max epochs | 150 |
| Early stopping patience | 30 |
| Seed / deterministic | 0 / true |
| AMP | true |

학습 종료 후 `best.pt`를 에피소드가 분리된 test split으로 추가 평가하는 명령이 스크립트에
포함돼 있다.

### 5.4 선정 모델과 validation 성능

```text
models/object_yolo/best.pt
```

`results.csv`에서 mAP50-95가 가장 높은 epoch 105의 validation 결과다.

| 지표 | 값 |
|---|---:|
| Precision | 0.9866 |
| Recall | 0.9982 |
| mAP50 | 0.9950 |
| mAP50-95 | 0.8795 |

선정 이유는 validation mAP50-95가 가장 높은 `best.pt`이며, 파이프라인에 필요한 두 클래스가
모두 포함된 단일 모델이기 때문이다. Test 결과 시각화는
`outputs/train/object_yolo_v1_test/`에 저장되어 있으나 현재 별도 CSV 요약은 없으므로 발표
수치에는 validation 값과 실제 로봇 성공률을 구분해 사용해야 한다.

### 5.5 단독 위치 검증

```bash
python ./src/scripts/object_yolo/object_yolo_verifier.py syringe \
  --model models/object_yolo/best.pt \
  --roi-config config/object_tray_rois.json \
  --camera 4 --confidence 0.5 --frames 10 --required 5
```

단일 프레임이 아니라 같은 트레이에서 연속 5프레임 검출되어야 `main` 또는 `assist`로
확정한다. 그 외에는 `unknown`으로 처리하여 로봇 동작을 차단한다.

## 6. Main/Assist Tray 다각형 좌표

대각선 트레이를 축 정렬 사각형으로 처리하면 책상 영역이 ROI에 포함되므로 3~8개 꼭짓점의
다각형을 사용한다.

```bash
python ./src/scripts/tray/calibrate_tray_rois.py \
  --camera 4 --min-points 3 --max-points 8
```

- 외곽점을 시계 또는 반시계 방향으로 선택
- 왼쪽 클릭: 점 추가
- 오른쪽 클릭: 마지막 점 취소
- `R`: 초기화, `Enter`: 저장, `Esc`: 취소
- 픽셀 좌표를 0~1로 정규화하여 `config/object_tray_rois.json`에 저장
- YOLO bbox 중심점을 OpenCV `pointPolygonTest`로 검사

```text
Main polygon 내부   → main
Assist polygon 내부 → assist
두 polygon 외부     → outside/unknown
```

카메라 또는 트레이 위치가 변경되면 반드시 다시 보정해야 한다.

## 7. 전체 파이프라인 실행

### 7.1 Flask 설치

```bash
source ~/venv/il/bin/activate
cd ~/ExpertSurgicalMentor
python -m pip install -r requirements-ui.txt
```

### 7.2 로봇 미동작 설정 검사

```bash
./src/scripts/pipeline/run_cold_scenario.sh 감기 \
  --patient 환자A \
  --checkpoint 050000 \
  --dry-run
```

### 7.3 웹 UI 실행

```bash
python ./src/scripts/pipeline/run_cold_scenario_web.py
```

브라우저 주소:

```text
http://127.0.0.1:5050
```

UI는 먼저 환자명과 질환 입력만 표시한다. 설정 검사는 입력 화면 아래에 결과만 출력한다.
전체 실행을 선택한 경우에만 다음 모니터 화면으로 이동한다.

- 왼쪽: 의료 장비 확인 화면 — Object YOLO 사전·사후 결과
- 오른쪽: 의료 장비 전달 수행 화면 — ACT가 사용하는 front 카메라 최신 화면
- 하단: 로그, 종료 코드, 소프트웨어 긴급 정지

### 7.4 CLI 전체 실행

```bash
PATIENT_NAME="환자A"
DISEASE="감기"

./src/scripts/pipeline/run_cold_scenario.sh "${DISEASE}" \
  --patient "${PATIENT_NAME}" \
  --checkpoint 050000 \
  --action-steps 100 \
  --episode-time 30 \
  --max-retries 1
```

## 8. 성공·재시도·중단 조건

| 시점 | 판정 | 동작 |
|---|---|---|
| 작업 전 | Main 연속 5프레임 | ACT 실행 허용 |
| 작업 전 | Assist | 이미 전달된 것으로 종료 |
| 작업 전 | Unknown | 로봇을 움직이지 않고 종료 코드 3 |
| 작업 후 | Assist 연속 5프레임 | 성공, 추가 명령 없이 자동 종료 |
| 작업 후 | Main 연속 5프레임 | 초기 자세에서 제한 횟수 재시도 |
| 작업 후 | Unknown | 낙하·파지 중 가능성 때문에 자동 재시도 차단 |

소프트웨어 긴급 정지는 프로세스 그룹에 SIGINT를 보내 정상 종료 처리를 요청한다. 이는 통신
장애에서도 동작이 보장되는 물리 비상정지 장치를 대체하지 않는다.

## 9. 결과 해석과 남은 평가

- YOLO validation 성능은 작은 고정 데이터셋 결과이며 안전 인증 수치가 아니다.
- ACT는 offline validation best가 없으므로 실제 로봇의 새로운 위치·회전 조건에서 checkpoint를
  비교해야 한다.
- 전체 성공률은 `목표 선택 → 접근 → 파지 → 이송 → 배치 → Assist 확인`이 모두 성공한
  비율로 별도 기록한다.
- 실제 개인정보 대신 `환자A`, `CASE_001` 같은 가상 식별자만 사용한다.
- 본 시스템은 임상용이 아니라 교육용 팬텀 데모다.
