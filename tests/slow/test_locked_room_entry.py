# -*- coding: UTF-8 -*-
"""
博士锁门后谁能进门的回归测试（走进门的过程）
==========================================
开新游戏后：
- 博士走进会议室锁门，在「干员位置一览」里把杜宾召集到自己当前位置；杜宾走进锁着的会议室，门仍锁着。
- 博士在走廊，锁着的博士办公室和博士房间他走得进去，锁着的会议室走不进去。
各条进门判定在 tests/fast/test_locked_room_entry.py。
"""

from tests.slow.base import SlowTestCase
from tests import kernel_data
from tests.kernel_project import activity
from tests.kernel_project import identity

ROOM = ["中枢", "会议室"]
DR_ROOM = ["中枢", "博士房间"]
DR_OFFICE = ["中枢", "博士办公室"]
CORRIDOR = ["中枢", "走廊"]


class LockedRoomEntryTest(SlowTestCase):
    """被召集的干员走进博士锁着的房间；门外的博士走进自己锁着的房间"""

    def test_summoned_operator_walks_into_locked_room(self) -> None:
        """杜宾被召集后一小时内走进博士锁着的会议室，门仍锁着"""
        from Script.Core import constant

        self.walk(ROOM)
        self.instruct(constant.Instruct.DOOR_LOCK_INNER)
        room = self.world.scene(ROOM).scene_path
        scene_state = kernel_data.domain("scene_state")
        self.assertEqual(scene_state.close_flag(room), 1)
        operator = identity.of(self.npc("杜宾"))
        self.world.player.press("召集到自己当前位置", "杜宾", "返回")
        self.instruct(constant.Instruct.ALL_NPC_POSITION)
        self.show_panel()
        self.assertEqual(
            kernel_data.domain("flags").get(operator.cid, "is_follow"), 4
        )
        self.assertTrue(
            self.wait_until(
                lambda: activity.position(operator.cid) == ROOM, 60
            ),
            f"杜宾在 {activity.position(operator.cid)}",
        )
        self.assertEqual(scene_state.close_flag(room), 1)

    def test_doctor_walks_into_own_locked_rooms(self) -> None:
        """门锁着、博士在走廊：博士办公室和博士房间走得进去，会议室走不进去"""
        scene_state = kernel_data.domain("scene_state")
        for path, enters in ((DR_OFFICE, True), (DR_ROOM, True), (ROOM, False)):
            self.walk(CORRIDOR)
            # 博士离开房间时游戏会解开门锁；这里布置的是之后屋里有人把门锁上
            scene = self.world.scene(path)
            kernel_data.put(
                scene_state.set_close_flag, scene.scene_path, scene.close_type
            )
            self.walk(path)
            self.assertEqual(
                activity.position(0),
                path if enters else CORRIDOR,
                f"走向锁着的{scene.scene_name}",
            )
