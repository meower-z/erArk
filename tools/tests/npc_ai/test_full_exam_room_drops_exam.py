# -*- coding: UTF-8 -*-
"""
体检科满员时干员放弃今天体检的回归测试
======================================
体检科满员（Room_Area 0 上限 10 人）时，要去体检的干员会在门口被拒，之后每分钟重选同一个体检目标、整天在走廊重试。
现在她在要动身时发现满员，就放弃今天的体检：清掉今日体检时间、退出等待名单，当天不再去，下一个体检日照常抽选。
断言都落在 handle_npc_ai.find_character_target 选出行动后角色的移动终点、今日体检时间与等待体检名单上。

在仓库根目录运行：python tools/tests/npc_ai/test_full_exam_room_drops_exam.py
退出码：0 全部断言通过；1 有断言失败；2 未捕获异常。
"""
import datetime
import sys

sys.path.insert(0, "tools/tests")
from headless_boot import boot, check, finish, mute_ui, new_chara  # noqa: E402

cache = boot()
mute_ui()

from Script.Core import constant  # noqa: E402
from Script.Design import handle_npc_ai, map_handle  # noqa: E402
from Script.UI.Panel import physical_check_and_manage  # noqa: E402

CORRIDOR = ["中枢", "走廊"]
EXAM_ROOM_STR = constant.place_data["Physical_Examination"][0]
EXAM_ROOM = map_handle.get_map_system_path_for_str(EXAM_ROOM_STR)

# 上午 10 点，在上午体检时段（9:00~12:00）内
cache.game_time = datetime.datetime(2020, 12, 22, 10, 0)
new_chara(0, "博士", position=["中枢", "博士房间"])
operator = new_chara(1, "干员", position=CORRIDOR)
# 检修工程师的工作没有自动 AI，AI 会逐条查工作链（target 组 21/22）的目标行，体检行就在其中
operator.work.work_type = 21
waiting_list = cache.rhodes_island.waiting_for_exam_operator_ids


def decide():
    """
    让 1 号角色重新选一次行动
    Return arguments:
    list -- 本次行动的移动终点（没有移动时为空列表）
    """
    operator.behavior.move_final_target = []
    operator.behavior.start_time = cache.game_time
    handle_npc_ai.find_character_target(1, cache.game_time)
    return list(operator.behavior.move_final_target)


# ==== 1. 体检科没满：排了上午体检的干员照常去体检科 ====
operator.action_info.health_check_today = 1
target = decide()
check("体检科没满时，排了上午体检的干员去体检科", target == EXAM_ROOM, f"move_final_target={target}")
check("体检科没满时，她的今日体检时间不变", operator.action_info.health_check_today == 1, f"health_check_today={operator.action_info.health_check_today}")

# 让 10 个干员坐满体检科
for cid in range(2, 12):
    new_chara(cid, f"占位干员{cid}", position=EXAM_ROOM)
check("体检科坐满 10 人后满员", map_handle.judge_scene_is_full(EXAM_ROOM_STR))

# ==== 2. 体检科满员：排了上午体检的干员放弃今天的体检（目标 210500） ====
target = decide()
check("体检科满员时，排了上午体检的干员不去体检科", target != EXAM_ROOM, f"move_final_target={target}")
check("她的今日体检时间清零", operator.action_info.health_check_today == 0, f"health_check_today={operator.action_info.health_check_today}")
check("她不在等待体检名单上", 1 not in waiting_list)
target = decide()
check("放弃后再选一次行动，她仍不去体检科", target != EXAM_ROOM, f"move_final_target={target}")

# ==== 2b. 体检科满员：今日体检时间为 3（新干员立刻体检）的干员同样放弃 ====
operator.action_info.health_check_today = 3
target = decide()
check("体检科满员时，要立刻体检的干员不去体检科", target != EXAM_ROOM, f"move_final_target={target}")
check("她的今日体检时间同样清零", operator.action_info.health_check_today == 0, f"health_check_today={operator.action_info.health_check_today}")

# ==== 3. 体检科满员：前一天起就在等待名单上的干员退出名单（目标 220505） ====
waiting_list.add(1)
target = decide()
check("体检科满员时，等待名单上的干员不去体检科", target != EXAM_ROOM, f"move_final_target={target}")
check("她退出了等待体检名单", 1 not in waiting_list)
target = decide()
check("退出名单后再选一次行动，她仍不去体检科", target != EXAM_ROOM, f"move_final_target={target}")

# ==== 4. 下一个体检日照常抽选 ====
# 开启定期体检、每天体检、全体干员、已体检的仍需再检、每天抽 50 人（多于全部干员，全员抽中）
cache.rhodes_island.physical_examination_setting.update({2: 1, 3: 3, 4: 1, 5: 1, 6: 49})
cache.game_time = datetime.datetime(2020, 12, 23, 0, 0)
physical_check_and_manage.settle_health_check()
check("下一个体检日的抽选抽中了她", operator.action_info.health_check_today in (1, 2), f"health_check_today={operator.action_info.health_check_today}")

finish()
