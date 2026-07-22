# 전체 파이프라인 실행 명령

이 문서는 최종 데모에 필요한 다섯 단계만 정리한다. 과거 실험 명령은
`backup/legacy/docs/command_legacy.md`에 보관한다.

## 1. 모방학습: 데이터·학습·추론

물체별 시연 데이터 수집:

```bash
./src/scripts/imitation_learning/record_object_dataset.sh new pick_and_place_v2 syringe 40
./src/scripts/imitation_learning/record_object_dataset.sh more pick_and_place_v2 pill 40
```

ACT 학습:

```bash
STEPS=100000 SAVE_FREQ=10000 BATCH_SIZE=8 \
  ./src/scripts/imitation_learning/train_act_objects.sh syringe pill
```

50,000-step 단독 추론:

```bash
MODEL_PREFIX=act_v2_full100k \
  ./src/scripts/imitation_learning/run_act_object.sh syringe --checkpoint 050000
```

## 2. Hand YOLO: 학습·안전 추론

배포 모델은 ACT와 동시에 실행할 때의 지연과 GPU 사용량을 고려해 YOLO11n을 사용한다.

```bash
MODEL=yolo11n.pt RUN_NAME=hand_yolo_n_sweep_stable_v1 \
  DEVICE=0 BATCH=8 ./src/scripts/hand_yolo/train_hand_yolo.sh
```

최종 가중치:

```text
outputs/train/hand_yolo_n_sweep_stable_v1/weights/best.pt
```

손 추론은 `run_act_object.sh` 내부에서 실행된다. 손 검출 시 현재 관절 위치를 유지하고,
손이 10초 연속 사라지면 기존 action chunk를 폐기한 뒤 현재 영상에서 다시 계획한다.

## 3. Object YOLO: 데이터·학습·검증

Object YOLO는 YOLO11s 기반 `pill`, `syringe` 2-class 검출 모델이다.

```bash
python ./src/scripts/object_yolo/prepare_object_yolo_dataset.py
./src/scripts/object_yolo/train_object_yolo.sh
```

최종 가중치:

```text
outputs/train/object_yolo_v1/weights/best.pt
```

단독 위치 검증:

```bash
python ./src/scripts/object_yolo/object_yolo_verifier.py syringe \
  --model outputs/train/object_yolo_v1/weights/best.pt \
  --roi-config config/object_tray_rois.json \
  --frames 10 --required 5
```

## 4. Main/Assist Tray 좌표

카메라와 트레이를 고정한 뒤 각 트레이 외곽점을 순서대로 선택한다.

```bash
python ./src/scripts/tray/calibrate_tray_rois.py \
  --camera 4 --min-points 3 --max-points 8
```

- 왼쪽 클릭: 점 추가
- 오른쪽 클릭: 마지막 점 취소
- `R`: 전체 초기화
- `Enter`: 저장
- `Esc`: 취소

결과는 `config/object_tray_rois.json`에 정규화 좌표로 저장한다. 자세한 원리는
`docs/tray_roi_presentation.md`를 참고한다.

## 5. 전체 파이프라인

Flask 설치:

```bash
source ~/venv/il/bin/activate
cd ~/ExpertSurgicalMentor
python -m pip install -r requirements-ui.txt
```

설정 검사 CLI:

```bash
./src/scripts/pipeline/run_cold_scenario.sh 감기 \
  --patient 환자A --checkpoint 050000 --dry-run
```

웹 UI:

```bash
python ./src/scripts/pipeline/run_cold_scenario_web.py
```

브라우저 주소는 `http://127.0.0.1:5050`이다. 전체 실행 순서는 다음과 같다.

1. 가상 환자 식별자와 질환 입력
2. `감기 → syringe` 허용 목록 매핑
3. Object YOLO로 Main Tray에서 주사기 연속 5프레임 확인
4. 손 안전 YOLO11n을 활성화한 ACT 50,000-step 정책 실행
5. 초기 자세 복귀
6. Object YOLO로 Assist Tray에서 주사기 연속 5프레임 확인
7. 성공 시 자동 종료; Main Tray에 남으면 제한 횟수 재시도
8. 위치가 불명확하면 추가 동작 없이 안전 중단
