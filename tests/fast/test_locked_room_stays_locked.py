# -*- coding: UTF-8 -*-
"""
玩家在上锁房间内时，其他角色离开不解锁的回归测试
==============================================
博士在屋内锁门后，屋里的其他角色（例如同住的助理）走出房间，门必须仍然锁着；
玩家自己离开、或屋里没有玩家时有人离开，则照旧解锁（空房间不会一直锁着）。
断言都落在 map_handle.character_move_scene 之后场景的 close_flag 上。
"""
from tests.fast.base import FastTestCase

ROOM = ["中枢", "博士房间"]
CORRIDOR = ["中枢", "走廊"]


class LockedRoomStaysLockedTest(FastTestCase):
    """character_move_scene 只在旧场景里已没有玩家时解锁"""

    def setUp(self):
        """
        博士和两名干员都在博士房间里，门已上锁
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.world.chara(0, "博士", position=ROOM)
        self.world.chara(1, "助理", position=ROOM)
        self.world.chara(2, "干员", position=ROOM)
        self.room = self.world.scene(ROOM)
        self.room.close_flag = 1

    def test_npc_leaving_with_player_inside_keeps_lock(self):
        """玩家在屋内时，NPC 离开后房间仍上锁"""
        self.world.move(1, CORRIDOR)
        self.assertEqual(self.room.close_flag, 1)

    def test_player_leaving_unlocks(self):
        """玩家离开后房间解锁"""
        self.world.move(0, CORRIDOR)
        self.assertEqual(self.room.close_flag, 0)

    def test_npc_leaving_without_player_unlocks(self):
        """屋里只有 NPC、没有玩家时，其中一个离开后房间解锁"""
        self.world.move(0, CORRIDOR)
        self.room.close_flag = 1
        self.world.move(2, CORRIDOR)
        self.assertEqual(self.room.close_flag, 0)
        self.assertEqual(self.room.character_list, {1})
