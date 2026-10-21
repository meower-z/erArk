# -*- coding: UTF-8 -*-
"""
排了体检的干员到了体检时段去体检科的回归测试
============================================
午夜抽签给干员排上午（9:00~12:00）或下午（14:00~18:00）体检时，会顺手结算异常位3（高优先级AI：助理、跟随、体检）并缓存。
那时还不在体检时段，缓存记成「正常」，到了体检时段也没有地方重算，干员就一直按「正常」在岗位上工作，不去体检科。
现在排了上午或下午体检的干员，异常位3每次都按当时的时间重新判定。
断言都落在 handle_npc_ai.find_character_target 选出行动后角色的移动终点上。

在仓库根目录运行：python tools/tests/npc_ai/test_booked_exam_slot_not_cached.py
退出码：0 全部断言通过；1 有断言失败；2 未捕获异常。
"""
import datetime
import sys

sys.path.insert(0, "tools/tests")
from headless_boot import boot, check, finish, mute_ui, new_chara  # noqa: E402

cache = boot()
mute_ui()

from Script.Core import constant  # noqa: E402
from Script.Design import basement, clothing, handle_npc_ai, handle_premise, map_handle  # noqa: E402
from Script.UI.Panel import physical_check_and_manage  # noqa: E402

EXAM_ROOM = map_handle.get_map_system_path_for_str(constant.place_data["Physical_Examination"][0])
POST = map_handle.get_map_system_path_for_str(constant.place_data["Maintenance_Department"][0])
MIDNIGHT = datetime.datetime(2020, 12, 22, 0, 0)

# 按开局流程初始化基地（设施开放表等）：检修工作要随机挑设施，读设施开放表
cache.rhodes_island = basement.get_base_zero()
basement.get_base_updata()
new_chara(0, "博士", position=["中枢", "博士房间"])
operator = new_chara(1, "干员", position=POST)
# 检修工程师的工作没有自动 AI，AI 会逐条查工作链（target 组 22 再 21）的目标行；她在自己的岗位运维部
operator.work.work_type = 21
# 夹具默认全裸，异常位4（服装异常）会让工作行要求的 normal_all 不成立，先穿上衣服
clothing.get_common_cloth(1)
handle_premise.settle_chara_unnormal_flag(1, 4)
# 开启定期体检、每天体检、全体干员、已体检的仍需再检、每天抽 10 人（面板上限，多于全部干员，全员抽中）
cache.rhodes_island.physical_examination_setting.update({2: 1, 3: 3, 4: 1, 5: 1, 6: 9})


def book_at_midnight(slot):
    """
    午夜按抽签代码给她排体检，并结算异常位3
    Keyword arguments:
    slot -- 今日体检时间（1 上午，2 下午）
    """
    cache.game_time = MIDNIGHT
    operator.behavior.start_time = MIDNIGHT
    map_handle.character_move_scene(operator.position, POST, 1)
    operator.action_info.health_check_today = slot
    handle_premise.settle_chara_unnormal_flag(1, 3)


def decide(hour):
    """
    在当天的某个整点让 1 号角色重新选一次行动
    Keyword arguments:
    hour -- 整点
    Return arguments:
    list -- 本次行动的移动终点（没有移动时为空列表）
    """
    now = datetime.datetime(2020, 12, 22, hour, 0)
    cache.game_time = now
    operator.behavior.start_time = now
    operator.behavior.move_final_target = []
    operator.sp_flag.work_maintenance = 0
    handle_npc_ai.find_character_target(1, now)
    return list(operator.behavior.move_final_target)


# ==== 1. 游戏自己的午夜抽签排了体检，到了她的时段去体检科 ====
cache.game_time = MIDNIGHT
operator.behavior.start_time = MIDNIGHT
physical_check_and_manage.settle_health_check()
first = operator.action_info.health_check_today
check("午夜抽签给她排了上午或下午体检", first in (1, 2), f"health_check_today={first}")
first_hour = 10 if first == 1 else 15
target = decide(first_hour)
check(f"抽签排的时段内（{first_hour}:00），她去体检科", target == EXAM_ROOM, f"move_final_target={target}")

# ==== 2. 上午体检：时段前不去，时段内去 ====
book_at_midnight(1)
target = decide(8)
check("排了上午体检，8:00 还没到时段，她不去体检科", target != EXAM_ROOM, f"move_final_target={target}")
target = decide(10)
check("排了上午体检，10:00 她去体检科", target == EXAM_ROOM, f"move_final_target={target}")

# ==== 3. 下午体检：上午不去，下午去 ====
book_at_midnight(2)
target = decide(10)
check("排了下午体检，10:00 还没到时段，她不去体检科", target != EXAM_ROOM, f"move_final_target={target}")
target = decide(15)
check("排了下午体检，15:00 她去体检科", target == EXAM_ROOM, f"move_final_target={target}")

finish()
