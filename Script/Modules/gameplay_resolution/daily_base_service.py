"""
基地每日结算服务（daily_base_service）
======================================
提供香薰疗愈次数刷新与定期体检抽选等基地每日结算逻辑。
不直接导入界面模块，供基地每日结算入口调用。
"""

import random

from Script.Design import game_time, handle_premise
from Script.Modules.domains import action_info, facility, identity
from Script.Modules.domains import physical_exam, roster, tallies


def settle_aromatherapy_sessions() -> None:
    """
    按设施 16（疗养庭院）的等级刷新当日可用的香薰疗愈次数。
    等级达到 5 级时设为 3 次，4 级时设为 2 次，3 级及以下设为 1 次。
    Keyword arguments:
    无
    Return arguments:
    None -- 直接写入每日计数中的香薰疗愈次数
    """

    level = facility.level(16)

    if level >= 5:
        tallies.set(tallies.AROMATHERAPY, 3)
    elif level == 4:
        tallies.set(tallies.AROMATHERAPY, 2)
    elif level <= 3:
        tallies.set(tallies.AROMATHERAPY, 1)


def settle_health_check() -> None:
    """
    执行每日体检结算，重置今日体检记录并按定期体检设置抽选体检干员。
    开启定期体检且当日为体检日时，清空非玩家在编干员的今日体检时段，并按每日人数上限随机抽选名单内干员分配时段 1 或 2。
    开启定期体检时，按体检周期设置（年、月、周、日）在对应重置日清空本周期已体检名单。
    Keyword arguments:
    无
    Return arguments:
    None -- 直接更新体检领域状态与干员今日体检时段
    """
    physical_exam.clear(physical_exam.TODAY)
    if handle_premise.handle_periodic_health_check_on(0):
        if handle_premise.handle_today_is_healty_check_day(0):
            need_physical_examination_chara_id_list = []
            for chara_id in roster.active():
                if chara_id == 0:
                    continue
                action_info.set(chara_id, "health_check_today", 0)
                if handle_premise.handle_self_in_health_check_list(chara_id):
                    need_physical_examination_chara_id_list.append(chara_id)
            need_chara_num = int(physical_exam.setting(6)) + 1
            final_physical_examination_chara_id_list = []
            if need_chara_num >= len(need_physical_examination_chara_id_list):
                final_physical_examination_chara_id_list = (
                    need_physical_examination_chara_id_list
                )
            else:
                final_physical_examination_chara_id_list = random.sample(
                    need_physical_examination_chara_id_list, need_chara_num
                )
            for chara_id in final_physical_examination_chara_id_list:
                now_character_data = identity.of(chara_id)
                if random.randint(0, 1) == 0:
                    action_info.set(
                        now_character_data.cid, "health_check_today", 1
                    )
                else:
                    action_info.set(
                        now_character_data.cid, "health_check_today", 2
                    )
        if physical_exam.setting(3) == 0:
            if game_time.now().month == 3 and game_time.now().day == 1:
                physical_exam.clear(physical_exam.EXAMINED)
        elif physical_exam.setting(3) == 1:
            if game_time.now().day == 1:
                physical_exam.clear(physical_exam.EXAMINED)
        elif physical_exam.setting(3) == 2:
            if game_time.now().weekday() == 0:
                physical_exam.clear(physical_exam.EXAMINED)
        elif physical_exam.setting(3) == 3:
            physical_exam.clear(physical_exam.EXAMINED)
