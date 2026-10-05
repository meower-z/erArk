# -*- coding: UTF-8 -*-
"""
淫纹指令与前提注册

一个处理函数、两个指令 id（按钮名不同、前提互斥）：
    mod_lewd_tattoo_apply   "刻印淫纹"   目标没有淫纹时出现
    mod_lewd_tattoo_adjust  "调整淫纹"   目标已有淫纹时出现
不用"一个 id 运行时改名"：handle_instruct_name_data 是全局表，改名要在每次绘制前改写，等于再造一个钩子。

绕开 add_instruct 的已知陷阱（Script/System/Instruct_System/handle_instruct.py add_instruct）：
1. 没有 CSV 行时 panel_id 未绑定 → UnboundLocalError：先注入 InstructConfig 到 config_instruct / config_instruct_by_id，
   且不设 panel_id 属性（getattr 默认 None）
2. 传了 premise_set 就不再按 h_mode_show_type / tired_type 自动补前提 → 手动补 NOT_H、NOT_SHOW_NON_H_IN_HIDDEN_SEX、TIRED_LE_84、HP_G_1、DRUNK_LEVEL_NOT_3
3. 不传 behavior_id 默认 share_blankly，会覆盖 behavior_id_to_instruct_id["share_blankly"] → 每个 id 传一个独有的假行为串
4. cid 映射只从配置读，缺失则 Tk 按钮编号为 0 → 注入的 InstructConfig 带 cid
5. web 按小类列指令 → 注入 web_major_type="arts"、web_minor_type="arts_hypnosis"、body_parts="belly"
"""
from Script.Config import config_def, game_config
from Script.Core import cache_control, constant, constant_promise, get_text

from . import MOD_ID, effects, store

_ = get_text._
""" 翻译api """

APPLY_ID = "mod_lewd_tattoo_apply"
""" 刻印指令id """
ADJUST_ID = "mod_lewd_tattoo_adjust"
""" 调整指令id """

P_TARGET_ELIGIBLE = "mod_lewd_tattoo_target_eligible"
""" 前提：交互对象陷落等级==4 或 被监禁 """
P_SANITY_ENOUGH = "mod_lewd_tattoo_sanity_enough"
""" 前提：玩家理智 >= SANITY_COST """
P_TARGET_HAS = "mod_lewd_tattoo_target_has"
""" 前提：交互对象已有淫纹 """
P_TARGET_HAS_NOT = "mod_lewd_tattoo_target_has_not"
""" 前提：交互对象没有淫纹 """

SANITY_COST = 100
""" 每次刻印/调整的理智消耗 """
CID_SEARCH_START = 4900
""" 分配 cid 的起点：ARTS 段(41xx)之后、5xxx 之前的空档；cid 不进存档，每次加载重新分配 """


def register_all() -> None:
    """
    注册 4 个前提、注入 2 条 InstructConfig、注册 2 个指令
    Keyword arguments:
    无
    Return arguments:
    None
    """
    from Script.System.Instruct_System import handle_instruct

    _register_premises()
    common = {
        constant_promise.Premise.HAVE_TARGET,
        constant_promise.Premise.NOT_H,
        constant_promise.Premise.NOT_SHOW_NON_H_IN_HIDDEN_SEX,
        constant_promise.Premise.TIRED_LE_84,
        constant_promise.Premise.HP_G_1,
        constant_promise.Premise.DRUNK_LEVEL_NOT_3,
        P_TARGET_ELIGIBLE,
        P_SANITY_ENOUGH,
    }
    for instruct_id, name, extra in ((APPLY_ID, _("刻印淫纹"), P_TARGET_HAS_NOT), (ADJUST_ID, _("调整淫纹"), P_TARGET_HAS)):
        _inject_config(instruct_id, name, _alloc_cid())
        handle_instruct.add_instruct(
            instruct_id,
            constant.InstructType.ARTS,
            name,
            common | {extra},
            behavior_id=f"{instruct_id}_behavior",
            sub_type=constant.SexInstructSubType.ARTS,
        )(handle_tattoo_instruct)


