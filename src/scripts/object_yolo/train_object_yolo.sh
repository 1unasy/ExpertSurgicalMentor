#!/usr/bin/env bash

set -Eeuo pipefail

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  cat <<'EOF'
Usage:
  ./src/scripts/object_yolo/train_object_yolo.sh

Environment overrides:
  DATASET_ROOT, MODEL, RUN_NAME, OUTPUT_ROOT, EPOCHS, BATCH, IMGSZ,
  PATIENCE, DEVICE, PROJECT_ROOT, VENV_DIR

This command trains; --help never starts training.
EOF
  exit 0
fi
if [[ $# -gt 0 ]]; then
  echo "ERROR: unknown positional arguments: $*" >&2
  exit 2
fi

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/ExpertSurgicalMentor}"
VENV_DIR="${VENV_DIR:-$HOME/venv/il}"
DATASET_ROOT="${DATASET_ROOT:-$PROJECT_ROOT/datasets/objects_grouped}"
MODEL="${MODEL:-yolo11s.pt}"
RUN_NAME="${RUN_NAME:-object_yolo_v1}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$PROJECT_ROOT/outputs/train}"
EPOCHS="${EPOCHS:-150}"
BATCH="${BATCH:-8}"
IMGSZ="${IMGSZ:-640}"
PATIENCE="${PATIENCE:-30}"
DEVICE="${DEVICE:-0}"

for split in train valid test; do
  if [[ ! -d "$DATASET_ROOT/$split/images" || ! -d "$DATASET_ROOT/$split/labels" ]]; then
    echo "ERROR: missing $DATASET_ROOT/$split/{images,labels}" >&2
    echo "Label the extracted images and export them in YOLO format first." >&2
    exit 1
  fi
done

if [[ ! -f "$VENV_DIR/bin/activate" ]]; then
  echo "ERROR: virtual environment not found: $VENV_DIR" >&2
  exit 1
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if ! python -c 'import ultralytics' >/dev/null 2>&1; then
  echo "ERROR: ultralytics is not installed in $VENV_DIR" >&2
  exit 1
fi

DATA_YAML="$DATASET_ROOT/data.yaml"
if [[ ! -f "$DATA_YAML" ]]; then
  echo "ERROR: data.yaml not found: $DATA_YAML" >&2
  exit 1
fi

echo "Object YOLO training"
echo "dataset: $DATASET_ROOT"
echo "classes: pill, syringe"
echo "model:   $MODEL"
echo "output:  $OUTPUT_ROOT/$RUN_NAME"

yolo detect train \
  data="$DATA_YAML" \
  model="$MODEL" \
  epochs="$EPOCHS" \
  batch="$BATCH" \
  imgsz="$IMGSZ" \
  patience="$PATIENCE" \
  device="$DEVICE" \
  project="$OUTPUT_ROOT" \
  name="$RUN_NAME" \
  exist_ok=false \
  pretrained=true

echo "Best model: $OUTPUT_ROOT/$RUN_NAME/weights/best.pt"

BEST_MODEL="$OUTPUT_ROOT/$RUN_NAME/weights/best.pt"
if [[ ! -f "$BEST_MODEL" ]]; then
  echo "ERROR: best.pt was not created: $BEST_MODEL" >&2
  exit 1
fi

echo
echo "Evaluating best.pt on the episode-separated test split..."
yolo detect val \
  data="$DATA_YAML" \
  model="$BEST_MODEL" \
  split=test \
  imgsz="$IMGSZ" \
  batch="$BATCH" \
  device="$DEVICE" \
  project="$OUTPUT_ROOT" \
  name="${RUN_NAME}_test" \
  exist_ok=true

echo "Test results: $OUTPUT_ROOT/${RUN_NAME}_test"
