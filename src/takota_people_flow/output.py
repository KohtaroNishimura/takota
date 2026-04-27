"""Event output writers."""

from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path
from types import TracebackType

from .events import FlowEvent


class CsvEventWriter:
    fieldnames = [
        "timestamp",
        "frame_index",
        "track_id",
        "event",
        "direction",
        "center_x",
        "center_y",
        "dwell_time_sec",
        "bbox_x1",
        "bbox_y1",
        "bbox_x2",
        "bbox_y2",
        "confidence",
        "active_tracks",
    ]

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file = None
        self._writer: csv.DictWriter | None = None

    def __enter__(self) -> "CsvEventWriter":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        file_exists = self.path.exists() and self.path.stat().st_size > 0
        self._file = self.path.open("a", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=self.fieldnames)
        if not file_exists:
            self._writer.writeheader()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._file is not None:
            self._file.close()
            self._file = None
            self._writer = None

    def write_events(self, events: list[FlowEvent]) -> None:
        if self._writer is None:
            raise RuntimeError("CsvEventWriter is not open.")
        for event in events:
            row = asdict(event)
            row["center_x"] = round(row["center_x"], 2)
            row["center_y"] = round(row["center_y"], 2)
            row["dwell_time_sec"] = round(row["dwell_time_sec"], 3)
            row["bbox_x1"] = round(row["bbox_x1"], 2)
            row["bbox_y1"] = round(row["bbox_y1"], 2)
            row["bbox_x2"] = round(row["bbox_x2"], 2)
            row["bbox_y2"] = round(row["bbox_y2"], 2)
            row["confidence"] = round(row["confidence"], 4)
            self._writer.writerow(row)
