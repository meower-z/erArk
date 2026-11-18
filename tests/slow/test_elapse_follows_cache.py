# -*- coding: UTF-8 -*-
"""
时间流逝跟上缓存的回归测试
==========================
内核只在行动结束处停表。干员在缓存里的行为比它在内核里的行动先结束时（别人的结算改短了它、睡觉被截到起床的时刻），
时钟要停在缓存里的结束时刻，并让这个干员在那一刻来选下一个行动；时钟跨过 0 点时，新一天的结算跑一次。

开新游戏后，用 gameplay_resolution 的时间钩子单独跑内核：博士与一名干员在内核里都还要做 60 分钟，
缓存里干员的行为只剩 10 分钟。第一个来选行动的角色与当时的时钟就是要看的结果，由本文件的选择钩子记下后停住内核。
"""

import datetime
from types import MappingProxyType
import sys

from tests.slow.base import SlowTestCase

OPERATOR = "杜宾"
""" 测试用的干员 """


class Picked(Exception):
    """内核让某个角色选下一个行动：记下角色与时钟后停住内核"""

    def __init__(self, who: str, clock: int) -> None:
        """
        Keyword arguments:
        who -- 来选行动的角色键
        clock -- 当时的时钟
        """
        super().__init__(who, clock)
        self.who = who
        self.clock = clock


class ElapseFollowsCacheTest(SlowTestCase):
    """时钟停在缓存里干员该结束的时刻；跨过 0 点时跑新一天的结算"""

    def _run(self, clock: int, npc_id: int, length: int) -> Picked:
        """
        从 clock 起跑内核：博士与干员在内核里都做 length 分钟，到第一个角色来选行动为止
        Keyword arguments:
        clock -- 起始时钟
        npc_id -- 干员的角色id
        length -- 内核里两人行动的分钟数
        Return arguments:
        Picked -- 第一个来选行动的角色与当时的时钟
        """
        from Script.Kernel import core
        from Script.Modules.gameplay_resolution import actions, time_hooks

        def stop_at_pick(
            result: tuple[core.Action, core.Effects],
        ) -> tuple[core.Action, core.Effects]:
            """
            第一个来选行动的角色：停住内核
            Keyword arguments:
            result -- 内层选出的行动与效果
            Return arguments:
            tuple -- 不会返回
            """
            core.discard_all_changes(result[1])
            raise Picked(result[0].who, core.state().clock)

        core.output_hook(core.pick_next_action)(stop_at_pick)
        characters = {
            who: core.Character(
                core.Action(who, actions.behave.name, None, clock, length),
                MappingProxyType({}),
            )
            for who in (actions.PLAYER, str(npc_id))
        }
        game = core.GameState(
            clock, MappingProxyType(characters), MappingProxyType({})
        )
        with self.assertRaises(Picked) as caught:
            core.run(game, (time_hooks, sys.modules[__name__]))
        return caught.exception

    def test_clock_stops_at_cached_end(self) -> None:
        """干员在缓存里 10 分钟后结束：时钟停在那一刻，先来选行动的是她"""
        from Script.Core import constant
        from Script.Modules.gameplay_resolution import actions

        npc_id = self.npc(OPERATOR)
        behavior = self.cache.character_data[npc_id].behavior
        behavior.behavior_id = constant.Behavior.WAIT
        behavior.start_time = self.cache.game_time
        behavior.duration = 10
        clock = actions.minutes(self.cache.game_time)
        picked = self._run(clock, npc_id, 60)
        self.assertEqual(
            (picked.who, picked.clock - clock),
            (str(npc_id), 10),
            "她在缓存里的结束时刻来选行动",
        )

    def test_new_day_once_past_midnight(self) -> None:
        """博士的行动从 23:50 做到次日 0:10：时钟过 0 点时新一天的结算跑了，跑完缓存记下的是新的一天"""
        from Script.Core import constant
        from Script.Modules.gameplay_resolution import actions

        npc_id = self.npc(OPERATOR)
        start = self.cache.game_time.replace(hour=23, minute=50)
        end = start + datetime.timedelta(minutes=20)
        self.cache.pre_game_time = start
        self.cache.game_time = end
        behavior = self.cache.character_data[npc_id].behavior
        behavior.behavior_id = constant.Behavior.WAIT
        behavior.start_time = start
        behavior.duration = 20
        clock = actions.minutes(start)
        picked = self._run(clock, npc_id, 20)
        self.assertEqual(picked.clock - clock, 20)
        self.assertEqual(
            self.cache.pre_game_time.date(),
            end.date(),
            "新一天的结算跑过",
        )
