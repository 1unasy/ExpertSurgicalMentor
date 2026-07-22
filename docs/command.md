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

`pick_and_place_v2`에 물체별 40개씩 확보한다.

| 물체 | 현재 | 추가 | 최종 |
|---|---:|---:|---:|
| syringe | 40 | 0 | 40 |
| pill | 40 | 0 | 40 |
| glasses | 0 | 40 | 40 |
| x-ray image | 0 | 40 | 40 |
| 합계 | 80 | 80 | 160 |

명령으로 여러 물체를 순서대로 전달하면 Main Tray에 남은 물체 수가 줄어든다. 물체별 40개는 여러 잔여 상태를 포함하도록 수집한다.

- 8개: 네 물체 모두 Main Tray에 있음
- 6개: 목표 물체를 포함해 3개가 Main Tray에 있음
- 4개: 목표 물체를 포함해 2개가 Main Tray에 있음
- 2개: 목표 물체만 Main Tray에 있음

각 조건에서 목표 물체의 시작 위치와 회전 각도, 주변 물체 위치, Assist Tray의 상태를 바꾼다. 실패한 시연은 저장하지 않거나 삭제한다.

## 3. 환경 변수 및 현재 데이터 확인

```bash
source ~/venv/il/bin/activate

export HF_USER=1unasy
export DATASET_ID="${HF_USER}/pick_and_place_v2"
export DATASET_DIR="$HOME/.cache/huggingface/lerobot/${DATASET_ID}"
```

```bash
python3 -c "import json; i=json.load(open('${DATASET_DIR}/meta/info.json')); print('episodes:', i['total_episodes'], 'tasks:', i['total_tasks'])"
```

현재 데이터가 정상이라면 다음과 같이 출력된다.

```text
episodes: 80 tasks: 2
```

### `pick_and_place_v2` 새 세트 수집

모든 명령과 로컬 경로, Hub 저장소는 `1unasy/pick_and_place_v2`를 사용한다.

이미 완료한 최초 syringe 수집 명령:

```bash
cd ~/ExpertSurgicalMentor

./scripts/record_object_dataset.sh new pick_and_place_v2 syringe 40
```

이미 완료한 pill 수집 명령:

```bash
./scripts/record_object_dataset.sh more pick_and_place_v2 pill 40
```

향후 같은 데이터셋에 이어서 수집할 명령:

```bash
./scripts/record_object_dataset.sh more pick_and_place_v2 glasses 40
./scripts/record_object_dataset.sh more pick_and_place_v2 xray 40
```

추가 에피소드를 더 수집할 때도 `more`를 사용한다.

```bash
./scripts/record_object_dataset.sh more pick_and_place_v2 syringe 10
```

기본 포트는 follower `/dev/ttyACM0`, leader `/dev/ttyACM1`이다. 포트가 달라지면:

```bash
FOLLOWER_PORT=/dev/omx_follower \
LEADER_PORT=/dev/omx_leader \
./scripts/record_object_dataset.sh new pick_and_place_v2 syringe 40
```

새 로컬 폴더:

```text
/home/user/.cache/huggingface/lerobot/1unasy/pick_and_place_v2
```

수집 결과 확인:

```bash
python3 -c "import json; p='$HOME/.cache/huggingface/lerobot/1unasy/pick_and_place_v2/meta/info.json'; i=json.load(open(p)); print('episodes:', i['total_episodes'], 'tasks:', i['total_tasks'], 'frames:', i['total_frames'])"
```

Hugging Face에 새 데이터셋으로 업로드:

```bash
source ~/venv/il/bin/activate

hf upload-large-folder \
  "1unasy/pick_and_place_v2" \
  "$HOME/.cache/huggingface/lerobot/1unasy/pick_and_place_v2" \
  --repo-type dataset
```

업로드 결과:

```text
https://huggingface.co/datasets/1unasy/pick_and_place_v2
```

