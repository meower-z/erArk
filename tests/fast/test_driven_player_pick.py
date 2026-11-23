# -*- coding: UTF-8 -*-
"""
界面由内核驱动：玩家的选择在 core.step() 里跑，面板经 player_pick.choose 交回行动
================================================================================
start_flow.start_frame 是唯一的循环：标题与建角色面板在内核外显示，进了游戏就一步一步推进内核。
玩家的 PickNextAction 钩子反复跑一轮选择，直到面板抛出 Chosen；面板回到标题时抛出 LeftGame，
穿过 core.step() 回到 start_frame。
"""

from collections.abc import Callable
from types import MappingProxyType
from unittest import mock

from Script.Core import constant, py_cmd
from Script.Design import start_flow
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.gameplay_resolution import actions, intent
from Script.Modules.tk_ui import player_hook, player_pick
from tests.fast.base import FastTestCase
from Script.UI.Moudle import view

_started: list[tuple[str, int, int]] = []
""" 开始过的测试行动：(行为id, 开始的分钟, 时长) """


@core.action(intent.KIND_PREFIX + "DrivenPickProbe")
def _probe(act: core.Action) -> core.Effects:
    """测试行动的开始：记下行为id、开始的分钟与时长"""
    assert isinstance(act.action_data, MappingProxyType)
    _started.append(
        (str(act.action_data["behavior_id"]), act.start, act.duration)
    )
    return ()


def _player_only(clock: int) -> core.GameState:
    """
    只有玩家的 GameState：玩家的 Idle 在 clock 结束
    Keyword arguments:
    clock -- 时钟
    Return arguments:
    GameState -- 新的 GameState
    """
    who = actions.PLAYER
    idle = core.Action(who, core.idle.name, None, clock, 0)
    characters = {who: core.Character(idle, MappingProxyType({}))}
    return core.GameState(
        clock, MappingProxyType(characters), MappingProxyType({})
    )


_GAME_PANEL = -7031
""" 测试用的游戏面板id，不与 constant.Panel 重复 """


def _choose(behavior_id: str, minutes: int) -> None:
    """面板定下一个测试行动"""
    player_pick.choose(behavior_id, minutes, kind="DrivenPickProbe")


class DrivenPlayerPick(FastTestCase):
    """玩家的选择在内核的一步里跑"""

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
        _started.clear()

    def script(self, rounds: list[Callable[[], None]]) -> list[int]:
        """
        把选择换成脚本：每次跑 rounds 的下一个，跑完后抛 LeftGame
        Keyword arguments:
        rounds -- 每一轮选择
        Return arguments:
        list -- 跑过的轮数，只有一个元素
        """
        calls = [0]

        def chooser() -> None:
            calls[0] += 1
            if not rounds:
                raise player_pick.LeftGame
            rounds.pop(0)()

        self.enterContext(mock.patch.object(player_pick, "chooser", chooser))
        return calls

    def test_scripted_chooser_plays_three_turns(self) -> None:
        """脚本选三个行动：每个在前一个结束的那一分钟开始，空的一轮之后再问一轮"""

        def swallowing() -> None:
            try:
                _choose("b", 5)
            except Exception:
                self.fail("Chosen 被面板的 except Exception 拦下")

        calls = self.script(
            [
                lambda: _choose("a", 10),
                lambda: None,
                swallowing,
                lambda: _choose("c", 1),
            ]
        )
        core.load(load_order.LOAD_ORDER)
        core.reset_state(_player_only(0))
        with self.assertRaises(player_pick.LeftGame):
            while True:
                core.step()
        self.assertEqual(_started, [("a", 0, 10), ("b", 10, 5), ("c", 15, 1)])
        self.assertEqual(calls[0], 5, "4 轮脚本，加 1 轮抛 LeftGame")
        self.assertEqual(core.state().clock, 16, "LeftGame 的那一步不改状态")
        player = core.state().characters[actions.PLAYER].action
        self.assertEqual((player.start, player.duration), (15, 1))

    def test_start_frame_runs_panels_and_steps(self) -> None:
        """
        start_frame：标题面板开始新游戏，游戏面板经内核定下三个行动后回到标题，标题面板随后结束主流程
        """

        class FlowDone(Exception):
            """结束 start_frame 的循环"""

        titles: list[int] = []
        game_rounds = [("a", 30), ("b", 5), ("c", 1)]

        def title() -> None:
            titles.append(core.state().clock)
            if len(titles) > 1:
                raise FlowDone
            core.reset_state(_player_only(60))
            view.now_panel_id = _GAME_PANEL

        def in_game() -> None:
            if not game_rounds:
                view.now_panel_id = constant.Panel.TITLE
                return
            _choose(*game_rounds.pop(0))

        self.enterContext(
            mock.patch.dict(
                constant.panel_data,
                {constant.Panel.TITLE: title, _GAME_PANEL: in_game},
            )
        )
        view.now_panel_id = constant.Panel.TITLE
        with self.assertRaises(FlowDone):
            start_flow.start_frame()
        self.assertEqual(_started, [("a", 60, 30), ("b", 90, 5), ("c", 95, 1)])
        self.assertEqual(titles[1], 96, "回到标题时内核停在玩家的选择之前")
