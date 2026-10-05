# -*- coding: UTF-8 -*-
"""
淫纹 mod 无头冒烟测试：经 ModManager 加载（不改 mod/mod_config.json），走真实本体结算函数验证效果
覆盖：快感状态表核对、指令/前提注册与可见性、H1 倍率与联结、苦痛/负面转心理、直写点、欲望锁、
寸止压制、每日增长、信息页、指令面板（刻印/调整/返回）、不认识的数据
用法：python3 mod/lewd_tattoo/tests/test_smoke.py
"""
import os
import random
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(TESTS_DIR, "..", "..", "..", "tools", "tests", "education"))
from _bootstrap import *  # noqa: F401,F403,E402  复用生长养成测试的无头引导（初始化配置、屏蔽绘制、make_character）
from _bootstrap import cache, check, drawn_text, finish, make_character, section  # noqa: E402

from Script.Core import mod_hook, mod_manager  # noqa: E402
from Script.Settle import common_default, item_effect  # noqa: E402
from Script.Design import web_interaction_manager  # noqa: E402
from Script.UI.Panel import see_character_info_panel  # noqa: E402

# ==== 加载 mod ====
section("加载")
manager = mod_manager.ModManager()
infos = {info.mod_id: info for info in manager.scan_mods()}
manager._load_single_mod(infos["lewd_tattoo"])
from _erark_mod_lewd_tattoo import MOD_ID, effects, hooks, instruct, store, ui  # noqa: E402

check("mod 已加载", mod_hook.state_gain.has_fns())

# ==== 角色 ====
PL = cache.character_data[0] if 0 in cache.character_data else make_character(0, "博士")
PL.sex = 0
NPC_ID = 9001
npc = make_character(NPC_ID, "测试干员")
npc.sex = 1
PL.target_character_id = NPC_ID
FEEL = sorted(effects.FEEL_PARTS)


def set_tattoo(keys) -> None:
    """
    直接设定淫纹（None 为去掉）
    Keyword arguments:
    keys -- 效果键列表或 None
    Return arguments:
    None
    """
    npc.mod_data.pop(MOD_ID, None)
    if keys is not None:
        store.write(NPC_ID, keys)


def settle(state_id: int, keys, add_time: int = 10, base_value: int = 30, **kwargs):
    """
    清零全部快感与目标状态后，用本体 base_chara_state_common_settle 结算一次
    Keyword arguments:
    state_id -- 状态id
    keys -- 淫纹效果键列表；None 为没有淫纹
    add_time / base_value / kwargs -- 透传给本体结算函数
    Return arguments:
    tuple -- (各状态增量 dict, change_data)
    """
    set_tattoo(keys)
    for sid in FEEL + [12, 17, 18, 19, 20]:
        npc.status_data[sid] = 0
    change = game_type.CharacterStatusChange()
    common_default.base_chara_state_common_settle(NPC_ID, add_time, state_id, base_value, change_data=change, **kwargs)
    return dict(npc.status_data), change


# ==== 快感状态表 ====
section("快感状态表")
feel_in_config = {cid for cid, cfg in game_config.config_character_state.items() if cfg.type == 0}
check("FEEL_PARTS 与 CharacterState type==0 一致", feel_in_config == set(effects.FEEL_PARTS), feel_in_config)
check("心理快感状态名为'心理'", game_config.config_character_state[23].name == _("心理"))

# ==== 指令与前提 ====
section("指令注册")
for instruct_id in (instruct.APPLY_ID, instruct.ADJUST_ID):
    check(f"{instruct_id} 在 ARTS 类型", instruct_id in constant.instruct_type_data[constant.InstructType.ARTS])
    check(f"{instruct_id} 有 cid", constant.instruct_id_to_cid.get(instruct_id, 0) >= instruct.CID_SEARCH_START)
    check(f"{instruct_id} web 小类为催眠", constant.instruct_minor_type_data.get(instruct_id) == "arts_hypnosis")
    check(f"{instruct_id} 关联小腹", constant.instruct_body_parts_data.get(instruct_id) == ["belly"])
    check(f"{instruct_id} 带非H前提", constant_promise.Premise.NOT_H in constant.instruct_premise_data[instruct_id])
    check(f"{instruct_id} 不是系统面板类", constant.instruct_category_data.get(instruct_id) != constant.InstructCategory.SYSTEM_PANEL)


