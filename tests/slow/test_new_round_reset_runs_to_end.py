# -*- coding: UTF-8 -*-
"""
新周目在玩家选行动时重置游戏数据，重置跑到最后
==============================================
新周目面板在玩家选行动时调用 New_Round_Handle.reset_game_data。选行动中换内核状态会中止这次选择，
所以重置本身不换内核状态（时钟与角色由面板最后的 kernel_state.new_game 换上），周目数照样加一。
"""

from tests import world
from tests.slow.base import SlowTestCase


class NewRoundResetRunsToEndTest(SlowTestCase):
    """新周目的重置游戏数据"""

    def test_reset_at_pick_raises_round(self) -> None:
        """玩家选行动时重置游戏数据：周目数加一"""
        from Script.Core import cache_control
        from Script.UI.Panel import new_round

        handle = new_round.New_Round_Handle()
        before = self.cache.game_round
        world.act(handle.reset_game_data)
        self.assertEqual(cache_control.cache.game_round, before + 1)
