#!/usr/bin/env bash
#
# Sweep YOLOv11 variants (n/s/m by default) for hand-safety detection.
# Reuses scripts/train_hand_yolo.sh for each run, then prints and saves a
# comparison table read from each run's results.csv (best-fitness epoch).
#
# Env vars (all optional):
#   VARIANTS   space-separated list of v11 sizes (default: "n s m")
#   SWEEP_TAG  suffix appended to run names (default: sweep_v1)
#   EPOCHS, BATCH, IMGSZ, PATIENCE, DEVICE   forwarded to train_hand_yolo.sh
#   OUTPUT_ROOT project root under which runs are saved (default: outputs/train)
#
# Example:
#   VARIANTS="n s m" EPOCHS=100 BATCH=16 DEVICE=mps \
#     scripts/train_hand_yolo_sweep.sh

set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

VARIANTS="${VARIANTS:-n s m}"
SWEEP_TAG="${SWEEP_TAG:-sweep_v1}"
OUTPUT_ROOT="${OUTPUT_ROOT:-outputs/train}"
if [[ "$OUTPUT_ROOT" != /* ]]; then
  OUTPUT_ROOT="$PROJECT_ROOT/$OUTPUT_ROOT"
fi

mkdir -p "$OUTPUT_ROOT"

echo "======================================================"
echo "  YOLOv11 sweep"
echo "  variants: $VARIANTS"
echo "  tag:      $SWEEP_TAG"
echo "  output:   $OUTPUT_ROOT"
echo "======================================================"

for V in $VARIANTS; do
  MODEL_PT="yolo11${V}.pt"
  RUN_NAME="hand_yolo_${V}_${SWEEP_TAG}"
  RUN_DIR="$OUTPUT_ROOT/$RUN_NAME"

  if [[ -f "$RUN_DIR/weights/best.pt" ]]; then
    echo
    echo "[skip] $RUN_NAME already has best.pt — reusing"
    continue
  fi

  echo
  echo "=== training $MODEL_PT → $RUN_NAME ==="
  MODEL="$MODEL_PT" RUN_NAME="$RUN_NAME" OUTPUT_ROOT="$OUTPUT_ROOT" \
    "$PROJECT_ROOT/scripts/train_hand_yolo.sh"
done

SUMMARY_CSV="$OUTPUT_ROOT/${SWEEP_TAG}_summary.csv"

echo
echo "======================================================"
echo "  Summary"
echo "======================================================"

python3 - "$OUTPUT_ROOT" "$SUMMARY_CSV" "$SWEEP_TAG" $VARIANTS <<'PY'
import csv, sys
from pathlib import Path

output_root = Path(sys.argv[1])
summary_csv = Path(sys.argv[2])
sweep_tag = sys.argv[3]
variants = sys.argv[4:]

# Ultralytics default fitness = 0.1 * mAP50 + 0.9 * mAP50-95.
# best.pt corresponds to the epoch that maximizes this.
def fitness(row):
    return 0.1 * row["mAP50"] + 0.9 * row["mAP50_95"]

def load_best_row(results_csv):
    rows = []
    with results_csv.open() as f:
        for r in csv.DictReader(f):
            try:
                rows.append({
                    "epoch": int(float(r["epoch"])),
                    "time_s": float(r.get("time", 0) or 0),
                    "precision": float(r["metrics/precision(B)"]),
                    "recall": float(r["metrics/recall(B)"]),
                    "mAP50": float(r["metrics/mAP50(B)"]),
                    "mAP50_95": float(r["metrics/mAP50-95(B)"]),
                })
            except (KeyError, ValueError):
                continue
    if not rows:
        return None, None
    best = max(rows, key=fitness)
    last = rows[-1]
    return best, last

records = []
for v in variants:
    run = f"hand_yolo_{v}_{sweep_tag}"
    run_dir = output_root / run
    best_pt = run_dir / "weights" / "best.pt"
    results_csv = run_dir / "results.csv"

    if not results_csv.exists():
        print(f"[warn] no results.csv for {run}")
        continue

    best, last = load_best_row(results_csv)
    if best is None:
        print(f"[warn] no valid rows in {results_csv}")
        continue

    size_mb = best_pt.stat().st_size / (1024 * 1024) if best_pt.exists() else 0.0

    records.append({
        "variant": f"yolo11{v}",
        "run": run,
        "best_epoch": best["epoch"],
        "total_epochs": last["epoch"],
        "train_time_s": round(last["time_s"], 1),
        "weights_mb": round(size_mb, 2),
        "precision": round(best["precision"], 4),
        "recall": round(best["recall"], 4),
        "mAP50": round(best["mAP50"], 4),
        "mAP50-95": round(best["mAP50_95"], 4),
    })

if not records:
    print("no runs to summarize")
    sys.exit(0)

with summary_csv.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(records[0].keys()))
    w.writeheader()
    w.writerows(records)

cols = ["variant", "best_epoch", "train_time_s", "weights_mb",
        "precision", "recall", "mAP50", "mAP50-95"]
widths = {c: max(len(c), max(len(str(r[c])) for r in records)) for c in cols}
sep = " | "
print(sep.join(c.ljust(widths[c]) for c in cols))
print("-+-".join("-" * widths[c] for c in cols))
for r in records:
    print(sep.join(str(r[c]).ljust(widths[c]) for c in cols))

print(f"\nsaved → {summary_csv}")
PY

echo
echo "======================================================"
echo "  Done."
echo "  Summary CSV: $SUMMARY_CSV"
echo "======================================================"