def visible() -> set:
    """
    本 mod 两个指令中前提全部满足的那些（按本体 web 列表函数判断，debug 模式关闭）
    Keyword arguments:
    无
    Return arguments:
    set -- 指令id集合
    """
    cache.debug_mode = False
    listed = set(web_interaction_manager.get_instructs_by_minor_type("arts_hypnosis"))
    return listed & {instruct.APPLY_ID, instruct.ADJUST_ID}


set_tattoo(None)
PL.sanity_point = 500
npc.sp_flag.imprisonment = 0
check("未陷落未监禁：两个都不出现", visible() == set())
npc.sp_flag.imprisonment = 1
check("被监禁、没淫纹：只出现刻印", visible() == {instruct.APPLY_ID}, visible())
web_parts = set(web_interaction_manager.get_instructs_by_body_part("belly"))
check("web 按小腹部位能列出刻印", instruct.APPLY_ID in web_parts)
set_tattoo([])
check("已有淫纹：只出现调整", visible() == {instruct.ADJUST_ID}, visible())
PL.sanity_point = 99
check("理智不足 100：不出现", visible() == set())
PL.sanity_point = 500
npc.sp_flag.imprisonment = 0
npc.talent[204] = 1
check("陷落等级 4（未监禁）：出现", visible() == {instruct.ADJUST_ID})
npc.talent[204] = 0
npc.sp_flag.imprisonment = 1
set_tattoo(None)

# ==== H1：倍率与联结 ====
section("快感倍率与联结")
base_status, _change = settle(4, None)
d0 = base_status[4]
check("无淫纹时阴道快感有正增量", d0 > 0, d0)
check("无淫纹时其他部位不动", all(base_status[s] == 0 for s in FEEL if s != 4))
status, change = settle(4, ["boost:vagina", "all_boost"])
check("单部位×全部位 = int(d0×2.25)", status[4] == int(d0 * 2.25), (d0, status[4]))
check("结算记录写的是改写后的值", change.status_data.get(4) == status[4])
status, change = settle(4, ["link1", "link2"])
expected = effects.plan_gain(effects.compile_profile(frozenset({"link1", "link2"})), 4, d0)
side = dict(expected.side)
check("联结I+II：本部位 int(d0×0.8)", status[4] == expected.main == int(d0 * 0.8), (status[4], expected))
present = hooks.present_feel_parts(NPC_ID)
check("女性没有阴茎、没兽部素质没有兽部", 3 not in present and 22 not in present and 23 in present)
check("联结只发给拥有的部位", all(status[s] == side[s] for s in present if s != 4) and status[3] == 0 and status[22] == 0, {s: status[s] for s in FEEL})
check("联结增量记进结算记录", all(change.status_data.get(s) == side[s] for s in present if s != 4))
npc.talent[112] = 1
status, _change = settle(4, ["link1", "link2"])
check("有兽角素质后兽部也得联结", status[22] == side[22])
npc.talent[112] = 0

# ==== 苦痛 / 负面 转心理 ====
section("转心理快感")
_s, _c = settle(23, None, add_time=10, base_value=0, ability_level=npc.ability[36], tenths_add=False)
m_ref = _s[23]
pain_status, _c = settle(17, None)
pain_raw = pain_status[17]
_s, _c = settle(23, None, add_time=pain_raw, base_value=0, ability_level=npc.ability[36], tenths_add=False)
m_from_pain = _s[23]
status, change = settle(17, ["pain_to_mind"])
check("苦痛快感化：苦痛不增加", status[17] == 0)
check("苦痛快感化：心理快感 = 以原增量递归结算的值", status[23] == m_from_pain and m_from_pain > 0, (status[23], m_from_pain))
check("转出的心理快感记进结算记录", change.status_data.get(23) == m_from_pain)
status, _c = settle(17, ["pain_to_mind", "all_boost"])
check("转出的心理快感也吃全部位倍率", status[23] == int(m_from_pain * 1.5), (status[23], m_from_pain))
status, _c = settle(17, ["pain_to_mind", "link1"])
link_side = effects.plan_gain(effects.compile_profile(frozenset({"link1"})), 23, m_from_pain).side
check("转出的心理快感也带联结", status[4] == dict(link_side).get(4, 0) and status[4] > 0, status[4])
status, _c = settle(17, ["negative_to_mind"])
check("只有负面情感快感化时苦痛照常", status[17] == pain_raw)
check("没有转化时心理快感参照值为正", m_ref > 0)

