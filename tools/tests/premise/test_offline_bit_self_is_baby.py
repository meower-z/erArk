# -*- coding: UTF-8 -*-
"""
异常位7（角色离线）只看自己是不是婴儿的回归测试
==============================================
异常位7 表示角色离线（装袋搬走、外勤、婴儿、他国外交访问、逃跑中），其中「婴儿」指她自己是婴儿。
保育员照料婴儿时交互对象是婴儿，此时重算位7，她仍然在线；婴儿自己离线，刚出生时就离线。
断言落在 handle_premise.handle_normal_7 的返回值与位7是否已结算上。

在仓库根目录运行：python tools/tests/premise/test_offline_bit_self_is_baby.py
退出码：0 全部断言通过；1 有断言失败；2 未捕获异常。
"""
import sys

sys.path.insert(0, "tools/tests")
from headless_boot import boot, check, finish, mute_ui, new_chara  # noqa: E402

cache = boot()
mute_ui()

from Script.Core import constant  # noqa: E402
from Script.Design import character_handle, handle_premise, handle_state_machine, map_handle  # noqa: E402

NURSERY_STR = next(key for key, scene in cache.scene_data.items() if "Nursery" in scene.scene_tag)
NURSERY = map_handle.get_map_system_path_for_str(NURSERY_STR)

new_chara(0, "博士", position=["中枢", "博士房间"])
new_chara(1, "母亲")

# ==== 1. 刚出生的婴儿离线 ====
baby_id = character_handle.born_new_character(1, "婴儿")
baby = cache.character_data[baby_id]
check("新生儿有婴儿素质", baby.talent[101] == 1)
check("出生时已结算位7", baby.sp_flag.unnormal_flag.is_known(7))
check("新生儿离线", handle_premise.handle_normal_7(baby_id) == 0)

# ==== 2. 保育员照料婴儿：交互对象是婴儿时重算位7，她仍在线 ====
# 正常游戏里婴儿不进任何场景，这里把她放进育儿室，保育员状态机才能选她作照料对象
map_handle.character_move_scene(baby.position, NURSERY, baby_id)
carer = new_chara(2, "保育员", position=NURSERY)
carer.work.work_type = 153
handle_state_machine.handle_state_machine(constant.StateMachine.WORK_NURSERY_CARE, 2)
check("保育员照料后，交互对象是婴儿", carer.target_character_id == baby_id, f"target={carer.target_character_id}")
# 跨日结算对每个角色调用的全量重算
handle_premise.refresh_unnormal_flag(2)
check("交互对象是婴儿时重算位7，保育员仍在线", handle_premise.handle_normal_7(2) == 1)

# ==== 3. 婴儿自己重算位7后仍离线 ====
handle_premise.refresh_unnormal_flag(baby_id)
check("重算位7后，婴儿仍离线", handle_premise.handle_normal_7(baby_id) == 0)

finish()
