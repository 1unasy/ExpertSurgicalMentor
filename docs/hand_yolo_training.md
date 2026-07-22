# Hand YOLO 데이터셋 및 학습 결과

## 1. 목적

Front 카메라에서 사람 손을 검출하여 ACT 동작 중 로봇을 일시정지한다. 손이 10초 연속
사라지면 정지 전 action chunk를 폐기하고 현재 영상에서 다시 계획한다.

## 2. 데이터셋

| 항목 | 값 |
|---|---|
| 경로 | `datasets/hand/yolo_v1/hospital.yolov11` |
| 원본 / 라벨 결과 | 152 / 150장 |
| Train / Valid | 120 / 30장 |
| 클래스 | `hand` |
| Positive / Negative | 104 / 46장 |
| 카메라 | front |

Negative에는 빈 장면뿐 아니라 트레이, 장비, 로봇팔, 그리퍼를 포함한다. 특히 N3 로봇팔
negative는 그리퍼를 손으로 잘못 인식해 로봇이 스스로 정지하는 문제를 줄이기 위한 데이터다.

자세한 수집 조건은 [hand_safety_dataset.md](hand_safety_dataset.md)를 참고한다.

## 3. 학습 명령과 조건

```bash
source ~/venv/il/bin/activate
cd ~/ExpertSurgicalMentor
DEVICE=0 BATCH=8 ./src/scripts/hand_yolo/train_hand_yolo.sh
```

| 설정 | 값 |
|---|---|
| Base model | `yolo11s.pt` |
| Image size | 640 |
| Batch | 8 |
| Max epochs | 100 |
| Early stopping patience | 20 |
| Optimizer | AdamW |
| AMP | true |
| Seed / deterministic | 0 / true |

## 4. YOLO11 n/s/m 비교

각 `results.csv`에서 validation mAP50-95가 가장 높은 epoch를 비교했다.

| 모델 | Best epoch | Precision | Recall | mAP50 | mAP50-95 |
|---|---:|---:|---:|---:|---:|
| YOLO11n | 35 | 1.0000 | 0.9984 | 0.9950 | 0.7445 |
| **YOLO11s** | **49** | **0.9448** | **1.0000** | **0.9892** | **0.7799** |
| YOLO11m | 23 | 0.8305 | 0.8889 | 0.9350 | 0.6733 |

YOLO11s를 선정한 이유:

- 안전 감지에서 중요한 validation recall 1.0
- 세 모델 중 가장 높은 mAP50-95
- YOLO11m보다 계산량이 작으면서 더 높은 성능

## 5. 선정 모델

```text
outputs/train/hand_yolo_s_sweep_stable_v1/weights/best.pt
```

관련 결과:

```text
outputs/train/hand_yolo_s_sweep_stable_v1/results.csv
outputs/train/hand_yolo_s_sweep_stable_v1/results.png
outputs/train/hand_yolo_s_sweep_stable_v1/confusion_matrix.png
outputs/train/hand_yolo_s_sweep_stable_v1/val_batch0_pred.jpg
```

## 6. 단독 실시간 추론

```bash
yolo detect predict \
  model=outputs/train/hand_yolo_s_sweep_stable_v1/weights/best.pt \
  source=4 imgsz=640 conf=0.15 device=0 show=true save=false
```

## 7. 해석 시 주의점

Validation은 30장으로 작다. 위 수치는 실제 안전 인증 성능이 아니며 다음 조건을 별도로
검증해야 한다.

- 장갑과 피부색 변화
- 조명과 그림자
- 빠르게 진입하는 손
- 장비·로봇팔에 가려진 손
- 손이 없는 상태에서 로봇팔·그리퍼 오탐
