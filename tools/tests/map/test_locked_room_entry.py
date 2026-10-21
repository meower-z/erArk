# -*- coding: UTF-8 -*-
"""
博士锁门后谁能进门的回归测试
============================
博士在屋内锁门后：
- 被博士「召集到自己当前位置」（is_follow=4）的角色，不论是不是助理，都能进博士所在的锁门房间；别的锁门房间照旧进不了。
- 自己找来的助理（送饭、早晚安问候等走「移动到玩家位置」）与其他干员一样被挡在门外；
  她只能自己进锁着的博士房间（Dr_room）和博士办公室（Dr_Office）。
- 智能跟随或强制跟随博士的助理照旧能进博士所在的锁门房间；没被召集的非助理干员跟不跟随都照旧被挡。
断言落在 map_handle.judge_scene_accessible 的返回值上，
以及「移动到玩家位置」状态机给角色选出的行动上。

在仓库根目录运行：python tools/tests/map/test_locked_room_entry.py
退出码：0 全部断言通过；1 有断言失败；2 未捕获异常。
"""
import sys

sys.path.insert(0, "tools/tests")
from headless_boot import boot, check, finish, mute_ui, new_chara  # noqa: E402

cache = boot()
mute_ui()

from Script.Config import game_config  # noqa: E402
from Script.Core import constant  # noqa: E402
from Script.Design import attr_calculation, map_handle  # noqa: E402

ROOM = ["中枢", "会议室"]
OTHER_ROOM = ["中枢", "茶水间"]
DR_ROOM = ["中枢", "博士房间"]
DR_OFFICE = ["中枢", "博士办公室"]
CORRIDOR = ["中枢", "走廊"]
ROOM_STR = map_handle.get_map_system_path_str_for_list(ROOM)
OTHER_ROOM_STR = map_handle.get_map_system_path_str_for_list(OTHER_ROOM)
DR_ROOM_STR = map_handle.get_map_system_path_str_for_list(DR_ROOM)
DR_OFFICE_STR = map_handle.get_map_system_path_str_for_list(DR_OFFICE)

# 需要解锁的设施按已开放处理，只测锁门
for scene_str in (ROOM_STR, OTHER_ROOM_STR, DR_ROOM_STR, DR_OFFICE_STR):
    scene_name = cache.scene_data[scene_str].scene_name
    if scene_name in game_config.config_facility_open_name_set:
        cache.rhodes_island.facility_open[game_config.config_facility_open_name_to_cid[scene_name]] = 1

pl = new_chara(0, "博士", position=CORRIDOR)
assistant = new_chara(1, "助理", position=CORRIDOR)
assistant.chara_setting = attr_calculation.get_chara_setting_zero()
other = new_chara(2, "干员", position=CORRIDOR)
other.chara_setting = attr_calculation.get_chara_setting_zero()
pl.assistant_character_id = 1


def doctor_locks_inside(scene: list):
    """
    让博士走进指定房间并锁上门（与「锁上门内侧锁」指令的结果一致）
    Keyword arguments:
    scene -- 房间的场景路径
    Return arguments:
    无
    """
    map_handle.character_move_scene(pl.position, scene, 0)
    room_data = cache.scene_data[map_handle.get_map_system_path_str_for_list(scene)]
    room_data.close_flag = room_data.close_type


def move_to_player(chara, cid: int):
    """
    清掉角色上一次的行动后运行「移动到玩家位置」状态机
    Keyword arguments:
    chara -- 角色数据
    cid -- 角色id
    Return arguments:
    无
    """
    chara.behavior.behavior_id = constant.Behavior.SHARE_BLANKLY
    chara.behavior.move_target = []
    constant.handle_state_machine_data[constant.StateMachine.MOVE_TO_PLAYER](cid)


