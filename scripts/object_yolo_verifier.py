#!/usr/bin/env python3
"""Vote over multiple YOLO frames to locate a target object in a tray ROI."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
from ultralytics import YOLO


def contains(rect: list[float], x: float, y: float) -> bool:
    return rect[0] <= x <= rect[2] and rect[1] <= y <= rect[3]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("object", choices=("syringe", "pill"))
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--roi-config", type=Path, default=Path("config/object_tray_rois.json"))
    parser.add_argument("--confidence", type=float, default=0.5)
    parser.add_argument("--frames", type=int, default=10)
    parser.add_argument("--required", type=int, default=7)
    parser.add_argument("--camera", type=int)
    args = parser.parse_args()

    if not args.model.is_file():
        raise FileNotFoundError(f"Object YOLO model not found: {args.model}")
    config = json.loads(args.roi_config.read_text())
    camera = args.camera if args.camera is not None else int(config["camera_index"])
    if not (1 <= args.required <= args.frames):
        raise ValueError("--required must be between 1 and --frames")

    model = YOLO(str(args.model))
    names = model.names
    class_id = next((int(i) for i, name in names.items() if name == args.object), None)
    if class_id is None:
        raise ValueError(f"Class '{args.object}' not found in model names: {names}")

    capture = cv2.VideoCapture(camera)
    if not capture.isOpened():
        raise RuntimeError(f"Could not open /dev/video{camera}")
    votes: Counter[str] = Counter()
    try:
        for _ in range(args.frames):
            ok, frame = capture.read()
            if not ok:
                votes["unreadable"] += 1
                continue
            result = model.predict(frame, conf=args.confidence, verbose=False)[0]
            candidates = []
            for box in result.boxes:
                if int(box.cls.item()) == class_id:
                    candidates.append(box)
            if not candidates:
                votes["missing"] += 1
                continue
            box = max(candidates, key=lambda item: float(item.conf.item()))
            x1, y1, x2, y2 = (float(v) for v in box.xyxyn[0].tolist())
            center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
            if contains(config["main_tray_xyxy_normalized"], center_x, center_y):
                votes["main"] += 1
            elif contains(config["assist_tray_xyxy_normalized"], center_x, center_y):
                votes["assist"] += 1
            else:
                votes["outside"] += 1
            time.sleep(0.02)
    finally:
        capture.release()

    state = "unknown"
    for candidate in ("main", "assist"):
        if votes[candidate] >= args.required:
            state = candidate
            break
    print(json.dumps({"object": args.object, "state": state, "votes": dict(votes)}), file=sys.stderr)
    print(state)


if __name__ == "__main__":
    main()
