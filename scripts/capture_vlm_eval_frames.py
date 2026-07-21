#!/usr/bin/env python3
"""Capture one three-frame VLM evaluation trial and append its manifest rows."""

import argparse
import importlib
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from expert_surgical_mentor.vlm.evaluation import STATE_LABELS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", choices=STATE_LABELS, required=True)
    parser.add_argument("--trial", type=int, choices=range(1, 6), required=True)
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--output-dir", type=Path, default=Path("data/vlm_eval/syringe_pill"))
    args = parser.parse_args()
    cv2 = importlib.import_module("cv2")
    images_dir = args.output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(args.camera)
    if not capture.isOpened():
        raise RuntimeError("카메라를 열 수 없습니다.")
    main_tools, assist_tools = STATE_LABELS[args.state]
    split = "development" if args.trial <= 3 else "locked_validation"
    rows = []
    try:
        for sequence in range(1, 4):
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError("카메라 프레임을 읽지 못했습니다.")
            captured_at_ns = time.time_ns()
            name = f"{args.state}_trial{args.trial:02d}_frame{sequence}.jpg"
            cv2.imwrite(str(images_dir / name), frame)
            rows.append({
                "image_path": f"images/{name}", "state_id": args.state,
                "trial_id": args.trial, "split": split,
                "frame_sequence": sequence, "captured_at_ns": captured_at_ns,
                "main_tray_tools": list(main_tools), "assist_tray_tools": list(assist_tools),
            })
            time.sleep(0.15)
    finally:
        capture.release()
    with (args.output_dir / "manifest.jsonl").open("a", encoding="utf-8") as manifest:
        for row in rows:
            manifest.write(json.dumps(row, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
