#!/usr/bin/env python3
"""Vote over multiple YOLO frames to locate a target object in a tray ROI."""

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


def contains_polygon(polygon: list[list[float]], x: float, y: float) -> bool:
    """Return whether a normalized point is inside or on a polygon."""
    contour = np.array(polygon, dtype=np.float32).reshape((-1, 1, 2))
    return cv2.pointPolygonTest(contour, (x, y), False) >= 0


def tray_polygon(config: dict, name: str) -> list[list[float]]:
    """Read polygon ROIs while remaining compatible with the old xyxy format."""
    polygon_key = f"{name}_tray_polygon_normalized"
    if polygon_key in config:
        polygon = config[polygon_key]
        if len(polygon) < 3:
            raise ValueError(f"{polygon_key} must contain at least three points")
        return polygon

    rect = config[f"{name}_tray_xyxy_normalized"]
    x1, y1, x2, y2 = rect
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def draw_polygon(frame, polygon: list[list[float]], label: str, color: tuple[int, int, int]) -> None:
    height, width = frame.shape[:2]
    points = np.array(
        [[round(x * width), round(y * height)] for x, y in polygon], dtype=np.int32
    ).reshape((-1, 1, 2))
    cv2.polylines(frame, [points], True, color, 3, cv2.LINE_AA)
    anchor = tuple(points[0][0])
    cv2.putText(frame, label, anchor, cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2, cv2.LINE_AA)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("object", choices=("syringe", "pill"))
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--roi-config", type=Path, default=Path("config/object_tray_rois.json"))
    parser.add_argument("--confidence", type=float, default=0.5)
    parser.add_argument("--frames", type=int, default=10)
    parser.add_argument("--required", type=int, default=7)
    parser.add_argument("--camera", type=int)
    parser.add_argument("--preview-output", type=Path)
    args = parser.parse_args()

    if not args.model.is_file():
        raise FileNotFoundError(f"Object YOLO model not found: {args.model}")
    config = json.loads(args.roi_config.read_text())
    main_polygon = tray_polygon(config, "main")
    assist_polygon = tray_polygon(config, "assist")
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
    current_streak_state: str | None = None
    current_streak = 0
    max_streaks: Counter[str] = Counter()
    confirmed_state: str | None = None
    preview_frame = None
    preview_score = -1.0
    try:
        for _ in range(args.frames):
            ok, frame = capture.read()
            if not ok:
                votes["unreadable"] += 1
                current_streak_state = None
                current_streak = 0
                continue
            result = model.predict(frame, conf=args.confidence, verbose=False)[0]
            annotated = frame.copy()
            draw_polygon(annotated, main_polygon, "MAIN", (0, 255, 255))
            draw_polygon(annotated, assist_polygon, "ASSIST", (255, 255, 0))
            candidates = []
            for box in result.boxes:
                if int(box.cls.item()) == class_id:
                    candidates.append(box)
            if not candidates:
                votes["missing"] += 1
                current_streak_state = None
                current_streak = 0
                cv2.putText(
                    annotated, f"{args.object}: NOT DETECTED", (12, 55),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA,
                )
                if preview_frame is None:
                    preview_frame = annotated
                continue
            box = max(candidates, key=lambda item: float(item.conf.item()))
            confidence = float(box.conf.item())
            x1, y1, x2, y2 = (float(v) for v in box.xyxyn[0].tolist())
            center_x, center_y = (x1 + x2) / 2, (y1 + y2) / 2
            if contains_polygon(main_polygon, center_x, center_y):
                votes["main"] += 1
                location = "MAIN"
            elif contains_polygon(assist_polygon, center_x, center_y):
                votes["assist"] += 1
                location = "ASSIST"
            else:
                votes["outside"] += 1
                location = "OUTSIDE"
            location_key = location.lower()
            if location_key in {"main", "assist"}:
                if current_streak_state == location_key:
                    current_streak += 1
                else:
                    current_streak_state = location_key
                    current_streak = 1
                max_streaks[location_key] = max(max_streaks[location_key], current_streak)
                if current_streak >= args.required:
                    confirmed_state = location_key
            else:
                current_streak_state = None
                current_streak = 0
            px1, py1, px2, py2 = (round(v) for v in box.xyxy[0].tolist())
            color = (0, 220, 0) if location in {"MAIN", "ASSIST"} else (0, 0, 255)
            cv2.rectangle(annotated, (px1, py1), (px2, py2), color, 3)
            cv2.putText(
                annotated, f"{args.object} {confidence:.2f} / {location}",
                (px1, max(25, py1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                color, 2, cv2.LINE_AA,
            )
            if confidence > preview_score:
                preview_score = confidence
                preview_frame = annotated
            time.sleep(0.02)
    finally:
        capture.release()

    state = confirmed_state or "unknown"
    if args.preview_output is not None and preview_frame is not None:
        args.preview_output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.preview_output.with_suffix(".tmp.jpg")
        if not cv2.imwrite(str(temporary), preview_frame):
            raise RuntimeError(f"Could not write preview image: {temporary}")
        temporary.replace(args.preview_output)
    print(
        json.dumps(
            {
                "object": args.object,
                "state": state,
                "votes": dict(votes),
                "max_consecutive": dict(max_streaks),
                "required_consecutive": args.required,
            }
        ),
        file=sys.stderr,
    )
    print(state)


if __name__ == "__main__":
    main()
