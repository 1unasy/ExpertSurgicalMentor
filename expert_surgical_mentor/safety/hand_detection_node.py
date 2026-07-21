"""YOLO hand-only observation adapter; ROS transport is intentionally separate."""

from typing import Protocol


class HandDetector(Protocol):
    def detects_hand(self, image: object) -> bool: ...


class UltralyticsHandDetector:
    """Lazy adapter for a hand-trained Ultralytics checkpoint."""

    def __init__(self, checkpoint: str, confidence: float = 0.5) -> None:
        self._checkpoint = checkpoint
        self._confidence = confidence
        self._model = None

    def detects_hand(self, image: object) -> bool:
        if self._model is None:
            from ultralytics import YOLO

            self._model = YOLO(self._checkpoint)
        results = self._model.predict(image, conf=self._confidence, verbose=False)
        return any(len(result.boxes) > 0 for result in results)