# ==== 1. 博士锁在会议室里：自己找来的助理被挡在门外 ====
doctor_locks_inside(ROOM)
check("会议室已上锁", cache.scene_data[ROOM_STR].close_flag == 1)
check("没在跟随的助理进不了锁着的会议室", map_handle.judge_scene_accessible(ROOM_STR, 1) == "door_lock", map_handle.judge_scene_accessible(ROOM_STR, 1))
move_to_player(assistant, 1)
check("「移动到玩家位置」让自己找来的助理在门外等待", assistant.behavior.behavior_id == constant.Behavior.WAIT and assistant.position == CORRIDOR,
      f"behavior={assistant.behavior.behavior_id} move_target={assistant.behavior.move_target}")

# ==== 2. 被博士召集到他身边（is_follow=4）的角色，不论是不是助理，都能进他锁着的会议室 ====
for chara, cid, label in ((assistant, 1, "助理"), (other, 2, "非助理干员")):
    chara.sp_flag.is_follow = 4
    check(f"被召集的{label}可进博士锁着的会议室", map_handle.judge_scene_accessible(ROOM_STR, cid) == "open", map_handle.judge_scene_accessible(ROOM_STR, cid))
    move_to_player(chara, cid)
    check(f"「移动到玩家位置」让被召集的{label}走进锁着的会议室", chara.behavior.behavior_id == constant.Behavior.MOVE and chara.behavior.move_target == ROOM,
          f"behavior={chara.behavior.behavior_id} move_target={chara.behavior.move_target}")

# ==== 3. 召集只开博士所在的那扇门：另一间锁着的房间照旧进不了 ====
other_room = cache.scene_data[OTHER_ROOM_STR]
other_room.close_flag = other_room.close_type
for cid, label in ((1, "助理"), (2, "非助理干员")):
    check(f"被召集的{label}进不了博士不在的锁门房间", map_handle.judge_scene_accessible(OTHER_ROOM_STR, cid) == "door_lock", map_handle.judge_scene_accessible(OTHER_ROOM_STR, cid))
other_room.close_flag = 0
assistant.sp_flag.is_follow = 0
other.sp_flag.is_follow = 0

# ==== 4. 跟随博士的助理照旧可以进博士所在的锁门房间 ====
for is_follow in (1, 2):
    assistant.sp_flag.is_follow = is_follow
    check(f"is_follow={is_follow} 的助理可进博士锁着的会议室", map_handle.judge_scene_accessible(ROOM_STR, 1) == "open")
assistant.sp_flag.is_follow = 1
move_to_player(assistant, 1)
check("「移动到玩家位置」让智能跟随的助理走进锁着的会议室", assistant.behavior.behavior_id == constant.Behavior.MOVE and assistant.behavior.move_target == ROOM,
      f"behavior={assistant.behavior.behavior_id} move_target={assistant.behavior.move_target}")
assistant.sp_flag.is_follow = 0

# ==== 5. 没被召集的非助理干员不变：跟不跟随都进不了锁着的会议室 ====
for is_follow in (0, 1, 2):
    other.sp_flag.is_follow = is_follow
    check(f"is_follow={is_follow} 的非助理干员进不了锁着的会议室", map_handle.judge_scene_accessible(ROOM_STR, 2) == "door_lock")
other.sp_flag.is_follow = 0

# ==== 6. 博士房间与博士办公室：没在跟随的助理照旧可进，非助理干员照旧被挡 ====
for scene, scene_str, label in ((DR_ROOM, DR_ROOM_STR, "博士房间"), (DR_OFFICE, DR_OFFICE_STR, "博士办公室")):
    doctor_locks_inside(scene)
    check(f"{label}已上锁", cache.scene_data[scene_str].close_flag == 1)
    check(f"没在跟随的助理可进锁着的{label}", map_handle.judge_scene_accessible(scene_str, 1) == "open", map_handle.judge_scene_accessible(scene_str, 1))
    check(f"非助理干员进不了锁着的{label}", map_handle.judge_scene_accessible(scene_str, 2) == "door_lock")

finish()
