# 실행 코드 구조

전체 파이프라인에 필요한 코드만 기능별로 분리했다.

| 단계 | 디렉터리 | 핵심 역할 |
|---|---|---|
| 모방학습 | `src/scripts/imitation_learning/` | LeRobot 데이터 수집·업로드, ACT 학습, ACT 추론 |
| 손 안전 | `src/scripts/hand_yolo/` | 손 영상 수집, YOLO11s 학습 |
| 장비 검출 | `src/scripts/object_yolo/` | 프레임 추출·분할, YOLO11s 학습, 사전·사후 위치 검증 |
| 트레이 좌표 | `src/scripts/tray/` | Main/Assist 다각형 ROI 보정 |
| 전체 파이프라인 | `src/scripts/pipeline/` | 질환 매핑, 검증형 ACT 실행, Flask UI |

## 최종 실행

```bash
source ~/venv/il/bin/activate
cd ~/ExpertSurgicalMentor
python ./src/scripts/pipeline/run_cold_scenario_web.py
```

로봇을 움직이지 않는 CLI 검사:

```bash
./src/scripts/pipeline/run_cold_scenario.sh 감기 --patient 환자A --dry-run
```

사용하지 않는 과거 코드는 삭제하지 않고 `backup/legacy/`에 둔다.
