#!/usr/bin/env python3
"""Collect hand images for the YOLO safety detector.

Single-camera capture tool. On the target robot PC there are two cameras
(front + wrist); on a MacBook or any dev machine you'll usually only have one.
This script uses one camera and cycles through the 200-image plan defined in
docs/hand_safety_dataset.md. Wrist-view conditions (B1/B2/N4) can be:
  - collected later on the robot with the actual wrist camera, or
  - simulated now by mounting/holding the single camera close to the workspace.

Usage:
    python3 ./src/scripts/hand_yolo/collect_hand_images.py --cam 0 --out datasets/hand/raw

Probe available indices first:
    python3 ./src/scripts/hand_yolo/collect_hand_images.py --list-cameras

Runtime keys (preview window focused):
    SPACE  capture one frame for the active condition
    a      toggle auto-capture (default 1.0s interval, overridable via --auto-interval)
    n      pick next unfinished condition
    p      pick previous condition
    1..9   jump directly to conditions 1..9
    0      jump to condition 10
    l      list conditions and remaining counts in the terminal
    s      mark current condition as satisfied (skip)
    q / ESC quit
"""

import argparse
import platform
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import cv2


@dataclass
class Condition:
    code: str
    mount: str  # "front" | "wrist"  (informational: which robot mount this simulates)
    description: str
    target: int
    saved: int = 0
    dir: Path = field(default=Path("."))

    @property
    def done(self) -> bool:
        return self.saved >= self.target


PLAN: list[Condition] = [
    Condition("A1_front_entering",      "front", "Hand entering frame from side",          20),
    Condition("A2_front_near_tray",     "front", "Hand near AssistTray (receive pose)",    20),
    Condition("A3_front_holding_tool",  "front", "Hand holding a tool while moving",       20),
    Condition("A4_front_over_zone",     "front", "Hand over MainTray/PracticeZone",        20),
    Condition("B1_wrist_close",         "wrist", "Wrist mount: hand entering close-up",    25),
    Condition("B2_wrist_with_robot",    "wrist", "Wrist mount: hand near tool with robot", 25),
    Condition("N1_front_bg_empty",      "front", "No hand, empty scene",                   15),
    Condition("N2_front_bg_tools",      "front", "No hand, tools/trays only",              15),
    Condition("N3_front_bg_robot",      "front", "No hand, OMX-F arm visible (varied)",    20),
    Condition("N4_wrist_bg_robot",      "wrist", "Wrist mount: robot/gripper only",        20),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Collect hand images (single camera) for YOLO safety detector.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("--cam", type=int, default=0, help="OpenCV camera index (default: 0).")
    p.add_argument("--backend", default="auto",
                   choices=["auto", "avfoundation", "v4l2", "any"],
                   help="OpenCV VideoIO backend. On macOS 'avfoundation' avoids Orbbec/OBSENSOR "
                        "interference. 'auto' picks AVFoundation on macOS, V4L2 on Linux.")
    p.add_argument("--width", type=int, default=640)
    p.add_argument("--height", type=int, default=480)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--out", type=Path, default=Path("datasets/hand/raw"),
                   help="Root output directory. Per-condition subfolders are created.")
    p.add_argument("--auto-interval", type=float, default=1.0,
                   help="Seconds between auto-capture frames (default: 1.0).")
    p.add_argument("--fourcc", default="",
                   help="Optional OpenCV FourCC (e.g. MJPG, YUYV). Empty = camera default.")
    p.add_argument("--list-cameras", action="store_true",
                   help="Probe indices 0..7 with the selected backend, print result, then exit.")
    p.add_argument("--mirror", action="store_true",
                   help="Horizontally flip preview and saved frames (selfie-style).")
    return p.parse_args()


def resolve_backend(name: str) -> int:
    if name == "auto":
        return cv2.CAP_AVFOUNDATION if platform.system() == "Darwin" else cv2.CAP_V4L2
    return {
        "avfoundation": cv2.CAP_AVFOUNDATION,
        "v4l2": cv2.CAP_V4L2,
        "any": cv2.CAP_ANY,
    }[name]


def open_camera(index: int, backend: int, width: int, height: int, fps: int, fourcc: str) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        raise RuntimeError(f"Camera index {index} could not be opened (backend={backend}).")
    if fourcc:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    return cap


def probe_cameras(backend: int) -> None:
    print(f"Probing camera indices 0..7 with backend={backend} ...")
    for i in range(8):
        cap = cv2.VideoCapture(i, backend)
        ok = cap.isOpened()
        frame_ok = False
        wh = ""
        if ok:
            r, frame = cap.read()
            if r and frame is not None:
                frame_ok = True
                wh = f"  {frame.shape[1]}x{frame.shape[0]}"
        cap.release()
        status = "OK" if frame_ok else ("opened-but-no-frame" if ok else "none")
        print(f"  index {i}: {status}{wh}")


