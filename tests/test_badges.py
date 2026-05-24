import csv
from datetime import datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from takota_people_flow.badges import BadgeCounter


class BadgeCounterTest(unittest.TestCase):
    def test_end_day_without_partial_progress_records_ended_at(self) -> None:
        with TemporaryDirectory() as directory:
            counter = BadgeCounter(Path(directory) / "badge_counts.csv")

            counter.start_day()
            status = counter.end_day(partial_progress=0)

            self.assertIsNotNone(status.today_ended_at)
            self.assertEqual(status.carryover_progress, 0.0)
            self.assertEqual(status.today_badges, 0.0)

    def test_status_reports_current_week_badges(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "badge_counts.csv"
            today = datetime.now().astimezone().date()
            week_start = today - timedelta(days=today.weekday())
            previous_week = week_start - timedelta(days=1)

            with path.open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=BadgeCounter.fieldnames)
                writer.writeheader()
                writer.writerow(
                    {
                        "timestamp": datetime.combine(previous_week, datetime.min.time()).astimezone().isoformat(),
                        "event": "consume",
                        "badges_delta": 3,
                        "total_badges": 3,
                        "partial_progress": 0,
                    }
                )
                writer.writerow(
                    {
                        "timestamp": datetime.combine(week_start, datetime.min.time()).astimezone().isoformat(),
                        "event": "consume",
                        "badges_delta": 2,
                        "total_badges": 5,
                        "partial_progress": 0,
                    }
                )
                writer.writerow(
                    {
                        "timestamp": datetime.combine(today, datetime.min.time()).astimezone().isoformat(),
                        "event": "consume",
                        "badges_delta": 1,
                        "total_badges": 6,
                        "partial_progress": 0,
                    }
                )

            status = BadgeCounter(path).status()

            self.assertEqual(status.total_badges, 6.0)
            self.assertEqual(status.week_badges, 3.0)

    def test_carryover_progress_is_discarded_across_week_boundary(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "badge_counts.csv"
            sunday = datetime(2026, 5, 24, 18, 0).astimezone()
            monday = datetime(2026, 5, 25, 9, 0).astimezone()

            with path.open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=BadgeCounter.fieldnames)
                writer.writeheader()
                writer.writerow(
                    {
                        "timestamp": sunday.isoformat(),
                        "event": "end",
                        "badges_delta": 0.5,
                        "total_badges": 0.5,
                        "partial_progress": 0.5,
                    }
                )

            class FixedDateTime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return monday if tz is None else monday.astimezone(tz)

            with patch("takota_people_flow.badges.datetime", FixedDateTime):
                counter = BadgeCounter(path)
                self.assertEqual(counter.status().carryover_progress, 0.0)

                status = counter.consume()

            self.assertEqual(status.today_badges, 1.0)
            self.assertEqual(status.total_badges, 1.5)
            self.assertEqual(status.carryover_progress, 0.0)

    def test_carryover_progress_is_used_within_same_week(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "badge_counts.csv"
            thursday = datetime(2026, 5, 21, 18, 0).astimezone()
            friday = datetime(2026, 5, 22, 9, 0).astimezone()

            with path.open("w", newline="", encoding="utf-8") as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=BadgeCounter.fieldnames)
                writer.writeheader()
                writer.writerow(
                    {
                        "timestamp": thursday.isoformat(),
                        "event": "end",
                        "badges_delta": 0.5,
                        "total_badges": 0.5,
                        "partial_progress": 0.5,
                    }
                )

            class FixedDateTime(datetime):
                @classmethod
                def now(cls, tz=None):
                    return friday if tz is None else friday.astimezone(tz)

            with patch("takota_people_flow.badges.datetime", FixedDateTime):
                counter = BadgeCounter(path)
                self.assertEqual(counter.status().carryover_progress, 0.5)

                status = counter.consume()

            self.assertEqual(status.today_badges, 0.5)
            self.assertEqual(status.total_badges, 1.0)


if __name__ == "__main__":
    unittest.main()
