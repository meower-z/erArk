# -*- coding: UTF-8 -*-
"""
平然催眠的干员在时停结束后按清醒判定的回归测试
==============================================
平然催眠（unconscious_h=4）使异常位5（意识模糊）为异常。开时停把她的 unconscious_h 改成 3，关时停再改成 0。
关时停后她已经清醒，异常位5必须读成正常；否则玩家对她用的、要求交互对象5、6正常的指令都不可用。
断言都落在异常位5的判定 handle_normal_5 与玩家指令用的前提 t_normal_5_6 上；时停开关走游戏自己的结算函数。

在仓库根目录运行：python tools/tests/premise/test_hypnosis_bit5_after_time_stop.py
退出码：0 全部断言通过；1 有断言失败；2 未捕获异常。
"""
import datetime
import sys

sys.path.insert(0, "tools/tests")
from headless_boot import boot, check, finish, mute_ui, new_chara  # noqa: E402

cache = boot()
mute_ui()

from Script.Config import game_config  # noqa: E402
from Script.Core import game_type  # noqa: E402
from Script.Design import basement, handle_premise  # noqa: E402
from Script.Settle import default as settle_default  # noqa: E402
from Script.UI.Panel import hypnosis_panel  # noqa: E402

NOW = datetime.datetime(2020, 12, 22, 10, 0)
HYPNOSIS_TYPE_CALM = 1  # 平然

cache.game_time = NOW
# 按开局流程初始化基地：催眠完成时的素质检测会走成就结算，读基地资源
cache.rhodes_island = basement.get_base_zero()
basement.get_base_updata()
player = new_chara(0, "博士")
operator = new_chara(1, "干员")
player.target_character_id = 1

# ==== 1. 玩家对她完成平然催眠 ====
player.pl_ability.hypnosis_type = HYPNOSIS_TYPE_CALM
operator.hypnosis.hypnosis_degree = game_config.config_hypnosis_type[HYPNOSIS_TYPE_CALM].hypnosis_degree
done = hypnosis_panel.evaluate_hypnosis_completion(1)
check("平然催眠完成，她进入平然状态", done == 1 and operator.sp_flag.unconscious_h == 4, f"done={done} unconscious_h={operator.sp_flag.unconscious_h}")
check("平然中异常位5为异常", handle_premise.handle_normal_5(1) == 0)

# ==== 2. 开时停、关时停（游戏的结算函数） ====
settle_default.handle_time_stop_on(0, 0, game_type.CharacterStatusChange(), NOW)
check("时停中异常位6为异常", handle_premise.handle_normal_6(1) == 0)
settle_default.handle_time_stop_off(0, 0, game_type.CharacterStatusChange(), NOW)
check("关时停后她清醒：unconscious_h=0", operator.sp_flag.unconscious_h == 0, f"unconscious_h={operator.sp_flag.unconscious_h}")
check("关时停后异常位5为正常", handle_premise.handle_normal_5(1) == 1)
check("关时停后玩家对她的指令前提「交互对象5、6正常」成立", handle_premise.handle_t_normal_5_6(0) == 1)

finish()
