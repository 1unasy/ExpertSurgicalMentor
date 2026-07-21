#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/ExpertSurgicalMentor}"
HF_USER="${HF_USER:-1unasy}"
DATASET_PREFIX="${DATASET_PREFIX:-pick_and_place_v2}"
OUTPUT_PREFIX="${OUTPUT_PREFIX:-act_v2_split100k}"
BATCH_SIZE="${BATCH_SIZE:-8}"
STEPS="${STEPS:-100000}"
SAVE_FREQ="${SAVE_FREQ:-10000}"
POLL_SECONDS="${POLL_SECONDS:-1800}"

WAIT_FOR_PID=""
TMUX_TARGET="0:0.0"
OBJECTS=()

usage() {
  cat <<'EOF'
Usage:
  ./scripts/split_train_act_objects_100k.sh [syringe] [pill]
  ./scripts/split_train_act_objects_100k.sh --wait-for-pid PID \
    [--tmux-target TARGET] [syringe] [pill]

Default objects:
  syringe pill

For each object:
  - split 40 episodes into train=28, valid=6, test=6 (if needed)
  - train ACT using only the train split
  - run 100,000 optimization steps
  - save every 10,000 steps

Default outputs:
  src/lerobot/outputs/train/act_v2_split100k_syringe
  src/lerobot/outputs/train/act_v2_split100k_pill

PID watcher:
  Checks the PID every 30 minutes (POLL_SECONDS=1800), then sends this
  script to tmux 0:0.0 after the watched process exits.

Environment overrides:
  HF_USER, DATASET_PREFIX, OUTPUT_PREFIX, BATCH_SIZE, STEPS, SAVE_FREQ,
  POLL_SECONDS, PROJECT_ROOT
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
    syringe|pill)
      OBJECTS+=("$1")
      shift
      ;;
    *)
      echo "ERROR: 지원하지 않는 옵션 또는 물체입니다: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if (( ${#OBJECTS[@]} == 0 )); then
  OBJECTS=(syringe pill)
fi

for value_name in BATCH_SIZE STEPS SAVE_FREQ POLL_SECONDS; do
  value="${!value_name}"
  if ! [[ "$value" =~ ^[1-9][0-9]*$ ]]; then
    echo "ERROR: $value_name must be a positive integer." >&2
    exit 2
  fi
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

  echo "PID $WAIT_FOR_PID 상태를 ${POLL_SECONDS}초(기본 30분)마다 확인합니다."
  while kill -0 "$WAIT_FOR_PID" 2>/dev/null; do
    echo "$(date '+%F %T') - PID $WAIT_FOR_PID 실행 중; 다음 확인까지 ${POLL_SECONDS}초"
    sleep "$POLL_SECONDS"
  done

  object_args="${OBJECTS[*]}"
  tmux send-keys -t "$TMUX_TARGET" \
    "cd '$PROJECT_ROOT' && ./scripts/split_train_act_objects_100k.sh $object_args" C-m
  echo "$(date '+%F %T') - tmux $TMUX_TARGET 에 학습 명령을 전송했습니다."
  exit 0
fi

cd "$PROJECT_ROOT"

echo "============================================================"
echo "ACT 100k split training"
echo "objects:       ${OBJECTS[*]}"
echo "dataset:       ${HF_USER}/${DATASET_PREFIX}_<object>"
echo "split:         train=28, valid=6, test=6"
echo "steps:         $STEPS"
echo "batch_size:    $BATCH_SIZE"
echo "save_freq:     $SAVE_FREQ"
echo "output_prefix: $OUTPUT_PREFIX"
echo "============================================================"
echo

for object in "${OBJECTS[@]}"; do
  dataset_name="${DATASET_PREFIX}_${object}"
  base="$HOME/.cache/huggingface/lerobot/${HF_USER}/${dataset_name}"
  source_info="$base/meta/info.json"
  train_info="${base}_train/meta/info.json"
  valid_info="${base}_valid/meta/info.json"
  test_info="${base}_test/meta/info.json"

  if [[ ! -f "$source_info" ]]; then
    echo "ERROR: $object 원본 40개 데이터셋을 찾을 수 없습니다: $source_info" >&2
    exit 1
  fi

  existing_splits=0
  for info in "$train_info" "$valid_info" "$test_info"; do
    [[ -f "$info" ]] && existing_splits=$((existing_splits + 1))
  done

  if (( existing_splits == 0 )); then
    echo "[$object] 40개 데이터를 28/6/6으로 분할합니다."
    ./scripts/split_lerobot_40.sh "$dataset_name"
  elif (( existing_splits == 3 )); then
    echo "[$object] 기존 train/valid/test 분할을 사용합니다."
  else
    echo "ERROR: $object 분할 중 일부만 존재합니다." >&2
    echo "       ${base}_{train,valid,test} 폴더를 확인하세요." >&2
    exit 1
  fi
done

echo
echo "분할 완료. ACT 모델을 다음 순서로 학습합니다: ${OBJECTS[*]}"
echo

DATASET_PREFIX="$DATASET_PREFIX" \
DATASET_SPLIT=train \
OUTPUT_PREFIX="$OUTPUT_PREFIX" \
STEPS="$STEPS" \
SAVE_FREQ="$SAVE_FREQ" \
BATCH_SIZE="$BATCH_SIZE" \
./scripts/train_act_objects.sh "${OBJECTS[@]}"

