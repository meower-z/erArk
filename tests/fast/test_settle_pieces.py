# -*- coding: UTF-8 -*-
"""
随时间变化的数值按分钟精确结算：怎么切段，合计都与整段一样
==========================================================
- 8 分钟按 1+7、5+3、八个 1 分钟切开结算，与整段 8 分钟结算得到的疲劳、睡眠中减少的疲劳、玩家的精液、
  视觉系技艺消耗的理智、醉酒值完全相同，且等于手算的精确值（这几项没有随机抽取）。
- 精液吸收与饥饿在 5 分钟格上等于手算值（随机浮动固定为 100%）。
"""

import datetime
from collections.abc import Callable
from fractions import Fraction
from unittest import mock

from Script.Core import constant, game_type
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import needs
from Script.Modules.gameplay_resolution import working
from Script.Settle import realtime_settle
from tests.fast.base import FastTestCase

CUTS = {
    "8": [0, 8],
    "1+7": [0, 1, 8],
    "5+3": [0, 5, 8],
    "8x1": list(range(9)),
}
""" 8 分钟的四种切法：从开局时刻算起的切点分钟数 """


class SettlePiecesTest(FastTestCase):
    """分段结算的合计与精确值"""

    def behave(self, who: int, behavior_id: str, minutes: int) -> None:
        """
        角色从开局时刻起做一个行为
        Keyword arguments:
        who -- 角色id
        behavior_id -- 行为id
        minutes -- 分钟数
        """
        behavior = self.cache.character_data[who].behavior
        behavior.behavior_id = behavior_id
        behavior.start_time = game_time.now()
        behavior.duration = minutes

    def settle(self, who: int, cuts: list[int]) -> None:
        """
        从开局时刻起按切点依次结算，每段从上一个切点到下一个
        Keyword arguments:
        who -- 角色id
        cuts -- 从开局时刻算起的切点分钟数，递增
        """
        start = game_time.now()
        for since, now in zip(cuts, cuts[1:], strict=False):
            realtime_settle.character_aotu_change_value(
                who,
                start + datetime.timedelta(minutes=now),
                start + datetime.timedelta(minutes=since),
            )

    def by_cuts(
        self,
        prepare: Callable[[], game_type.Character],
        read: Callable[[game_type.Character], object],
    ) -> dict[str, object]:
        """
        每种切法在复原的世界里各结算一次，读写的 GameState 数据记在以复原后的状态为底的缓冲区里
        Keyword arguments:
        prepare -- 造出角色、摆好行为，返回要读的角色
        read -- 结算后读出的数值
        Return arguments:
        dict -- 切法到读出的数值
        """
        out = {}
        for name, cuts in CUTS.items():
            self.world.reset()
            with working.based_on(core.state()):
                chara = prepare()
                self.settle(chara.cid, cuts)
                out[name] = read(chara)
        return out

    def assert_exact(
        self, values: dict[str, object], expected: Fraction
    ) -> None:
        """
        四种切法都等于手算值
        Keyword arguments:
        values -- 切法 -> 读出的数值
        expected -- 手算的精确值
        """
        self.assertEqual(values, dict.fromkeys(CUTS, expected))

    def npc(self, behavior_id: str) -> game_type.Character:
        """
        造玩家与一名干员，干员从开局时刻起做 8 分钟的 behavior_id
        Keyword arguments:
        behavior_id -- 行为id
        Return arguments:
        Character -- 干员
        """
        self.world.chara(0, "博士")
        chara = self.world.chara(1, "干员")
        self.behave(1, behavior_id, 8)
        return chara

    def test_tired(self) -> None:
        """干员醒着等待 8 分钟：疲劳加 8 * 7/72 = 7/9"""

        def prepare() -> game_type.Character:
            chara = self.npc(constant.Behavior.WAIT)
            needs.set(chara.cid, tired=0)
            return chara

        self.assert_exact(
            self.by_cuts(prepare, lambda c: needs.of(c.cid)["tired"]),
            Fraction(7, 9),
        )

    def test_sleep_tired(self) -> None:
        """睡 8 分钟：疲劳 100 减 8/3"""

        def prepare() -> game_type.Character:
            chara = self.npc(constant.Behavior.SLEEP)
            needs.set(chara.cid, tired=100)
            return chara

        self.assert_exact(
            self.by_cuts(prepare, lambda c: needs.of(c.cid)["tired"]),
            100 - Fraction(8, 3),
        )

    def test_player_semen(self) -> None:
        """玩家等待 8 分钟：精液加 8/20"""

        def prepare() -> game_type.Character:
            player = self.world.chara(0, "博士")
            player.semen_point = 0
            player.semen_point_max = 100
            self.behave(0, constant.Behavior.WAIT, 8)
            return player

        self.assert_exact(
            self.by_cuts(prepare, lambda c: c.semen_point), Fraction(2, 5)
        )

    def test_visual_sanity(self) -> None:
        """视觉系技艺开着等待 8 分钟：理智 100 减 8/12"""

        def prepare() -> game_type.Character:
            player = self.world.chara(0, "博士")
            player.pl_ability.visual = True
            player.sanity_point = 100
            self.behave(0, constant.Behavior.WAIT, 8)
            return player

        self.assert_exact(
            self.by_cuts(prepare, lambda c: c.sanity_point),
            100 - Fraction(2, 3),
        )

    def test_drunk(self) -> None:
        """微醺（醉酒值 40）、不饿不饱、醒着等待 8 分钟：醉酒值减 8/10"""

        def prepare() -> game_type.Character:
            chara = self.npc(constant.Behavior.WAIT)
            chara.drunk_point = 40
            needs.set(chara.cid, hunger=120)
            return chara

        self.assert_exact(
            self.by_cuts(prepare, lambda c: c.drunk_point), 40 - Fraction(4, 5)
        )

    def test_absorb_and_hunger_on_grid(self) -> None:
        """体内 250 ml、饥饿 100、体力气力全满，5 分钟：吸收 max(1/5, 250/500) * 5 = 5/2 ml，饥饿加 5 * 3/4 再减 5/2"""
        chara = self.npc(constant.Behavior.WAIT)
        chara.dirty.body_semen[8][1] = 250
        self.enterContext(working.based_on(core.state()))
        needs.set(1, hunger=100)
        with mock.patch("random.randint", return_value=100):
            self.settle(1, [0, 5])
        self.assertEqual(chara.dirty.body_semen[8][1], Fraction(495, 2))
        self.assertEqual(chara.dirty.absorbed_total_semen, Fraction(5, 2))
        self.assertEqual(needs.of(1)["hunger"], Fraction(405, 4))

    def test_hunger_rate_on_grid(self) -> None:
        """体力剩一半、气力全满，5 分钟：饥饿加 5 * 3/4 * (2 - 50/100) = 45/8"""
        chara = self.npc(constant.Behavior.WAIT)
        chara.hit_point = 50
        self.enterContext(working.based_on(core.state()))
        needs.set(1, hunger=0)
        with mock.patch("random.randint", return_value=100):
            self.settle(1, [0, 5])
        self.assertEqual(needs.of(1)["hunger"], Fraction(45, 8))
