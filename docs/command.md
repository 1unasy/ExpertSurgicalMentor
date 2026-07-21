# ExpertSurgicalMentor 데이터 수집·ACT 학습·추론 명령어

## 1. 목표 아키텍처

한 트레이에 `syringe`, `glasses`, `pill`, `x-ray image`가 동시에 있을 때 명령으로 지정된 물체를 다른 트레이로 옮긴다.

일반 ACT는 `single_task` 문자열을 행동 입력으로 사용하지 않으므로, 명령 라우터가 물체별 ACT 정책을 선택하는 구조를 사용한다.

```text
명령: "syringe와 pill을 옮겨"
              ↓
명령 라우터/VLM
              ↓
act_syringe 실행
              ↓
act_pill 실행
```

## 2. 데이터 수집 목표

현재 물체별 10개에서 각각 20개를 추가해 30개씩 확보한다.

| 물체 | 현재 | 추가 | 최종 |
|---|---:|---:|---:|
| syringe | 10 | 20 | 30 |
| glasses | 10 | 20 | 30 |
| pill | 10 | 20 | 30 |
| x-ray image | 10 | 20 | 30 |
| 합계 | 40 | 80 | 120 |

명령으로 여러 물체를 순서대로 전달하면 Main Tray에 남은 물체 수가 줄어든다. 물체별 추가 20개는 다음 조건을 권장한다.

- 8개: 네 물체 모두 Main Tray에 있음
- 6개: 목표 물체를 포함해 3개가 Main Tray에 있음
- 4개: 목표 물체를 포함해 2개가 Main Tray에 있음
- 2개: 목표 물체만 Main Tray에 있음

각 조건에서 목표 물체의 시작 위치와 회전 각도, 주변 물체 위치, Assist Tray의 상태를 바꾼다. 실패한 시연은 저장하지 않거나 삭제한다.

## 3. 환경 변수 및 현재 데이터 확인

```bash
source ~/venv/il/bin/activate

export HF_USER=1unasy
export DATASET_ID="${HF_USER}/pick_and_place"
export DATASET_DIR="$HOME/.cache/huggingface/lerobot/${DATASET_ID}"
```

```bash
python3 -c "import json; i=json.load(open('${DATASET_DIR}/meta/info.json')); print('episodes:', i['total_episodes'], 'tasks:', i['total_tasks'])"
```

현재 데이터가 정상이라면 다음과 같이 출력된다.

```text
episodes: 40 tasks: 4
```

## 4. 이어 녹화 함수

터미널에 다음 함수를 한 번 등록한다.

```bash
record_more() {
  local TASK="$1"
  local COUNT="$2"

  cd ~/ExpertSurgicalMentor/src/lerobot && lerobot-record \
    --robot.type=omx_follower \
    --robot.port=/dev/omx_follower \
    --robot.id=omx_follower_arm \
    --robot.cameras='{
      front: {type: opencv, index_or_path: 4, width: 640, height: 480, fps: 30, fourcc: MJPG},
      wrist: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30, fourcc: MJPG}
    }' \
    --teleop.type=omx_leader \
    --teleop.port=/dev/omx_leader \
    --teleop.id=omx_leader_arm \
    --display_data=true \
    --dataset.repo_id="${DATASET_ID}" \
    --dataset.single_task="${TASK}" \
    --dataset.episode_time_s=20 \
    --dataset.num_episodes="${COUNT}" \
    --dataset.reset_time_s=10 \
    --dataset.push_to_hub=false \
    --resume=true
}
```

## 5. 물체별 20개 추가 수집

아래 순서대로 수집하면 추가 에피소드 번호를 명확히 관리할 수 있다.

```bash
record_more "Pick up syringe" 20
record_more "Pick up glasses" 20
record_more "Pick up a pill" 20
record_more "Pick up xray-image" 20
```

기존 task 문자열과 철자, 대소문자, 공백을 동일하게 유지한다.

| 물체 | 기존 에피소드 | 추가 에피소드 |
|---|---|---|
| syringe | 0–9 | 40–59 |
| glasses | 10–19 | 60–79 |
| pill | 20–29 | 80–99 |
| x-ray image | 30–39 | 100–119 |

## 6. 수집 결과 확인

전체 개수 확인:

```bash
python3 -c "import json; i=json.load(open('${DATASET_DIR}/meta/info.json')); print('episodes:', i['total_episodes'], 'tasks:', i['total_tasks'], 'frames:', i['total_frames'])"
```

