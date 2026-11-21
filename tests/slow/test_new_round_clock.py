# -*- coding: UTF-8 -*-
"""
新周目在开局时刻建起，之后照常选行动
====================================
新游戏里等待 12 次（时钟走过开局一小时），玩家选行动时开新周目，按下「醒来」。
新周目重建的时间戳都是新周目的开局时刻：罗德岛的访客来访时间，每个角色的行动信息（交谈、移动、醒来、入睡）。
周目数加一，内核里有博士以外的角色，时钟在开局时刻。之后等待一次，时钟走过 5 分钟。
"""

import importlib
from types import ModuleType

from tests.slow.base import SlowTestCase


def game(name: str) -> ModuleType:
    """按模块全名 name 导入游戏模块，返回模块"""
    return importlib.import_module(name)


class NewRoundClockTest(SlowTestCase):
    """新周目的时间戳与内核时钟都是新周目的开局时刻"""

    def wait(self, times: int = 1) -> None:
        """
        像玩家在主界面点「等待五分钟」一样等待
        Keyword arguments:
        times -- 次数
        """
        from tests.snapshot_states import instruct

        constant = game("Script.Core.constant")
        for _ in range(times):
            instruct(self.world, constant.Instruct.WAIT)

    def test_new_round_stamps_first_clock(self) -> None:
        """玩家选行动时开新周目：时间戳、内核时钟都在开局时刻，周目数加一，之后照常等待"""
        from tests import world

        core = game("Script.Kernel.core")
        game_time = game("Script.Design.game_time")
        kernel_state = game("Script.Modules.save_load.kernel_state")
        new_round = game("Script.UI.Panel.new_round")
        cache_control = game("Script.Core.cache_control")
        playthrough = game("Script.Modules.domains.playthrough")
        first = kernel_state.first_clock()
        self.wait(12)
        self.assertGreater(core.state().clock, first, "等待后时钟已过开局")
        before_round = playthrough.game_round()
        handle = new_round.New_Round_Handle()
        self.world.player.press("醒来")
        world.act(handle.start_new_round)
        self.world.player.check_done()
        cache = cache_control.cache
        self.assertEqual(playthrough.game_round(), before_round + 1)
        game_state = core.state()
        self.assertEqual(game_state.clock, first, "新周目从开局时刻开始")
        self.assertGreater(len(game_state.characters), 1, "内核里有干员")
        visitor = game("Script.Modules.domains.visitor")
        self.assertEqual(game_time.minutes(visitor.last_arrival()), first)
        action_info = game("Script.Modules.domains.action_info")
        for chara_id in cache.character_data:
            stamps = {
                "talk_time": action_info.get(chara_id, "talk_time"),
                "last_move_time": action_info.get(chara_id, "last_move_time"),
                "wake_time": action_info.get(chara_id, "wake_time"),
                "sleep_time": action_info.get(chara_id, "sleep_time"),
            }
            for name, stamp in stamps.items():
                self.assertEqual(
                    game_time.minutes(stamp),
                    first,
                    f"角色 {chara_id} 的 {name} 是 {stamp}",
                )
        self.wait()
        self.assertEqual(core.state().clock, first + 5, "新周目里照常等待")
