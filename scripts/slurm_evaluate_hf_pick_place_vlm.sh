#!/bin/bash

set -euo pipefail

echo "### START DATE=$(date)"
echo "### HOSTNAME=$(hostname)"
echo "### SLURM_JOB_ID=${SLURM_JOB_ID:-unset}"
echo "### CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-unset}"

########################################
# -------- Default arguments ----------
########################################
EPISODES_PER_TOOL=${1:-5}
MODEL=${MODEL:-all}
PROJECT_ROOT=${PROJECT_ROOT:-/home/jyseo9506/wsy_ws/ExpertSurgicalMentor}
CONDA_ENV=${CONDA_ENV:-surgical-mentor}
OUTPUT_DIR=${OUTPUT_DIR:-${PROJECT_ROOT}/results/vlm_pick_place_v2}
CACHE_DIR=${CACHE_DIR:-${PROJECT_ROOT}/data/hf_cache}
PROMPT_LANGUAGE=${PROMPT_LANGUAGE:-ko}
PROMPT_FILE=${PROMPT_FILE:-${PROJECT_ROOT}/config/vlm_inventory_prompt.txt}

########################################
# -------- Conda environment ----------
########################################
source /home/jyseo9506/anaconda3/etc/profile.d/conda.sh
conda activate "${CONDA_ENV}"

cd "${PROJECT_ROOT}"

echo "### PROJECT_ROOT=${PROJECT_ROOT}"
echo "### CONDA_ENV=${CONDA_ENV}"
echo "### MODEL=${MODEL}"
echo "### EPISODES_PER_TOOL=${EPISODES_PER_TOOL}"
echo "### TOTAL_EPISODES=$((EPISODES_PER_TOOL * 2))"
echo "### OUTPUT_DIR=${OUTPUT_DIR}"
echo "### CACHE_DIR=${CACHE_DIR}"
echo "### PROMPT_LANGUAGE=${PROMPT_LANGUAGE}"
echo "### PROMPT_FILE=${PROMPT_FILE}"

python - <<'PY'
import torch

print(f"### torch={torch.__version__}")
print(f"### cuda_available={torch.cuda.is_available()}")
print(f"### cuda_device_count={torch.cuda.device_count()}")
if not torch.cuda.is_available():
    raise SystemExit("ERROR: Slurm compute node에서 CUDA GPU를 사용할 수 없습니다.")
print(f"### gpu={torch.cuda.get_device_name(0)}")
print(f"### gpu_memory_gib={torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f}")
PY

########################################
# -------- Build command --------------
########################################
CMD=(
  python scripts/evaluate_hf_pick_place_vlm.py
  --model "${MODEL}"
  --episodes-per-tool "${EPISODES_PER_TOOL}"
  --cache-dir "${CACHE_DIR}"
  --output-dir "${OUTPUT_DIR}"
  --prompt-language "${PROMPT_LANGUAGE}"
  --prompt-file "${PROMPT_FILE}"
)

echo "### RUN COMMAND:"
printf ' %q' "${CMD[@]}"
echo

srun --unbuffered "${CMD[@]}"

echo "### COMPARISON TABLE"
cat "${OUTPUT_DIR}/comparison.md"
echo "### END DATE=$(date)"
