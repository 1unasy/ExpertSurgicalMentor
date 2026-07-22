#!/usr/bin/env python3
"""Interactively select arbitrary Main/Assist tray polygons."""

import argparse
import json
from pathlib import Path

import cv2


def select_polygon(
    window: str,
    frame,
    color: tuple[int, int, int],
    min_points: int,
    max_points: int,
) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    canvas = frame.copy()

    def redraw() -> None:
        nonlocal canvas
        canvas = frame.copy()
        for point in points:
            cv2.circle(canvas, point, 6, color, -1)
        for index in range(1, len(points)):
            cv2.line(canvas, points[index - 1], points[index], color, 2)
        if len(points) >= min_points:
            cv2.line(canvas, points[-1], points[0], color, 2)
        cv2.putText(
            canvas,
            f"{window}: click {min_points}-{max_points} corners clockwise "
            "(right click=undo, R=reset, ENTER=save)",
            (10, 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            color,
            1,
            cv2.LINE_AA,
        )

    def on_mouse(event: int, x: int, y: int, _flags: int, _param: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < max_points:
            points.append((x, y))
            redraw()
        elif event == cv2.EVENT_RBUTTONDOWN and points:
            points.pop()
            redraw()

    cv2.namedWindow(window)
    cv2.setMouseCallback(window, on_mouse)
    redraw()
    while True:
        cv2.imshow(window, canvas)
        key = cv2.waitKey(20) & 0xFF
        if key in (10, 13) and len(points) >= min_points:
            break
        if key in (ord("r"), ord("R")):
            points.clear()
            redraw()
        if key == 27:
            points.clear()
            break
    cv2.destroyWindow(window)
    if not (min_points <= len(points) <= max_points):
        raise RuntimeError(
            f"Select between {min_points} and {max_points} corners for {window}"
        )
    return points


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", type=int, default=4)
    parser.add_argument("--output", type=Path, default=Path("config/object_tray_rois.json"))
    parser.add_argument("--min-points", type=int, default=3)
    parser.add_argument("--max-points", type=int, default=8)
    args = parser.parse_args()
    if args.min_points < 3 or args.max_points < args.min_points:
        raise ValueError("Require 3 <= --min-points <= --max-points")

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
    main = select_polygon(
        "MAIN tray", frame, (0, 255, 255), args.min_points, args.max_points
    )
    assist = select_polygon(
        "ASSIST tray", frame, (255, 255, 0), args.min_points, args.max_points
    )
    cv2.destroyAllWindows()

    def normalize(points: list[tuple[int, int]]) -> list[list[float]]:
        return [[round(x / width, 6), round(y / height, 6)] for x, y in points]

    config = {
        "camera_index": args.camera,
        "roi_format": "polygon_v1",
        "main_tray_polygon_normalized": normalize(main),
        "assist_tray_polygon_normalized": normalize(assist),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(config, indent=2) + "\n")
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
