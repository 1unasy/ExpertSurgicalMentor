#!/usr/bin/env bash

# End-to-end educational demo for the common-cold scenario:
# disease input -> allow-listed tool plan -> object verification -> hand-safe ACT
# execution -> post-action verification/retry.

set -Eeuo pipefail

PROJECT_ROOT="${PROJECT_ROOT:-$HOME/ExpertSurgicalMentor}"
VERIFIED_RUNNER="${VERIFIED_RUNNER:-$PROJECT_ROOT/src/scripts/pipeline/run_verified_act_object.sh}"
OBJECT_MODEL="${OBJECT_MODEL:-$PROJECT_ROOT/outputs/train/object_yolo_v1/weights/best.pt}"
ROI_CONFIG="${ROI_CONFIG:-$PROJECT_ROOT/config/object_tray_rois.json}"
HAND_MODEL="${SAFETY_YOLO_MODEL:-$PROJECT_ROOT/outputs/train/hand_yolo_n_sweep_stable_v1/weights/best.pt}"
LEROBOT_DIR="${LEROBOT_DIR:-$PROJECT_ROOT/src/lerobot}"

MODEL_PREFIX="${MODEL_PREFIX:-act_v2_full100k}"
CHECKPOINT="${CHECKPOINT:-050000}"
ACTION_STEPS="${ACTION_STEPS:-100}"
EPISODE_TIME="${EPISODE_TIME:-30}"
MAX_RETRIES="${MAX_RETRIES:-1}"
OBJECT_CONF="${OBJECT_CONF:-0.5}"
SAFETY_CONF="${SAFETY_CONF:-0.15}"
SAFETY_CLEAR_S="${SAFETY_CLEAR_S:-10}"

DISEASE="감기"
PATIENT_NAME="${PATIENT_NAME:-환자A}"
NO_SAFETY=false
DRY_RUN=false

usage() {
  cat <<'EOF'
Usage:
  ./src/scripts/pipeline/run_cold_scenario.sh [감기|cold] [options]

Scenario plan:
  감기/cold -> syringe

Pipeline:
  1. Validate the disease and map it to an allow-listed object.
  2. Verify syringe is in Main Tray with object YOLO.
  3. Run the syringe ACT policy with YOLO hand interruption enabled.
  4. Verify syringe moved to Assist Tray; retry only when safely possible.

Options:
  --patient NAME        Virtual patient identifier (default: 환자A)
  --checkpoint NAME     ACT checkpoint (default: 050000)
  --action-steps N      ACT actions before replanning (default: 100)
  --episode-time SEC    Maximum ACT execution time (default: 30)
  --max-retries N       Additional attempts if syringe remains in Main (default: 1)
  --object-conf VALUE   Object YOLO confidence threshold (default: 0.5)
  --safety-conf VALUE   Hand YOLO confidence threshold (default: 0.15)
  --safety-clear SEC    No-hand duration required to resume (default: 10)
  --no-safety           Disable hand detection (not recommended)
  --dry-run             Validate and print the plan without moving the robot
  -h, --help            Show this help

Examples:
  ./src/scripts/pipeline/run_cold_scenario.sh --dry-run
  ./src/scripts/pipeline/run_cold_scenario.sh 감기 --checkpoint 050000
  ./src/scripts/pipeline/run_cold_scenario.sh cold --max-retries 2
EOF
}

if [[ $# -gt 0 && "$1" != -* ]]; then
  DISEASE="$1"
  shift
fi

while [[ $# -gt 0 ]]; do
  case "$1" in
    --checkpoint) CHECKPOINT="${2:?--checkpoint requires a value}"; shift 2 ;;
    --patient) PATIENT_NAME="${2:?--patient requires a value}"; shift 2 ;;
    --action-steps) ACTION_STEPS="${2:?--action-steps requires a value}"; shift 2 ;;
    --episode-time) EPISODE_TIME="${2:?--episode-time requires a value}"; shift 2 ;;
    --max-retries) MAX_RETRIES="${2:?--max-retries requires a value}"; shift 2 ;;
    --object-conf) OBJECT_CONF="${2:?--object-conf requires a value}"; shift 2 ;;
    --safety-conf) SAFETY_CONF="${2:?--safety-conf requires a value}"; shift 2 ;;
    --safety-clear) SAFETY_CLEAR_S="${2:?--safety-clear requires a value}"; shift 2 ;;
    --no-safety) NO_SAFETY=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "${DISEASE,,}" in
  감기|cold|common_cold|common-cold)
    SCENARIO_ID="DEMO_COMMON_COLD_001"
    OBJECT="syringe"
    ;;
  *)
    echo "ERROR: unsupported disease scenario: $DISEASE" >&2
    echo "Supported inputs: 감기, cold" >&2
    exit 2
    ;;
