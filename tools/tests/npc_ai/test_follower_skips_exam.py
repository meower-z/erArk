# -*- coding: UTF-8 -*-
"""
智能跟随中的干员不去体检的回归测试
==================================
排了体检的干员处于智能跟随时，不应动身去体检科：否则她在博士身边时去体检科，离开一步后又被「移动到玩家位置」拉回，
逐分钟来回。跟随中她留在等待体检名单上，跟随结束后再去体检科。
断言都落在 handle_npc_ai.find_character_target 选出行动后角色的移动终点与等待体检名单上。

在仓库根目录运行：python tools/tests/npc_ai/test_follower_skips_exam.py
退出码：0 全部断言通过；1 有断言失败；2 未捕获异常。
"""
import datetime
import sys

sys.path.insert(0, "tools/tests")
from headless_boot import boot, check, finish, mute_ui, new_chara  # noqa: E402

cache = boot()
mute_ui()

from Script.Core import constant  # noqa: E402
from Script.Design import attr_calculation, handle_npc_ai, map_handle  # noqa: E402

ROOM = ["中枢", "博士房间"]
CORRIDOR = ["中枢", "走廊"]
EXAM_ROOMS = [map_handle.get_map_system_path_for_str(path) for path in constant.place_data["Physical_Examination"]]

# 上午 10 点，在上午体检时段（9:00~12:00）内
cache.game_time = datetime.datetime(2020, 12, 22, 10, 0)
new_chara(0, "博士", position=ROOM)
follower = new_chara(1, "助理", position=ROOM)
# 走向玩家时要读角色设置（是否进入私密场所），夹具默认没有
follower.chara_setting = attr_calculation.get_chara_setting_zero()
# 她是博士的助理：只有助理能进博士房间，回博士身边时不会被挡在门外
cache.character_data[0].assistant_character_id = 1
# 检修工程师的工作没有自动 AI，AI 会逐条查工作链（target 组 21/22）的目标行，体检行就在其中；
# 检修自己的工作行都要求 normal_all，处在体检行动链中时不成立，所以工作链里只剩体检行可选
follower.work.work_type = 21
waiting_list = cache.rhodes_island.waiting_for_exam_operator_ids


def decide():
    """
    让 1 号角色重新选一次行动
    Return arguments:
    list -- 本次行动的移动终点（没有移动时为空列表）
    """
    follower.behavior.move_final_target = []
    follower.behavior.start_time = cache.game_time
    handle_npc_ai.find_character_target(1, cache.game_time)
    return list(follower.behavior.move_final_target)


# ==== 1. 今天上午排了体检、还没进等待名单（目标 210500） ====
follower.action_info.health_check_today = 1
follower.sp_flag.is_follow = 1
target = decide()
check("排了上午体检、跟随中的干员不动身去体检科", target not in EXAM_ROOMS, f"move_final_target={target}")
follower.sp_flag.is_follow = 0
target = decide()
check("排了上午体检的干员跟随结束后去体检科", target in EXAM_ROOMS, f"move_final_target={target}")

# ==== 2. 已在等待体检名单上（目标 220505） ====
follower.action_info.health_check_today = 0
waiting_list.add(1)
follower.sp_flag.is_follow = 1
target = decide()
check("在等待名单上、跟随中的干员不动身去体检科", target not in EXAM_ROOMS, f"move_final_target={target}")
check("跟随中的干员仍在等待体检名单上", 1 in waiting_list)

# ==== 3. 跟随中离开博士一步，被「移动到玩家位置」拉回（目标 100） ====
map_handle.character_move_scene(ROOM, CORRIDOR, 1)
target = decide()
check("跟随中离开博士一步的干员回到博士身边", target == ROOM, f"move_final_target={target}")
map_handle.character_move_scene(CORRIDOR, ROOM, 1)

# ==== 4. 跟随结束 ====
follower.sp_flag.is_follow = 0
target = decide()
check("在等待名单上的干员跟随结束后去体检科", target in EXAM_ROOMS, f"move_final_target={target}")

finish()
