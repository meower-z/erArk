# -*- coding: UTF-8 -*-
"""
游戏里的主面板循环：点下有时长的指令后，场景面板在这一行动结算之后才再次等玩家输入
==================================================================================
开新游戏后像游戏一样一步步跑内核（core.step），主面板在玩家的选择（player_pick.chooser）里。
玩家在场景面板里点两次「等待五分钟」：场景面板每次等输入时，游戏时间比上一次多 5 分钟，
第三次等输入时测试没有安排按钮，UnplannedInput 结束这次运行。
"""

import datetime
import importlib
from unittest import mock

from tests.slow.base import SlowTestCase
from tests.world import UnplannedInput

WAITS = 2
""" 点「等待五分钟」的次数 """


class SceneWaitsForActionSettleTest(SlowTestCase):
    """场景面板在玩家的行动结算之后才往下走、再次等输入"""

    def test_each_wait_settles_before_next_input(self) -> None:
        """每次场景面板等输入时，游戏时间比上一次多 5 分钟；面板经玩家的选择入口跑"""
        from Script.UI.Moudle import view

        constant = importlib.import_module("Script.Core.constant")
        flow_handle = importlib.import_module("Script.Core.flow_handle")
        game_time = importlib.import_module("Script.Design.game_time")
        core = importlib.import_module("Script.Kernel.core")
        player_pick = importlib.import_module(
            "Script.Modules.tk_ui.player_pick"
        )

        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
        asked_at: list[datetime.datetime] = []
        order_deal = flow_handle.order_deal
        chooser = player_pick.chooser
        picks: list[None] = []

        def counted_chooser() -> None:
            """玩家的选择入口：记一次，照常跑一轮面板"""
            picks.append(None)
            chooser()

        def record_scene_ask(*args: object, **kwargs: object) -> object:
            """场景面板等玩家选择时记下游戏时间（「按任意键继续」不算），再交给 PlayerInput"""
            choice = (
                args[2]
                if len(args) > 2
                else kwargs.get("donot_return_null_str", True)
            )
            if choice and view.now_panel_id == constant.Panel.IN_SCENE:
                asked_at.append(game_time.now())
            return order_deal(*args, **kwargs)

        self.world.player.press(*["等待五分钟"] * WAITS)
        start = game_time.now()
        with mock.patch.object(
            flow_handle, "order_deal", record_scene_ask
        ), mock.patch.object(
            player_pick, "chooser", counted_chooser
        ), self.assertRaises(
            UnplannedInput
        ):
            while True:
                core.step()
        self.world.player.check_done()

        expected = [
            game_time.get_sub_date(minute=5 * i, old_date=start)
            for i in range(WAITS + 1)
        ]
        self.assertEqual(
            asked_at[: WAITS + 1],
            expected,
            "场景面板每次等输入时，上一个「等待五分钟」已经结算",
        )
        self.assertGreater(len(picks), 0, "面板经玩家的选择入口跑")
