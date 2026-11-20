# -*- coding: UTF-8 -*-
"""
选行动只读：pick_guard 的指纹看得见选择里的写入，看不见界面状态
================================================================
- 场景里的一轮选择只改界面状态（面板id、命令表）后取消（player_pick.back()）：指纹不变，没有 Chosen。
- 一轮选择定下一个普通的等待：Chosen 抛出之前指纹不变。
- 对照：一轮选择写了游戏数据后取消，指纹变了。
"""

from collections.abc import Callable

from Script.Core import constant
from Script.Modules.tk_ui import player_pick
from tests import pick_guard
from tests import world as world_module
from tests.fast.base import FastTestCase
from Script.UI.Moudle import view


class PickReadsOnlyTest(FastTestCase):
    """pick_guard.watch 记下每一轮选择是否写了缓存或内核状态"""

    def setUp(self) -> None:
        """博士与一名干员在场景里"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "干员")
        view.now_panel_id = constant.Panel.IN_SCENE

    def play(self, round_fn: Callable[[], None]) -> pick_guard.Round:
        """
        玩家跑一轮选择，记下这一轮
        Keyword arguments:
        round_fn -- 一轮选择
        Return arguments:
        Round -- 这一轮的记录
        """
        guard = pick_guard.watch()
        world_module.act(guard(round_fn))
        self.assertEqual(len(guard.rounds), 1)
        return guard.rounds[0]

    def test_back_out_of_scene_writes_nothing(self) -> None:
        """只改界面状态后取消：指纹不变，没有 Chosen"""

        def browse() -> None:
            view.now_panel_id = constant.Panel.SEE_MAP
            player_pick.back()

        got = self.play(browse)
        self.assertEqual(
            got, pick_guard.Round(constant.Panel.IN_SCENE, False, False)
        )

    def test_plain_wait_writes_nothing_before_chosen(self) -> None:
        """定下等待五分钟：Chosen 之前指纹不变"""
        got = self.play(lambda: player_pick.choose(constant.Behavior.WAIT, 5))
        self.assertEqual(
            got, pick_guard.Round(constant.Panel.IN_SCENE, True, False)
        )

    def test_a_write_is_seen(self) -> None:
        """对照：选择里改了角色的数值后取消，指纹变了"""

        def write() -> None:
            self.cache.character_data[1].hit_point += 1
            player_pick.back()

        self.assertTrue(self.play(write).changed)
