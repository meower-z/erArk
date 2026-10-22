# -*- coding: UTF-8 -*-
"""
H结束后门回到H开始前状态的回归测试
==================================
谁锁的门谁来开：H开始时自动锁上的门，H结束时打开；博士在H开始前就锁上的门，H结束后仍锁着。

H的开始与结束都走 settle_behavior.handle_instruct_data 结算 Behavior_Effect.csv 里的整行效果，
与游戏里行为结算的入口相同；update.game_update_flow 换成空桩，不进主循环。邀请H指令 handle_do_h 的成功判定换成恒成功的桩，
它最后交给 chara_handle_instruct_common_settle 的行为换成只记录行为id的桩，再由测试结算该行为。

在仓库根目录运行：python tools/tests/h/test_h_end_restores_door.py
退出码：0 全部断言通过；1 有断言失败；2 未捕获异常。
"""
import datetime
import sys

sys.path.insert(0, "tools/tests")
from headless_boot import SCENE, boot, check, finish, mute_ui, new_chara  # noqa: E402

cache = boot()
mute_ui()

from Script.Config import game_config  # noqa: E402
from Script.Core import constant, game_type, save_handle  # noqa: E402
from Script.Design import attr_calculation, instuct_judege, map_handle, settle_behavior, update  # noqa: E402
from Script.System.Instruct_System import handle_instruct  # noqa: E402

ROOM = ["中枢", "博士房间"]
room = cache.scene_data[map_handle.get_map_system_path_str_for_list(ROOM)]

pl = new_chara(0, "博士", position=ROOM)
npc = new_chara(1, "干员", position=ROOM)

# 不进主循环
update.game_update_flow = lambda add_time: None
# 邀请H恒成功；交给通用结算的行为只记录下来，由测试自己结算
instuct_judege.calculation_instuct_judege = lambda *args, **kwargs: [True]
settled_behaviors = []
handle_instruct.chara_handle_instruct_common_settle = lambda behavior_id, *args, **kwargs: settled_behaviors.append(behavior_id)


def settle(behavior_id):
    """
    以玩家为主体、干员为交互对象结算一个行为的整行效果
    Keyword arguments:
    behavior_id -- 行为id
    """
    pl.target_character_id = 1
    pl.behavior.behavior_id = behavior_id
    settle_behavior.handle_instruct_data(0, behavior_id, cache.game_time, 1, game_type.CharacterStatusChange())


def reset_door(locked_by_doctor):
    """
    把房间恢复为开门或博士已锁门的状态，并清空H状态
    Keyword arguments:
    locked_by_doctor -- 是否用博士的锁门指令锁上
    """
    room.close_flag = 0
    pl.h_state = attr_calculation.get_h_state_reset(pl.h_state)
    npc.h_state = attr_calculation.get_h_state_reset(npc.h_state)
    # 体力气力补满，免得H中途因体力耗尽另行结束
    for chara in (pl, npc):
        chara.hit_point = chara.hit_point_max = 10000
        chara.mana_point = chara.mana_point_max = 10000
    if locked_by_doctor:
        handle_instruct.handle_door_lock_inner()


print(f"房间 close_type={room.close_type}")

# ==== 1. 博士锁门后邀请H，各种H结束后门仍锁着 ====
for end_behavior in ("end_h", "t_h_hp_0", "h_interrupt", "group_sex_end"):
    reset_door(locked_by_doctor=True)
    check(f"[{end_behavior}] 博士锁门后门锁着", room.close_flag == 1, f"close_flag={room.close_flag}")
    settled_behaviors.clear()
    handle_instruct.handle_do_h()
    check(f"[{end_behavior}] 邀请H交给通用结算的行为是 h", settled_behaviors == ["h"], f"{settled_behaviors}")
    settle("h")
    check(f"[{end_behavior}] H中门锁着", room.close_flag == 1, f"close_flag={room.close_flag}")
    settle(end_behavior)
    check(f"[{end_behavior}] 博士锁的门在H结束后仍锁着", room.close_flag == 1, f"close_flag={room.close_flag}")

# ==== 2. 门开着时邀请H，H自动锁门，各种H结束后门打开 ====
for end_behavior in ("end_h", "t_h_hp_0", "h_interrupt", "group_sex_end"):
    reset_door(locked_by_doctor=False)
    handle_instruct.handle_do_h()
    check(f"[{end_behavior}] 邀请H后门被自动锁上", room.close_flag == 1, f"close_flag={room.close_flag}")
    settle("h")
    settle(end_behavior)
    check(f"[{end_behavior}] H锁的门在H结束后打开", room.close_flag == 0, f"close_flag={room.close_flag}")

# ==== 3. 不经邀请指令、直接结算 h_by_active 开始的H（门开着）：H锁的门在H结束后打开 ====
reset_door(locked_by_doctor=False)
settle("h_by_active")
check("[h_by_active] 开始后门被锁上", room.close_flag == 1, f"close_flag={room.close_flag}")
settle("end_h")
check("[h_by_active] H锁的门在H结束后打开", room.close_flag == 0, f"close_flag={room.close_flag}")

