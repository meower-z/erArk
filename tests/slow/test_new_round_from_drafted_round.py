# -*- coding: UTF-8 -*-
"""
选择的草稿里开新周目：新周目建在原物上，草稿里的改动不进新周目，之后的选择里也没有写进来
================================================================================
新游戏里开启 DEBUG 模式（源石技艺面板才列出「Re:败者食尘」），罗德岛有 2 至纯源石。
- 第一次选择：源石技艺面板里花 1 至纯源石习得「博士信息素」再退出：
  一个 0 分钟的 Edit，玩家有这个素质。之后等待一次。
- 第二次选择：同一个面板里花 1 至纯源石习得「内衣透视」（草稿里的改动），
  接着「Re:败者食尘」、「是」、新周目结算面板「确定」、「醒来」。
  新周目继承博士的源石技艺：继承等级 1（它的「提高」按钮与其他继承项的文字相同，测试替玩家调好）。
新周目从开局时刻开始，周目数加一；玩家留着上一周目定下的「博士信息素」，没有草稿里的「内衣透视」；
这次选择与之后的等待里玩家没有开始 Edit。之后等待一次，时钟走过 5 分钟，玩家仍没有「内衣透视」。
"""

import importlib
from types import ModuleType
from typing import TYPE_CHECKING, Any
from unittest import mock

from tests import kernel_data
from tests.slow.base import SlowTestCase

if TYPE_CHECKING:
    from Script.Kernel import core

PURE_ORIGINIUM = 3
""" 至纯源石的资源id """
KEPT_TALENT = 304
""" 第一次选择定下的源石技艺：博士信息素（1 级，没有前置） """
DRAFTED_TALENT = 307
""" 第二次选择草稿里习得的源石技艺：内衣透视（1 级，没有前置） """


def game(name: str) -> ModuleType:
    """按模块全名 name 导入游戏模块，返回模块"""
    return importlib.import_module(name)


class NewRoundFromDraftedRoundTest(SlowTestCase):
    """源石技艺面板的草稿里开新周目"""

    def setUp(self) -> None:
        """开新游戏，开启 DEBUG 模式，罗德岛有 2 至纯源石，记下内核开始的每个行动"""
        super().setUp()
        normal_config = game("Script.Config.normal_config")
        constant = game("Script.Core.constant")
        kernel = game("Script.Kernel.core")
        normal_config.config_normal.debug = True
        self.instruct(constant.Instruct.DEBUG_MODE_ON)
        warehouse = game("Script.Modules.domains.warehouse")
        kernel_data.written(warehouse.set, PURE_ORIGINIUM, 2)
        self.started: list[core.Action] = []
        saved = kernel._bodies["kernel.StartAction"]

        def spy(act: "core.Action") -> "core.Effects":
            self.started.append(act)
            return saved(act)

        kernel._bodies["kernel.StartAction"] = spy
        self.addCleanup(kernel._bodies.__setitem__, "kernel.StartAction", saved)

    def player_starts(self) -> list[tuple[str, int]]:
        """self.started 上次清空以来玩家开始的行动：(action_id, 分钟数)"""
        return [(a.action_id, a.duration) for a in self.started if a.who == "0"]

    def talent_button(self, talent_id: int) -> str:
        """源石技艺面板「能力获得与升级」里花 1 至纯源石习得 talent_id 的按钮文字"""
        game_config = game("Script.Config.game_config")
        return f"[{game_config.config_talent[talent_id].name}]( 1 至纯源石)"

    def pick_in_arts_panel(self) -> None:
        """玩家这一次选择显示源石技艺面板（经 handle_panel 注册，在选择的草稿里运行），按钮由 self.world.player 安排"""
        from Script.UI.Moudle import view

        constant = game("Script.Core.constant")
        view.now_panel_id = constant.Panel.ORIGINIUM_ARTS
        self.show_panel()
        self.world.player.check_done()

    def wait(self) -> None:
        """像玩家在主界面点「等待五分钟」一样等待"""
        from tests.snapshot_states import instruct

        constant = game("Script.Core.constant")
        instruct(self.world, constant.Instruct.WAIT)

    def test_new_round_in_draft_runs_on_originals(self) -> None:
        """草稿里习得素质后开新周目：开局时刻、周目数加一，留着定下的素质，草稿里的素质不进新周目，之后没有 Edit"""
        kernel = game("Script.Kernel.core")
        kernel_state = game("Script.Modules.save_load.kernel_state")
        new_round = game("Script.UI.Panel.new_round")
        edits = game("Script.Modules.gameplay_resolution.edits")
        cache_control = game("Script.Core.cache_control")
        playthrough = game("Script.Modules.domains.playthrough")

        self.world.player.press(
            "[011]", self.talent_button(KEPT_TALENT), "[返回]", "[返回]"
        )
        self.pick_in_arts_panel()
        self.assertEqual(self.player_starts(), [(edits.EDIT, 0)])
        player = cache_control.cache.character_data[0]
        self.assertEqual(player.talent[KEPT_TALENT], 1, "第一次选择定下了素质")
        self.assertEqual(player.talent[DRAFTED_TALENT], 0)

        self.wait()
        before_round = playthrough.game_round()
        first = kernel_state.first_clock()
        self.assertGreater(kernel.state().clock, first, "开局后时钟已走过")
        handle_init = new_round.New_Round_Handle.__init__

        def inherit_arts(handle: Any) -> None:
            handle_init(handle)
            handle.pl_originium_arts_count = 1

        self.started.clear()
        self.world.player.press(
            "[011]",
            self.talent_button(DRAFTED_TALENT),
            "[返回]",
            "[012]",
            "[是]",
            "[确定]",
            "[醒来]",
        )
        with mock.patch.object(
            new_round.New_Round_Handle, "__init__", inherit_arts
        ):
            self.pick_in_arts_panel()
        cache = cache_control.cache
        self.assertEqual(
            playthrough.game_round(), before_round + 1, "周目数加一"
        )
        self.assertEqual(kernel.state().clock, first, "新周目从开局时刻开始")
        player = cache.character_data[0]
        self.assertEqual(
            player.talent[KEPT_TALENT], 1, "继承了上一周目定下的素质"
        )
        self.assertEqual(
            player.talent[DRAFTED_TALENT], 0, "草稿里的素质进了新周目"
        )

        self.wait()
        self.assertEqual(kernel.state().clock, first + 5, "新周目里照常等待")
        self.assertNotIn(
            edits.EDIT,
            [action_id for action_id, _ in self.player_starts()],
            f"开新周目以来玩家开始的行动：{self.player_starts()}",
        )
        self.assertEqual(
            cache_control.cache.character_data[0].talent[DRAFTED_TALENT],
            0,
            "等待后草稿里的素质写了进来",
        )