목표 결과:

```text
episodes: 120 tasks: 4
```

물체별 개수 확인:

```bash
python3 - <<'PY'
import collections
import pathlib
import pyarrow as pa
import pyarrow.parquet as pq

root = pathlib.Path.home() / ".cache/huggingface/lerobot/1unasy/pick_and_place/meta/episodes"
tables = [
    pq.read_table(path, columns=["episode_index", "tasks"])
    for path in sorted(root.rglob("*.parquet"))
]
rows = pa.concat_tables(tables).to_pylist()
counts = collections.Counter(row["tasks"][0] for row in rows)

for task, count in sorted(counts.items()):
    print(f"{task}: {count}")
PY
```

목표 결과:

```text
Pick up a pill: 30
Pick up glasses: 30
Pick up syringe: 30
Pick up xray-image: 30
```

## 7. 기존 Hugging Face 저장소 갱신

```bash
huggingface-cli upload \
  "${DATASET_ID}" \
  "${DATASET_DIR}" \
  . \
  --repo-type dataset
```

업로드 결과는 다음에서 확인한다.

```text
https://huggingface.co/datasets/1unasy/pick_and_place
```

## 8. 물체별 학습 데이터셋 생성

원본 데이터셋은 보존하고 물체별 분할본을 생성한다.

```bash
cd ~/ExpertSurgicalMentor/src/lerobot && lerobot-edit-dataset \
  --repo_id="${HF_USER}/pick_and_place" \
  --operation.type=split \
  --operation.splits='{
    "syringe": [0,1,2,3,4,5,6,7,8,9,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59],
    "glasses": [10,11,12,13,14,15,16,17,18,19,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79],
    "pill": [20,21,22,23,24,25,26,27,28,29,80,81,82,83,84,85,86,87,88,89,90,91,92,93,94,95,96,97,98,99],
    "xray_image": [30,31,32,33,34,35,36,37,38,39,100,101,102,103,104,105,106,107,108,109,110,111,112,113,114,115,116,117,118,119]
  }' \
  --push_to_hub=false
```

생성 결과:

```text
1unasy/pick_and_place_syringe
1unasy/pick_and_place_glasses
1unasy/pick_and_place_pill
1unasy/pick_and_place_xray_image
```

확인:

```bash
find ~/.cache/huggingface/lerobot/1unasy \
  -maxdepth 1 -type d -name 'pick_and_place_*' -print
```

## 9. ACT 모델 학습

공통 설정:

- 물체별 30 episodes
- 50,000 steps
- 10,000 steps마다 체크포인트 저장
- RTX 4060 기준 batch size 4

### Syringe

```bash
cd ~/ExpertSurgicalMentor/src/lerobot && lerobot-train \
  --dataset.repo_id="${HF_USER}/pick_and_place_syringe" \
  --policy.type=act \
  --policy.device=cuda \
  --policy.use_amp=true \
  --policy.push_to_hub=false \
  --output_dir="outputs/train/act_syringe" \
  --job_name="act_syringe" \
  --batch_size=4 \
  --steps=50000 \
  --save_checkpoint=true \
  --save_freq=10000 \
  --eval_freq=0 \
  --wandb.enable=false
```

### Glasses

```bash
cd ~/ExpertSurgicalMentor/src/lerobot && lerobot-train \
  --dataset.repo_id="${HF_USER}/pick_and_place_glasses" \
  --policy.type=act \
  --policy.device=cuda \
  --policy.use_amp=true \
  --policy.push_to_hub=false \
  --output_dir="outputs/train/act_glasses" \
  --job_name="act_glasses" \
  --batch_size=4 \
  --steps=50000 \
  --save_checkpoint=true \
  --save_freq=10000 \
  --eval_freq=0 \
  --wandb.enable=false
```

### Pill

```bash
cd ~/ExpertSurgicalMentor/src/lerobot && lerobot-train \
  --dataset.repo_id="${HF_USER}/pick_and_place_pill" \
  --policy.type=act \
  --policy.device=cuda \
  --policy.use_amp=true \
  --policy.push_to_hub=false \
  --output_dir="outputs/train/act_pill" \
  --job_name="act_pill" \
  --batch_size=4 \
  --steps=50000 \
  --save_checkpoint=true \
  --save_freq=10000 \
  --eval_freq=0 \
  --wandb.enable=false
```

