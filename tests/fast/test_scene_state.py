# -*- coding: UTF-8 -*-
"""
场景运行态在内核状态里（scene.closed）与在场角色计算
====================================================
- 门锁表只存已关门场景，解锁后移除条目，未在表内的场景读出 0。
- 门锁表经 kernel_state 编解码往返后不变，写出的存档版本等于 upgrade.CURRENT。
- scene_state.occupants 按角色 id 升序返回玩家 0 与在编干员，每次返回新列表。
- 同一写入缓冲区内修改位置或移出名册后，occupants 立即反映最新状态，传入旧 GameState 时仍读旧状态。
- 玩家在已锁房间内时其他角色离开不解锁，玩家离开后解锁。
- adopt_old_save 从旧存档缓存字典移除 scene_data，仅导入存在于 constant.scene_data 且 close_flag 非 0 的门锁。
- adopt_old_save 在缓存不含 scene_data 时同样清理 scene.closed，统一异系统分隔符为 os.sep 并剔除不存在的场景。
- snapshot.build_snapshot 的 scene_data 只收录有角色或已关门的场景，并附升序 character_list 与 close_flag。
"""

import os

from Script.Core import constant, game_type
from Script.Kernel import core
from Script.Modules.domains import activity, roster, scene_state
from Script.Modules.save_load import kernel_state, upgrade
from Script.Test.Static_Check import snapshot
from tests import kernel_data
from tests.fast.base import FastTestCase

ROOM = ["中枢", "博士房间"]
ROOM_PATH = os.sep.join(ROOM)
CORRIDOR = ["中枢", "走廊"]
CORRIDOR_PATH = os.sep.join(CORRIDOR)


class SceneStateTest(FastTestCase):
    """场景门锁读写、编解码、在场角色计算、离开解锁与旧存档导入测试"""

    def setUp(self) -> None:
        """放入博士与三名干员，分别置于走廊与博士房间"""
        super().setUp()
        self.world.chara(0, "博士", position=CORRIDOR)
        self.world.chara(3, "干员丙", position=ROOM)
        self.world.chara(1, "干员甲", position=ROOM)
        self.world.chara(2, "干员乙", position=CORRIDOR)

    def test_close_flag_keeps_only_locked_rooms(self) -> None:
        """门锁表只保留已关门场景，未关门场景读出 0，写入 0 后移除条目"""
        kernel_data.put(scene_state.set_close_flag, ROOM_PATH, 1)
        self.assertEqual(scene_state.closed(), {ROOM_PATH: 1})
        self.assertEqual(scene_state.close_flag(CORRIDOR_PATH), 0)
        kernel_data.put(scene_state.set_close_flag, ROOM_PATH, 0)
        self.assertEqual(scene_state.closed(), {})

    def test_close_flag_survives_codec(self) -> None:
        """门锁状态经 kernel_state 编解码往返后不变，写出的存档版本等于 upgrade.CURRENT"""
        kernel_data.put(scene_state.set_close_flag, ROOM_PATH, 2)
        encoded = kernel_state.encode(core.state(), "tok")
        self.assertEqual(encoded["version"], upgrade.CURRENT)
        decoded = kernel_state.decode(encoded, tagged=True)
        self.assertEqual(scene_state.close_flag(ROOM_PATH, decoded), 2)

    def test_occupants_ascending(self) -> None:
        """occupants 按角色 id 升序返回场景内的玩家与在编干员"""
        self.assertEqual(scene_state.occupants(ROOM_PATH), [1, 3])
        self.assertEqual(scene_state.occupants(CORRIDOR_PATH), [0, 2])

    def test_occupants_follow_writes_in_one_buffer(self) -> None:
        """同一缓冲区内修改位置与移出名册后 occupants 立即更新，传入旧 GameState 时仍读旧状态"""
        before = core.state()
        with kernel_data.writing():
            self.assertEqual(scene_state.occupants(ROOM_PATH), [1, 3])
            activity.set_position(2, ROOM)
            self.assertEqual(scene_state.occupants(ROOM_PATH), [1, 2, 3])
            roster.remove(3)
            self.assertEqual(scene_state.occupants(ROOM_PATH), [1, 2])
            self.assertEqual(scene_state.occupants(ROOM_PATH, before), [1, 3])
        self.assertEqual(scene_state.occupants(ROOM_PATH), [1, 2])
        self.assertEqual(scene_state.occupants(CORRIDOR_PATH), [0])

    def test_occupants_returns_a_copy(self) -> None:
        """修改 occupants 返回的列表不影响后续读取结果"""
        scene_state.occupants(ROOM_PATH).append(9)
        self.assertEqual(scene_state.occupants(ROOM_PATH), [1, 3])

    def test_player_leaving_unlocks(self) -> None:
        """玩家在已锁房间内时干员离开保持锁门，玩家离开后房间解锁"""
        self.world.move(0, ROOM)
        kernel_data.put(scene_state.set_close_flag, ROOM_PATH, 1)
        self.world.move(1, CORRIDOR)
        self.assertEqual(scene_state.close_flag(ROOM_PATH), 1)
        self.world.move(0, CORRIDOR)
        self.assertEqual(scene_state.closed(), {})
        self.assertEqual(scene_state.occupants(ROOM_PATH), [3])

    def test_adopt_old_save_imports_flags(self) -> None:
        """adopt_old_save 移除 scene_data，导入现有场景的非 0 门锁并跳过 0 值与不存在的路径"""
        room, corridor, gone = (
            game_type.Scene(),
            game_type.Scene(),
            game_type.Scene(),
        )
        vars(room)["close_flag"] = 1
        vars(corridor)["close_flag"] = 0
        vars(gone)["close_flag"] = 2
        loaded = {
            "scene_data": {
                ROOM_PATH: room,
                CORRIDOR_PATH: corridor,
                "旧区块\\旧房间": gone,
            }
        }
        self.assertNotIn("旧区块\\旧房间", constant.scene_data)
        with kernel_data.writing():
            scene_state.adopt_old_save(loaded)
        self.assertNotIn("scene_data", loaded)
        self.assertEqual(scene_state.closed(), {ROOM_PATH: 1})

    def test_adopt_old_save_tidies_stored_flags(self) -> None:
        """adopt_old_save 在缓存不含 scene_data 时仍规范化已存门锁的异系统分隔符并剔除不存在的场景"""
        foreign = "\\" if os.sep == "/" else "/"
        kernel_data.put(scene_state.set_close_flag, foreign.join(ROOM), 1)
        kernel_data.put(
            scene_state.set_close_flag, "旧区块" + os.sep + "旧房间", 2
        )
        with kernel_data.writing():
            scene_state.adopt_old_save({})
        self.assertEqual(scene_state.closed(), {ROOM_PATH: 1})

    def test_snapshot_lists_occupied_and_locked_scenes(self) -> None:
        """build_snapshot 的 scene_data 只列出有角色或已关门的场景，并附升序 character_list 与 close_flag"""
        kernel_data.put(scene_state.set_close_flag, ROOM_PATH, 1)
        self.assertEqual(
            snapshot.build_snapshot(self.cache)["scene_data"],
            {
                ROOM_PATH: {"character_list": [1, 3], "close_flag": 1},
                CORRIDOR_PATH: {"character_list": [0, 2], "close_flag": 0},
            },
        )