# 直写点：直写点的调用形状是 state_gain(v, cid, sid, None, change_data)；先按这个形状直接调钩子，再跑一个真实直写函数（item_effect 媚药）
section("直写点")
change = game_type.CharacterStatusChange()
set_tattoo(["negative_to_mind"])
npc.status_data[23] = 0
result = mod_hook.state_gain(40, NPC_ID, 20, None, change)
check("直写点负面转心理：返回 None", result is None)
check("直写点转出的心理记进交互对象记录", change.target_change[NPC_ID].status_data.get(23, 0) == npc.status_data[23] > 0)
set_tattoo(["aphrodisiac"])
npc.status_data[12] = 0
change = game_type.CharacterStatusChange()
item_effect.handle_target_add_huge_desire_and_submit(0, 10, change, cache.game_time)
check("媚药道具直写欲情 ×1.5", npc.status_data[12] == 15000 and change.target_change[NPC_ID].status_data[12] == 15000, npc.status_data[12])

# ==== 欲望锁 ====
section("欲望锁")
set_tattoo(["aphrodisiac"])
npc.desire_point = 0
mod_hook.desire_written(npc)
check("desire_written 后钳到 60", npc.desire_point == 60)
npc.desire_point = 10
settle(4, ["aphrodisiac"])
check("任意状态结算时顺带钳到 60", npc.desire_point == 60)
npc.desire_point = 80
mod_hook.desire_written(npc)
check("高于 60 不动", npc.desire_point == 80)
set_tattoo(["link1"])
npc.desire_point = 0
mod_hook.desire_written(npc)
check("无媚药式不钳", npc.desire_point == 0)

# ==== 每日增长 ====
section("每日欲望增长")
set_tattoo(["aphrodisiac"])
npc.desire_point = 10
check("dp=10,g=5 → 增量 60", mod_hook.daily_desire_growth(5, NPC_ID) == 60)
set_tattoo(None)
check("没淫纹原样", mod_hook.daily_desire_growth(5, NPC_ID) == 5)

# ==== 寸止压制 ====
section("寸止压制")
fail_text = "\n尝试寸止测试干员的绝顶，但失败了\n"
set_tattoo(["edge_suppress"])
random.seed(1)
flag, text = mod_hook.edge_judged((False, fail_text), NPC_ID, -2)
check("k<=2 必定压制成功", flag is True)
check("提示替换为 spec 两条之一并带名字", text.strip() in {_(t).format(NPCName="测试干员") for t in effects.EDGE_RESCUE_TEXTS}, text)
check("本体成功时原样", mod_hook.edge_judged((True, "x"), NPC_ID, 5) == (True, "x"))
random.seed(2)
hits = sum(mod_hook.edge_judged((False, fail_text), NPC_ID, -3)[0] for _i in range(2000))
check("k=3 成功率约 0.85", 1600 < hits < 1800, hits)
set_tattoo(["link1"])
check("无寸止压制原样", mod_hook.edge_judged((False, fail_text), NPC_ID, -2) == (False, fail_text))

# ==== 信息页 ====
section("信息页")
set_tattoo(None)
panel = see_character_info_panel.SeeCharacterThirdPanel(NPC_ID, 80)
check("没淫纹不追加", not any(isinstance(d, ui.TattooInfoDraw) for d in panel.draw_list))
set_tattoo(["boost:vagina", "link1"])
panel = see_character_info_panel.SeeCharacterThirdPanel(NPC_ID, 80)
info = [d for d in panel.draw_list if isinstance(d, ui.TattooInfoDraw)]
check("有淫纹追加一个信息块", len(info) == 1)
drawn_text.clear()
info[0].draw()
joined = "".join(drawn_text)
check("信息块显示槽位与效果", "5/10" in joined and "阴道快感强化" in joined and "快感联结I" in joined, joined)
check("信息块 return_list 为空列表", info[0].return_list == [])
check("玩家页不追加（钩子对 cid 0 原样返回）", mod_hook.character_info_draw_list([], 0, 80) == [])

# ==== 指令面板 ====
section("指令面板")
answers = []
""" 面板脚本化输入 """
seen_lists = []
""" 每次 askfor_all 收到的可选列表 """


def scripted_askfor_all(return_list, *args, **kwargs):
    """
    按 answers 顺序作答的 askfor_all 桩
    Keyword arguments:
    return_list -- 可选列表
    Return arguments:
    str -- 本次答案
    """
    seen_lists.append(list(return_list))
    answer = answers.pop(0)
    assert answer in return_list, (answer, return_list)
    return answer


flow_handle.askfor_all = scripted_askfor_all
index_of = {effect.key: str(i) for i, effect in enumerate(effects.EFFECTS, start=1)}