def preload_saved_counts(plan: list[Condition], out_root: Path) -> None:
    for cond in plan:
        cond.dir = out_root / cond.code
        cond.dir.mkdir(parents=True, exist_ok=True)
        cond.saved = sum(1 for _ in cond.dir.glob("*.jpg"))


def print_plan(plan: list[Condition]) -> None:
    print()
    print(f"{'#':>2}  {'code':<26} {'mount':<6} {'saved/target':<14} description")
    print("-" * 90)
    for i, c in enumerate(plan, 1):
        mark = "OK" if c.done else "  "
        print(f"{i:>2}  {c.code:<26} {c.mount:<6} {c.saved:>4}/{c.target:<9} {mark} {c.description}")
    total_saved = sum(c.saved for c in plan)
    total_target = sum(c.target for c in plan)
    print("-" * 90)
    print(f"    total: {total_saved}/{total_target}")
    print()


def draw_hud(frame, cond: Condition, auto: bool) -> None:
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 76), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.55, frame, 0.45, 0, frame)

    line1 = f"[{cond.code}] {cond.description}"
    line2 = f"mount={cond.mount}  saved={cond.saved}/{cond.target}  auto={'ON' if auto else 'off'}"
    line3 = "SPACE=snap  a=auto  n/p=nav  1-9,0=jump  l=list  s=skip  q=quit"
    cv2.putText(frame, line1, (10, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
    cv2.putText(frame, line2, (10, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 200), 1, cv2.LINE_AA)
    cv2.putText(frame, line3, (10, 66), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (200, 200, 200), 1, cv2.LINE_AA)

    if cond.done:
        cv2.putText(frame, "CONDITION COMPLETE - press n", (10, h - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2, cv2.LINE_AA)


def next_unfinished_index(plan: list[Condition], start: int) -> int:
    n = len(plan)
    for offset in range(1, n + 1):
        i = (start + offset) % n
        if not plan[i].done:
            return i
    return start


def save_frame(frame, cond: Condition) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    seq = cond.saved + 1
    path = cond.dir / f"{cond.code}_{ts}_{seq:04d}.jpg"
    ok = cv2.imwrite(str(path), frame)
    if not ok:
        raise RuntimeError(f"Failed to write {path}")
    cond.saved += 1
    return path


def main() -> int:
    args = parse_args()
    backend = resolve_backend(args.backend)

    if args.list_cameras:
        probe_cameras(backend)
        return 0

    preload_saved_counts(PLAN, args.out)
    print_plan(PLAN)

    cap = open_camera(args.cam, backend, args.width, args.height, args.fps, args.fourcc)
    win = f"hand-collect (cam {args.cam})"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)

    idx = next((i for i, c in enumerate(PLAN) if not c.done), 0)
    auto = False
    last_auto_capture = 0.0

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                print("Camera read failed. Exiting.", file=sys.stderr)
                return 1
            if args.mirror:
                frame = cv2.flip(frame, 1)

            cond = PLAN[idx]
            hud = frame.copy()
            draw_hud(hud, cond, auto)
            cv2.imshow(win, hud)

            if auto and not cond.done:
                now = time.time()
                if now - last_auto_capture >= args.auto_interval:
                    path = save_frame(frame, cond)
                    print(f"[auto] {path.name}  ({cond.saved}/{cond.target})")
                    last_auto_capture = now
                    if cond.done:
                        auto = False
                        print(f"-> {cond.code} complete.")

            key = cv2.waitKey(1) & 0xFF
            if key == 255:
                continue

            if key in (ord("q"), 27):
                break
            elif key == ord(" "):
                if cond.done:
                    print(f"{cond.code} already complete. Press n for next.")
                else:
                    path = save_frame(frame, cond)
                    print(f"[snap] {path.name}  ({cond.saved}/{cond.target})")
            elif key == ord("a"):
                auto = not auto
                last_auto_capture = 0.0
                print(f"auto = {'ON' if auto else 'off'}")
            elif key == ord("n"):
                idx = next_unfinished_index(PLAN, idx)
                auto = False
                print(f"-> {PLAN[idx].code}  ({PLAN[idx].mount}) : {PLAN[idx].description}")
            elif key == ord("p"):
                idx = (idx - 1) % len(PLAN)
                auto = False
                print(f"-> {PLAN[idx].code}  ({PLAN[idx].mount})")
            elif key == ord("s"):
                PLAN[idx].saved = PLAN[idx].target
                print(f"marked {PLAN[idx].code} as satisfied.")
            elif key == ord("l"):
                print_plan(PLAN)
            elif ord("1") <= key <= ord("9"):
                jump = key - ord("1")
                if jump < len(PLAN):
                    idx = jump
                    auto = False
                    print(f"-> {PLAN[idx].code}  ({PLAN[idx].mount})")
            elif key == ord("0"):
                if len(PLAN) >= 10:
                    idx = 9
                    auto = False
                    print(f"-> {PLAN[idx].code}  ({PLAN[idx].mount})")
    finally:
        cap.release()
        cv2.destroyAllWindows()

    print_plan(PLAN)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
