# -*- coding: UTF-8 -*-
"""
跟随博士的干员进入满员房间的回归测试（走进门的过程）
==================================================
开新游戏后招募 10 名干员：新干员都在博士办公室原地等待 30 分钟，办公室（Room_Area 0，10 人满员）满员。
杜宾在走廊被博士邀请同行，进入智能跟随；博士走进满员的办公室，杜宾跟着走进去。
各条满员判定在 tests/fast/test_follower_enters_full_room.py。
"""
from tests.slow.base import SlowTestCase

DR_OFFICE = ["中枢", "博士办公室"]
CORRIDOR = ["中枢", "走廊"]
RECRUITS = 10
""" 招募的干员数：正好填满博士办公室 """


class FollowerEntersFullRoomTest(SlowTestCase):
    """智能跟随的干员跟着博士走进满员的房间"""

    def test_follower_enters_full_office(self):
        """博士走进满员的博士办公室，智能跟随的杜宾也进去了"""
        from Script.Core import constant
        from Script.Design import character_handle, map_handle

        self.walk(CORRIDOR)
        recruits = sorted(cid for cid in self.cache.character_data if cid and cid not in self.cache.npc_id_got)[:RECRUITS]
        for cid in recruits:
            character_handle.get_new_character(cid)
        office_str = map_handle.get_map_system_path_str_for_list(DR_OFFICE)
        self.assertTrue(map_handle.judge_scene_is_full(office_str))
        follower_id = self.npc("杜宾")
        follower = self.cache.character_data[follower_id]
        self.world.move(follower_id, CORRIDOR)
        # 在场景里点选杜宾，再点「邀请同行」
        self.cache.character_data[0].target_character_id = follower_id
        self.instruct(constant.Instruct.FOLLOW)
        self.assertEqual(follower.sp_flag.is_follow, 1)
        self.walk(DR_OFFICE)
        self.assertEqual(self.cache.character_data[0].position, DR_OFFICE)
        self.assertEqual(follower.position, DR_OFFICE)
        self.assertEqual(sum(self.cache.character_data[cid].position == DR_OFFICE for cid in recruits), RECRUITS)
