"""YOLO11 person detection."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from ultralytics import YOLO

from .capture import CapturedFrame
from .tracker import BoundingBox, TrackedPerson

PERSON_CLASS_ID = 0


class PersonTracker:
    def __init__(
        self,
        model_path: str,
        *,
        imgsz: int = 416,
        conf: float = 0.35,
        iou: float = 0.5,
        device: str = "cpu",
    ) -> None:
        self.model_path = model_path
        self.imgsz = imgsz
        self.conf = conf
        self.iou = iou
        self.device = device
        self._model = YOLO(model_path)

    def track_frame(self, frame: CapturedFrame) -> list[TrackedPerson]:
        results = self._model.track(
            source=frame.image,
            classes=[PERSON_CLASS_ID],
            conf=self.conf,
            iou=self.iou,
            imgsz=self.imgsz,
            device=self.device,
            persist=True,
            verbose=False,
        )
        return list(self._tracked_people_from_results(frame.index, results))

    def _tracked_people_from_results(self, frame_index: int, results: Iterable[object]) -> Iterable[TrackedPerson]:
        for result in results:
            boxes = getattr(result, "boxes", None)
            if boxes is None or len(boxes) == 0:
                continue

            xyxy = boxes.xyxy.cpu().numpy()
            confidences = boxes.conf.cpu().numpy()
            track_ids: np.ndarray | list[None]
            if boxes.id is None:
                track_ids = [None] * len(xyxy)
            else:
                track_ids = boxes.id.cpu().numpy().astype(int)

            for bbox_values, confidence, track_id in zip(xyxy, confidences, track_ids, strict=True):
                x1, y1, x2, y2 = [float(value) for value in bbox_values]
                yield TrackedPerson(
                    frame_index=frame_index,
                    track_id=None if track_id is None else int(track_id),
                    confidence=float(confidence),
                    bbox=BoundingBox(x1=x1, y1=y1, x2=x2, y2=y2),
                )
