# -*- coding: UTF-8 -*-
"""
访客的状态（base.visitor）
==========================
- 访客上限是已开放的客房数，开放一间客房后上限加 1。访客的抵达、离开与邀请见慢速层的 test_visitor_settle。
- 读档：罗德岛对象带着旧的访客属性时，值写进 GameState，属性从对象上删掉。邀请只留目标与进度。
  visitor.adopt_old_save 交回缺了或类型不符的属性个数。换id后访客与邀请目标是新id，访客的顺序不变。
"""

from types import SimpleNamespace

from Script.Config import game_config
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import facility, visitor
from Script.Modules.gameplay_resolution import working
from tests import kernel_data
from tests.fast.base import FastTestCase


class VisitorStateTest(FastTestCase):
    """访客上限与读档"""

    def setUp(self) -> None:
        """放进玩家（角色id 0），再以 core.state() 为底开一个缓冲区，测试里对 GameState 的读写都记在里面"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))

    def test_capacity_counts_open_guest_rooms(self) -> None:
        """开放一间关着的客房后，访客上限加 1"""
        closed = [
            cid
            for cid, room in game_config.config_facility_open.items()
            if "客房" in room.name and not facility.is_open(cid, False)
        ]
        before = visitor.capacity()
        kernel_data.set_room_open(closed[0])
        self.assertEqual(visitor.capacity(), before + 1)

    def test_old_island_moves_into_state(self) -> None:
        """
        旧罗德岛对象缺了移动标记时交回 1，移动标记读到 False。访客、上次来访时刻与邀请的目标和进度写进 GameState。
        属性从对象上删掉。换id后访客与邀请目标是新id，访客的顺序不变
        """
        leave = game_time.at(core.state().clock + 1440)
        last = game_time.at(core.state().clock - 1440)
        island = SimpleNamespace(
            visitor_info={7: leave, 8: leave},
            last_visitor_time=last,
            invite_visitor=[9, 55.5, 2.5],
            people_max=10,
        )
        missing = visitor.adopt_old_save({"rhodes_island": island}, 0)
        self.assertEqual(missing, 1)
        self.assertEqual(visitor.visitors(), {7: leave, 8: leave})
        self.assertEqual(visitor.last_arrival(), last)
        self.assertEqual(visitor.invite(), (9, 55.5))
        self.assertFalse(visitor.moved())
        self.assertEqual(vars(island), {"people_max": 10})
        visitor.remap({7: 70, 9: 90})
        self.assertEqual(list(visitor.visitors()), [70, 8])
        self.assertEqual(visitor.invite(), (90, 55.5))
