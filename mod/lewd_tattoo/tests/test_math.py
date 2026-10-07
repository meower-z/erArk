# -*- coding: UTF-8 -*-
"""
effects.py 纯数学单测（不 import 游戏）：倍率乘区、联结、欲情、每日增长、寸止概率、槽位、确认条件、效果表
用法：python3 mod/lewd_tattoo/tests/test_math.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import check, finish, load_mod_package  # noqa: E402

load_mod_package()
from _erark_mod_lewd_tattoo import effects  # noqa: E402

VAGINA = 4
""" 阴道快感 """


def plan(keys, state_id, value):
    """
    以一组效果键算一次增量去向
    Keyword arguments:
    keys -- 效果键列表
    state_id -- 状态id
    value -- 正增量
    Return arguments:
    effects.GainPlan -- 去向
    """
    return effects.plan_gain(effects.compile_profile(frozenset(keys)), state_id, value)


print("==== 包加载不带入游戏 ====")
check("纯数学测试没有 import Script.Core.cache_control", "Script.Core.cache_control" not in sys.modules)

print("==== 倍率与联结 ====")
p = plan(["boost:vagina", "all_boost"], VAGINA, 100)
check("单部位×全部位：100 → 225，无联结", p.main == 225 and p.side == () and not p.to_mind, p)
p = plan(["boost:vagina", "all_boost", "link1"], VAGINA, 100)
sides = dict(p.side)
check("加联结I：本部位 225，其余各 22", p.main == 225 and set(sides.values()) == {22} and len(sides) == 10 and VAGINA not in sides, p)
p = plan(["boost:vagina", "all_boost", "link1", "link2"], VAGINA, 100)
check("联结I+II：本部位 180，其余各 67", p.main == 180 and set(dict(p.side).values()) == {67}, p)
p = plan(["link2"], VAGINA, 100)
check("只有联结II：80 / 20", p.main == 80 and set(dict(p.side).values()) == {20}, p)
p = plan(["link1"], VAGINA, 5)
check("联结裸增量为 0 时不列 side", p.main == 5 and p.side == (), p)
p = plan(["boost:breast"], VAGINA, 100)
check("其他部位的单部位强化不影响本部位", p.main == 100, p)
p = plan(["all_boost"], 23, 10)
check("心理快感也吃全部位", p.main == 15, p)

print("==== 转化与欲情 ====")
check("苦痛快感化：17 转心理", plan(["pain_to_mind"], 17, 30).to_mind)
check("苦痛快感化不管 18/19/20", not any(plan(["pain_to_mind"], sid, 30).to_mind for sid in (18, 19, 20)))
check("负面情感快感化：17/18/19/20 都转心理", all(plan(["negative_to_mind"], sid, 30).to_mind for sid in (17, 18, 19, 20)))
check("媚药式：欲情 ×1.5 取整", plan(["aphrodisiac"], 12, 33).main == 49)
check("无媚药式：欲情原样", plan(["all_boost"], 12, 33).main == 33)
check("非快感非转化状态原样", plan(["all_boost", "link1"], 15, 40) == effects.GainPlan(40, False, ()))

print("==== 每日欲望增长 ====")
aph = effects.compile_profile(frozenset({"aphrodisiac"}))
none = effects.compile_profile(frozenset())
check("dp=10,g=5：先抬到 60 再 +10 → 增量 60", effects.daily_growth(aph, 10, 5) == 60)
check("dp=90,g=5：增量 10", effects.daily_growth(aph, 90, 5) == 10)
check("无媚药式：原增量", effects.daily_growth(none, 10, 5) == 5)
check("媚药式欲望下限 60", aph.desire_floor == 60 and none.desire_floor == 0)

print("==== 寸止压制判定 ====")


def rolls(*values):
    """ 按顺序给出随机数；用完再调用就报错，用来确认不该掷骰时没掷 """
    it = iter(values)
    return lambda: next(it)


judge = effects.judge_edge_suppress
check("强度 1、耐久上限 10", effects.EDGE_POWER == 1 and effects.EDGE_DURABILITY == 10)
check("超出 <=1 必成功，耐久不变", judge(1, 10, rolls(0.999)) == ("rescue", 10) and judge(-5, 10, rolls(0.999)) == ("rescue", 10))
check("超出 3：首判成功率 0.85^2", judge(3, 10, rolls(0.72)) == ("rescue", 10) and judge(3, 10, rolls(0.73, 0.84)) == ("rescue", 9))
check("每失败一次耐久 -1、阈值临时 +1", judge(3, 10, rolls(0.99, 0.99, 0.999)) == ("rescue", 8))
check("一次判定里耐久从 10 掉到 0：勉强成功，耐久置 -1", judge(30, 10, rolls(*[0.99] * 10)) == ("exhaust", -1))
check("耐久 1 掉到 0 也算勉强成功", judge(30, 1, rolls(0.99)) == ("exhaust", -1))
check("耐久 -1：直接失败，不掷骰", judge(30, -1, rolls()) == ("fail", -1) and judge(0, -1, rolls()) == ("fail", -1))
check("勉强成功提示带名字占位", "{NPCName}" in effects.EDGE_EXHAUST_TEXT)
check("寸止压制标志", effects.compile_profile(frozenset({"edge_suppress"})).edge_suppress and not none.edge_suppress)

print("==== 槽位与确认 ====")
check("槽位求和", effects.slots_of(["boost:vagina", "all_boost", "link2"]) == 11)
check("重复键只算一次", effects.slots_of(["link1", "link1"]) == 4)
check("Profile.slots_used 与 slots_of 一致", effects.compile_profile(frozenset({"link1", "aphrodisiac"})).slots_used == 6)
empty = frozenset()
check("选择未改变不能确认", not effects.can_confirm(empty, empty))
check("新刻印空选择也不能确认（未改变）", not effects.can_confirm(frozenset(), frozenset()))
check("10 格以内且改变可确认", effects.can_confirm(empty, frozenset({"link2", "all_boost"})))
check("超过 10 格不能确认", not effects.can_confirm(empty, frozenset({"link2", "all_boost", "boost:vagina"})))
check("调整为空集合可确认（清空效果）", effects.can_confirm(frozenset({"link1"}), empty))

print("==== 效果表 ====")
check("共 18 项效果", len(effects.EFFECTS) == 18)
check("效果键唯一", len(effects.EFFECT_BY_KEY) == 18)
check("11 个单部位各 1 格", sum(1 for e in effects.EFFECTS if e.kind == "boost_part" and e.slots == 1) == 11)
expected = {"all_boost": 4, "pain_to_mind": 2, "negative_to_mind": 3, "aphrodisiac": 2, "link1": 4, "link2": 6, "edge_suppress": 3}
check("其他效果槽位同 spec", all(effects.EFFECT_BY_KEY[k].slots == v for k, v in expected.items()))
names = {e.key: e.name for e in effects.EFFECTS}
check("spec 名称", names["aphrodisiac"] == "媚药式" and names["edge_suppress"] == "寸止压制" and names["link2"] == "快感联结II")
check("存档键只用 ASCII", all(k.isascii() for k in effects.EFFECT_BY_KEY))
check("寸止压制两条文本同 spec", effects.EDGE_RESCUE_TEXTS == ("{NPCName}的寸止险些失败，依靠淫纹才压制住奔涌的快感", "{NPCName}的大量快感被淫纹抑制，浑身剧烈颤抖却无法高潮"))

finish()