esac

[[ -n "${PATIENT_NAME//[[:space:]]/}" ]] || {
  echo "ERROR: --patient must not be empty" >&2; exit 2;
}

[[ "$ACTION_STEPS" =~ ^[1-9][0-9]*$ ]] && (( ACTION_STEPS <= 100 )) || {
  echo "ERROR: --action-steps must be an integer between 1 and 100" >&2; exit 2;
}
[[ "$MAX_RETRIES" =~ ^[0-9]+$ ]] || {
  echo "ERROR: --max-retries must be a non-negative integer" >&2; exit 2;
}
[[ "$CHECKPOINT" == "last" || "$CHECKPOINT" =~ ^[0-9]{6}$ ]] || {
  echo "ERROR: --checkpoint must be last or six digits such as 050000" >&2; exit 2;
}

ACT_MODEL="$LEROBOT_DIR/outputs/train/${MODEL_PREFIX}_${OBJECT}/checkpoints/${CHECKPOINT}/pretrained_model"

echo "============================================================"
echo "Educational scenario: $SCENARIO_ID"
echo "Patient identifier:   $PATIENT_NAME"
echo "Disease input:        $DISEASE"
echo "Allow-listed plan:    $OBJECT"
echo "Object detector:      $OBJECT_MODEL"
echo "Tray ROI config:      $ROI_CONFIG"
echo "ACT policy:           $ACT_MODEL"
if $NO_SAFETY; then
  echo "Hand safety:          DISABLED"
else
  echo "Hand safety:          $HAND_MODEL (conf=$SAFETY_CONF, clear=${SAFETY_CLEAR_S}s)"
fi
echo "Retry policy:         $MAX_RETRIES additional attempt(s)"
echo "============================================================"

errors=0
[[ -x "$VERIFIED_RUNNER" ]] || { echo "MISSING: executable $VERIFIED_RUNNER" >&2; errors=$((errors + 1)); }
[[ -f "$OBJECT_MODEL" ]] || { echo "MISSING: $OBJECT_MODEL" >&2; errors=$((errors + 1)); }
[[ -f "$ROI_CONFIG" ]] || {
  echo "MISSING: $ROI_CONFIG" >&2
  echo "Run: python ./src/scripts/tray/calibrate_tray_rois.py --camera 4" >&2
  errors=$((errors + 1))
}
[[ -d "$ACT_MODEL" ]] || { echo "MISSING: $ACT_MODEL" >&2; errors=$((errors + 1)); }
if ! $NO_SAFETY && [[ ! -f "$HAND_MODEL" ]]; then
  echo "MISSING: $HAND_MODEL" >&2
  errors=$((errors + 1))
fi
(( errors == 0 )) || exit 1

if $DRY_RUN; then
  echo "DRY RUN OK: configuration is complete; the robot was not moved."
  exit 0
fi

runner_args=(
  "$OBJECT"
  --checkpoint "$CHECKPOINT"
  --max-retries "$MAX_RETRIES"
  --object-conf "$OBJECT_CONF"
)
$NO_SAFETY && runner_args+=(--no-safety)

echo "Starting verified cold-scenario execution..."
MODEL_PREFIX="$MODEL_PREFIX" \
ACTION_STEPS="$ACTION_STEPS" \
EPISODE_TIME="$EPISODE_TIME" \
OBJECT_MODEL="$OBJECT_MODEL" \
ROI_CONFIG="$ROI_CONFIG" \
SAFETY_YOLO_MODEL="$HAND_MODEL" \
SAFETY_CONF="$SAFETY_CONF" \
SAFETY_CLEAR_S="$SAFETY_CLEAR_S" \
  "$VERIFIED_RUNNER" "${runner_args[@]}"

echo "SCENARIO SUCCESS: $SCENARIO_ID completed and $OBJECT was verified in Assist Tray."
