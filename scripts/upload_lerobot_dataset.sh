#!/usr/bin/env bash

set -Eeuo pipefail

VENV_DIR="${VENV_DIR:-$HOME/venv/il}"
HF_USER="${HF_USER:-1unasy}"

if [[ $# -ne 1 ]]; then
  echo "Usage: ./scripts/upload_lerobot_dataset.sh DATASET_NAME" >&2
  exit 2
fi

DATASET_NAME="$1"
if ! [[ "$DATASET_NAME" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "ERROR: Invalid DATASET_NAME: $DATASET_NAME" >&2
  exit 2
fi

DATASET_ID="${HF_USER}/${DATASET_NAME}"
DATASET_DIR="$HOME/.cache/huggingface/lerobot/${DATASET_ID}"

if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
  echo "ERROR: Virtual environment not found: $VENV_DIR" >&2
  exit 1
fi

if [[ ! -f "$DATASET_DIR/meta/info.json" ]]; then
  echo "ERROR: Dataset metadata not found: $DATASET_DIR/meta/info.json" >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if ! command -v hf >/dev/null 2>&1; then
  echo "ERROR: The 'hf' command was not found in the active environment." >&2
  exit 1
fi

echo "Uploading: $DATASET_DIR"
echo "Target:    https://huggingface.co/datasets/$DATASET_ID"

exec hf upload-large-folder \
  "$DATASET_ID" \
  "$DATASET_DIR" \
  --repo-type dataset
