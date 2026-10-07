# -*- coding: UTF-8 -*-
"""
群交功能扩展 mod 无头测试：经 ModManager 加载（不改 mod/mod_config.json），用真实本体表与 fixture 角色验证
覆盖：注册表逐项核对（类型/子类型/名字/大类/web 大小类/身体部位/前提/行为映射）、cid 分配与淫纹 mod 不撞、
重复 install 无副作用、参与者收集（模板 ∪ 场景、滤掉非 H 与失效id）、三个指令的效果与提示、前提与 web 可见性
用法：python3 -u mod/group_sex_extension/tests/test_group_sex_extension_mod.py
"""

import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(TESTS_DIR, "..", "..", "..", "tools", "tests", "education"))
from _bootstrap import *  # noqa: F401,F403,E402  复用生长养成测试的无头引导（初始化配置、屏蔽绘制、make_character）
from _bootstrap import SCENE_DORM, SCENE_NURSERY, cache, check, drawn_text, finish, make_character, pl, section  # noqa: E402

from Script.Core import constant, constant_promise, mod_manager  # noqa: E402
from Script.Design import handle_premise, web_interaction_manager  # noqa: E402

SHARE_BLANKLY_BEFORE = constant.behavior_id_to_instruct_id.get("share_blankly")
""" 加载 mod 前 share_blankly 对应的指令（mod 不得覆盖） """

# ==== 加载 mod（淫纹 mod 在则先加载，验证两者 cid 不撞） ====
section("加载")
manager = mod_manager.ModManager()
infos = {info.mod_id: info for info in manager.scan_mods()}
LOADED = [mod_id for mod_id in ("lewd_tattoo", "group_sex_extension") if mod_id in infos]
for mod_id in LOADED:
    manager._load_single_mod(infos[mod_id])
check("淫纹 mod 已加载（不在则只测本 mod）", "lewd_tattoo" not in LOADED or "_erark_mod_lewd_tattoo" in sys.modules)
check("本 mod 已安装", getattr(sys.modules.get("_erark_mod_group_sex_extension"), "_installed", False))
import _erark_mod_group_sex_extension as package  # noqa: E402
from _erark_mod_group_sex_extension import actions, instruct, members  # noqa: E402

IDS = (instruct.EDGE_ALL_ID, instruct.EQUIP_TOYS_ALL_ID, instruct.HYPNOSIS_BOOST_ALL_ID)
NAMES = {instruct.EDGE_ALL_ID: "全员寸止", instruct.EQUIP_TOYS_ALL_ID: "全员戴上玩具", instruct.HYPNOSIS_BOOST_ALL_ID: "全员催眠增强"}


def table(instruct_id: str) -> dict:
    """
    取一个指令在本体各张注册表里的值（cid 单独核对）
    Keyword arguments:
    instruct_id -- 指令id
    Return arguments:
    dict -- 表名 → 值
    """
    return {
        "handler": instruct_id in constant.handle_instruct_data,
        "premises": set(constant.instruct_premise_data.get(instruct_id, ())),
        "types": {t for t, ids in constant.instruct_type_data.items() if instruct_id in ids},
        "sub_type": constant.instruct_sub_type_data.get(instruct_id),
        "name": constant.handle_instruct_name_data.get(instruct_id),
        "category": constant.instruct_category_data.get(instruct_id),
        "panel_id": constant.instruct_panel_id_data.get(instruct_id),
        "major": constant.instruct_major_type_data.get(instruct_id),
        "minor": constant.instruct_minor_type_data.get(instruct_id),
        "body_parts": constant.instruct_body_parts_data.get(instruct_id),
        "behaviors": {b for b, i in constant.behavior_id_to_instruct_id.items() if i == instruct_id},
    }


def expected(instruct_id: str) -> dict:
    """
    重构前（scripts/group_sex_extension.py 1.1.0）实测的注册值
    Keyword arguments:
    instruct_id -- 指令id
    Return arguments:
    dict -- 表名 → 值
    """
    premises = {constant_promise.Premise.GROUP_SEX_MODE_ON}
    if instruct_id == instruct.HYPNOSIS_BOOST_ALL_ID:
        premises.add(instruct.P_COMPLETE_HYPNOSIS_GE_2)
    return {
        "handler": True,
        "premises": premises,
        "types": {constant.InstructType.ARTS},
        "sub_type": constant.SexInstructSubType.ARTS,
        "name": _(NAMES[instruct_id]),
        "category": constant.InstructCategory.CHARACTER,
        "panel_id": None,
        "major": "arts",
        "minor": "arts_hypnosis",
        "body_parts": ["head"],
        "behaviors": {instruct_id},
    }


