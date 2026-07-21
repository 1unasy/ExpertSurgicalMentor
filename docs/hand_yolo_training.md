# 손 안전 감지 YOLO 학습 결과

## 1. 목적

로봇 작업 영역에 사람 손이 들어오는 상황을 front/wrist 카메라에서 감지하기 위해
YOLO11n 단일 클래스 객체 감지 모델을 학습했다. 현재 모델은 손을 감지하고 화면에 박스를
표시할 수 있지만, 손 감지 결과를 로봇 정지 신호에 연결하는 기능은 아직 별도 구현이 필요하다.

## 2. 데이터셋

```text
datasets/hand/yolo_v1/hospital.yolov11
```

| 분할 | 이미지 | 손 박스 |
|---|---:|---:|
| train | 120 | 데이터셋 라벨 참조 |
| valid | 30 | 18 |

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

다른 LeRobot/OpenCV 프로그램이 카메라를 점유하지 않은 상태에서 실행한다.

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

Wrist 카메라(`/dev/video2`):

```bash
yolo detect predict \
  model=outputs/train/hand_yolo_v1/weights/best.pt \
  source=2 \
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
