#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/ExpertSurgicalMentor}"
LEROBOT_DIR="${LEROBOT_DIR:-$PROJECT_ROOT/src/lerobot}"
VENV_DIR="${VENV_DIR:-$HOME/venv/il}"
HF_USER="${HF_USER:-1unasy}"
FOLLOWER_PORT="${FOLLOWER_PORT:-/dev/ttyACM0}"
LEADER_PORT="${LEADER_PORT:-/dev/ttyACM1}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/record_object_dataset.sh new  DATASET_NAME OBJECT COUNT
  ./scripts/record_object_dataset.sh more DATASET_NAME OBJECT COUNT

Objects:
  syringe | glasses | pill | xray

Examples:
  ./scripts/record_object_dataset.sh new  pick_and_place_v2 syringe 10
  ./scripts/record_object_dataset.sh more pick_and_place_v2 glasses 10

Environment overrides:
  HF_USER, FOLLOWER_PORT, LEADER_PORT, PROJECT_ROOT, LEROBOT_DIR, VENV_DIR
EOF
}

if [[ $# -eq 1 && ( "$1" == "-h" || "$1" == "--help" ) ]]; then
  usage
  exit 0
fi

if [[ $# -ne 4 ]]; then
  usage >&2
  exit 2
fi

MODE="${1,,}"
DATASET_NAME="$2"
OBJECT_INPUT="${3,,}"
COUNT="$4"

if [[ "$MODE" != "new" && "$MODE" != "more" ]]; then
  echo "ERROR: Mode must be 'new' or 'more'." >&2
  exit 2
fi

if ! [[ "$DATASET_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "ERROR: DATASET_NAME may contain only letters, numbers, '.', '_' and '-'." >&2
  exit 2
fi

if ! [[ "$COUNT" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: COUNT must be a positive integer." >&2
  exit 2
fi

case "$OBJECT_INPUT" in
  syringe)
    OBJECT="syringe"
    TASK="Pick up syringe"
    ;;
  glasses|glass)
    OBJECT="glasses"
    TASK="Pick up glasses"
    ;;
  pill)
    OBJECT="pill"
    TASK="Pick up a pill"
    ;;
  xray|xray_image|x-ray|x-ray_image)
    OBJECT="xray_image"
    TASK="Pick up xray-image"
    ;;
  *)
    echo "ERROR: Unsupported object: $OBJECT_INPUT" >&2
    echo "Supported objects: syringe, glasses, pill, xray" >&2
    exit 2
    ;;
esac

DATASET_ID="${HF_USER}/${DATASET_NAME}"
DATASET_DIR="$HOME/.cache/huggingface/lerobot/${DATASET_ID}"

if [[ "$MODE" == "new" && -e "$DATASET_DIR" ]]; then
  echo "ERROR: A local dataset already exists: $DATASET_DIR" >&2
  echo "Use mode 'more' to append, or choose a new DATASET_NAME." >&2
  exit 1
fi

if [[ "$MODE" == "more" ]]; then
  if [[ ! -f "$DATASET_DIR/meta/info.json" ]]; then
    echo "ERROR: Existing dataset metadata was not found: $DATASET_DIR/meta/info.json" >&2
    echo "Create it first with mode 'new'." >&2
    exit 1
  fi
  if [[ ! -f "$DATASET_DIR/meta/tasks.parquet" ]]; then
    echo "ERROR: The local dataset is incomplete: $DATASET_DIR" >&2
    echo "Missing: $DATASET_DIR/meta/tasks.parquet" >&2
    echo "A previous 'new' recording likely failed before its first episode was saved." >&2
    echo "Back up or remove the incomplete folder, then run mode 'new' again." >&2
    exit 1
  fi
fi

for path in "$VENV_DIR/bin/activate" "$LEROBOT_DIR" "$FOLLOWER_PORT" "$LEADER_PORT"; do
  if [[ ! -e "$path" ]]; then
    echo "ERROR: Required path does not exist: $path" >&2
    exit 1
  fi
done

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "Mode:          $MODE"
echo "Dataset:       $DATASET_ID"
echo "Local folder:  $DATASET_DIR"
echo "Object:        $OBJECT"
echo "Task:          $TASK"
echo "Episodes:      $COUNT"
echo "Follower port: $FOLLOWER_PORT"
echo "Leader port:   $LEADER_PORT"
echo

cd "$LEROBOT_DIR"

args=(
  lerobot-record
  --robot.type=omx_follower
  --robot.port="$FOLLOWER_PORT"
  --robot.id=omx_follower_arm
  --robot.cameras='{
    front: {type: opencv, index_or_path: 4, width: 640, height: 480, fps: 30, fourcc: MJPG},
    wrist: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30, fourcc: MJPG}
  }'
  --teleop.type=omx_leader
  --teleop.port="$LEADER_PORT"
  --teleop.id=omx_leader_arm
  --display_data=true
  --play_sounds=true
  --dataset.repo_id="$DATASET_ID"
  --dataset.single_task="$TASK"
  --dataset.episode_time_s=13
  --dataset.num_episodes="$COUNT"
  --dataset.reset_time_s=8
  --dataset.push_to_hub=false
)

if [[ "$MODE" == "more" ]]; then
  args+=(--resume=true)
fi

exec "${args[@]}"
