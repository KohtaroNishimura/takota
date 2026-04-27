"""Saved event analysis helpers."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class IntervalSummary:
    start: datetime
    end: datetime
    left_to_right: int = 0
    right_to_left: int = 0
    stopped: int = 0
    total_events: int = 0
    unique_tracks: int = 0
    peak_active_tracks: int = 0


@dataclass
class _MutableIntervalSummary:
    start: datetime
    end: datetime
    left_to_right: int = 0
    right_to_left: int = 0
    stopped: int = 0
    total_events: int = 0
    peak_active_tracks: int = 0
    track_ids: set[int] | None = None

    def __post_init__(self) -> None:
        if self.track_ids is None:
            self.track_ids = set()

    def freeze(self) -> IntervalSummary:
        return IntervalSummary(
            start=self.start,
            end=self.end,
            left_to_right=self.left_to_right,
            right_to_left=self.right_to_left,
            stopped=self.stopped,
            total_events=self.total_events,
            unique_tracks=len(self.track_ids or set()),
            peak_active_tracks=self.peak_active_tracks,
        )


def summarize_csv(path: Path, *, interval_minutes: int = 30) -> list[IntervalSummary]:
    """Summarize saved people-flow events into fixed-width time intervals."""
    if interval_minutes <= 0 or 60 % interval_minutes != 0:
        raise ValueError("interval_minutes must be a positive divisor of 60.")

    summaries: dict[datetime, _MutableIntervalSummary] = {}
    with path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            timestamp_text = row.get("timestamp", "")
            if not timestamp_text:
                continue

            timestamp = datetime.fromisoformat(timestamp_text)
            start = floor_datetime(timestamp, interval_minutes=interval_minutes)
            summary = summaries.setdefault(
                start,
                _MutableIntervalSummary(
                    start=start,
                    end=start + timedelta(minutes=interval_minutes),
                ),
            )
            summary.total_events += 1

            direction = row.get("direction", "")
            event = row.get("event", "")
            if direction == "left_to_right":
                summary.left_to_right += 1
            elif direction == "right_to_left":
                summary.right_to_left += 1
            elif event == "stopped" or direction == "stopped":
                summary.stopped += 1

            track_id = parse_int(row.get("track_id", ""))
            if track_id is not None and summary.track_ids is not None:
                summary.track_ids.add(track_id)

            active_tracks = parse_int(row.get("active_tracks", ""))
            if active_tracks is not None:
                summary.peak_active_tracks = max(summary.peak_active_tracks, active_tracks)

    return [summaries[start].freeze() for start in sorted(summaries)]


def floor_datetime(value: datetime, *, interval_minutes: int) -> datetime:
    minute = value.minute - (value.minute % interval_minutes)
    return value.replace(minute=minute, second=0, microsecond=0)


def parse_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None