# ==== 注册表 ====
section("注册表")
for instruct_id in IDS:
    actual, want = table(instruct_id), expected(instruct_id)
    for key in want:
        check(f"{instruct_id}.{key}", actual[key] == want[key], f"实际={actual[key]!r} 期望={want[key]!r}")
    cid = constant.instruct_id_to_cid.get(instruct_id)
    check(f"{instruct_id} cid≥{instruct.CID_SEARCH_START} 且双向映射", cid is not None and cid >= instruct.CID_SEARCH_START and constant.cid_to_instruct_id.get(cid) == instruct_id, cid)
check("前提已登记", constant.handle_premise_data.get(instruct.P_COMPLETE_HYPNOSIS_GE_2) is instruct.premise_complete_hypnosis_ge_2)
check("share_blankly 映射未被覆盖", constant.behavior_id_to_instruct_id.get("share_blankly") == SHARE_BLANKLY_BEFORE)
all_cids = list(constant.instruct_id_to_cid.values())
check(f"全部 cid 不重复（已加载 {LOADED}）", len(all_cids) == len(set(all_cids)))
check("全部 cid 双向一致", all(constant.cid_to_instruct_id.get(c) == i for i, c in constant.instruct_id_to_cid.items()))
cids_before = {i: constant.instruct_id_to_cid[i] for i in IDS}
package.install()
check("重复 install 不再注册", {i: constant.instruct_id_to_cid[i] for i in IDS} == cids_before and len(constant.instruct_id_to_cid) == len(all_cids))

# ==== 参与者 ====
section("参与者")
TEMPLATE_ONLY, SCENE_H, SCENE_NOT_H, STALE = 9101, 9102, 9103, 9104
pl.position = list(SCENE_DORM)
in_template = make_character(TEMPLATE_ONLY, "模板干员", position=SCENE_NURSERY)
in_scene = make_character(SCENE_H, "场景干员")
bystander = make_character(SCENE_NOT_H, "旁观干员")
in_template.sp_flag.is_h = True
in_scene.sp_flag.is_h = True
template_a = pl.h_state.group_sex_body_template_dict["A"]
template_a[0]["mouth"][0] = TEMPLATE_ONLY
template_a[1][0] = [STALE]
check("模板 ∪ 场景，只留 H 中且存在的 NPC", members.member_ids() == [TEMPLATE_ONLY, SCENE_H], members.member_ids())

# ==== 全员寸止 ====
section("全员寸止")
feel_ids = [state_id for state_id, state_config in game_config.config_character_state.items() if state_config.type == 0]
for character_data in (in_template, in_scene, bystander):
    for state_id in feel_ids:
        character_data.h_state.orgasm_edge_count[state_id] = 3
in_scene.h_state.orgasm_edge = 1
drawn_text.clear()
constant.handle_instruct_data[instruct.EDGE_ALL_ID]()
check("提示 1/2", drawn_text == [_("\n已为{0}/{1}名干员开启寸止模式\n").format(1, 2)], drawn_text)
check("新开启者寸止且次数清零", in_template.h_state.orgasm_edge == 1 and all(in_template.h_state.orgasm_edge_count[s] == 0 for s in feel_ids))
check("已在寸止者不动次数", all(in_scene.h_state.orgasm_edge_count[s] == 3 for s in feel_ids))
check("非参与者不动", bystander.h_state.orgasm_edge == 0 and all(bystander.h_state.orgasm_edge_count[s] == 3 for s in feel_ids))
drawn_text.clear()
constant.handle_instruct_data[instruct.EDGE_ALL_ID]()
check("再按一次提示 0/2", drawn_text == [_("\n已为{0}/{1}名干员开启寸止模式\n").format(0, 2)], drawn_text)

