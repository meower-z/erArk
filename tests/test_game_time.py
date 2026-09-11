"""季月边界的实际分钟数。"""

from datetime import datetime
import unittest

from Script.Design.game_time import elapsed_minutes, get_sub_date


class GameTimeTests(unittest.TestCase):
    """覆盖跨季、跨年及同日的时间区间。"""

    def test_elapsed_minutes_matches_scheduled_duration(self):
        """无需参数；推进后计算分钟数应还原原始时长；无返回值。"""
        for start in (datetime(2026, 3, 31, 23, 50), datetime(2026, 6, 30, 23, 50), datetime(2026, 9, 30, 23, 50), datetime(2026, 12, 31, 23, 50), datetime(2026, 3, 1, 10)):
            with self.subTest(start=start):
                end = get_sub_date(minute=30, old_date=start)
                self.assertEqual(elapsed_minutes(start, end), 30)
                self.assertEqual(elapsed_minutes(end, start), -30)

    def test_partial_interval_across_season(self):
        """无需参数；跨季动作只计算实际剩余的部分区间；无返回值。"""
        self.assertEqual(elapsed_minutes(datetime(2026, 3, 31, 23, 55), datetime(2026, 6, 1, 0, 20)), 25)


if __name__ == "__main__":
    unittest.main()
