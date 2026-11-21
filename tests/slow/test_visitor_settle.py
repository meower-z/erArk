# -*- coding: UTF-8 -*-
"""
访客的邀请、抵达与离开
======================
开新游戏，邀请一名可招募的角色：
- 邀请的结算（handle_invite_visitor_add_adjust）给进度加上正数。进度到 100 后刷新邀请，目标作为访客抵达，
  邀请清掉，离开时刻在当前时间之后。
- 过了离开时刻，访客结算后目标不是访客，罗德岛抵达过别处的一记也清掉。
- 邀请目标已在编时，邀请的结算清掉邀请。
"""

import datetime
import importlib
from typing import Any

from tests import kernel_data, world
from tests.slow.base import SlowTestCase


def game(name: str) -> Any:
    """
    导入游戏模块
    Keyword arguments:
    name -- 模块全名
    Return arguments:
    Any -- 模块
    """
    return importlib.import_module(name)


class VisitorSettleTest(SlowTestCase):
    """邀请进度、访客的抵达与离开"""

    def test_invited_visitor_arrives_and_leaves(self) -> None:
        """
        邀请的结算加了进度。进度到 100 后目标作为访客抵达，邀请清掉。过了离开时刻，访客结算后目标不是访客，
        罗德岛抵达过别处的一记清掉
        """
        visitor = game("Script.Modules.domains.visitor")
        game_type = game("Script.Core.game_type")
        game_time = game("Script.Design.game_time")
        settle = game("Script.Settle.default").handle_invite_visitor_add_adjust
        panel = game("Script.UI.Panel.invite_visitor_panel")
        recruit_panel = game("Script.UI.Panel.recruit_panel")
        self.assertGreater(visitor.capacity(), 0, "前提：开新游戏后有客房")
        target = min(recruit_panel.find_recruitable_npc())
        player = self.cache.character_data[0]
        player.target_character_id = min(self.cache.npc_id_got - {0})
        change = game_type.CharacterStatusChange()
        with kernel_data.writing():
            visitor.set_invite(target)
            settle(0, 5, change, game_time.now())
        progress = visitor.invite()[1]
        self.assertGreater(progress, 0, "话术结算加了进度")
        with kernel_data.writing():
            visitor.set_invite(target, 100)
            panel.update_invite_visitor()
        self.assertEqual(visitor.invite(), (0, 0), "抵达后邀请清掉")
        leave = visitor.visitors()[target]
        self.assertGreater(leave, game_time.now(), "离开时刻在之后")
        world.set_clock(leave + datetime.timedelta(minutes=5))
        with kernel_data.writing():
            visitor.set_moved(True)
            panel.settle_visitor_arrivals_and_departures()
        self.assertFalse(visitor.is_visitor(target), "过了离开时刻后不是访客")
        self.assertFalse(visitor.moved(), "抵达过别处的一记清掉")

    def test_invite_cleared_when_target_joined(self) -> None:
        """邀请目标已在编时，邀请的结算清掉邀请"""
        visitor = game("Script.Modules.domains.visitor")
        game_type = game("Script.Core.game_type")
        game_time = game("Script.Design.game_time")
        settle = game("Script.Settle.default").handle_invite_visitor_add_adjust
        joined = min(self.cache.npc_id_got - {0})
        self.cache.character_data[0].target_character_id = joined
        with kernel_data.writing():
            visitor.set_invite(joined, 30)
            settle(0, 5, game_type.CharacterStatusChange(), game_time.now())
        self.assertEqual(visitor.invite(), (0, 0))
