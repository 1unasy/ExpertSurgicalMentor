# 손 안전 감지 YOLO 학습 결과

## 1. 목적

로봇 작업 영역에 사람 손이 들어오는 상황을 front 카메라에서 감지하기 위해
YOLO11n 단일 클래스 객체 감지 모델을 학습했다. wrist 카메라는 사각지대·그리퍼 방해로
안전 검출에서 제외했다 (`docs/hand_safety_dataset.md` §1 참조). 현재 모델은 손을 감지하고
화면에 박스를 표시하며, 손 감지 결과는 LeRobot 실행기의 일시 정지·재개 안전 로직에
연결되어 있다.

## 2. 데이터셋

```text
datasets/hand/yolo_v1/hospital.yolov11
```

| 분할 | 이미지 | 손 박스 | Null (배경) |
|---|---:|---:|---:|
| train | 120 | 88 (86장에 분산, 2장은 두 손) | 34 |
| valid | 30 | 18 (18장 각 1개) | 12 (N1 3 / N2 3 / N3 6) |

클래스는 하나다.

```text
0: hand
```

학습 스크립트는 Roboflow `data.yaml`의 상대경로와 클래스 이름을 그대로 사용하지 않고,
실제 디렉터리를 가리키는 임시 `data.yaml`을 생성한다.

## 3. 학습 환경 및 명령

```text
GPU: NVIDIA GeForce RTX 4060 Laptop GPU
PyTorch: 2.10.0+cu128
Ultralytics: 8.4.103
Base model: yolo11n.pt
Image size: 640
Batch size: 16
Maximum epochs: 100
Early-stopping patience: 20
AMP: enabled
```

실행:

```bash
source ~/venv/il/bin/activate
cd ~/ExpertSurgicalMentor

DEVICE=0 bash scripts/train_hand_yolo.sh
```

CUDA 메모리가 부족할 때만 batch를 낮춘다.

```bash
DEVICE=0 BATCH=8 bash scripts/train_hand_yolo.sh
```

## 4. Early Stopping 결과

최대 100 epoch로 설정했지만 66 epoch 이후 20 epoch 동안 validation 성능 개선이 없어
86 epoch에서 자동 종료됐다.

```text
Best epoch: 66
Stopped epoch: 86
Patience: 20
Training time: 약 0.034시간
```

Early Stopping은 오류가 아니다. validation 성능이 더 이상 개선되지 않을 때 불필요한
학습과 과적합을 줄이고, 가장 성능이 좋았던 epoch의 가중치를 `best.pt`로 보존한다.
배포와 추론에는 마지막 상태인 `last.pt`가 아니라 `best.pt`를 사용한다.

## 5. 최종 validation 성능

`best.pt`를 30개 validation 이미지로 평가한 결과다.

| 지표 | 값 |
|---|---:|
| Precision | 0.900 |
| Recall | 0.995 |
| mAP50 | 0.975 |
| mAP50-95 | 0.770 |
| 추론 시간 | 약 1.6 ms/image |

Validation 데이터가 30장, 손 박스가 18개뿐이므로 이 수치를 실제 안전 성능으로 바로
간주하면 안 된다. 카메라 위치, 조명, 손 방향, 가림, 장갑 조건을 바꾼 별도 현장 평가가
필요하다.

학습 결과:

```text
outputs/train/hand_yolo_v1
```

배포 가중치:

```text
outputs/train/hand_yolo_v1/weights/best.pt
```

## 6. Validation 이미지 시각 검사

30개 validation 이미지에 confidence 0.25를 적용한 결과:

```text
정답 손 포함 이미지: 18
손 감지 이미지: 17
미탐: 1
오탐: 0
```

배경 이미지(N* 12장) 세부 검증:

```text
N1 빈 씬 (3장):        오탐 0
N2 도구/트레이 (3장):   오탐 0
N3 로봇 팔/그리퍼 (6장): 오탐 0   ← 그리퍼 오탐 방지 목표 달성
```