def _target_id() -> int:
    """
    玩家当前交互对象id
    Keyword arguments:
    无
    Return arguments:
    int -- 交互对象id；没有交互对象时为 0
    """
    target_id = cache_control.cache.character_data[0].target_character_id
    if target_id not in cache_control.cache.character_data:
        return 0
    return target_id


def premise_target_eligible(character_id: int) -> int:
    """
    前提：交互对象陷落等级==4 或 被监禁
    Keyword arguments:
    character_id -- 角色id（指令前提以玩家 0 调用）
    Return arguments:
    int -- 1 满足，0 不满足
    """
    from Script.Design import attr_calculation

    target_id = _target_id()
    if target_id == 0:
        return 0
    target_data = cache_control.cache.character_data[target_id]
    return int(attr_calculation.get_character_fall_level(target_id) == 4 or target_data.sp_flag.imprisonment == 1)


def premise_sanity_enough(character_id: int) -> int:
    """
    前提：玩家理智足够支付一次刻印/调整
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 1 满足，0 不满足
    """
    return int(cache_control.cache.character_data[character_id].sanity_point >= SANITY_COST)


def premise_target_has(character_id: int) -> int:
    """
    前提：交互对象已有淫纹
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 1 满足，0 不满足
    """
    target_id = _target_id()
    return int(target_id != 0 and store.has_tattoo(target_id))


def premise_target_has_not(character_id: int) -> int:
    """
    前提：交互对象没有淫纹
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    int -- 1 满足，0 不满足
    """
    target_id = _target_id()
    return int(target_id != 0 and not store.has_tattoo(target_id))


def _register_premises() -> None:
    """
    把 4 个前提函数写进 constant.handle_premise_data；键已被别人占用则抛错（防两个 mod 撞名）
    Keyword arguments:
    无
    Return arguments:
    None
    """
    table = {
        P_TARGET_ELIGIBLE: premise_target_eligible,
        P_SANITY_ENOUGH: premise_sanity_enough,
        P_TARGET_HAS: premise_target_has,
        P_TARGET_HAS_NOT: premise_target_has_not,
    }
    for key, fn in table.items():
        existing = constant.handle_premise_data.get(key)
        if existing is not None and existing is not fn:
            raise RuntimeError(f"[{MOD_ID}] 前提键 {key} 已被占用")
        constant.handle_premise_data[key] = fn


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
    不设 panel_id / premise_set / behavior_id（这三项由 add_instruct 的参数给出）
    Keyword arguments:
    instruct_id -- 指令id
    name -- 显示名
    cid -- 分配到的 cid
    Return arguments:
    None
    """
    old_cid = game_config.config_instruct_by_id.get(instruct_id)
    if old_cid is not None:
        # 重复安装（只在测试里出现）：沿用旧 cid 的配置
        return
    config = config_def.InstructConfig()
    config.cid = cid
    config.instruct_id = instruct_id
    config.name = name
    config.instruct_type = "ARTS"
    config.instruct_sub_type = "ARTS"
    config.h_mode_show_type = 1
    config.tired_type = 1
    config.web_category = 2
    config.web_major_type = "arts"
    config.web_minor_type = "arts_hypnosis"
    config.body_parts = "belly"
    game_config.config_instruct[cid] = config
    game_config.config_instruct_by_id[instruct_id] = cid


def handle_tattoo_instruct() -> None:
    """
    刻印/调整共用处理：打开效果选择面板；确认才写入并扣理智，返回不扣；不推进时间
    Keyword arguments:
    无
    Return arguments:
    None
    """
    from . import hooks, ui

    pl_data = cache_control.cache.character_data[0]
    target_id = pl_data.target_character_id
    current = store.view(target_id)
    # 不认识的数据：不许调整，原数据不动
    if current.present and not current.active:
        ui.draw_refused(target_id, current.problem)
        return
    chosen = ui.ask_for_effects(target_id, current.keys if current.present else None)
    if chosen is None:
        return
    store.write(target_id, chosen)
    # 媚药式：提交时立刻钳一次欲望值
    hooks.clamp_desire(cache_control.cache.character_data[target_id], effects.compile_profile(chosen))
    pl_data.sanity_point = max(pl_data.sanity_point - SANITY_COST, 0)
    pl_data.pl_ability.today_sanity_point_cost += SANITY_COST
    ui.draw_result(target_id, not current.present, chosen)
