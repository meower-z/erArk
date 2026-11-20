# -*- coding: UTF-8 -*-
"""
取消整个行动：面板在任意一层调 player_pick.back()，这一轮不定下行动
==================================================================
- back() 抛出的 Back 越过面板里的 except Exception，回到玩家的选择循环，再跑一轮。
- 取消的那一轮没有行动开始，时钟不走，core.state() 不变；下一轮从场景面板开始。
"""

from collections.abc import Callable
from types import MappingProxyType
from unittest import mock

from Script.Core import constant, py_cmd
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.gameplay_resolution import actions, intent
from Script.Modules.tk_ui import player_hook, player_pick
from tests.fast.base import FastTestCase
from Script.UI.Moudle import view

_started: list[tuple[str, int]] = []
""" 开始过的测试行动：(行为id, 开始的分钟) """


@core.action(intent.KIND_PREFIX + "PickBackProbe")
def _probe(act: core.Action) -> core.Effects:
    """测试行动的开始：记下行为id与开始的分钟"""
    assert isinstance(act.action_data, MappingProxyType)
    _started.append((str(act.action_data["behavior_id"]), act.start))
    return ()


class PickBackTest(FastTestCase):
    """back() 回到选择循环，不定下行动"""

    def setUp(self) -> None:
        """只载入 tk_ui 的两个文件，换上空的事件表，清空记录"""
        super().setUp()
        self.enterContext(mock.patch.object(core, "_events", []))
        self.enterContext(
            mock.patch.object(
                load_order, "LOAD_ORDER", (player_pick, player_hook)
            )
        )
        self.enterContext(mock.patch.object(py_cmd, "clr_cmd"))
        self.enterContext(mock.patch.object(py_cmd, "focus_cmd"))
        _started.clear()

    def test_back_returns_to_the_loop(self) -> None:
        """子菜单深处 back()：面板的 except Exception 拦不住，下一轮在场景面板，看到的时钟与状态和这一轮开始时一样"""
        seen: list[tuple[int, int, core.GameState]] = []

        def look() -> None:
            seen.append((core.state().clock, core.instant()[1], core.state()))

        def sub_menu() -> None:
            look()
            view.now_panel_id = constant.Panel.MAKE_FOOD
            try:
                player_pick.back()
            except Exception:
                self.fail("Back 被面板的 except Exception 拦下")

        def scene() -> None:
            panels.append(view.now_panel_id)
            look()

        panels: list[int] = []
        rounds: list[Callable[[], None]] = [
            sub_menu,
            scene,
            lambda: player_pick.choose("a", 5, kind="PickBackProbe"),
        ]

        def chooser() -> None:
            if not rounds:
                raise player_pick.LeftGame
            rounds.pop(0)()

        self.enterContext(mock.patch.object(player_pick, "chooser", chooser))
        who = actions.PLAYER
        idle = core.Action(who, core.idle.name, None, 0, 0)
        characters = {who: core.Character(idle, MappingProxyType({}))}
        core.load(load_order.LOAD_ORDER)
        core.reset_state(
            core.GameState(
                0, MappingProxyType(characters), MappingProxyType({})
            )
        )
        before = core.state()
        core.step()
        self.assertEqual(_started, [("a", 0)])
        self.assertEqual(len(seen), 2)
        self.assertEqual(seen[0], seen[1])
        self.assertIs(seen[1][2], before)
        self.assertEqual(panels, [constant.Panel.IN_SCENE])
