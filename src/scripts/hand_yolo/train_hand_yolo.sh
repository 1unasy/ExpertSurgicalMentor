#!/usr/bin/env bash
#
# Train YOLO11n for hand-safety detection.
#
# Dataset:  datasets/hand/yolo_v1/hospital.yolov11/  (Roboflow export)
# Output:   outputs/train/${RUN_NAME}/weights/best.pt
#
# Env vars (all optional):
#   MODEL      base checkpoint (default: yolo11n.pt; ultralytics auto-downloads)
#   EPOCHS     training epochs (default: 100)
#   BATCH      batch size (default: 16; try 8 on Mac MPS if OOM)
#   IMGSZ      input image size (default: 640, matches Roboflow export)
#   PATIENCE   early-stop patience in epochs (default: 20)
#   DEVICE     0 for CUDA, "mps" for Apple Silicon, "cpu", or unset = auto
#   OPTIMIZER  optimizer name (default: auto)
#   LR0        initial learning rate; omitted by default
#   RUN_NAME   run subdirectory (default: hand_yolo_n_sweep_stable_v1)
#   OUTPUT_ROOT project root under which runs are saved (default: outputs/train)

set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$PROJECT_ROOT"

MODEL="${MODEL:-yolo11n.pt}"
EPOCHS="${EPOCHS:-100}"
BATCH="${BATCH:-16}"
IMGSZ="${IMGSZ:-640}"
PATIENCE="${PATIENCE:-20}"
DEVICE="${DEVICE:-}"
OPTIMIZER="${OPTIMIZER:-auto}"
LR0="${LR0:-}"
RUN_NAME="${RUN_NAME:-hand_yolo_n_sweep_stable_v1}"
OUTPUT_ROOT="${OUTPUT_ROOT:-outputs/train}"

if [[ "$OUTPUT_ROOT" != /* ]]; then
  OUTPUT_ROOT="$PROJECT_ROOT/$OUTPUT_ROOT"
fi

DATASET_ROOT="$PROJECT_ROOT/datasets/hand/yolo_v1/hospital.yolov11"

if [[ ! -d "$DATASET_ROOT/train/images" || ! -d "$DATASET_ROOT/valid/images" ]]; then
  echo "ERROR: expected dataset at $DATASET_ROOT" >&2
  echo "       missing train/images or valid/images" >&2
  exit 1
fi

if ! python3 -c "import ultralytics" >/dev/null 2>&1; then
  echo "ERROR: ultralytics not installed." >&2
  echo "       pip install ultralytics" >&2
  exit 1
fi

# Ultralytics resolves relative paths in data.yaml via its own settings; using an
# absolute-path yaml generated at run time avoids surprises from Roboflow's
# ../train/images defaults and renames the class from 'hospital' to 'hand'.
DATA_TMP_DIR="$(mktemp -d -t hand_data.XXXXXX 2>/dev/null || mktemp -d)"
DATA_YAML="$DATA_TMP_DIR/data.yaml"
trap 'rm -rf "$DATA_TMP_DIR"' EXIT

cat > "$DATA_YAML" <<EOF
path: $DATASET_ROOT
train: train/images
val: valid/images
nc: 1
names: ['hand']
EOF

device_arg=()
[[ -n "$DEVICE" ]] && device_arg=("device=$DEVICE")
optimizer_args=("optimizer=$OPTIMIZER")
[[ -n "$LR0" ]] && optimizer_args+=("lr0=$LR0")

train_images=$(ls "$DATASET_ROOT/train/images" | wc -l | tr -d ' ')
val_images=$(ls "$DATASET_ROOT/valid/images" | wc -l | tr -d ' ')

echo "======================================================"
echo "  YOLO Hand-Safety Training"
echo "======================================================"
echo "  dataset:  $DATASET_ROOT"
echo "  train:    $train_images images"
echo "  valid:    $val_images images"
echo "  model:    $MODEL"
echo "  epochs:   $EPOCHS  (patience: $PATIENCE)"
echo "  batch:    $BATCH"
echo "  imgsz:    $IMGSZ"
echo "  device:   ${DEVICE:-auto}"
echo "  optimizer: $OPTIMIZER"
echo "  lr0:      ${LR0:-auto}"
echo "  output:   $OUTPUT_ROOT/$RUN_NAME"
echo "======================================================"
echo

yolo detect train \
  data="$DATA_YAML" \
  model="$MODEL" \
  epochs="$EPOCHS" \
  batch="$BATCH" \
  imgsz="$IMGSZ" \
  patience="$PATIENCE" \
  project="$OUTPUT_ROOT" \
  name="$RUN_NAME" \
  exist_ok=false \
  pretrained=true \
  "${device_arg[@]}" \
  "${optimizer_args[@]}"

BEST="$OUTPUT_ROOT/$RUN_NAME/weights/best.pt"
echo
echo "======================================================"
echo "  Done."
if [[ -f "$BEST" ]]; then
  echo "  Best weights: $BEST"
  echo "  Validate:     yolo detect val data=$DATA_YAML model=$BEST"
  echo "  Try on image: yolo detect predict model=$BEST source=<path-to-image>"
else
  echo "  WARNING: best.pt not found. Check the training log above."
fi
echo "======================================================"