이 실행 파일은 현재 권장 CLI인 `hf upload-large-folder`를 사용하므로 대용량 업로드가
중단되어도 다시 같은 명령을 실행해 이어서 처리할 수 있다.

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
    --dataset.episode_time_s=13 \
    --dataset.num_episodes="${COUNT}" \
    --dataset.reset_time_s=8 \
    --dataset.push_to_hub=false \
    --resume=true
}
```

## 5. 현재 수집 상태와 남은 수집

아래 순서대로 수집하면 추가 에피소드 번호를 명확히 관리할 수 있다.

```bash
record_more "Pick up glasses" 40
record_more "Pick up xray-image" 40
```

기존 task 문자열과 철자, 대소문자, 공백을 동일하게 유지한다.

| 물체 | 상태 | 에피소드 |
|---|---|---|
| syringe | 완료 | 0–39 |
| pill | 완료 | 40–79 |
| glasses | 수집 예정 | 80–119 |
| x-ray image | 수집 예정 | 120–159 |

## 6. 수집 결과 확인

전체 개수 확인:

```bash
python3 -c "import json; i=json.load(open('${DATASET_DIR}/meta/info.json')); print('episodes:', i['total_episodes'], 'tasks:', i['total_tasks'], 'frames:', i['total_frames'])"
```

현재 결과:

```text
episodes: 80 tasks: 2
```

물체별 개수 확인:

```bash
python3 - <<'PY'
import collections
import pathlib
import pyarrow as pa
import pyarrow.parquet as pq

root = pathlib.Path.home() / ".cache/huggingface/lerobot/1unasy/pick_and_place_v2/meta/episodes"
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

현재 결과:

```text
Pick up a pill: 40
Pick up syringe: 40
```

glasses와 x-ray image까지 수집한 최종 목표는 `episodes: 160 tasks: 4`이다.

## 7. 기존 Hugging Face 저장소 갱신

```bash
hf upload-large-folder \
  "${DATASET_ID}" \
  "${DATASET_DIR}" \
  --repo-type dataset
```

업로드 결과는 다음에서 확인한다.

```text
https://huggingface.co/datasets/1unasy/pick_and_place_v2
```

## 8. 물체별 학습 데이터셋 생성

현재 수집이 완료된 syringe와 pill의 분할본을 생성한다. glasses와 x-ray image는 각각
40개 수집을 완료한 뒤 split 항목에 추가한다.

```bash
cd ~/ExpertSurgicalMentor/src/lerobot && lerobot-edit-dataset \
  --repo_id="${HF_USER}/pick_and_place_v2" \
  --operation.type=split \
  --operation.splits='{
    "syringe": [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39],
    "pill": [40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59,60,61,62,63,64,65,66,67,68,69,70,71,72,73,74,75,76,77,78,79]
  }' \
  --push_to_hub=false
```

생성 결과:

```text
1unasy/pick_and_place_v2_syringe
1unasy/pick_and_place_v2_pill
```

### Syringe와 pill 전체 40개·100,000 step 순차 학습

데이터가 적으므로 별도 train/valid 분할 없이 각 물체의 40개 에피소드 전체를 학습에
사용한다. 과적합 여부는 10,000 step마다 저장된 checkpoint를 실제 로봇의 새로운 배치에서
비교한다.

```bash
cd ~/ExpertSurgicalMentor
./scripts/train_act_objects.sh syringe pill
```

기본 설정:

```text
dataset:    1unasy/pick_and_place_v2_<object> (각 40 episodes 전체)
steps:      100000
batch_size: 8
save_freq:  10000
output:     outputs/train/act_v2_full100k_<object>
```

syringe가 완료되면 pill 학습을 순차적으로 시작한다. 최종 모델 선택은 `10k`, `20k`,
`30k` 등의 checkpoint를 새로운 위치·회전 배치에서 반복 평가하여 결정한다.

확인:

```bash
find ~/.cache/huggingface/lerobot/1unasy \
  -maxdepth 1 -type d -name 'pick_and_place_v2_*' -print
```

## 9. ACT 모델 학습

