#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/ExpertSurgicalMentor}"
LEROBOT_DIR="${LEROBOT_DIR:-$PROJECT_ROOT/src/lerobot}"
VENV_DIR="${VENV_DIR:-$HOME/venv/il}"
HF_USER="${HF_USER:-1unasy}"

DATASET_NAME="${1:-pick_and_place_v2_syringe}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/split_lerobot_40.sh [DATASET_NAME]

Default:
  DATASET_NAME=pick_and_place_v2_syringe

Creates:
  <repo_id>_train   28 episodes
  <repo_id>_valid    6 episodes
  <repo_id>_test     6 episodes

Example:
  ./scripts/split_lerobot_40.sh pick_and_place_v2_syringe
EOF
}

if [[ "$DATASET_NAME" == "-h" || "$DATASET_NAME" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "$DATASET_NAME" == */* || ! "$DATASET_NAME" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "ERROR: DATASET_NAME에는 저장소 이름만 입력하세요: $DATASET_NAME" >&2
  exit 2
fi

if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
  echo "ERROR: 가상환경을 찾을 수 없습니다: $VENV_DIR" >&2
  exit 1
fi

if [[ ! -d "$LEROBOT_DIR" ]]; then
  echo "ERROR: LeRobot 디렉터리를 찾을 수 없습니다: $LEROBOT_DIR" >&2
  exit 1
fi

REPO_ID="${HF_USER}/${DATASET_NAME}"
DATASET_ROOT="$HOME/.cache/huggingface/lerobot/$REPO_ID"
INFO_PATH="$DATASET_ROOT/meta/info.json"

if [[ ! -f "$INFO_PATH" ]]; then
  echo "ERROR: 원본 데이터셋을 찾을 수 없습니다: $INFO_PATH" >&2
  exit 1
fi

TOTAL_EPISODES="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["total_episodes"])' "$INFO_PATH")"
if [[ "$TOTAL_EPISODES" != "40" ]]; then
  echo "ERROR: 이 스크립트는 정확히 40개 에피소드용입니다 (현재: $TOTAL_EPISODES)." >&2
  exit 1
fi

for split in train valid test; do
  output="$HOME/.cache/huggingface/lerobot/${REPO_ID}_${split}"
  if [[ -e "$output" ]]; then
    echo "ERROR: 기존 분할 폴더가 있습니다: $output" >&2
    echo "       내용을 확인한 뒤 직접 백업하거나 삭제하고 다시 실행하세요." >&2
    exit 1
  fi
done

# valid/test를 수집 순서 전체에 고르게 배치한다. 나머지 28개는 train이다.
SPLITS='{
  "train": [0,1,2,4,5,7,8,9,11,12,14,15,16,18,19,21,22,23,25,26,28,29,30,32,33,35,36,37],
  "valid": [3,10,17,24,31,38],
  "test": [6,13,20,27,34,39]
}'

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
cd "$LEROBOT_DIR"

echo "Source: $REPO_ID (40 episodes)"
echo "Split:  train=28, valid=6, test=6"
echo

lerobot-edit-dataset \
  --repo_id="$REPO_ID" \
  --operation.type=split \
  --operation.splits="$SPLITS" \
  --push_to_hub=false

echo
echo "Created:"
for split in train valid test; do
  echo "  $HOME/.cache/huggingface/lerobot/${REPO_ID}_${split}"
done

