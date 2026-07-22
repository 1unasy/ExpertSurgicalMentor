# Hand Safety Dataset

> 목적: OMX-F가 도구를 이송하는 중 사람 손이 작업 반경에 진입하면 즉시 정지시키기 위한 YOLO 손 검출 모델 학습 데이터.

## 1. 요약

| 항목             | 값                                                                              |
| ---------------- | ------------------------------------------------------------------------------- |
| 현재 단계        | **Phase 1 완료** (라벨링·export까지)                                            |
| 수집 원본        | 152장 (`datasets/hand/raw/`, git ignored)                                       |
| 라벨링 결과      | 150장 (Roboflow 처리 중 2장 유사 이미지 자동 제거)                              |
| Train / Val      | 120 / 30 (8:2 stratified)                                                       |
| 클래스           | `hand` (단일)                                                                   |
| 검출 대상 카메라 | **front 카메라 단독** — 조기 검출에 유리, wrist는 사각지대·그리퍼 방해로 부적합 |
| 선정 모델        | YOLO11s (`hand_yolo_s_sweep_stable_v1/weights/best.pt`)                         |
| 학습 스크립트    | `src/scripts/hand_yolo/train_hand_yolo.sh`                                                    |
| 수집 도구        | `src/scripts/hand_yolo/collect_hand_images.py`                                                |

## 2. 데이터 분포 (실측)

| 코드     | 조건                                                 |    수집 |  라벨링 | 라벨        |
| -------- | ---------------------------------------------------- | ------: | ------: | ----------- |
| A1       | 손이 옆에서 프레임으로 진입                          |      19 |      19 | `hand` bbox |
| A2       | 손이 Assist Tray 근처 (도구 수령 자세)               |      17 |      17 | `hand` bbox |
| A3       | 손이 도구를 파지한 채 이동                           |      19 |      19 | `hand` bbox |
| A4       | 손이 Main Tray / Practice Zone 위                    |      16 |      16 | `hand` bbox |
| B1       | 손 근접 각도 (원래 wrist용, front로 수집)            |      17 |      17 | `hand` bbox |
| B2       | 손 근접 + 도구 (원래 wrist용, front로 수집)          |      16 |      16 | `hand` bbox |
| N1       | 손 없음, 빈 씬                                       |      15 |      15 | 없음 (Null) |
| N2       | 손 없음, 도구/트레이만                               |      13 |      13 | 없음 (Null) |
| **N3**   | **손 없음, OMX-F 팔·그리퍼 (그리퍼 오탐 방지 핵심)** |      20 |      18 | 없음 (Null) |
| **합계** |                                                      | **152** | **150** |             |

### 분포 설계 근거

- **A/B (positive) 104장**: recall 확보. 실제 손 등장 위치·자세를 커버
- **N1–N3 (negative) 46장**: 배경만 학습하면 “움직이는 살색 물체 = 손”으로 오탐. 특히 **N3(로봇 팔)** 이 없으면 자기 그리퍼를 손으로 오탐해 로봇이 스스로 멈춤
- **B1/B2 33장**: 원래 wrist 마운트 각도용으로 계획됐으나 Phase 1에서 front 카메라로 수집됨. 근접 각도의 추가 positive로 활용

## 3. 변형 요건 (같은 조건 내 다양화)

- **손 방향**: 정면 / 측면 / 손등
- **손 개수**: 한 손 / 두 손
- **속도**: 정지 / 저속
- **거리**: 가까움 / 보통 / 멀리
- **가림**: 도구·트레이·로봇 팔에 부분 가려진 손

## 4. 저장 구조

```
datasets/hand/
├── raw/                                    # 원본 (gitignored)
│   ├── A1_front_entering/                  # 조건별 폴더
│   ├── ...
│   └── N3_front_bg_robot/
└── yolo_v1/                                # Roboflow export (현재 datasets/ 전체 gitignored)
    └── hospital.yolov11/
        ├── train/
        │   ├── images/                     # 120 JPG
        │   └── labels/                     # 120 TXT (배경은 빈 파일)
        ├── valid/
        │   ├── images/                     # 30 JPG
        │   └── labels/                     # 30 TXT
        ├── data.yaml                       # Roboflow 원본 (class name 'hospital')
        └── README.*.txt
```

파일명 규칙: `{condition}_{YYYYMMDD_HHMMSS}_{seq:04d}.jpg`
(예: `A1_front_entering_20260721_115313_0001.jpg`)

**참고**: `train_hand_yolo.sh`는 학습 시 절대경로와 클래스명 `hand`를 담은 임시 `data.yaml`을 자동 생성하므로 Roboflow의 원본 `data.yaml`은 참고용으로만 남겨둔다.

## 5. 수집 도구 사용법

`src/scripts/hand_yolo/collect_hand_images.py` — 단일 카메라 인터랙티브 캡처.

