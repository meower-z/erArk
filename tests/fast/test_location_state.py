# -*- coding: UTF-8 -*-
"""
罗德岛所在位置（base.location）
===============================
- 没有 base.location 时，罗德岛在国家 location.START，停着。
- 抵达判断（navigation_service.judge_arrive）时，抵达时刻未到的移动不变。抵达时刻已到的移动结束：所在国家换成目标，
  移动清掉，访客的移动标记记为 True。按所在国家判断的前提随之变化。
- 读档：所在国家取旧位置列表的第一项。旧移动列表的目标不为 0 且第三项是时间时记为移动。属性从对象上删掉。
  location.adopt_old_save 交回缺了或类型不符的属性个数。
"""

import datetime
from types import SimpleNamespace

from Script.Design import game_time
from Script.Design.handle_premise import handle_premise_place
from Script.Kernel import core
from Script.Modules.domains import location, visitor
from Script.Modules.gameplay_resolution import navigation_service, working
from tests.fast.base import FastTestCase

AEGIR = 1
""" handle_in_aegir 判断的国家id """


class LocationStateTest(FastTestCase):
    """移动与抵达、按所在国家判断的前提、读档"""

    def setUp(self) -> None:
        """放进玩家（角色id 0），再以 core.state() 为底开一个缓冲区，测试里对 GameState 的读写都记在里面"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))

    def test_move_arrives_when_due(self) -> None:
        """
        抵达时刻未到时抵达判断不改移动。抵达时刻已到时所在国家换成 AEGIR，移动清掉，访客的移动标记为 True，
        handle_in_aegir 成立
        """
        self.assertEqual(location.country(), location.START)
        self.assertFalse(handle_premise_place.handle_in_aegir(0))
        later = game_time.now() + datetime.timedelta(days=1)
        location.set_move(AEGIR, later)
        navigation_service.judge_arrive()
        self.assertEqual(location.move(), (AEGIR, later))
        location.set_move(AEGIR, game_time.now())
        navigation_service.judge_arrive()
        self.assertEqual(location.country(), AEGIR)
        self.assertIsNone(location.move())
        self.assertTrue(visitor.moved())
        self.assertTrue(handle_premise_place.handle_in_aegir(0))

    def test_old_island_moves_into_state(self) -> None:
        """旧罗德岛对象的位置与移动写进 GameState，属性从对象上删掉。两个属性都在时交回 0"""
        at = game_time.at(core.state().clock + 600)
        island = SimpleNamespace(
            current_location=[AEGIR, 1701],
            move_target_and_time=[5, 0, at],
            people_max=10,
        )
        self.assertEqual(
            location.adopt_old_save({"rhodes_island": island}, 0), 0
        )
        self.assertEqual(location.country(), AEGIR)
        self.assertEqual(location.move(), (5, at))
        self.assertEqual(vars(island), {"people_max": 10})

    def test_old_island_without_move(self) -> None:
        """旧移动列表为 [0, 0, 0] 时罗德岛停着。缺了位置属性时在国家 location.START，交回 1"""
        island = SimpleNamespace(move_target_and_time=[0, 0, 0])
        self.assertEqual(
            location.adopt_old_save({"rhodes_island": island}, 0), 1
        )
        self.assertEqual(location.country(), location.START)
        self.assertIsNone(location.move())
