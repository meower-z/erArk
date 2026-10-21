# -*- coding: UTF-8 -*-
"""
干员袭击事件选「逆来顺受」后门仍锁着的回归测试
==============================================
博士用「锁上门内侧锁」锁门后，屋里只剩一名想逆推博士的干员时，会触发
「{Name}最近有些欲求不满……向{PlayerName}扑了过来」事件（行为 move 与 wait 各一个）。
选项「逆来顺受」的结算跑完后，门必须仍然锁着（谁锁的门谁来开）；该选项的其他结算照旧生效。

结算走 settle_behavior.handle_event_data，与游戏里事件结算的入口相同。
综合指令结算 CSE_A2_h_by_active 会经 update.game_update_flow 进入主循环，测试把它换成只记录调用的桩，
不跑主循环；锁门用游戏自己的锁门指令 handle_door_lock_inner。

在仓库根目录运行：python tools/tests/event/test_ambush_event_keeps_door_locked.py
退出码：0 全部断言通过；1 有断言失败；2 未捕获异常。
"""
import sys

sys.path.insert(0, "tools/tests")
from headless_boot import boot, check, finish, mute_ui, new_chara  # noqa: E402

cache = boot()
mute_ui()

from Script.Config import game_config  # noqa: E402
from Script.Core import game_type  # noqa: E402
from Script.Design import handle_premise, map_handle, settle_behavior, update  # noqa: E402
from Script.System.Instruct_System import handle_instruct  # noqa: E402

ROOM = ["中枢", "博士房间"]
room = cache.scene_data[map_handle.get_map_system_path_str_for_list(ROOM)]

pl = new_chara(0, "博士", position=ROOM)
npc = new_chara(1, "干员", position=ROOM)
npc.sp_flag.npc_masturebate_for_player = True

# 不进主循环：只记录 game_update_flow 被调用时的时长
update_calls = []
update.game_update_flow = lambda add_time: update_calls.append(add_time)


def find_event(behavior_id, text_prefix):
    """
    在指定行为的事件表里按文本开头找事件
    Keyword arguments:
    behavior_id -- 行为id
    text_prefix -- 事件文本开头
    Return arguments:
    str -- 事件id（找不到时为空串）
    """
    for event_id in game_config.config_event_status_data.get(behavior_id, ()):
        if game_config.config_event[event_id].text.startswith(text_prefix):
            return event_id
    return ""


for behavior_id in ("move", "wait"):
    print(f"== 行为 {behavior_id} ==")
    father_id = find_event(behavior_id, "{Name}最近有些欲求不满")
    son_id = find_event(behavior_id, "逆来顺受|")
    check(f"[{behavior_id}] 找到袭击事件与「逆来顺受」选项", father_id != "" and son_id != "", f"father={father_id!r} son={son_id!r}")

    # ==== 1. 博士锁门 ====
    handle_instruct.handle_door_lock_inner()
    check(f"[{behavior_id}] 锁门指令后门锁着", room.close_flag == room.close_type == 1, f"close_flag={room.close_flag} close_type={room.close_type}")

    # ==== 2. 锁着的房间里，袭击事件的前提成立 ====
    npc.behavior.behavior_id = behavior_id
    weight, _ = handle_premise.get_weight_from_premise_dict(game_config.config_event[father_id].premise, 1, {}, unconscious_pass_flag=True)
    check(f"[{behavior_id}] 锁门后袭击事件的前提成立", weight > 0, f"weight={weight}")

    # ==== 3. 结算「逆来顺受」选项 ====
    pl.behavior.behavior_id = "wait"
    npc.h_state.npc_active_h = False
    npc.sp_flag.move_stop = False
    update_calls.clear()
    settle_behavior.handle_event_data(son_id, 1, 1, game_type.CharacterStatusChange(), cache.game_time)
    check(f"[{behavior_id}] 「逆来顺受」结算后门仍锁着", room.close_flag == 1, f"close_flag={room.close_flag}")
    check(f"[{behavior_id}] 干员开启主动H（1401）", npc.h_state.npc_active_h is True)
    check(
        f"[{behavior_id}] 博士对干员开始被动H（CSE_A2_h_by_active）",
        pl.behavior.behavior_id == "h_by_active" and pl.target_character_id == 1 and len(update_calls) == 1,
        f"behavior={pl.behavior.behavior_id} target={pl.target_character_id} update_calls={update_calls}",
    )
    check(f"[{behavior_id}] 干员停止移动（367）", npc.sp_flag.move_stop is True)

finish()
