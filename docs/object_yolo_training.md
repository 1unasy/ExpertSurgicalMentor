# Object YOLO 데이터셋 및 학습 결과

## 1. 목적

`pill`, `syringe`를 검출하여 ACT 수행 전 Main Tray에 목표 장비가 있는지 확인하고, 수행 후
Assist Tray로 이동했는지 검증한다.

## 2. 데이터 생성

LeRobot의 syringe 40개, pill 40개 에피소드에서 시간상 균등한 프레임을 추출한다.

```bash
python ./src/scripts/object_yolo/extract_object_yolo_frames.py \
  --repo-id 1unasy/pick_and_place_v2 \
  --samples-per-episode 4
```

Roboflow에서 두 클래스의 bbox 라벨링을 완료한 뒤 다운로드한 train/valid/test를 합치고,
인접 프레임 누수를 막기 위해 에피소드 단위로 다시 분리한다.

```bash
python ./src/scripts/object_yolo/prepare_object_yolo_dataset.py \
  --source datasets/objects \
  --output datasets/objects_grouped \
  --seed 42 --overwrite
```

## 3. 데이터 분포

| Split | 에피소드 | 이미지 | pill 이미지 | syringe 이미지 | pill bbox | syringe bbox |
|---|---:|---:|---:|---:|---:|---:|
| Train | 64 | 233 | 113 | 120 | 210 | 153 |
| Valid | 8 | 29 | 13 | 16 | 26 | 19 |
| Test | 8 | 32 | 16 | 16 | 28 | 29 |
| **합계** | **80** | **294** | **142** | **152** | **264** | **201** |

syringe/pill 에피소드를 각각 32/4/4개로 분리하여 물체별 8:1:1 비율을 유지한다.

## 4. 학습 방법

```bash
source ~/venv/il/bin/activate
cd ~/ExpertSurgicalMentor
./src/scripts/object_yolo/train_object_yolo.sh
```

| 설정 | 값 |
|---|---|
| Base model | `yolo11s.pt` |
| Classes | `pill`, `syringe` |
| Image size | 640 |
| Batch | 8 |
| Max epochs | 150 |
| Early stopping patience | 30 |
| Seed / deterministic | 0 / true |
| AMP | true |

## 5. 선정 모델과 성능

```text
models/object_yolo/best.pt
```

Validation mAP50-95가 가장 높은 epoch 105의 결과:

| 지표 | 값 |
|---|---:|
| Precision | 0.9866 |
| Recall | 0.9982 |
| mAP50 | 0.9950 |
| mAP50-95 | 0.8795 |

`best.pt`는 validation mAP50-95 기준으로 선정했다. 학습 스크립트는 이후 에피소드가 분리된
test split 평가도 수행하며 시각화는 다음에 저장한다.

```text
outputs/train/object_yolo_v1_test/
```

현재 test 결과의 별도 CSV 요약이 없으므로 발표에서는 validation 수치와 실제 로봇 성공률을
구분한다.

## 6. 트레이 위치 검증

```bash
python ./src/scripts/object_yolo/object_yolo_verifier.py syringe \
  --model models/object_yolo/best.pt \
  --roi-config config/object_tray_rois.json \
  --camera 4 --confidence 0.5 --frames 10 --required 5
```

YOLO bbox 중심점이 Main/Assist 다각형 내부에 있는지 검사한다. 같은 위치에서 연속 5프레임
확인되어야 `main` 또는 `assist`로 확정하고, 나머지는 `unknown`으로 처리한다.

## 7. 결과 해석 시 주의점

- 고정 카메라·트레이 조건의 데이터이므로 위치 변경 시 성능을 다시 확인한다.
- bbox 검출 성공은 파지 성공을 의미하지 않는다.
- 겹침, 반사, 가림, 새로운 배경 조건의 실제 로봇 평가가 필요하다.
- `unknown`에서는 자동 재시도하지 않는 보수적 정책을 사용한다.
