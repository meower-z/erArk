# -*- coding: UTF-8 -*-
"""
醉酒等级按醉酒等级表的上限分档
==============================
一名没有酒量素质的干员，醉酒值（body.needs 的 drunk）取 0、40、各档上限与上限加一。
drunk_sex_common.get_drunk_level 给出的等级是醉酒等级表（Drunk_Level.csv）里上限不小于醉酒值的第一档。
"""

from Script.System.Sex_System import drunk_sex_common
from tests import kernel_data
from tests.fast.base import FastTestCase

BANDS = [
    (0, 0),
    (20, 0),
    (21, 1),
    (40, 1),
    (50, 1),
    (51, 2),
    (80, 2),
    (81, 3),
    (100, 3),
]
""" (醉酒值, 等级)。醉酒等级表 0 到 3 档的上限是 20、50、80、100 """


class DrunkLevelBandsTest(FastTestCase):
    """醉酒值落在醉酒等级表的哪一档"""

    def setUp(self) -> None:
        """博士与一名没有酒量素质的干员（角色id 1）"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "干员")

    def test_level_follows_table_limits(self) -> None:
        """BANDS 里每个醉酒值得到的等级与等级表的分档相同"""
        got = []
        for value, _level in BANDS:
            kernel_data.set_needs(1, drunk=value)
            got.append((value, drunk_sex_common.get_drunk_level(1)[0]))
        self.assertEqual(got, BANDS)