공통 설정:

- 현재 syringe와 pill 각각 40 episodes
- 20,000 steps
- 5,000 steps마다 체크포인트 저장
- RTX 4060 기준 batch size 8

현재 수집 완료된 syringe와 pill만 순차 학습하는 권장 실행 파일:

```bash
cd ~/ExpertSurgicalMentor

./scripts/train_act_objects.sh syringe pill
```

기본값은 RTX 4060에서 확인한 `batch_size=8`, 물체별 `20,000 steps`, `5,000
steps`마다 체크포인트 저장이다. 환경 변수로 변경할 수 있다.

```bash
BATCH_SIZE=8 \
STEPS=20000 \
SAVE_FREQ=5000 \
./scripts/train_act_objects.sh syringe pill
```

학습 순서와 출력 경로:

```text
pick_and_place_v2_syringe → outputs/train/act_v2_syringe
pick_and_place_v2_pill    → outputs/train/act_v2_pill
```

### Syringe

```bash
cd ~/ExpertSurgicalMentor/src/lerobot && lerobot-train \
  --dataset.repo_id="${HF_USER}/pick_and_place_v2_syringe" \
  --policy.type=act \
  --policy.device=cuda \
  --policy.use_amp=true \
  --policy.push_to_hub=false \
  --output_dir="outputs/train/act_syringe" \
  --job_name="act_syringe" \
  --batch_size=8 \
  --steps=20000 \
  --save_checkpoint=true \
  --save_freq=5000 \
  --eval_freq=0 \
  --wandb.enable=false
```

### Glasses

```bash
cd ~/ExpertSurgicalMentor/src/lerobot && lerobot-train \
  --dataset.repo_id="${HF_USER}/pick_and_place_v2_glasses" \
  --policy.type=act \
  --policy.device=cuda \
  --policy.use_amp=true \
  --policy.push_to_hub=false \
  --output_dir="outputs/train/act_glasses" \
  --job_name="act_glasses" \
  --batch_size=8 \
  --steps=20000 \
  --save_checkpoint=true \
  --save_freq=5000 \
  --eval_freq=0 \
  --wandb.enable=false
```

### Pill

```bash
cd ~/ExpertSurgicalMentor/src/lerobot && lerobot-train \
  --dataset.repo_id="${HF_USER}/pick_and_place_v2_pill" \
  --policy.type=act \
  --policy.device=cuda \
  --policy.use_amp=true \
  --policy.push_to_hub=false \
  --output_dir="outputs/train/act_pill" \
  --job_name="act_pill" \
  --batch_size=8 \
  --steps=20000 \
  --save_checkpoint=true \
  --save_freq=5000 \
  --eval_freq=0 \
  --wandb.enable=false
```

### X-ray image

```bash
cd ~/ExpertSurgicalMentor/src/lerobot && lerobot-train \
  --dataset.repo_id="${HF_USER}/pick_and_place_v2_xray_image" \
  --policy.type=act \
  --policy.device=cuda \
  --policy.use_amp=true \
  --policy.push_to_hub=false \
  --output_dir="outputs/train/act_xray_image" \
  --job_name="act_xray_image" \
  --batch_size=8 \
  --steps=20000 \
  --save_checkpoint=true \
  --save_freq=5000 \
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

### Syringe 모델 10회 연속 평가

아래 명령은 학습이 완료된 syringe의 마지막 체크포인트를 사용해 10회 연속 추론한다.
각 에피소드는 20초이며, 에피소드 사이에 물품과 로봇 시작 자세를 다시 설정할 수 있도록
30초의 대기 시간을 둔다. `RUN_ID`는 나노초까지 포함해 기존 평가 데이터셋과 이름이
겹치지 않도록 한다.

```bash
source ~/venv/il/bin/activate
export HF_USER=1unasy
RUN_ID=$(date +%Y%m%d_%H%M%S_%N)

cd ~/ExpertSurgicalMentor/src/lerobot

