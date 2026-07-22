#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/ExpertSurgicalMentor}"
LEROBOT_DIR="${LEROBOT_DIR:-$PROJECT_ROOT/src/lerobot}"
VENV_DIR="${VENV_DIR:-$HOME/venv/il}"
HF_USER="${HF_USER:-1unasy}"
ROBOT_PORT="${ROBOT_PORT:-/dev/ttyACM0}"
START_POSE_PATH="${START_POSE_PATH:-$PROJECT_ROOT/config/omx_start_pose.json}"
MODEL_PREFIX="${MODEL_PREFIX:-act_v2}"
SAFETY_YOLO_MODEL="${SAFETY_YOLO_MODEL:-$PROJECT_ROOT/models/hand_yolo/best.pt}"
SAFETY_CONF="${SAFETY_CONF:-0.15}"
SAFETY_CLEAR_S="${SAFETY_CLEAR_S:-10}"
SAFETY_CAMERA="${SAFETY_CAMERA:-front}"
SAFETY_DEVICE="${SAFETY_DEVICE:-0}"
CAMERA_PREVIEW_OUTPUT="${CAMERA_PREVIEW_OUTPUT:-$PROJECT_ROOT/outputs/runtime/front_camera_latest.jpg}"

EPISODES=1
EPISODE_TIME_S=15
RESET_TIME_S=10
RETURN_TIME_S=5
ACTION_STEPS=20
CHECKPOINT="050000"

usage() {
  cat <<'EOF'
Usage:
  ./src/scripts/imitation_learning/run_act_object.sh OBJECT [options]

Objects:
  syringe | glasses | pill | xray

Options:
  --episodes N          Number of evaluation episodes (default: 1)
  --episode-time SEC    Policy execution time per episode (default: 15)
  --reset-time SEC      Manual scene reset time between episodes (default: 10)
  --return-time SEC     Automatic start-pose return duration (default: 5)
  --action-steps N      ACT actions executed before replanning (default: 20)
  --checkpoint NAME     Checkpoint directory, e.g. 050000 or last (default: 050000)
  --safety-clear SEC    Continuous no-hand time before resuming (default: 10)
  --safety-conf VALUE   YOLO hand confidence threshold (default: 0.15)
  --no-safety           Disable YOLO hand safety (not recommended)
  -h, --help            Show this help

Environment overrides:
  ROBOT_PORT, START_POSE_PATH, MODEL_PREFIX, HF_USER, PROJECT_ROOT, LEROBOT_DIR, VENV_DIR
  SAFETY_YOLO_MODEL, SAFETY_CONF, SAFETY_CLEAR_S, SAFETY_CAMERA, SAFETY_DEVICE

Examples:
  ./src/scripts/imitation_learning/run_act_object.sh syringe
  ./src/scripts/imitation_learning/run_act_object.sh syringe --episodes 10
  ./src/scripts/imitation_learning/run_act_object.sh syringe --episodes 10 --safety-clear 10 --safety-conf 0.15
  ./src/scripts/imitation_learning/run_act_object.sh syringe --action-steps 30
  MODEL_PREFIX=act_v2_full100k ./src/scripts/imitation_learning/run_act_object.sh syringe --checkpoint 040000
  ROBOT_PORT=/dev/omx_follower ./src/scripts/imitation_learning/run_act_object.sh pill
EOF
}

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 2
fi

if [[ "$1" == "-h" || "$1" == "--help" ]]; then
  usage
  exit 0
fi

OBJECT_INPUT="$1"
shift

while [[ $# -gt 0 ]]; do
  case "$1" in
    --episodes)
      EPISODES="${2:?--episodes requires a value}"
      shift 2
      ;;
    --episode-time)
      EPISODE_TIME_S="${2:?--episode-time requires a value}"
      shift 2
      ;;
    --reset-time)
      RESET_TIME_S="${2:?--reset-time requires a value}"
      shift 2
      ;;
    --return-time)
      RETURN_TIME_S="${2:?--return-time requires a value}"
      shift 2
      ;;
    --action-steps)
      ACTION_STEPS="${2:?--action-steps requires a value}"
      shift 2
      ;;
    --checkpoint)
      CHECKPOINT="${2:?--checkpoint requires a value}"
      shift 2
      ;;
    --safety-clear)
      SAFETY_CLEAR_S="${2:?--safety-clear requires a value}"
      shift 2
      ;;
    --safety-conf)
      SAFETY_CONF="${2:?--safety-conf requires a value}"
      shift 2
      ;;
    --no-safety)
      SAFETY_YOLO_MODEL=""
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! [[ "$EPISODES" =~ ^[1-9][0-9]*$ ]]; then
  echo "ERROR: --episodes must be a positive integer." >&2
  exit 2
fi

if ! [[ "$ACTION_STEPS" =~ ^[1-9][0-9]*$ ]] || (( ACTION_STEPS > 100 )); then
  echo "ERROR: --action-steps must be an integer between 1 and 100." >&2
  exit 2
fi

