# -*- coding: UTF-8 -*-
"""
玩家在上锁房间内时，其他角色离开不解锁的回归测试
==============================================
博士在屋内锁门后，屋里的其他角色（例如同住的助理）走出房间，门必须仍然锁着；
玩家自己离开、或屋里没有玩家时有人离开，则照旧解锁（空房间不会一直锁着）。
断言都落在 map_handle.character_move_scene 之后场景的 close_flag 上。

在仓库根目录运行：python tools/tests/map/test_locked_room_stays_locked.py
退出码：0 全部断言通过；1 有断言失败；2 未捕获异常。
"""
import sys

sys.path.insert(0, "tools/tests")
from headless_boot import boot, check, finish, mute_ui, new_chara  # noqa: E402

cache = boot()
mute_ui()

from Script.Design import map_handle  # noqa: E402

ROOM = ["中枢", "博士房间"]
CORRIDOR = ["中枢", "走廊"]
room = cache.scene_data[map_handle.get_map_system_path_str_for_list(ROOM)]

new_chara(0, "博士", position=ROOM)
new_chara(1, "助理", position=ROOM)
new_chara(2, "干员", position=ROOM)

# ==== 1. 玩家与 NPC 都在锁着的房间里，NPC 走出去 ====
room.close_flag = 1
map_handle.character_move_scene(ROOM, CORRIDOR, 1)
check("玩家在屋内时，NPC 离开后房间仍上锁", room.close_flag == 1, f"close_flag={room.close_flag}")

# ==== 2. 玩家自己走出去 ====
map_handle.character_move_scene(ROOM, CORRIDOR, 0)
check("玩家离开后房间解锁", room.close_flag == 0, f"close_flag={room.close_flag}")

# ==== 3. 屋里只有两个 NPC、没有玩家，其中一个走出去 ====
map_handle.character_move_scene(CORRIDOR, ROOM, 1)
room.close_flag = 1
map_handle.character_move_scene(ROOM, CORRIDOR, 2)
check("屋里没有玩家时，NPC 离开后房间解锁", room.close_flag == 0, f"close_flag={room.close_flag} character_list={room.character_list}")

finish()