# ==== 全员戴上玩具 ====
section("全员戴上玩具")
in_template.h_state.body_item[0][1] = True
in_template.h_state.body_item[0][2] = "keep"
drawn_text.clear()
constant.handle_instruct_data[instruct.EQUIP_TOYS_ALL_ID]()
check("提示 2/2 新增 7 件", drawn_text == [_("\n已为{0}/{1}名干员戴上玩具，共新增{2}件\n").format(2, 2, 7)], drawn_text)
check("参与者四件全戴上", all(cd.h_state.body_item[i][1] for cd in (in_template, in_scene) for i in actions.TOY_BODY_ITEM_IDS))
check("已戴的不重置", in_template.h_state.body_item[0][2] == "keep")
check("新戴的清空附带数据", all(in_scene.h_state.body_item[i][2] is None for i in actions.TOY_BODY_ITEM_IDS))
check("非参与者不动", not any(bystander.h_state.body_item[i][1] for i in actions.TOY_BODY_ITEM_IDS))
drawn_text.clear()
constant.handle_instruct_data[instruct.EQUIP_TOYS_ALL_ID]()
check("再按一次提示 0/2 新增 0 件", drawn_text == [_("\n已为{0}/{1}名干员戴上玩具，共新增{2}件\n").format(0, 2, 0)], drawn_text)

# ==== 全员催眠增强：前提与可见性 ====
section("全员催眠增强")
cache.group_sex_mode = 1


def visible_ids() -> set:
    """
    web 面板按小类与身体部位能看到的本 mod 指令
    Keyword arguments:
    无
    Return arguments:
    set -- 指令id集合（两种查法取交集）
    """
    by_minor = set(web_interaction_manager.get_instructs_by_minor_type("arts_hypnosis"))
    by_head = set(web_interaction_manager.get_instructs_by_body_part("head"))
    return by_minor & by_head & set(IDS)


in_template.talent[members.COMPLETE_HYPNOSIS_TALENT] = 1
bystander.hypnosis.hypnosis_degree = members.COMPLETE_HYPNOSIS_DEGREE
check("只有一名完全催眠参与者：前提不满足", handle_premise.handle_premise(instruct.P_COMPLETE_HYPNOSIS_GE_2, 0) == 0)
check("只有一名：增强按钮不显示", visible_ids() == {instruct.EDGE_ALL_ID, instruct.EQUIP_TOYS_ALL_ID}, visible_ids())
drawn_text.clear()
constant.handle_instruct_data[instruct.HYPNOSIS_BOOST_ALL_ID]()
check("直接调用：只画拒绝提示", drawn_text == [_("\n当前完全催眠的群交干员不足{0}人，无法执行全员催眠增强\n").format(2)], drawn_text)
check("直接调用：不改任何人", not any(cd.hypnosis.increase_body_sensitivity or cd.hypnosis.pain_as_pleasure for cd in (in_template, in_scene, bystander)))

in_scene.hypnosis.hypnosis_degree = members.COMPLETE_HYPNOSIS_DEGREE
in_scene.hypnosis.pain_as_pleasure = True
unconscious_before = {cd.cid: cd.sp_flag.unconscious_h for cd in (in_template, in_scene)}
check("两名（素质 + 催眠度）：前提满足", handle_premise.handle_premise(instruct.P_COMPLETE_HYPNOSIS_GE_2, 0) == 1)
check("两名：三个按钮都显示", visible_ids() == set(IDS), visible_ids())
drawn_text.clear()
constant.handle_instruct_data[instruct.HYPNOSIS_BOOST_ALL_ID]()
check("提示 2 名，新增敏感 2 苦痛 1", drawn_text == [_("\n已为{0}名完全催眠干员设置敏感度上升与苦痛快感化（新增敏感度上升{1}人，新增苦痛快感化{2}人）\n").format(2, 2, 1)], drawn_text)
check("参与者两项都开", all(cd.hypnosis.increase_body_sensitivity and cd.hypnosis.pain_as_pleasure for cd in (in_template, in_scene)))
check("不改催眠状态", {cd.cid: cd.sp_flag.unconscious_h for cd in (in_template, in_scene)} == unconscious_before)
check("完全催眠的非参与者不动", not bystander.hypnosis.increase_body_sensitivity and not bystander.hypnosis.pain_as_pleasure)

cache.group_sex_mode = 0
check("群交模式关闭：三个按钮都不显示", visible_ids() == set(), visible_ids())

finish()
