"""Manual badge completion counter."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock


@dataclass(frozen=True)
class BadgeStatus:
    total_badges: float
    today_badges: float
    week_badges: float
    today: str
    today_started_at: str | None
    today_ended_at: str | None
    carryover_progress: float


@dataclass(frozen=True)
class DailyBadgeSummary:
    day: date
    started_at: datetime | None
    ended_at: datetime | None
    partial_progress: float
    badges: float
    first_finished_at: datetime | None
    last_finished_at: datetime | None
    average_hours_per_badge: float | None


@dataclass(frozen=True)
class WeeklyBadgeSummary:
    week_start: date
    week_end: date
    badges: float
    first_finished_at: datetime | None
    last_finished_at: datetime | None
    average_hours_per_badge: float | None


class BadgeCounter:
    fieldnames = [
        "timestamp",
        "event",
        "badges_delta",
        "total_badges",
        "partial_progress",
    ]

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()
        self._total_badges = 0.0
        self._load()

    def status(self) -> BadgeStatus:
        with self._lock:
            today = datetime.now().astimezone().date()
            today_started_at = _latest_start_on_day(self.path, today)
            today_end = _latest_end_on_day(self.path, today)
            return BadgeStatus(
                total_badges=self._total_badges,
                today_badges=self._badges_on_day(today),
                week_badges=self._badges_in_week(_week_start(today)),
                today=today.isoformat(),
                today_started_at=today_started_at.isoformat(timespec="minutes") if today_started_at else None,
                today_ended_at=today_end.timestamp.isoformat(timespec="minutes") if today_end else None,
                carryover_progress=_open_partial_progress(self.path, today=today),
            )

    def start_day(self) -> BadgeStatus:
        return self._record(event="start", badges_delta=0)

    def end_day(self, *, partial_progress: float) -> BadgeStatus:
        partial_progress = min(max(partial_progress, 0.0), 0.99)
        return self._record(event="end", badges_delta=partial_progress, partial_progress=partial_progress)

    def consume(self) -> BadgeStatus:
        today = datetime.now().astimezone().date()
        carryover_progress = _open_partial_progress(self.path, today=today)
        badges_delta = 1.0 - carryover_progress if carryover_progress > 0 else 1.0
        return self._record(event="consume", badges_delta=badges_delta)

    def undo(self) -> BadgeStatus:
        with self._lock:
            if self._total_badges <= 0:
                today = datetime.now().astimezone().date()
                today_started_at = _latest_start_on_day(self.path, today)
                today_end = _latest_end_on_day(self.path, today)
                return BadgeStatus(
                    total_badges=0.0,
                    today_badges=self._badges_on_day(today),
                    week_badges=self._badges_in_week(_week_start(today)),
                    today=today.isoformat(),
                    today_started_at=today_started_at.isoformat(timespec="minutes") if today_started_at else None,
                    today_ended_at=today_end.timestamp.isoformat(timespec="minutes") if today_end else None,
                    carryover_progress=_open_partial_progress(self.path, today=today),
                )
            undo_delta = _last_positive_badges_delta(self.path)
            if undo_delta <= 0:
                return self.status()
        return self._record(event="undo", badges_delta=-undo_delta)

    def _record(self, *, event: str, badges_delta: float, partial_progress: float = 0.0) -> BadgeStatus:
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._lock:
            self._total_badges = max(self._total_badges + badges_delta, 0)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            _ensure_schema(self.path, self.fieldnames)
            file_exists = self.path.exists() and self.path.stat().st_size > 0
            with self.path.open("a", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=self.fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(
                    {
                        "timestamp": timestamp,
                        "event": event,
                        "badges_delta": badges_delta,
                        "total_badges": self._total_badges,
                        "partial_progress": round(partial_progress, 2),
                    }
                )
            today = datetime.fromisoformat(timestamp).date()
            today_started_at = _latest_start_on_day(self.path, today)
            today_end = _latest_end_on_day(self.path, today)
            return BadgeStatus(
                total_badges=self._total_badges,
                today_badges=self._badges_on_day(today),
                week_badges=self._badges_in_week(_week_start(today)),
                today=today.isoformat(),
                today_started_at=today_started_at.isoformat(timespec="minutes") if today_started_at else None,
                today_ended_at=today_end.timestamp.isoformat(timespec="minutes") if today_end else None,
                carryover_progress=_open_partial_progress(self.path, today=today),
            )

    def _load(self) -> None:
        self._total_badges = _current_total(self.path)

    def _badges_on_day(self, day: date) -> float:
        total = 0.0
        for row in _read_badge_rows(self.path):
            if row.timestamp.date() == day:
                total += row.badges_delta
        return max(total, 0)

    def _badges_in_week(self, week_start: date) -> float:
        return _badges_in_week(_read_badge_rows(self.path), week_start)


@dataclass(frozen=True)
class _BadgeRow:
    timestamp: datetime
    event: str
    badges_delta: float
    partial_progress: float


@dataclass(frozen=True)
class _BadgeEnd:
    timestamp: datetime
    partial_progress: float


def summarize_badges(path: Path) -> tuple[list[DailyBadgeSummary], list[WeeklyBadgeSummary]]:
    rows = _read_badge_rows(path)
    consumed_at = _active_consumed_timestamps(rows)
    starts_by_day: dict[date, datetime] = {}
    ends_by_day: dict[date, _BadgeEnd] = {}
    for row in rows:
        if row.event == "start":
            starts_by_day[row.timestamp.date()] = row.timestamp
        elif row.event == "end":
            ends_by_day[row.timestamp.date()] = _BadgeEnd(row.timestamp, row.partial_progress)

    daily: dict[date, list[datetime]] = {}
    for timestamp in consumed_at:
        daily.setdefault(timestamp.date(), []).append(timestamp)

    badge_days = {row.timestamp.date() for row in rows if row.badges_delta != 0}
    days = sorted(set(daily) | set(starts_by_day) | badge_days)

    daily_summaries = [
        DailyBadgeSummary(
            day=day,
            started_at=starts_by_day.get(day),
            ended_at=ends_by_day.get(day).timestamp if day in ends_by_day else None,
            partial_progress=ends_by_day.get(day).partial_progress if day in ends_by_day else 0.0,
            badges=_badges_on_day(rows, day),
            first_finished_at=min(timestamps) if timestamps else None,
            last_finished_at=max(timestamps) if timestamps else None,
            average_hours_per_badge=_hours_per_badge(rows, day),
        )
        for day in days
        for timestamps in [daily.get(day, [])]
    ]

    weekly: dict[date, list[datetime]] = {}
    for day, timestamps in daily.items():
        week_start = _week_start(day)
        weekly.setdefault(week_start, []).extend(timestamps)
    for day in badge_days:
        week_start = _week_start(day)
        weekly.setdefault(week_start, [])

    weekly_summaries = [
        WeeklyBadgeSummary(
            week_start=week_start,
            week_end=week_start + timedelta(days=6),
            badges=_badges_in_week(rows, week_start),
            first_finished_at=min(timestamps) if timestamps else None,
            last_finished_at=max(timestamps) if timestamps else None,
            average_hours_per_badge=_hours_per_badge_in_week(rows, week_start),
        )
        for week_start, timestamps in sorted(weekly.items())
    ]
    return daily_summaries, weekly_summaries


def _read_badge_rows(path: Path) -> list[_BadgeRow]:
    if not path.exists() or path.stat().st_size == 0:
        return []

    rows: list[_BadgeRow] = []
    with path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            timestamp_text = row.get("timestamp")
            if not timestamp_text:
                continue
            badges_delta = _parse_float(row.get("badges_delta")) or 0.0
            rows.append(
                _BadgeRow(
                    timestamp=datetime.fromisoformat(timestamp_text),
                    event=row.get("event", ""),
                    badges_delta=badges_delta,
                    partial_progress=_parse_float(row.get("partial_progress")) or 0.0,
                )
            )
    return rows


def _active_consumed_timestamps(rows: list[_BadgeRow]) -> list[datetime]:
    consumed_at: list[datetime] = []
    for row in rows:
        if row.event == "consume" and row.badges_delta > 0:
            consumed_at.append(row.timestamp)
        elif row.event == "undo" and row.badges_delta < 0 and consumed_at:
            consumed_at.pop()
    return consumed_at


def _current_total(path: Path) -> float:
    last_total: float | None = None
    running_total = 0.0
    if not path.exists() or path.stat().st_size == 0:
        return 0

    with path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            badges_delta = _parse_float(row.get("badges_delta")) or 0.0
            running_total = max(running_total + badges_delta, 0)
            row_total = _parse_float(row.get("total_badges"))
            if row_total is not None:
                last_total = row_total
    return max(last_total if last_total is not None else running_total, 0)


def _latest_start_on_day(path: Path, day: date) -> datetime | None:
    starts = [row.timestamp for row in _read_badge_rows(path) if row.event == "start" and row.timestamp.date() == day]
    return max(starts) if starts else None


def _latest_end_on_day(path: Path, day: date) -> _BadgeEnd | None:
    stack: list[_BadgeRow] = []
    for row in _read_badge_rows(path):
        if row.timestamp.date() != day:
            continue
        if row.event == "end" or (row.event == "consume" and row.badges_delta > 0):
            stack.append(row)
        elif row.event == "undo" and row.badges_delta < 0 and stack:
            stack.pop()

    for row in reversed(stack):
        if row.event == "end":
            return _BadgeEnd(row.timestamp, row.partial_progress)
        if row.event == "consume":
            return None
    return None


def _open_partial_progress(path: Path, *, today: date | None = None) -> float:
    today = today or datetime.now().astimezone().date()
    stack = _positive_badge_stack(path)
    if stack and stack[-1].event == "end" and _week_start(stack[-1].timestamp.date()) == _week_start(today):
        return stack[-1].partial_progress
    return 0.0


def _last_positive_badges_delta(path: Path) -> float:
    stack = _positive_badge_stack(path)
    return stack[-1].badges_delta if stack else 0.0


def _positive_badge_stack(path: Path) -> list[_BadgeRow]:
    stack: list[_BadgeRow] = []
    for row in _read_badge_rows(path):
        if row.event in {"consume", "end"} and row.badges_delta > 0:
            stack.append(row)
        elif row.event == "undo" and row.badges_delta < 0 and stack:
            stack.pop()
    return stack


def _badges_on_day(rows: list[_BadgeRow], day: date) -> float:
    total = sum(row.badges_delta for row in rows if row.timestamp.date() == day)
    return max(total, 0.0)


def _badges_in_week(rows: list[_BadgeRow], week_start: date) -> float:
    week_end = week_start + timedelta(days=6)
    total = sum(row.badges_delta for row in rows if week_start <= row.timestamp.date() <= week_end)
    return max(total, 0.0)


def _week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _hours_per_badge(rows: list[_BadgeRow], day: date) -> float | None:
    badges = _badges_on_day(rows, day)
    if badges <= 0:
        return None
    hours = _active_hours_on_day(rows, day)
    return hours / badges if hours > 0 else None


def _hours_per_badge_in_week(rows: list[_BadgeRow], week_start: date) -> float | None:
    badges = _badges_in_week(rows, week_start)
    if badges <= 0:
        return None
    week_end = week_start + timedelta(days=6)
    hours = sum(_active_hours_on_day(rows, week_start + timedelta(days=offset)) for offset in range((week_end - week_start).days + 1))
    return hours / badges if hours > 0 else None


def _active_hours_on_day(rows: list[_BadgeRow], day: date) -> float:
    day_rows = [row for row in rows if row.timestamp.date() == day]
    start: datetime | None = None
    hours = 0.0
    last_badge_event: datetime | None = None
    for row in day_rows:
        if row.event == "start":
            start = row.timestamp
        elif row.event == "consume" and row.badges_delta > 0:
            if start is not None and row.timestamp >= start:
                hours += (row.timestamp - start).total_seconds() / 3600
            start = row.timestamp
            last_badge_event = row.timestamp
        elif row.event == "end":
            if start is not None and row.timestamp >= start and row.partial_progress > 0:
                hours += (row.timestamp - start).total_seconds() / 3600
            start = None
        elif row.event == "undo" and row.badges_delta < 0:
            last_badge_event = None

    if hours == 0 and start is not None and last_badge_event is not None and last_badge_event >= start:
        hours = (last_badge_event - start).total_seconds() / 3600
    return hours


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _parse_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _ensure_schema(path: Path, fieldnames: list[str]) -> None:
    if not path.exists() or path.stat().st_size == 0:
        return

    with path.open(newline="", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        existing_fieldnames = reader.fieldnames or []
        if existing_fieldnames == fieldnames:
            return
        rows = list(reader)

    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({fieldname: row.get(fieldname, "") for fieldname in fieldnames})
