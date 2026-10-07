# -*- coding: UTF-8 -*-
"""
指令与前提注册

三个指令都放在群交模式的"技艺"类别（ARTS / 子类型 ARTS），web 归入 arts / arts_hypnosis、关联身体部位 head：
    group_sex_extension_edge_all             "全员寸止"
    group_sex_extension_equip_toys_all       "全员戴上玩具"
    group_sex_extension_hypnosis_boost_all   "全员催眠增强"（另需至少两名完全催眠参与者）

绕开 add_instruct 的已知陷阱（Script/System/Instruct_System/handle_instruct.py add_instruct）：
1. 没有 CSV 行时 panel_id 未绑定 → UnboundLocalError：先注入 InstructConfig 到 config_instruct / config_instruct_by_id，
   且不设 panel_id 属性（getattr 默认 None）
2. 不传 behavior_id 默认 share_blankly，会覆盖 behavior_id_to_instruct_id["share_blankly"] → 行为id传指令id本身
3. cid 映射只从配置读，缺失则 Tk 按钮编号为 0 → 注入的 InstructConfig 带动态分配的 cid（与其他 mod 不撞）
4. 不给 web_category 时会读处理函数源码推断大类 → 注入 web_category=CHARACTER，不靠推断
5. web 按小类列指令 → 注入 web_major_type / web_minor_type / body_parts
传了 premise_set 就不再按 h_mode_show_type / tired_type 自动补前提：本 mod 只要群交模式前提，正合适。
"""

from Script.Config import config_def, game_config
from Script.Core import constant, constant_promise, get_text

# 先于本包的 members/actions 导入 handle_instruct，让本体模块按它自己的链路初始化（members 用到的 group_sex_panel 等随之就位）
from Script.System.Instruct_System import handle_instruct

from . import MOD_ID, actions, members

_ = get_text._
""" 翻译api """

EDGE_ALL_ID = "group_sex_extension_edge_all"
""" 全员寸止指令id """
EQUIP_TOYS_ALL_ID = "group_sex_extension_equip_toys_all"
""" 全员戴上玩具指令id """
HYPNOSIS_BOOST_ALL_ID = "group_sex_extension_hypnosis_boost_all"
""" 全员催眠增强指令id """

P_COMPLETE_HYPNOSIS_GE_2 = "group_sex_extension_complete_hypnosis_ge_2"
""" 前提：群交参与者中至少两名已完全催眠 """

CID_SEARCH_START = 4900
""" 分配 cid 的起点：ARTS 段(41xx)之后、5xxx 之前的空档；cid 不进存档，每次加载重新分配 """
WEB_MAJOR_TYPE = "arts"
""" web 大类 """
WEB_MINOR_TYPE = "arts_hypnosis"
""" web 小类 """
BODY_PARTS = "head"
""" 关联身体部位 """


def register_all() -> None:
    """
    注册 1 个前提、注入 3 条 InstructConfig、注册 3 个指令
    Keyword arguments:
    无
    Return arguments:
    None
    """
    _register_premise()
    group_sex_on = {constant_promise.Premise.GROUP_SEX_MODE_ON}
    table = (
        (EDGE_ALL_ID, _("全员寸止"), group_sex_on, actions.edge_all),
        (EQUIP_TOYS_ALL_ID, _("全员戴上玩具"), group_sex_on, actions.equip_toys_all),
        (HYPNOSIS_BOOST_ALL_ID, _("全员催眠增强"), group_sex_on | {P_COMPLETE_HYPNOSIS_GE_2}, actions.hypnosis_boost_all),
    )
    for instruct_id, name, premise_set, handler in table:
        _inject_config(instruct_id, name, _alloc_cid())
        handle_instruct.add_instruct(
            instruct_id,
            constant.InstructType.ARTS,
            name,
            set(premise_set),
            behavior_id=instruct_id,
            sub_type=constant.SexInstructSubType.ARTS,
        )(handler)


def premise_complete_hypnosis_ge_2(character_id: int) -> int:
    """
    前提：群交参与者中至少有 MIN_HYPNOSIS_BOOST_MEMBERS 名已完全催眠（不看当前是否处于催眠状态）
    Keyword arguments:
    character_id -- 角色id（指令前提以玩家 0 调用，不使用）
    Return arguments:
    int -- 1 满足，0 不满足
    """
    return int(len(members.complete_hypnosis_member_ids()) >= actions.MIN_HYPNOSIS_BOOST_MEMBERS)


def _register_premise() -> None:
    """
    把前提函数写进 constant.handle_premise_data；键已被别人占用则抛错（防两个 mod 撞名）
    Keyword arguments:
    无
    Return arguments:
    None
    """
    existing = constant.handle_premise_data.get(P_COMPLETE_HYPNOSIS_GE_2)
    if existing is not None and existing is not premise_complete_hypnosis_ge_2:
        raise RuntimeError(f"[{MOD_ID}] 前提键 {P_COMPLETE_HYPNOSIS_GE_2} 已被占用")
    constant.handle_premise_data[P_COMPLETE_HYPNOSIS_GE_2] = premise_complete_hypnosis_ge_2


def _alloc_cid() -> int:
    """
    从 CID_SEARCH_START 起找第一个 config_instruct 与 cid_to_instruct_id 都没用的 cid
    Keyword arguments:
    无
    Return arguments:
    int -- 可用 cid
    """
    cid = CID_SEARCH_START
    while cid in game_config.config_instruct or cid in constant.cid_to_instruct_id:
        cid += 1
    return cid


def _inject_config(instruct_id: str, name: str, cid: int) -> None:
    """
    构造 config_def.InstructConfig 并写入 game_config.config_instruct[cid] 与 config_instruct_by_id[instruct_id]
    只设 add_instruct 从配置里读的那几项；类型、子类型、前提、行为id 由 add_instruct 的参数给出，panel_id 不设
    Keyword arguments:
    instruct_id -- 指令id
    name -- 显示名
    cid -- 分配到的 cid
    Return arguments:
    None
    """
    config = config_def.InstructConfig()
    config.cid = cid
    config.instruct_id = instruct_id
    config.name = name
    config.web_category = constant.InstructCategory.CHARACTER
    config.web_major_type = WEB_MAJOR_TYPE
    config.web_minor_type = WEB_MINOR_TYPE
    config.body_parts = BODY_PARTS
    game_config.config_instruct[cid] = config
    game_config.config_instruct_by_id[instruct_id] = cid
