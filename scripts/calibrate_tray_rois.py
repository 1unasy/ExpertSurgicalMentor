#!/usr/bin/env python3
"""Interactively select Main/Assist tray rectangles from the fixed front camera."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=4)
    parser.add_argument("--output", type=Path, default=Path("config/object_tray_rois.json"))
    args = parser.parse_args()

    capture = cv2.VideoCapture(args.camera)
    if not capture.isOpened():
        raise RuntimeError(f"Could not open /dev/video{args.camera}")
    try:
        frame = None
        for _ in range(30):
            ok, candidate = capture.read()
            if ok:
                frame = candidate
        if frame is None:
            raise RuntimeError("Could not read a frame for ROI calibration")
    finally:
        capture.release()

    height, width = frame.shape[:2]
    main = cv2.selectROI("Select MAIN tray, then press ENTER", frame, fromCenter=False)
    cv2.destroyWindow("Select MAIN tray, then press ENTER")
    assist = cv2.selectROI("Select ASSIST tray, then press ENTER", frame, fromCenter=False)
    cv2.destroyAllWindows()
    if main[2] == 0 or main[3] == 0 or assist[2] == 0 or assist[3] == 0:
        raise RuntimeError("Both tray ROIs must be selected")

    def normalize(rect: tuple[int, int, int, int]) -> list[float]:
        x, y, w, h = rect
        return [x / width, y / height, (x + w) / width, (y + h) / height]

    config = {
        "camera_index": args.camera,
        "main_tray_xyxy_normalized": normalize(main),
        "assist_tray_xyxy_normalized": normalize(assist),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(config, indent=2) + "\n")
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