if [[ "$CHECKPOINT" != "last" && ! "$CHECKPOINT" =~ ^[0-9]{6}$ ]]; then
  echo "ERROR: --checkpoint must be 'last' or a six-digit directory such as 020000." >&2
  exit 2
fi

for value_name in EPISODE_TIME_S RESET_TIME_S RETURN_TIME_S SAFETY_CLEAR_S; do
  value="${!value_name}"
  if ! [[ "$value" =~ ^[0-9]+([.][0-9]+)?$ ]] || [[ "$value" == "0" ]]; then
    echo "ERROR: ${value_name} must be a positive number." >&2
    exit 2
  fi
done

if ! [[ "$SAFETY_CONF" =~ ^(0([.][0-9]+)?|1([.]0+)?)$ ]]; then
  echo "ERROR: --safety-conf must be a number between 0 and 1." >&2
  exit 2
fi

case "${OBJECT_INPUT,,}" in
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
    echo "ERROR: Unsupported object: ${OBJECT_INPUT}" >&2
    echo "Supported objects: syringe, glasses, pill, xray" >&2
    exit 2
    ;;
esac

if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
  echo "ERROR: Virtual environment not found: $VENV_DIR" >&2
  exit 1
fi

if [[ ! -d "$LEROBOT_DIR" ]]; then
  echo "ERROR: LeRobot directory not found: $LEROBOT_DIR" >&2
  exit 1
fi

if [[ ! -e "$ROBOT_PORT" ]]; then
  echo "ERROR: Robot port does not exist: $ROBOT_PORT" >&2
  exit 1
fi

if [[ ! -f "$START_POSE_PATH" ]]; then
  echo "ERROR: Start-pose file not found: $START_POSE_PATH" >&2
  exit 1
fi

if [[ -n "$SAFETY_YOLO_MODEL" && ! -f "$SAFETY_YOLO_MODEL" ]]; then
  echo "ERROR: YOLO hand model not found: $SAFETY_YOLO_MODEL" >&2
  exit 1
fi

MODEL_PATH="$LEROBOT_DIR/outputs/train/${MODEL_PREFIX}_${OBJECT}/checkpoints/${CHECKPOINT}/pretrained_model"
if [[ ! -d "$MODEL_PATH" ]]; then
  echo "ERROR: Trained model not found: $MODEL_PATH" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

RUN_ID="$(date +%Y%m%d_%H%M%S_%N)"
EVAL_REPO_ID="${HF_USER}/eval_${OBJECT}_${CHECKPOINT}_${RUN_ID}"

echo "Object:       $OBJECT"
echo "Task:         $TASK"
echo "Model:        $MODEL_PATH"
echo "Checkpoint:   $CHECKPOINT"
echo "Robot port:   $ROBOT_PORT"
echo "Start pose:   $START_POSE_PATH"
echo "Episodes:     $EPISODES"
echo "Action steps: $ACTION_STEPS"
if [[ -n "$SAFETY_YOLO_MODEL" ]]; then
  echo "Hand safety:  enabled (YOLO conf=$SAFETY_CONF, clear=${SAFETY_CLEAR_S}s, camera=$SAFETY_CAMERA)"
else
  echo "Hand safety:  DISABLED"
fi
echo "Eval dataset: $EVAL_REPO_ID"
echo
echo "The follower will move to the configured start pose before inference."

cd "$LEROBOT_DIR"

export LEROBOT_UI_CAMERA_PREVIEW_PATH="$CAMERA_PREVIEW_OUTPUT"
export LEROBOT_UI_CAMERA_PREVIEW_NAME="front"

SAFETY_ARGS=()
if [[ -n "$SAFETY_YOLO_MODEL" ]]; then
  SAFETY_ARGS+=(
    --safety_yolo_model_path="$SAFETY_YOLO_MODEL"
    --safety_yolo_confidence="$SAFETY_CONF"
    --safety_yolo_clear_s="$SAFETY_CLEAR_S"
    --safety_yolo_camera="$SAFETY_CAMERA"
    --safety_yolo_device="$SAFETY_DEVICE"
  )
fi

exec lerobot-record \
  --robot.type=omx_follower \
  --robot.port="$ROBOT_PORT" \
  --robot.id=omx_follower_arm \
  --robot.cameras='{
    front: {type: opencv, index_or_path: 4, width: 640, height: 480, fps: 30, fourcc: MJPG},
    wrist: {type: opencv, index_or_path: 2, width: 640, height: 480, fps: 30, fourcc: MJPG}
  }' \
  --display_data=true \
  --play_sounds=true \
  --return_to_start_pose=true \
  --return_to_start_duration_s="$RETURN_TIME_S" \
  --start_pose_path="$START_POSE_PATH" \
  --dataset.repo_id="$EVAL_REPO_ID" \
  --dataset.single_task="$TASK" \
  --dataset.episode_time_s="$EPISODE_TIME_S" \
  --dataset.num_episodes="$EPISODES" \
  --dataset.reset_time_s="$RESET_TIME_S" \
  --dataset.push_to_hub=false \
  --policy.path="$MODEL_PATH" \
  --policy.n_action_steps="$ACTION_STEPS" \
  "${SAFETY_ARGS[@]}"
