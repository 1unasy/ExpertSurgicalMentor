#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/ExpertSurgicalMentor}"
VENV_DIR="${VENV_DIR:-$HOME/venv/il}"
DATASET_ROOT="${DATASET_ROOT:-$PROJECT_ROOT/datasets/objects/yolo_v1/labeled}"
MODEL="${MODEL:-yolo11n.pt}"
RUN_NAME="${RUN_NAME:-object_yolo_v1}"
OUTPUT_ROOT="${OUTPUT_ROOT:-$PROJECT_ROOT/outputs/train}"
EPOCHS="${EPOCHS:-150}"
BATCH="${BATCH:-8}"
IMGSZ="${IMGSZ:-640}"
PATIENCE="${PATIENCE:-30}"
DEVICE="${DEVICE:-0}"

for split in train valid; do
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

TMP_DIR="$(mktemp -d -t object_yolo.XXXXXX)"
trap 'rm -rf "$TMP_DIR"' EXIT
DATA_YAML="$TMP_DIR/data.yaml"
cat > "$DATA_YAML" <<EOF
path: $DATASET_ROOT
train: train/images
val: valid/images
nc: 2
names: ['syringe', 'pill']
EOF

echo "Object YOLO training"
echo "dataset: $DATASET_ROOT"
echo "classes: syringe, pill"
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