놓친 이미지:

```text
B2_wrist_with_robot_20260721_115734_0023_jpg.rf.be12a4c80a4da8507189107759fc604a.jpg
```

전체 이미지 예측:

```bash
source ~/venv/il/bin/activate
cd ~/ExpertSurgicalMentor

yolo detect predict \
  model=outputs/train/hand_yolo_v1/weights/best.pt \
  source=datasets/hand/yolo_v1/hospital.yolov11/valid/images \
  imgsz=640 \
  conf=0.25 \
  device=0 \
  save=true \
  save_txt=true \
  save_conf=true
```

안전 감지는 미탐 감소가 우선이므로 실제 환경에서는 `conf=0.15`, `0.20`, `0.25`를
비교해야 한다. 임계값을 낮추면 미탐은 줄어들 수 있지만 오탐이 증가할 수 있다.

## 7. 실시간 카메라 테스트

안전 검출은 front 카메라 단독으로 운영한다. 다른 LeRobot/OpenCV 프로그램이 카메라를
점유하지 않은 상태에서 실행한다.

Front 카메라(`/dev/video4`):

```bash
source ~/venv/il/bin/activate
cd ~/ExpertSurgicalMentor

yolo detect predict \
  model=outputs/train/hand_yolo_v1/weights/best.pt \
  source=4 \
  imgsz=640 \
  conf=0.15 \
  device=0 \
  show=true \
  save=false
```

`q` 또는 `Ctrl+C`로 종료한다.

## 8. 커밋 대상

다음 항목은 재현, 검토, 배포에 필요하므로 Git 추적 대상으로 유지한다.

```text
scripts/train_hand_yolo.sh
datasets/hand/yolo_v1/hospital.yolov11/
outputs/train/hand_yolo_v1/args.yaml
outputs/train/hand_yolo_v1/results.csv
outputs/train/hand_yolo_v1/results.png
outputs/train/hand_yolo_v1/Box*_curve.png
outputs/train/hand_yolo_v1/confusion_matrix*.png
outputs/train/hand_yolo_v1/val_batch0_labels.jpg
outputs/train/hand_yolo_v1/val_batch0_pred.jpg
outputs/train/hand_yolo_v1/weights/best.pt
```

다음 항목은 재생성 가능하거나 중복이므로 계속 제외한다.

```text
outputs/train/hand_yolo_v1/weights/last.pt
runs/
yolo11n.pt
*.cache
```

## 9. YOLO11 n/s/m 손 감지 모델 비교 실험

### 9.1 목적과 모델 역할

동일한 손 데이터셋에서 YOLO11n, YOLO11s, YOLO11m의 검출 성능과 모델 크기를 비교했다.
이 세 모델은 ACT 행동 정책을 대체하지 않는다. 파이프라인에서 선택되는 것은 **손 감지
안전 모델**뿐이며, 물품별 ACT 모델과 syringe/pill 물체 검출 모델은 별도로 고정된다.

```text
YOLO11 n/s/m: 사람 손 감지 → 로봇 일시 정지·재개
Object YOLO:  pill/syringe의 Main/Assist Tray 위치 검증
ACT:          지정된 물품의 pick-and-place 행동 생성
```

### 9.2 데이터 및 실험 환경

라벨링 전 `datasets/hand/raw` 원본은 학습 입력으로 사용하지 않았다. YOLO 형식으로
라벨링된 다음 데이터만 사용했다.

```text
datasets/hand/yolo_v1/hospital.yolov11
```

| 분할 | 이미지 | 손 박스 | 배경 이미지 |
|---|---:|---:|---:|
| train | 120 | 88 | 34 |
| valid | 30 | 18 | 12 |

별도 test split은 없으므로 아래 결과는 30장 validation 기준이다. 실제 안전 성능을
확정하려면 카메라·조명·손 방향·장갑 조건을 바꾼 현장 평가가 추가로 필요하다.