### 사전 준비 (macOS)

- 시스템 설정 → 개인정보 보호 및 보안 → **카메라**에서 실행 앱(터미널 등) 허용
- OpenCV 필요: `pip install opencv-python`

### 카메라 인덱스 확인

```bash
python3 ./src/scripts/hand_yolo/collect_hand_images.py --list-cameras
```

- macOS는 AVFoundation, Linux는 V4L2 백엔드로 자동 선택
- 내장 FaceTime과 외장 USB를 구분하려면 인덱스 1~3 미리보기 창을 띄워 시각적으로 확인

### 실행

```bash
python3 ./src/scripts/hand_yolo/collect_hand_images.py --cam <INDEX> --out datasets/hand/raw
```

### 조작 키

| 키           | 동작                                              |
| ------------ | ------------------------------------------------- |
| `SPACE`      | 현재 조건에서 한 장 저장                          |
| `a`          | 자동 캡처 토글 (1초 간격, 목표 도달 시 자동 정지) |
| `n` / `p`    | 다음 / 이전 조건으로 이동                         |
| `1`–`9`, `0` | 조건 직접 선택                                    |
| `s`          | 현재 조건 완료 처리 (스킵)                        |
| `l`          | 진행 상황 콘솔 출력                               |
| `q` / `ESC`  | 종료 (다음 실행 시 이어서 수집)                   |

## 6. Roboflow 라벨링 워크플로

1. **프로젝트 생성**: `roboflow.com` → New Project → Object Detection → Annotation Group `hand`
2. **업로드**: `datasets/hand/raw/` 폴더 통째로 드래그 → 조건별 태그 자동 부여
3. **라벨링 (positive 104장)**: A1–A4, B1, B2 이미지에 손 bbox 그리기
   - 손목 이하까지 포함, 손가락 끝만 보여도 처리
   - 도구를 쥔 손은 도구 부분 제외
4. **Null 처리 (negative 46장)**: N1, N2, N3 이미지
   - 개별: 오른쪽 툴바 맨 아래 ⊘ 아이콘 또는 단축키 `~`
   - 일괄: Annotate 그리드에서 파일명 필터(`N1_`, `N2_`, `N3_`) → 전체 선택 → **⋯ → Mark as Null**
   - Null 처리 없이 넘기면 Unannotated로 분류되어 학습에서 제외됨
5. **Version 생성**: Train/Val split 80/20, Resize 640×640, 소량 augmentation (Horizontal flip, ±10° rotation, ±20% brightness)
6. **Export**: YOLOv11 포맷 → zip 다운로드 → `datasets/hand/yolo_v1/` 아래 압축 해제

## 7. 학습 (로봇 PC 권장)

### 데이터 확보

로봇 PC에서 브랜치 clone하면 `datasets/hand/yolo_v1/`가 자동으로 포함된다.

```bash
git clone https://github.com/1unasy/ExpertSurgicalMentor.git
cd ExpertSurgicalMentor
git checkout feature/hand-yolo
```

### 학습 실행 (로봇 PC에서(gpu pc))

```bash
pip install ultralytics
DEVICE=0 bash ./src/scripts/hand_yolo/train_hand_yolo.sh          # CUDA
```

환경 변수: `MODEL` (기본 `yolo11s.pt`), `EPOCHS` (100), `BATCH` (16), `IMGSZ` (640), `PATIENCE` (20), `RUN_NAME` (`hand_yolo_s_sweep_stable_v1`)

### 결과물

```
outputs/train/hand_yolo_s_sweep_stable_v1/
├── weights/best.pt          # 실사용 모델
├── results.png              # 학습 곡선
├── confusion_matrix.png
└── val_batch0_pred.jpg      # 예측 시각화
```

`outputs/`, `*.pt`는 `.gitignore`로 제외됨.

## 8. 품질 체크리스트 (수집·라벨링 후)

- [x] Phase 1: 조건별 목표 대비 수집량 확인 (`git log` 참조)
- [x] Roboflow에서 배경 이미지(N\*)를 모두 Mark as Null 처리
- [x] Train / Val stratified 분할 확인 (각 조건이 val에 최소 3장씩)
- [ ] 학습 후 val mAP50 ≥ 0.85 목표
- [ ] N3 이미지 추론 시 그리퍼가 false-positive로 뜨지 않는지 확인
- [ ] 실제 카메라 스트림에서 30 fps 유지되는지 (지연 예산)

## 10. Git 정책

- `datasets/hand/raw/` — **gitignored** (수집 스크립트로 재생성 가능)
- `datasets/hand/yolo_v*/` — 현재 루트 `/datasets/` 정책에 따라 **gitignored**
- `outputs/`, `runs/`, `*.pt` — **gitignored** (학습마다 새로 생성)
- 대용량 raw는 히스토리 커밋 47dd175에 한 번 들어갔음 (강제로 지우지 않음)