lerobot-record \
  --robot.type=omx_follower \
  --robot.port=/dev/ttyACM0 \
  --robot.id=omx_follower_arm \
  --robot.cameras='{
    front: {type: opencv, index_or_path: 4, width: 640, height: 480, fps: 30, fourcc: MJPG},
    wrist: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30, fourcc: MJPG}
  }' \
  --display_data=true \
  --play_sounds=true \
  --return_to_start_pose=true \
  --return_to_start_duration_s=5 \
  --start_pose_path="$HOME/ExpertSurgicalMentor/config/omx_start_pose.json" \
  --dataset.repo_id="${HF_USER}/eval_syringe_${RUN_ID}" \
  --dataset.single_task="Pick up syringe" \
  --dataset.episode_time_s=20 \
  --dataset.num_episodes=10 \
  --dataset.reset_time_s=30 \
  --dataset.push_to_hub=false \
  --policy.path="outputs/train/act_syringe/checkpoints/last/pretrained_model"
```

실행하면 follower가 5초 동안 `config/omx_start_pose.json`의 기준 자세로 먼저 이동한다.
각 20초 추론이 끝나면 5초 동안 동일한 자세로 부드럽게 복귀하고, 음성으로 reset 구간을 알린 뒤 30초 동안 화면을
표시하면서 기다린다. 이때 syringe와 주변 물품 위치를 바꾸고 로봇 동작 범위 밖으로
이동한다. 재설정 시간이 부족하면 `--dataset.reset_time_s=60`으로 늘린다.

기준 자세는 syringe 학습 데이터 30개 에피소드의 첫 프레임 관절값 중앙값으로 설정했다.
자동 이동 경로에 물품이나 사람이 있으면 충돌할 수 있으므로 시작 및 복귀 동작 중 작업 공간을 비워 둔다.
`Esc`로 비상 종료한 경우에는 자동 복귀하지 않는다.

동일한 명령을 물품 이름만 바꿔 실행할 수 있도록 실행 파일도 제공한다. 기본값은 VLM
라우터가 한 물품씩 호출하기 적합한 1회 실행이다.

```bash
cd ~/ExpertSurgicalMentor

./scripts/run_act_object.sh syringe
./scripts/run_act_object.sh glasses
./scripts/run_act_object.sh pill
./scripts/run_act_object.sh xray
```

수동으로 동일 물품을 10회 평가할 때는 다음처럼 실행한다.

```bash
./scripts/run_act_object.sh syringe --episodes 10
```

실행 파일은 기본적으로 `--policy.n_action_steps=20`을 적용해 약 0.67초마다 카메라를
다시 보고 행동을 생성한다. 기존 기본값 100과 비교하거나 동작이 끊기는 경우에는 다음처럼
변경할 수 있다.

```bash
./scripts/run_act_object.sh syringe --action-steps 30
./scripts/run_act_object.sh syringe --action-steps 100
```

follower 포트가 udev 링크로 설정되어 있으면 환경 변수로 변경할 수 있다.

```bash
ROBOT_PORT=/dev/omx_follower ./scripts/run_act_object.sh syringe
```

### YOLO 손 감지와 ACT 안전 정지 통합

`run_act_object.sh`는 기본적으로 다음 손 감지 모델을 함께 실행한다.

```text
outputs/train/hand_yolo_v1/weights/best.pt
```

실행 순서는 다음과 같다.

1. front 카메라 프레임에서 YOLO가 손을 감지한다.
2. 손이 보이면 ACT 액션 대신 현재 관절 위치를 전송하여 로봇을 정지시킨다.
3. 손이 다시 보일 때마다 안전 해제 타이머를 초기화한다.
4. 손이 연속 10초 동안 보이지 않으면 정지 전에 생성된 ACT 액션 큐를 버린다.
5. 현재 카메라 영상으로 ACT가 새 행동을 추론하고 남은 에피소드를 계속한다.

정지 시간은 `--episode-time`에 포함되지 않는다. 초기 자세 이동과 에피소드 종료 후
초기 자세 복귀에도 같은 손 감지 정지가 적용된다.

```bash
cd ~/ExpertSurgicalMentor

