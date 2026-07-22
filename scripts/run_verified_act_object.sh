#!/usr/bin/env bash

set -Eeuo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/ExpertSurgicalMentor}"
VENV_DIR="${VENV_DIR:-$HOME/venv/il}"
OBJECT_MODEL="${OBJECT_MODEL:-$PROJECT_ROOT/outputs/train/object_yolo_v1/weights/best.pt}"
ROI_CONFIG="${ROI_CONFIG:-$PROJECT_ROOT/config/object_tray_rois.json}"
MODEL_PREFIX="${MODEL_PREFIX:-act_v2_full100k}"
CHECKPOINT="${CHECKPOINT:-last}"
ACTION_STEPS="${ACTION_STEPS:-100}"
EPISODE_TIME="${EPISODE_TIME:-30}"
OBJECT_CONF="${OBJECT_CONF:-0.5}"
CONFIRM_FRAMES="${CONFIRM_FRAMES:-10}"
REQUIRED_DETECTIONS="${REQUIRED_DETECTIONS:-7}"
MAX_RETRIES="${MAX_RETRIES:-1}"
NO_SAFETY=false

usage() {
  cat <<'EOF'
Usage:
  ./scripts/run_verified_act_object.sh syringe|pill [options]

Options:
  --checkpoint NAME
  --max-retries N       Retry only if the object is still in Main Tray (default: 1)
  --object-conf VALUE   Object detector confidence (default: 0.5)
  --no-safety           Disable the separate hand-safety detector
EOF
}

[[ $# -ge 1 ]] || { usage >&2; exit 2; }
OBJECT="$1"
shift
[[ "$OBJECT" == "syringe" || "$OBJECT" == "pill" ]] || { usage >&2; exit 2; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --checkpoint) CHECKPOINT="${2:?}"; shift 2 ;;
    --max-retries) MAX_RETRIES="${2:?}"; shift 2 ;;
    --object-conf) OBJECT_CONF="${2:?}"; shift 2 ;;
    --no-safety) NO_SAFETY=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; exit 2 ;;
  esac
done

[[ -f "$OBJECT_MODEL" ]] || { echo "ERROR: object model not found: $OBJECT_MODEL" >&2; exit 1; }
[[ -f "$ROI_CONFIG" ]] || { echo "ERROR: ROI config not found: $ROI_CONFIG" >&2; exit 1; }
[[ "$MAX_RETRIES" =~ ^[0-9]+$ ]] || { echo "ERROR: --max-retries must be an integer" >&2; exit 2; }

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
cd "$PROJECT_ROOT"

verify() {
  python scripts/object_yolo_verifier.py "$OBJECT" \
    --model "$OBJECT_MODEL" --roi-config "$ROI_CONFIG" \
    --confidence "$OBJECT_CONF" --frames "$CONFIRM_FRAMES" \
    --required "$REQUIRED_DETECTIONS"
}

initial_state="$(verify)"
if [[ "$initial_state" == "assist" ]]; then
  echo "SUCCESS: $OBJECT is already in Assist Tray. No ACT command sent."
  exit 0
fi
if [[ "$initial_state" != "main" ]]; then
  echo "BLOCKED: $OBJECT is not confidently located in Main Tray ($initial_state)." >&2
  exit 3
fi

attempt=0
while (( attempt <= MAX_RETRIES )); do
  attempt=$((attempt + 1))
  echo "ACT attempt $attempt/$((MAX_RETRIES + 1)): $OBJECT"
  run_args=("$OBJECT" --checkpoint "$CHECKPOINT" --episodes 1 --episode-time "$EPISODE_TIME" --action-steps "$ACTION_STEPS")
  $NO_SAFETY && run_args+=(--no-safety)
  MODEL_PREFIX="$MODEL_PREFIX" ./scripts/run_act_object.sh "${run_args[@]}"

  final_state="$(verify)"
  if [[ "$final_state" == "assist" ]]; then
    echo "SUCCESS: $OBJECT verified in Assist Tray."
    exit 0
  fi
  if [[ "$final_state" != "main" ]]; then
    echo "FAILED: $OBJECT is not in Assist Tray and is not safely retryable ($final_state)." >&2
    exit 4
  fi
  if (( attempt > MAX_RETRIES )); then
    echo "FAILED: $OBJECT remained in Main Tray after all attempts." >&2
    exit 5
  fi
  echo "RETRY: $OBJECT is still confidently in Main Tray."
done
