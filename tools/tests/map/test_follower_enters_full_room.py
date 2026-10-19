# -*- coding: UTF-8 -*-
"""
跟随博士的干员进入满员房间的回归测试
====================================
房间满员（Room_Area 0 满 10 人）时，智能跟随或强制跟随的干员仍能跟着博士进门：
博士正迈进这个房间时与他同步迈进，博士已在房间里时走到他身边。
不在跟随的干员、或目标不是博士所在 / 正要进入的房间时，满员照旧挡在门外；私密场所的判定不变。
断言落在 handle_npc_ai.judge_same_position_npc_follow、跟随状态机「移动到玩家位置」选出的下一步，
以及 map_handle.judge_scene_accessible 的返回值上。

在仓库根目录运行：python tools/tests/map/test_follower_enters_full_room.py
退出码：0 全部断言通过；1 有断言失败；2 未捕获异常。
"""
import sys

sys.path.insert(0, "tools/tests")
from headless_boot import boot, check, finish, mute_ui, new_chara  # noqa: E402

cache = boot()
mute_ui()

from Script.Config import game_config  # noqa: E402
from Script.Core import constant  # noqa: E402
from Script.Design import attr_calculation, handle_npc_ai, map_handle  # noqa: E402

ROOM = ["医疗", "体检科"]
DOOR = ["医疗", "内走廊"]
DR_ROOM = ["中枢", "博士房间"]
ROOM_STR = map_handle.get_map_system_path_str_for_list(ROOM)
DR_ROOM_STR = map_handle.get_map_system_path_str_for_list(DR_ROOM)

# 体检科是要解锁的设施，按已开放处理
cache.rhodes_island.facility_open[game_config.config_facility_open_name_to_cid[cache.scene_data[ROOM_STR].scene_name]] = 1
pl = new_chara(0, "博士", position=DOOR)
follower = new_chara(1, "跟随者", position=DOOR)
follower.chara_setting = attr_calculation.get_chara_setting_zero()
other = new_chara(2, "路人", position=DOOR)
other.chara_setting = attr_calculation.get_chara_setting_zero()
# 体检科是 Room_Area 0，10 人即满员
for cid in range(10, 20):
    new_chara(cid, f"占位{cid}", position=ROOM)
check("体检科已满员", map_handle.judge_scene_is_full(ROOM_STR))


def doctor_steps_into_room():
    """
    让博士处在「正从门口迈进体检科」这一步：与 own_charcter_move 发起移动后的状态一致
    Return arguments:
    无
    """
    pl.behavior.behavior_id = constant.Behavior.MOVE
    pl.behavior.move_target = ROOM
    pl.behavior.move_final_target = ROOM
    pl.behavior.start_time = cache.game_time
    pl.behavior.duration = 1


def reset_npc(chara):
    """
    清掉 NPC 上一次判定写下的行动
    Keyword arguments:
    chara -- 角色数据
    Return arguments:
    无
    """
    chara.behavior.behavior_id = constant.Behavior.SHARE_BLANKLY
    chara.behavior.move_target = []
    chara.action_info.follow_wait_time = 0


# ==== 1. 博士迈进满员的体检科，智能跟随的干员同步迈进 ====
doctor_steps_into_room()
follower.sp_flag.is_follow = 1
reset_npc(follower)
handle_npc_ai.judge_same_position_npc_follow()
check("智能跟随的干员与博士同步迈进满员房间", follower.behavior.behavior_id == constant.Behavior.MOVE and follower.behavior.move_target == ROOM,
      f"behavior={follower.behavior.behavior_id} move_target={follower.behavior.move_target}")
check("没在跟随的干员仍被满员挡在门外", map_handle.judge_scene_accessible(ROOM_STR, 2) == "full")

# ==== 2. 博士已在体检科里，跟随者在门口：「移动到玩家位置」把她带进去 ====
map_handle.character_move_scene(DOOR, ROOM, 0)
pl.behavior.behavior_id = constant.Behavior.SHARE_BLANKLY
for is_follow in (1, 2):
    follower.sp_flag.is_follow = is_follow
    check(f"is_follow={is_follow} 的干员可进入博士所在的满员房间", map_handle.judge_scene_accessible(ROOM_STR, 1) == "open")
follower.sp_flag.is_follow = 1
reset_npc(follower)
constant.handle_state_machine_data[constant.StateMachine.MOVE_TO_PLAYER](1)
check("「移动到玩家位置」让智能跟随的干员走进满员房间", follower.behavior.behavior_id == constant.Behavior.MOVE and follower.behavior.move_target == ROOM,
      f"behavior={follower.behavior.behavior_id} move_target={follower.behavior.move_target}")
for is_follow in (3, 4):
    follower.sp_flag.is_follow = is_follow
    check(f"is_follow={is_follow}（被召集）的干员仍被满员挡在门外", map_handle.judge_scene_accessible(ROOM_STR, 1) == "full")

# ==== 3. 博士不在、也不去这个满员房间时，跟随中的干员照旧被挡 ====
map_handle.character_move_scene(ROOM, DOOR, 0)
follower.sp_flag.is_follow = 1
check("目标不是博士所在的房间时，跟随者仍被满员挡在门外", map_handle.judge_scene_accessible(ROOM_STR, 1) == "full")

# ==== 4. 私密场所不受影响：跟随的非助理干员仍进不了博士房间 ====
map_handle.character_move_scene(DOOR, DR_ROOM, 0)
check("跟随的非助理干员仍进不了博士房间", map_handle.judge_scene_accessible(DR_ROOM_STR, 1) == "private")

finish()