./scripts/run_act_object.sh syringe \
  --episodes 10 \
  --safety-clear 10 \
  --safety-conf 0.15
```

YOLO 오검출이 많으면 `--safety-conf`를 조금 높이고, 손을 놓치는 경우에는 낮춘다.
안전 기능을 끈 비교 실험은 `--no-safety`로 가능하지만 실제 로봇 시연에는 권장하지 않는다.
이 기능은 소프트웨어 보조 장치이므로 비상 정지 수단을 즉시 사용할 수 있는 상태로 시험한다.

### 100k 모델의 checkpoint 비교

`--checkpoint`로 `010000`부터 `100000` 또는 `last`를 직접 선택할 수 있다. 비교할 때는
카메라, 초기 자세, 물체 배치, `action-steps`를 모두 동일하게 유지하고 먼저 YOLO를 끈다.

```bash
cd ~/ExpertSurgicalMentor

MODEL_PREFIX=act_v2_full100k ./scripts/run_act_object.sh syringe \
  --checkpoint 020000 --episodes 5 --action-steps 30 --no-safety

MODEL_PREFIX=act_v2_full100k ./scripts/run_act_object.sh syringe \
  --checkpoint 040000 --episodes 5 --action-steps 30 --no-safety

MODEL_PREFIX=act_v2_full100k ./scripts/run_act_object.sh syringe \
  --checkpoint 060000 --episodes 5 --action-steps 30 --no-safety

MODEL_PREFIX=act_v2_full100k ./scripts/run_act_object.sh syringe \
  --checkpoint 080000 --episodes 5 --action-steps 30 --no-safety

MODEL_PREFIX=act_v2_full100k ./scripts/run_act_object.sh syringe \
  --checkpoint 100000 --episodes 5 --action-steps 30 --no-safety
```

각 실행 결과 데이터셋 이름에는 checkpoint 번호가 포함된다. 전체 성공률이 가장 높은
checkpoint를 고른 다음에만 YOLO 손 안전 기능을 켜서 통합 평가한다.

VLM 연동 시에는 VLM 출력값을 그대로 셸 명령으로 실행하지 않고, `syringe`, `glasses`,
`pill`, `xray` 중 하나인지 검증한 뒤 이 실행 파일의 첫 번째 인자로 전달한다. 실행 파일도
동일한 허용 목록을 검사하며 선택된 물품에 맞는 ACT 모델과 task 문자열만 불러온다.

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

### 감기 시나리오 전체 파이프라인

현재 교육용 감기 시나리오는 허용 목록에서 `감기/cold → pill`로 매핑한다. 실행 순서는
질병 입력 검증 → Main Tray pill 검출 → 손 안전 감시가 적용된 ACT 실행 → Assist Tray 결과
검증 → 안전하게 재시도 가능한 경우 1회 재시도이다.

처음 한 번, front 카메라와 두 트레이를 최종 위치에 고정한 뒤 ROI를 지정한다.

```bash
source ~/venv/il/bin/activate
cd ~/ExpertSurgicalMentor
python scripts/calibrate_tray_rois.py --camera 4
```

로봇을 움직이지 않고 모델·ROI·checkpoint 설정만 검사한다.

```bash
./scripts/run_cold_scenario.sh 감기 --dry-run
```

전체 파이프라인을 실행한다.

```bash
./scripts/run_cold_scenario.sh 감기
```

checkpoint와 재시도 횟수를 지정할 수도 있다.

```bash
./scripts/run_cold_scenario.sh cold \
  --checkpoint 050000 \
  --action-steps 100 \
  --episode-time 30 \
  --max-retries 1
```

ROI 보정은 카메라나 트레이 위치가 바뀔 때마다 다시 수행한다. 실제 실행 중에는 비상 정지
수단을 즉시 사용할 수 있어야 한다.

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
