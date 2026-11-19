# -*- coding: UTF-8 -*-
"""
0 分钟的编辑不收尾
==================
内核载入游戏的插件表，只有玩家在场。玩家第一次选择在草稿里改了自己的名字而没有定下行动（一个 0 分钟的 Edit），
第二次选择等待 5 分钟。收尾（character_behavior.end_action）换成记录调用的替身。
- Edit 开始之后，玩家在同一分钟里再选，中间没有收尾；Edit 改的名字在缓存里。
- 5 分钟的等待在结束的那一分钟收尾一次，之后玩家再选。
"""

from unittest import mock

from Script.Core import cache_control
from Script.Design import character_behavior, update
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.gameplay_resolution import actions, time_hooks
from Script.Modules.tk_ui import player_pick
from tests.fast.base import FastTestCase

LOADED_FIRST = update
""" 先于 Script.Modules 导入的 update """


class ScriptDone(Exception):
    """玩家的选择用完了"""


class EditNoWrapUpTest(FastTestCase):
    """0 分钟的 Edit 没有结束函数，行为有"""

    def setUp(self) -> None:
        """玩家在场，内核载入插件表，选择与收尾换成记录调用的替身"""
        super().setUp()
        self.world.chara(0, "博士")
        core.load(load_order.LOAD_ORDER)
        core.reset_state(actions.state_from_cache())
        self.log: list[tuple[str, int]] = []
        choices = [self.edit, self.wait]

        def chooser() -> None:
            self.log.append(("pick", core.state().clock))
            if not choices:
                raise ScriptDone
            choices.pop(0)()

        def end_action(who: int) -> None:
            self.log.append((f"end {who}", core.state().clock))

        for target, name, fn in (
            (player_pick, "chooser", chooser),
            (character_behavior, "end_action", end_action),
            (character_behavior, "player_after_end", lambda: None),
            (time_hooks, "tick_one", lambda who: None),
        ):
            self.enterContext(mock.patch.object(target, name, fn))

    def edit(self) -> None:
        """草稿里把玩家的名字改成「草稿」，不定下行动"""
        with player_pick.drafting("test"):
            cache_control.cache.character_data[0].name = "草稿"

    def wait(self) -> None:
        """等待 5 分钟"""
        player_pick.choose("wait", 5)

    def test_edit_skips_wrap_up_and_behavior_wraps_up(self) -> None:
        """Edit 后同一分钟再选、不收尾；等待在第 5 分钟收尾一次，然后再选"""
        with self.assertRaises(ScriptDone):
            for _ in range(200):
                core.step()
        first = self.log[0][1]
        self.assertEqual(
            self.log,
            [
                ("pick", first),
                ("pick", first),
                ("end 0", first + 5),
                ("pick", first + 5),
            ],
        )
        self.assertEqual(cache_control.cache.character_data[0].name, "草稿")
