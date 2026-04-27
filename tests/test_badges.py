from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

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


if __name__ == "__main__":
    unittest.main()
