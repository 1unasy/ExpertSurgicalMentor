# Hand Safety Dataset 수집 계획 (200장, 2단계)

> 목적: OMX-F가 물체를 이송하는 중 사람 손이 작업 반경에 진입하면 즉시 정지시키기 위한 YOLO 손 검출 모델 학습 데이터를 확보한다.

## 0. 수집 단계

카메라 사용 상황에 따라 2단계로 나누어 수집한다.

| 단계 | 장소 | 카메라 | 조건 | 장수 |
|---|---|---|---|---:|
| **Phase 1** | MacBook | 외장 USB 1대 (front mount 대체) | A1–A4, N1–N3 | **130** |
| **Phase 2** | 로봇 PC | wrist 카메라 (index 2) | B1, B2, N4 | 70 |

Phase 1만으로도 front 카메라 기반 안전 검출은 가능하다. Phase 2는 wrist 카메라를 실제로 마운트한 뒤 로봇 PC에서 추가 수집한다.

## 1. 총량 및 분포

총 200장을 다음 조건으로 분산 수집한다. 조건 편중을 막기 위해 반드시 분포를 지킨다.

| 코드 | 카메라 | 조건 | 목표 장수 | 라벨 |
|---|---|---|---:|---|
| A1 | front | 손이 옆에서 프레임으로 진입 | 20 | `hand` |
| A2 | front | 손이 Assist Tray 근처 (도구 수령 자세) | 20 | `hand` |
| A3 | front | 손이 도구를 파지한 채 이동 | 20 | `hand` |
| A4 | front | 손이 Main Tray/Practice Zone 위 | 20 | `hand` |
| B1 | wrist | 손이 wrist 카메라에 가까이 진입 | 25 | `hand` |
| B2 | wrist | 손이 파지 대상 근처, 로봇 팔과 공존 | 25 | `hand` |
| N1 | front | 손 없음, 빈 씬 | 15 | (배경) |
| N2 | front | 손 없음, 도구/트레이만 존재 | 15 | (배경) |
| N3 | front | 손 없음, **OMX-F 팔이 다양한 자세로 보임** | 20 | (배경, false-positive 억제용) |
| N4 | wrist | 손 없음, **로봇 팔·그리퍼만 근접** | 20 | (배경, wrist 특유의 false-positive 억제용) |
| **합계** |  |  | **200** |  |

### 왜 이 분포인가

- **A/B (positive) 130장**: 검출 recall을 위한 실제 손 샘플. 실제 사용 시 손이 등장하는 위치·자세를 커버.
- **N1–N4 (negative) 70장**: 배경만으로 학습하면 “움직이는 물체 = 손”으로 오탐. 특히 그리퍼가 손처럼 오검출되기 쉬우므로 **N3·N4를 넉넉히** 넣는다.

## 2. 변형 요건 (같은 조건 안에서도 다양화)

각 조건 안에서 다음을 골고루 섞는다.

- **손 방향**: 정면, 측면, 손등, 손바닥
- **손 개수**: 한 손, 두 손
- **손 상태**: 맨손, 장갑 착용 (실제 사용 조건과 일치)
- **속도**: 정지, 천천히 움직임, 빠르게 움직임 (motion blur 포함)
- **조명**: 기본 조명 + 조명 위치 1회 변경
- **거리**: 카메라에서 가까움/보통/멀리
- **가림**: 도구·트레이·로봇 팔에 부분적으로 가려진 손

## 3. 저장 구조

```
datasets/hand/
├── raw/                     # 수집 직후 원본
│   ├── A1_front_entering/
│   ├── A2_front_near_tray/
│   ├── ...
│   ├── N3_front_bg_robot/
│   └── N4_wrist_bg_robot/
├── images/                  # 라벨링 후 정리
│   ├── train/               # 160장 (80%)
│   └── val/                 # 40장  (20%)
├── labels/                  # YOLO txt 라벨 (배경은 빈 파일 또는 없음)
│   ├── train/
│   └── val/
└── data.yaml                # ultralytics 학습 설정
```

파일명 규칙: `{condition}_{YYYYMMDD_HHMMSS}_{seq:04d}.jpg` (예: `A1_front_entering_20260721_142310_0007.jpg`).

## 4. 라벨링

- 도구: **LabelImg** (오프라인, 간단) 또는 **Roboflow** (분할·증강까지)
- 클래스: 단일 `hand` (bbox)
- 배경 이미지(N*)는 라벨 파일을 만들지 않거나 빈 파일로 둔다 (ultralytics는 둘 다 negative로 취급)
- **손목 이하까지 포함**하여 bbox 지정. 손가락 끝만 보여도 bbox 처리
- 도구를 쥔 손은 도구 부분을 제외하고 손만 포함

## 5. 학습·검증 분할

무작위 8:2 분할 대신 **조건별 stratified split** 사용:

| 조건 | train | val |
|---|---:|---:|
| A1 | 16 | 4 |
| A2 | 16 | 4 |
| A3 | 16 | 4 |
| A4 | 16 | 4 |
| B1 | 20 | 5 |
| B2 | 20 | 5 |
| N1 | 12 | 3 |
| N2 | 12 | 3 |
| N3 | 16 | 4 |
| N4 | 16 | 4 |
| 합계 | 160 | 40 |

각 조건의 val 이미지는 수집 시간 순서상 마지막 20%로 고정 (같은 세션 다양성 유지).

## 6. 수집 방법

`scripts/collect_hand_images.py` 사용. 조건을 선택하면 목표 장수만큼 자동 캡처하거나 SPACE로 한 장씩 저장할 수 있다.

### Phase 1 (Mac, 외장 USB 1대)

```bash
python3 scripts/collect_hand_images.py --cam 3 --out datasets/hand/raw
```

- 조건 B1, B2, N4는 `s` 키로 건너뛴다 (Phase 2에서 로봇 PC로 수집).
- `--cam` 값은 `--list-cameras`로 확인한 외장 카메라 인덱스로 지정.

### Phase 2 (로봇 PC, wrist 카메라)

```bash
python3 scripts/collect_hand_images.py --cam 2 --backend v4l2 --out datasets/hand/raw
```

- A1–A4, N1–N3은 이미 완료되어 있으므로 자동으로 스킵됨.
- B1, B2, N4만 채우면 총 200장 완성.

세부 사용법은 스크립트 `--help` 참고.

## 7. 품질 체크리스트 (수집 후)

- [ ] 조건별 목표 장수를 채웠는가
- [ ] 정지 프레임만 있지 않은가 (motion blur, 다양한 손 위치 포함)
- [ ] N3·N4에 그리퍼 close-up 프레임이 충분한가
- [ ] 흐릿·빛번짐·완전 검은 프레임은 제거했는가
- [ ] 손이 아닌 팔뚝만 보이는 프레임은 제거했는가 (또는 별도 정책 결정)
- [ ] wrist 카메라 이미지에서 자기 팔이 항상 크게 잡히는 특성 반영됐는가

## 8. 다음 단계

1. 200장 수집 완료
2. LabelImg로 A/B 130장 bbox 라벨링
3. `data.yaml` 작성 + train/val 분할 스크립트 실행
4. `scripts/train_hand_yolo.sh`로 YOLOv8n 파인튜닝
5. `src/safety/hand_detector.py`에서 로드 → `SafetyGatedPolicy`에 연결