### X-ray image

```bash
cd ~/ExpertSurgicalMentor/src/lerobot && lerobot-train \
  --dataset.repo_id="${HF_USER}/pick_and_place_xray_image" \
  --policy.type=act \
  --policy.device=cuda \
  --policy.use_amp=true \
  --policy.push_to_hub=false \
  --output_dir="outputs/train/act_xray_image" \
  --job_name="act_xray_image" \
  --batch_size=4 \
  --steps=50000 \
  --save_checkpoint=true \
  --save_freq=10000 \
  --eval_freq=0 \
  --wandb.enable=false
```

CUDA 메모리 부족 시 `--batch_size=2`로 낮춘다.

## 10. 학습 결과 확인

```bash
find outputs/train \
  -path '*/checkpoints/last/pretrained_model' \
  -type d -print
```

예상 경로:

```text
outputs/train/act_syringe/checkpoints/last/pretrained_model
outputs/train/act_glasses/checkpoints/last/pretrained_model
outputs/train/act_pill/checkpoints/last/pretrained_model
outputs/train/act_xray_image/checkpoints/last/pretrained_model
```

## 11. 물체별 추론 함수

```bash
run_object() {
  local OBJECT="$1"
  local MODEL_PATH
  local TASK

  case "${OBJECT}" in
    syringe)
      MODEL_PATH="outputs/train/act_syringe/checkpoints/last/pretrained_model"
      TASK="Pick up syringe"
      ;;
    glasses)
      MODEL_PATH="outputs/train/act_glasses/checkpoints/last/pretrained_model"
      TASK="Pick up glasses"
      ;;
    pill)
      MODEL_PATH="outputs/train/act_pill/checkpoints/last/pretrained_model"
      TASK="Pick up a pill"
      ;;
    xray|xray_image)
      MODEL_PATH="outputs/train/act_xray_image/checkpoints/last/pretrained_model"
      TASK="Pick up xray-image"
      ;;
    *)
      echo "지원 물체: syringe, glasses, pill, xray"
      return 1
      ;;
  esac

  local RUN_ID
  RUN_ID=$(date +%Y%m%d_%H%M%S)

  cd ~/ExpertSurgicalMentor/src/lerobot && lerobot-record \
    --robot.type=omx_follower \
    --robot.port=/dev/omx_follower \
    --robot.id=omx_follower_arm \
    --robot.cameras='{
      front: {type: opencv, index_or_path: 4, width: 640, height: 480, fps: 30, fourcc: MJPG},
      wrist: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30, fourcc: MJPG}
    }' \
    --display_data=true \
    --dataset.repo_id="${HF_USER}/eval_${OBJECT}_${RUN_ID}" \
    --dataset.single_task="${TASK}" \
    --dataset.episode_time_s=20 \
    --dataset.num_episodes=1 \
    --dataset.reset_time_s=1 \
    --dataset.push_to_hub=false \
    --policy.path="${MODEL_PATH}"
}
```

단일 물체 실행:

```bash
run_object syringe
run_object glasses
run_object pill
run_object xray
```

여러 물체를 순차 실행:

```bash
run_object syringe
run_object pill
```

또는:

```bash
run_object glasses
run_object xray
run_object syringe
```

최종 시스템에서는 VLM이 다음처럼 물체 순서를 반환하고 라우터가 배열 순서대로 ACT 정책을 호출한다.

```json
{
  "tools": ["syringe", "pill"]
}
```

## 12. 실제 평가 기준

각 정책을 다음 조건에서 평가한다.

- 네 물체가 모두 Main Tray에 있는 상태
- 다른 물체 하나가 이미 Assist Tray에 있는 상태
- 두 개가 이미 옮겨진 상태
- 목표 물체 위치와 회전 각도를 바꾼 상태
- 목표 물체와 비목표 물체가 가까운 상태

정책별 최소 10회 평가한다.

| 정책 | 목표 선택 | 파지 | 이동 | 배치 | 전체 성공 |
|---|---:|---:|---:|---:|---:|
| syringe |  |  |  |  |  |
| glasses |  |  |  |  |  |
| pill |  |  |  |  |  |
| x-ray image |  |  |  |  |  |

명령 해석은 VLM/라우터가 담당하고, 각 ACT 정책은 지정된 물체의 시각적 특징과 파지·이동·배치 동작을 담당한다.
