# -*- coding: UTF-8 -*-
"""
失去泌乳后涨奶罩杯缩回的回归测试
================================
干员涨奶（奶量超过上限的 80%）时罩杯变大一级并记下涨奶标记。以前她一旦失去泌乳素质（停乳药、育儿结束），
涨奶罩杯结算在开头就直接返回，罩杯一直大一级，涨奶标记也一直留着。
现在失去泌乳素质后的第一次结算把罩杯缩小一级、清除涨奶标记，之后不再变化。
断言都落在 handle_talent.npc_b_talent_change_for_lactation_flag（行为循环每轮经 gain_talent 调用它）结算后的罩杯素质与涨奶标记上。

在仓库根目录运行：python tools/tests/talent/test_cup_shrinks_after_lactation_ends.py
退出码：0 全部断言通过；1 有断言失败；2 未捕获异常。
"""
import sys

sys.path.insert(0, "tools/tests")
from headless_boot import boot, check, finish, mute_ui, new_chara  # noqa: E402

cache = boot()
mute_ui()

from Script.Design import handle_talent  # noqa: E402
from Script.UI.Panel import gift_panel  # noqa: E402

CUPS = [121, 122, 123, 124, 125]
""" 罩杯素质：绝壁、贫乳、普乳、巨乳、爆乳 """
LACTATION_DRUG, STOP_LACTATION_DRUG, SHRINK_CHEST_DRUG = 33, 34, 22
""" 泌乳药、停乳药、缩胸药的药物id """

new_chara(0, "博士")


def make(cid, cup):
    """
    造一个指定罩杯、没有泌乳的干员
    Keyword arguments:
    cid -- 角色id
    cup -- 罩杯素质id
    Return arguments:
    game_type.Character -- 角色对象
    """
    cd = new_chara(cid, f"干员{cid}")
    for talent_id in CUPS:
        cd.talent[talent_id] = 0
    cd.talent[cup] = 1
    cd.pregnancy.milk_max = 190
    return cd


def settle(cid):
    """
    跑一次涨奶罩杯结算，返回结算后的罩杯与涨奶标记
    Keyword arguments:
    cid -- 角色id
    Return arguments:
    tuple -- (罩杯素质id列表, 涨奶标记)
    """
    handle_talent.npc_b_talent_change_for_lactation_flag(cid)
    cd = cache.character_data[cid]
    return [t for t in CUPS if cd.talent[t]], cd.pregnancy.lactation_flag


# ==== 1. 涨奶后用停乳药：罩杯缩回涨奶前的大小，只缩一次 ====
cd = make(1, 122)
gift_panel.handle_drug_use_effect(1, LACTATION_DRUG)
cd.pregnancy.milk = 190
result = settle(1)
check("涨奶时罩杯从贫乳变成普乳并记下涨奶标记", result == ([123], True), str(result))
gift_panel.handle_drug_use_effect(1, STOP_LACTATION_DRUG)
check("停乳药去掉了泌乳素质", cd.talent[27] == 0)
result = settle(1)
check("停乳后的第一次结算把罩杯缩回贫乳并清除涨奶标记", result == ([122], False), str(result))
result = settle(1)
check("再结算一次，罩杯仍是贫乳", result == ([122], False), str(result))

# ==== 2. 旧存档里已经卡住的状态（没有泌乳素质、涨奶标记还在、奶量为 0）：第一次结算修复，只修一次 ====
cd = make(2, 123)
cd.pregnancy.lactation_flag = True
cd.pregnancy.milk = 0
result = settle(2)
check("卡住的干员第一次结算后罩杯缩回贫乳、涨奶标记清除", result == ([122], False), str(result))
result = settle(2)
check("卡住的干员再结算一次，罩杯仍是贫乳", result == ([122], False), str(result))

# ==== 3. 罩杯已是爆乳时涨奶：没有变大也没有涨奶标记，停乳后保持爆乳 ====
cd = make(3, 125)
gift_panel.handle_drug_use_effect(3, LACTATION_DRUG)
cd.pregnancy.milk = 190
result = settle(3)
check("爆乳涨奶时罩杯不变、不记涨奶标记", result == ([125], False), str(result))
gift_panel.handle_drug_use_effect(3, STOP_LACTATION_DRUG)
result = settle(3)
check("爆乳停乳后仍是爆乳", result == ([125], False), str(result))

# ==== 4. 涨奶期间用过缩胸药：停乳后比涨奶前小一级（最小到绝壁），与奶量降到 79% 及以下时相同 ====
cd = make(4, 122)
gift_panel.handle_drug_use_effect(4, LACTATION_DRUG)
cd.pregnancy.milk = 190
settle(4)
gift_panel.handle_drug_use_effect(4, SHRINK_CHEST_DRUG)
result = settle(4)
check("涨奶期间用缩胸药后罩杯回到贫乳、涨奶标记还在", result == ([122], True), str(result))
gift_panel.handle_drug_use_effect(4, STOP_LACTATION_DRUG)
result = settle(4)
check("接着停乳，罩杯缩到绝壁", result == ([121], False), str(result))
cd = make(7, 122)
gift_panel.handle_drug_use_effect(7, LACTATION_DRUG)
cd.pregnancy.milk = 190
settle(7)
gift_panel.handle_drug_use_effect(7, SHRINK_CHEST_DRUG)
cd.pregnancy.milk = 100
result = settle(7)
check("涨奶期间用缩胸药后奶量降到 79% 及以下，罩杯同样缩到绝壁", result == ([121], False), str(result))
cd = make(8, 121)
gift_panel.handle_drug_use_effect(8, LACTATION_DRUG)
cd.pregnancy.milk = 190
settle(8)
gift_panel.handle_drug_use_effect(8, SHRINK_CHEST_DRUG)
gift_panel.handle_drug_use_effect(8, STOP_LACTATION_DRUG)
result = settle(8)
check("原为绝壁的干员涨奶期间用缩胸药后停乳，罩杯停在绝壁、涨奶标记清除", result == ([121], False), str(result))

# ==== 5. 不受影响的情形：从没泌乳过的干员、还在涨奶的干员 ====
make(5, 122)
result = settle(5)
check("从没泌乳过的干员罩杯不变", result == ([122], False), str(result))
cd = make(6, 122)
gift_panel.handle_drug_use_effect(6, LACTATION_DRUG)
cd.pregnancy.milk = 190
settle(6)
result = settle(6)
check("还在涨奶的干员保持普乳和涨奶标记", result == ([123], True), str(result))
cd.pregnancy.milk = 100
result = settle(6)
check("奶量降到 79% 及以下时罩杯照旧缩回贫乳", result == ([122], False), str(result))

finish()