```text
GPU: NVIDIA GeForce RTX 4060 Laptop GPU (8GB)
PyTorch: 2.10.0+cu128
Ultralytics: 8.4.103
Models: yolo11n.pt, yolo11s.pt, yolo11m.pt
Image size: 640
Batch size: 8
Maximum epochs: 100
Early-stopping patience: 20
AMP: enabled
Seed: 0 (Ultralytics deterministic mode)
Optimizer: AdamW
Initial learning rate: 0.0005
```

### 9.3 자동 optimizer 실험 실패와 안정화

최초에는 세 모델 모두 `optimizer=auto`를 사용했다. YOLO11n은 정상 수렴했지만,
Ultralytics가 자동 선택한 AdamW `lr=0.002`에서 YOLO11s는 validation fitness가 반복적으로
붕괴했고 YOLO11m은 NaN이 4 epoch 지속되어 학습이 중단됐다.

이는 GPU 메모리 부족이 아니라 작은 데이터셋에 비해 큰 모델의 학습률이 너무 높았던
문제로 판단했다. 공정한 재비교에서는 세 모델 모두에 동일하게 `AdamW`,
`lr0=0.0005`를 명시했다. 이를 위해 `scripts/train_hand_yolo.sh`가 `OPTIMIZER`, `LR0`
환경변수를 받도록 확장됐다.

재현 명령:

```bash
source ~/venv/il/bin/activate
cd ~/ExpertSurgicalMentor

VARIANTS="n s m" \
SWEEP_TAG="sweep_stable_v1" \
DEVICE=0 \
BATCH=8 \
EPOCHS=100 \
PATIENCE=20 \
OPTIMIZER=AdamW \
LR0=0.0005 \
./scripts/train_hand_yolo_sweep.sh
```

### 9.4 비교 결과

각 모델의 `best.pt`에 해당하는 validation 결과다. `best_epoch`와 `total_epochs`는
Ultralytics `results.csv`에 기록된 epoch 번호다.

| 모델 | Best epoch | 종료 epoch | 시간(초) | 크기(MB) | Precision | Recall | mAP50 | mAP50-95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| YOLO11n | 35 | 55 | 72.9 | 5.22 | **1.0000** | 0.9984 | **0.9950** | 0.7445 |
| YOLO11s | 49 | 69 | 138.7 | 18.29 | 0.9448 | **1.0000** | 0.9892 | **0.7799** |
| YOLO11m | 42 | 43 | 183.8 | 38.64 | 0.9079 | 0.9444 | 0.9656 | 0.6703 |

결과 CSV:

```text
outputs/train/sweep_stable_v1_summary.csv
```

손 미탐을 줄이는 것이 우선인 안전 감지 용도에는 recall 1.0과 가장 높은 mAP50-95를
기록한 **YOLO11s를 기본 후보**로 선택한다. 제어 주기 저하나 실시간 지연이 확인되면
크기가 작고 성능 차이가 제한적인 YOLO11n을 대안으로 사용한다. YOLO11m은 더 크고
느리면서 이번 validation 성능도 낮아 현재 환경에서는 채택하지 않는다.

### 9.5 파이프라인에서 모델 선택

YOLO11s를 사용한 감기 시나리오 설정 검사:

```bash
source ~/venv/il/bin/activate
cd ~/ExpertSurgicalMentor

SAFETY_YOLO_MODEL="$PWD/outputs/train/hand_yolo_s_sweep_stable_v1/weights/best.pt" \
./scripts/run_cold_scenario.sh 감기 --dry-run
```

실제 전체 파이프라인 실행:

```bash
SAFETY_YOLO_MODEL="$PWD/outputs/train/hand_yolo_s_sweep_stable_v1/weights/best.pt" \
./scripts/run_cold_scenario.sh 감기
```

모델 비교 시에는 위 경로에서 `s`만 `n` 또는 `m`으로 바꾼다. ACT 모델과 Object YOLO는
동일하게 유지되므로 손 감지 모델의 오탐, 미탐, 중단·재개 지연을 비교할 수 있다.
