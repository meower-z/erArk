# -*- coding: UTF-8 -*-
"""
分数数值通过游戏状态自检与读档修复
================================
随时间结算的连续数值（num.Num）可以是 Fraction。系统设置 14 打开时，读档先跑读档修复，回合开始再跑自检：
两者都要把 n + 1/3 当作合法数值，与整数 n 判得一样，修复也不能把分数改掉。
"""

from fractions import Fraction

from Script.Core import save_handle
from Script.Kernel import core
from Script.Modules.domains import h_meters, needs, status
from Script.Modules.gameplay_resolution import working
from Script.Test.Static_Check.check_registry import get_all_checks
from tests.fast.base import FastTestCase
from Script.Config import normal_config
from tests import kernel_data

THIRD = Fraction(1, 3)
""" 加到每个数值上的零头 """
H_METERS = {"eja": 100, "semen": 10}
""" h.meters 里的连续数值与测试用的整数部分，都在各自量程内 """
NEEDS = {
    "tired": 48,
    "urine": 100,
    "hunger": 38,
    "hit": 500,
    "mana": 500,
    "sanity": 50,
    "sleep": 66,
}
""" body.needs 里的数值与测试用的整数部分，都在各自量程内 """


class ExactStatsPassChecksTest(FastTestCase):
    """自检与读档修复接受分数数值"""

    def setUp(self) -> None:
        """
        玩家与一名干员，数值上限足够大。GameState 数据的读写记在 working.based_on(core.state()) 开的缓冲区里
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.charas = [
            self.world.chara(0, "博士"),
            self.world.chara(1, "干员"),
        ]
        self.enterContext(working.based_on(core.state()))
        for chara in self.charas:
            kernel_data.set_needs(
                chara.cid, hit_max=1000, mana_max=1000, sanity_max=100
            )
            h_meters.set(chara.cid, semen_max=100)

    def set_stats(self, extra: int | Fraction) -> None:
        """
        把每个连续数值与生理需求设为整数部分加 extra，状态值 0 号设为 1 加 extra
        Keyword arguments:
        extra -- 零头（0 时数值都是 int）
        """
        for chara in self.charas:
            h_meters.set(
                chara.cid, **{k: v + extra for k, v in H_METERS.items()}
            )
            needs.set(chara.cid, **{k: v + extra for k, v in NEEDS.items()})
            kernel_data.put(status.set, chara.cid, 0, 1 + extra)

    def failures(self) -> set[tuple[str, str]]:
        """
        跑全部自检
        Keyword arguments:
        无
        Return arguments:
        set -- (检查编号, 涉及的角色id) 的集合
        """
        found = set()
        for check_id, (_name, run) in get_all_checks().items():
            for failure in run():
                found.add((check_id, str(failure.involved_character_ids)))
        return found

    def test_checks_judge_fractions_like_whole_numbers(self) -> None:
        """数值带 1/3 的零头时，自检报告的失败与整数时相同"""
        self.set_stats(0)
        whole = self.failures()
        self.set_stats(THIRD)
        self.assertEqual(self.failures(), whole)

    def test_load_repair_keeps_fractions(self) -> None:
        """读档修复不改带零头的数值"""
        normal_config.system_setting.base_setting[14] = 1
        self.set_stats(THIRD)
        save_handle.repair_installed()
        for chara in self.charas:
            with self.subTest(chara=chara.cid):
                meters = h_meters.of(chara.cid).items()
                self.assertEqual(
                    {k: v for k, v in meters if k in H_METERS},
                    {k: v + THIRD for k, v in H_METERS.items()},
                )
                stats = needs.of(chara.cid).items()
                self.assertEqual(
                    {k: v for k, v in stats if k in NEEDS},
                    {k: v + THIRD for k, v in NEEDS.items()},
                )
                self.assertEqual(status.of(chara.cid)[0], 1 + THIRD)
