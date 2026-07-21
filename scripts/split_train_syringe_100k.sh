#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/ExpertSurgicalMentor}"
HF_USER="${HF_USER:-1unasy}"
DATASET_NAME="${DATASET_NAME:-pick_and_place_v2_syringe}"
BATCH_SIZE="${BATCH_SIZE:-8}"
STEPS="${STEPS:-100000}"
SAVE_FREQ="${SAVE_FREQ:-10000}"
OUTPUT_PREFIX="${OUTPUT_PREFIX:-act_v2_split100k}"

WAIT_FOR_PID=""
TMUX_TARGET="0:0.0"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/split_train_syringe_100k.sh
  ./scripts/split_train_syringe_100k.sh --wait-for-pid PID [--tmux-target TARGET]

Pipeline:
  1. Split 40 syringe episodes into train=28, valid=6, test=6 (if needed)
  2. Train ACT on the train split for 100,000 steps

Default output:
  src/lerobot/outputs/train/act_v2_split100k_syringe

Environment overrides:
  HF_USER, DATASET_NAME, BATCH_SIZE, STEPS, SAVE_FREQ, OUTPUT_PREFIX, PROJECT_ROOT
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --wait-for-pid)
      WAIT_FOR_PID="${2:?--wait-for-pid requires a PID}"
      shift 2
      ;;
    --tmux-target)
      TMUX_TARGET="${2:?--tmux-target requires a target}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: 알 수 없는 옵션: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -n "$WAIT_FOR_PID" ]]; then
  if ! [[ "$WAIT_FOR_PID" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: --wait-for-pid must be a positive integer." >&2
    exit 2
  fi
  if ! command -v tmux >/dev/null 2>&1; then
    echo "ERROR: tmux 명령을 찾을 수 없습니다." >&2
    exit 1
  fi

  echo "현재 학습 PID $WAIT_FOR_PID 종료를 기다립니다. 이후 tmux $TMUX_TARGET 에서 실행합니다."
  while kill -0 "$WAIT_FOR_PID" 2>/dev/null; do
    sleep 10
  done

  # Give the pane shell time to regain control after its foreground job exits.
  sleep 2
  tmux send-keys -t "$TMUX_TARGET" \
    "cd '$PROJECT_ROOT' && ./scripts/split_train_syringe_100k.sh" C-m
  echo "tmux $TMUX_TARGET 에 100k syringe 학습 명령을 전송했습니다."
  exit 0
fi

cd "$PROJECT_ROOT"

TRAIN_INFO="$HOME/.cache/huggingface/lerobot/${HF_USER}/${DATASET_NAME}_train/meta/info.json"
VALID_INFO="$HOME/.cache/huggingface/lerobot/${HF_USER}/${DATASET_NAME}_valid/meta/info.json"
TEST_INFO="$HOME/.cache/huggingface/lerobot/${HF_USER}/${DATASET_NAME}_test/meta/info.json"

existing_splits=0
for info in "$TRAIN_INFO" "$VALID_INFO" "$TEST_INFO"; do
  [[ -f "$info" ]] && existing_splits=$((existing_splits + 1))
done

if (( existing_splits == 0 )); then
  echo "40개 syringe 데이터셋을 28/6/6으로 분할합니다."
  ./scripts/split_lerobot_40.sh "$DATASET_NAME"
elif (( existing_splits == 3 )); then
  echo "기존 train/valid/test 분할을 사용합니다."
else
  echo "ERROR: train/valid/test 분할 중 일부만 존재합니다." >&2
  echo "       세 분할 폴더를 확인한 뒤 다시 실행하세요." >&2
  exit 1
fi

echo
echo "ACT syringe 학습을 시작합니다."
echo "dataset: ${HF_USER}/${DATASET_NAME}_train"
echo "steps: $STEPS"
echo "batch_size: $BATCH_SIZE"
echo "save_freq: $SAVE_FREQ"
echo "output: src/lerobot/outputs/train/${OUTPUT_PREFIX}_syringe"
echo

DATASET_PREFIX="${DATASET_NAME%_syringe}" \
DATASET_SPLIT=train \
OUTPUT_PREFIX="$OUTPUT_PREFIX" \
STEPS="$STEPS" \
SAVE_FREQ="$SAVE_FREQ" \
BATCH_SIZE="$BATCH_SIZE" \
./scripts/train_act_objects.sh syringe

