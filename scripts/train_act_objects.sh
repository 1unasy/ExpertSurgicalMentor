#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/ExpertSurgicalMentor}"
LEROBOT_DIR="${LEROBOT_DIR:-$PROJECT_ROOT/src/lerobot}"
VENV_DIR="${VENV_DIR:-$HOME/venv/il}"
HF_USER="${HF_USER:-1unasy}"
DATASET_PREFIX="${DATASET_PREFIX:-pick_and_place_v2}"
DATASET_SPLIT="${DATASET_SPLIT:-}"
OUTPUT_PREFIX="${OUTPUT_PREFIX:-act_v2}"

BATCH_SIZE="${BATCH_SIZE:-8}"
STEPS="${STEPS:-20000}"
SAVE_FREQ="${SAVE_FREQ:-5000}"
USE_AMP="${USE_AMP:-true}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/train_act_objects.sh OBJECT [OBJECT ...]

Objects:
  syringe | pill | glasses | xray

Examples:
  ./scripts/train_act_objects.sh syringe pill
  ./scripts/train_act_objects.sh glasses xray
  STEPS=30000 BATCH_SIZE=8 ./scripts/train_act_objects.sh syringe

Environment overrides:
  HF_USER, DATASET_PREFIX, DATASET_SPLIT, OUTPUT_PREFIX, BATCH_SIZE, STEPS, SAVE_FREQ,
  USE_AMP, PROJECT_ROOT, LEROBOT_DIR, VENV_DIR

Split-dataset example:
  DATASET_SPLIT=train OUTPUT_PREFIX=act_v2_split ./scripts/train_act_objects.sh syringe
EOF
}

if [[ $# -eq 1 && ( "$1" == "-h" || "$1" == "--help" ) ]]; then
  usage
  exit 0
fi

if [[ $# -lt 1 ]]; then
  usage >&2
  exit 2
fi

OBJECTS=()
for object_arg in "$@"; do
  case "${object_arg,,}" in
    syringe|pill|glasses)
      OBJECTS+=("${object_arg,,}")
      ;;
    xray|xray_image|x-ray|x-ray_image)
      OBJECTS+=("xray_image")
      ;;
    *)
      echo "ERROR: 지원하지 않는 물체입니다: $object_arg" >&2
      echo "지원 물체: syringe, pill, glasses, xray" >&2
      exit 2
      ;;
  esac
done

CURRENT_OBJECT=""

on_error() {
  local exit_code=$?
  if [[ -n "$CURRENT_OBJECT" ]]; then
    echo
    echo "ERROR: '${CURRENT_OBJECT}' 학습 중 실패했습니다 (exit=${exit_code})." >&2
    echo "뒤의 모델 학습은 시작하지 않았습니다." >&2
  fi
  exit "$exit_code"
}
trap on_error ERR

if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
  echo "ERROR: 가상환경을 찾을 수 없습니다: $VENV_DIR" >&2
  exit 1
fi

if [[ ! -d "$LEROBOT_DIR" ]]; then
  echo "ERROR: LeRobot 디렉터리를 찾을 수 없습니다: $LEROBOT_DIR" >&2
  exit 1
fi

if [[ -n "$DATASET_SPLIT" && ! "$DATASET_SPLIT" =~ ^(train|valid|test)$ ]]; then
  echo "ERROR: DATASET_SPLIT must be empty, train, valid, or test." >&2
  exit 2
fi

for value_name in BATCH_SIZE STEPS SAVE_FREQ; do
  value="${!value_name}"
  if ! [[ "$value" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: ${value_name} must be a positive integer." >&2
    exit 2
  fi
done

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
cd "$LEROBOT_DIR"

if ! command -v lerobot-train >/dev/null 2>&1; then
  echo "ERROR: il 가상환경에서 lerobot-train 명령을 찾을 수 없습니다." >&2
  exit 1
fi

if command -v nvidia-smi >/dev/null 2>&1; then
  echo "GPU:"
  nvidia-smi --query-gpu=name,memory.total,memory.free \
    --format=csv,noheader
  echo
fi

echo "ACT 순차 학습을 시작합니다."
echo "순서: ${OBJECTS[*]}"
echo "HF_USER: $HF_USER"
echo "dataset_prefix: $DATASET_PREFIX"
echo "dataset_split: ${DATASET_SPLIT:-all}"
echo "output_prefix: $OUTPUT_PREFIX"
echo "batch_size: $BATCH_SIZE"
echo "steps: $STEPS"
echo "save_freq: $SAVE_FREQ"
echo "use_amp: $USE_AMP"
echo

for object in "${OBJECTS[@]}"; do
  CURRENT_OBJECT="$object"
  dataset_repo="${HF_USER}/${DATASET_PREFIX}_${object}${DATASET_SPLIT:+_${DATASET_SPLIT}}"
  dataset_dir="$HOME/.cache/huggingface/lerobot/${dataset_repo}"
  output_dir="outputs/train/${OUTPUT_PREFIX}_${object}"
  final_model="${output_dir}/checkpoints/last/pretrained_model"

  if [[ ! -f "$dataset_dir/meta/info.json" ]]; then
    echo "ERROR: 분할 데이터셋을 찾을 수 없습니다: $dataset_dir" >&2
    exit 1
  fi

  if [[ -d "$final_model" ]]; then
    echo "SKIP: '${object}' 최종 모델이 이미 있습니다: $final_model"
    echo
    continue
  fi

  if [[ -e "$output_dir" ]]; then
    echo "ERROR: 미완료 출력 디렉터리가 이미 있습니다: $output_dir" >&2
    echo "기존 학습을 재개하거나, 백업 이름으로 옮긴 뒤 다시 실행하세요." >&2
    exit 1
  fi

  echo "============================================================"
  echo "START: $object"
  echo "dataset: $dataset_repo"
  echo "output:  $output_dir"
  echo "============================================================"

  lerobot-train \
    --dataset.repo_id="$dataset_repo" \
    --policy.type=act \
    --policy.device=cuda \
    --policy.use_amp="$USE_AMP" \
    --policy.push_to_hub=false \
    --output_dir="$output_dir" \
    --job_name="${OUTPUT_PREFIX}_${object}" \
    --batch_size="$BATCH_SIZE" \
    --steps="$STEPS" \
    --save_checkpoint=true \
    --save_freq="$SAVE_FREQ" \
    --eval_freq=0 \
    --wandb.enable=false

  echo
  echo "DONE: $object"
  echo "model: $final_model"
  echo
done

CURRENT_OBJECT=""
echo "모든 ACT 모델의 순차 학습이 완료됐습니다."