# 返回不扣理智
set_tattoo(None)
PL.sanity_point = 500
PL.pl_ability.today_sanity_point_cost = 0
answers[:] = [_("返回")]
seen_lists.clear()
constant.handle_instruct_data[instruct.APPLY_ID]()
check("返回：没有淫纹、理智不变", not store.has_tattoo(NPC_ID) and PL.sanity_point == 500)
check("初始未改变时没有确认按钮", _("确认") not in seen_lists[0])
check("女性的阴茎强化不可选", index_of["boost:penis"] not in seen_lists[0] and index_of["boost:vagina"] in seen_lists[0])
check("没兽部素质的兽部强化不可选", index_of["boost:beast"] not in seen_lists[0])

# 刻印：选阴道强化 + 联结II(6) → 7 格，联结I(4) 放不下
answers[:] = [index_of["boost:vagina"], index_of["link2"], _("确认")]
seen_lists.clear()
constant.handle_instruct_data[instruct.APPLY_ID]()
check("刻印写入存档", store.view(NPC_ID).keys == frozenset({"boost:vagina", "link2"}))
check("刻印扣理智 100", PL.sanity_point == 400 and PL.pl_ability.today_sanity_point_cost == 100)
check("7 格时联结I(4格)不可选", index_of["link1"] not in seen_lists[-1])
check("选择改变后出现确认", _("确认") in seen_lists[-1])
check("存档形状", npc.mod_data[MOD_ID] == {"v": 1, "effects": ["boost:vagina", "link2"]})

# 调整：取消联结II、加媚药式 → 立刻钳欲望
npc.desire_point = 0
answers[:] = [index_of["link2"], index_of["aphrodisiac"], _("确认")]
constant.handle_instruct_data[instruct.ADJUST_ID]()
check("调整写入", store.view(NPC_ID).keys == frozenset({"boost:vagina", "aphrodisiac"}))
check("调整再扣 100", PL.sanity_point == 300)
check("加媚药式后立刻钳欲望", npc.desire_point == 60)

# 调整：改了又改回 → 没有确认，只能返回
answers[:] = [index_of["link1"], index_of["link1"], _("返回")]
seen_lists.clear()
constant.handle_instruct_data[instruct.ADJUST_ID]()
check("改回原样后没有确认按钮", _("确认") not in seen_lists[-1] and PL.sanity_point == 300)

# 超过上限的旧配置：已选项仍可取消
npc.mod_data[MOD_ID] = {"v": 1, "effects": ["link1", "link2", "all_boost"]}
answers[:] = [_("返回")]
seen_lists.clear()
constant.handle_instruct_data[instruct.ADJUST_ID]()
check("超上限旧配置：无确认，已选项可点", _("确认") not in seen_lists[0] and index_of["link2"] in seen_lists[0])
check("超上限旧配置照常生效", store.active_keys(NPC_ID) == frozenset({"link1", "link2", "all_boost"}))

# ==== 不认识的数据 ====
section("不认识的数据")
unknown = {"v": 2, "effects": ["boost:vagina", "future_x"], "extra": {"k": 1}}
npc.mod_data[MOD_ID] = {"v": 2, "effects": ["boost:vagina", "future_x"], "extra": {"k": 1}}
view = store.view(NPC_ID)
check("高版本：有淫纹但不激活", view.present and not view.active and view.problem)
check("不激活时 state_gain 原样", mod_hook.state_gain(77, NPC_ID, 4, None, None) == 77)
answers[:] = []
drawn_text.clear()
PL.sanity_point = 300
constant.handle_instruct_data[instruct.ADJUST_ID]()
check("调整被拒：不弹面板、不扣理智", PL.sanity_point == 300 and any("无法识别" in t for t in drawn_text))
check("原数据原样保留", npc.mod_data[MOD_ID] == unknown)
try:
    store.write(NPC_ID, ["link1"])
    check("store.write 拒绝改写不认识的数据", False)
except ValueError:
    check("store.write 拒绝改写不认识的数据", True)
npc.mod_data[MOD_ID] = {"v": 1, "effects": ["future_x"]}
check("未知效果键：不激活", store.active_keys(NPC_ID) is None)
drawn_text.clear()
ui.TattooInfoDraw(NPC_ID, 80).draw()
check("信息页告警", any("无法识别" in t for t in drawn_text))
npc.mod_data[MOD_ID] = {"effects": ["link1"], "note": "kept"}
check("缺 v 视为 1", store.active_keys(NPC_ID) == frozenset({"link1"}))
store.write(NPC_ID, ["link2"])
check("写回保留条目里的其他字段", npc.mod_data[MOD_ID] == {"effects": ["link2"], "note": "kept", "v": 1})

finish()