# ==== 4. 别的场景里另一名角色结算 end_h，不影响玩家这次H锁的门 ====
other = new_chara(2, "别处干员")
other.target_character_id = 2
check("[别处 end_h] 另一名角色不在这个房间", other.position != pl.position, f"position={other.position}")
reset_door(locked_by_doctor=False)
handle_instruct.handle_do_h()
settle("h")
other.behavior.behavior_id = "end_h"
settle_behavior.handle_instruct_data(2, "end_h", cache.game_time, 1, game_type.CharacterStatusChange())
check("[别处 end_h] 别处结算 end_h 后这里的门仍锁着", room.close_flag == 1, f"close_flag={room.close_flag}")
settle("end_h")
check("[别处 end_h] 玩家的H结束后H锁的门解锁", room.close_flag == 0, f"close_flag={room.close_flag}")

# ==== 5. 睡眠猥亵：开始时面板关门（测试桩选「是」），停止后门回到开始前 ====
reset_door(locked_by_doctor=False)
handle_instruct.handle_sleep_obscenity()
check("[睡眠猥亵] 门开着时面板把门关上", room.close_flag == 1, f"close_flag={room.close_flag}")
handle_instruct.handle_stop_sleep_obscenity()
check("[睡眠猥亵] 停止后面板关上的门打开", room.close_flag == 0, f"close_flag={room.close_flag}")
reset_door(locked_by_doctor=True)
handle_instruct.handle_sleep_obscenity()
handle_instruct.handle_stop_sleep_obscenity()
check("[睡眠猥亵] 博士锁的门在停止后仍锁着", room.close_flag == 1, f"close_flag={room.close_flag}")

# ==== 6. H锁门的记录作废后，博士再锁的门在H结束后仍锁着 ====
# 6a. 睡眠猥亵的面板锁门后，玩家离开房间（门随之解锁），回来亲手锁门再邀请H
reset_door(locked_by_doctor=False)
handle_instruct.handle_sleep_obscenity()
npc.sp_flag.unconscious_h = 0
map_handle.character_move_scene(ROOM, SCENE, 0)
check("[离开作废] 玩家离开后房间解锁", room.close_flag == 0, f"close_flag={room.close_flag}")
map_handle.character_move_scene(SCENE, ROOM, 0)
handle_instruct.handle_door_lock_inner()
handle_instruct.handle_do_h()
settle("h")
settle("end_h")
check("[离开作废] 回来后博士锁的门在H结束后仍锁着", room.close_flag == 1, f"close_flag={room.close_flag}")
# 6b. H自动锁门后，博士在H中亲手解锁再锁上
reset_door(locked_by_doctor=False)
handle_instruct.handle_do_h()
settle("h")
handle_instruct.handle_door_unlock_inner()
handle_instruct.handle_door_lock_inner()
settle("end_h")
check("[解锁作废] H中博士解锁后再锁的门在H结束后仍锁着", room.close_flag == 1, f"close_flag={room.close_flag}")
# 6c. H自动锁门后，H中结算 753 解锁（如 other_sex_be_found_to_group_sex），博士再锁上
reset_door(locked_by_doctor=False)
handle_instruct.handle_do_h()
settle("h")
constant.settle_behavior_effect_data[753](0, 1, game_type.CharacterStatusChange(), datetime.datetime(1, 1, 1))
handle_instruct.handle_door_lock_inner()
settle("end_h")
check("[753作废] 753 解锁后博士再锁的门在H结束后仍锁着", room.close_flag == 1, f"close_flag={room.close_flag}")

# ==== 7. H以外的 752 / 753 照旧 ====
reset_door(locked_by_doctor=False)
expel_event_id = "a8f7d3d3-82f9-4cd1-97be-49435539bb4a"
check("[752] 「都给我从这里出去」选项的效果含 764 与 752", set(game_config.config_event[expel_event_id].effect) == {"764", "752"}, f"{game_config.config_event[expel_event_id].effect}")
settle_behavior.handle_event_data(expel_event_id, 0, 1, game_type.CharacterStatusChange(), cache.game_time)
check("[752] 该选项结算后门锁着", room.close_flag == 1, f"close_flag={room.close_flag}")
constant.settle_behavior_effect_data[753](0, 1, game_type.CharacterStatusChange(), datetime.datetime(1, 1, 1))
check("[753] 门锁着时结算 753 后门打开", room.close_flag == 0, f"close_flag={room.close_flag}")

# ==== 8. 旧存档：H状态结构体缺少新字段时，读档的递归更新补上默认值 ====
old_chara = game_type.Character()
old_chara.h_state.__dict__.pop("door_locked_by_h", None)
loaded_chara = game_type.Character()
save_handle.recursive_update(loaded_chara, old_chara)
check("[旧存档] 读档后H状态有 door_locked_by_h 且为空串", getattr(loaded_chara.h_state, "door_locked_by_h", None) == "", f"{getattr(loaded_chara.h_state, 'door_locked_by_h', '缺失')!r}")

finish()
