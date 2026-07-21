#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/ExpertSurgicalMentor}"
LEROBOT_DIR="${LEROBOT_DIR:-$PROJECT_ROOT/src/lerobot}"
VENV_DIR="${VENV_DIR:-$HOME/venv/il}"
HF_USER="${HF_USER:-1unasy}"

BATCH_SIZE="${BATCH_SIZE:-4}"
STEPS="${STEPS:-50000}"
SAVE_FREQ="${SAVE_FREQ:-10000}"
USE_AMP="${USE_AMP:-true}"

OBJECTS=(
  syringe
  glasses
  pill
  xray_image
)

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
echo "batch_size: $BATCH_SIZE"
echo "steps: $STEPS"
echo "save_freq: $SAVE_FREQ"
echo "use_amp: $USE_AMP"
echo

for object in "${OBJECTS[@]}"; do
  CURRENT_OBJECT="$object"
  dataset_repo="${HF_USER}/pick_and_place_${object}"
  output_dir="outputs/train/act_${object}"
  final_model="${output_dir}/checkpoints/last/pretrained_model"

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
    --job_name="act_${object}" \
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
