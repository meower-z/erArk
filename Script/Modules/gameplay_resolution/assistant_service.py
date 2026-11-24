"""
助理任命服务（assistant_service）
=================================
提供助理候选角色筛选、每周随机抽选助理与助理更换逻辑。
提示文本经 ui_hooks.emit_notice 发出。
分隔线经 ui_hooks.emit_divider 发出。
本模块不直接导入界面模块，供每日结算每周轮换与助理面板调用。
"""

import random
from types import FunctionType

from Script.Core import get_text
from Script.Design import attr_calculation, handle_premise, map_handle
from Script.Design import second_behavior
from Script.Modules.domains import chara_life, flags, identity, relations
from Script.Modules.domains import roster, visitor, work
from Script.Modules.gameplay_resolution import ui_hooks

_: FunctionType = get_text._
""" 翻译api """


def get_assistant_candidates() -> list[int]:
    """
    按 roster.active_sorted() 顺序筛选可担任助理的角色编号。
    筛选跳过玩家（编号 0）、监狱长、访客以及 handle_premise.handle_unnormal_27 为真的角色。
    其中状态 2 指监禁或产程等 AI 停摆状态。
    状态 7 指外勤或逃跑等离线状态。
    Return arguments:
    list[int] -- 按名册顺序排列的候选角色编号列表
    """
    candidates = []
    npc_id_got_list = list(roster.active_sorted())
    for npc_id in npc_id_got_list:
        if npc_id == 0:
            continue
        if handle_premise.handle_unnormal_27(npc_id):
            continue
        if npc_id == work.warden():
            continue
        if visitor.is_visitor(npc_id):
            continue
        candidates.append(npc_id)
    return candidates


def select_random_assistant() -> None:
    """
    从 get_assistant_candidates() 返回的候选中随机抽取一名角色担任本周助理。
    函数经 ui_hooks.emit_notice 发出按文本宽度排版的等待提示，再调用 assistant_replace。
    候选列表不排除当前助理。
    若抽中当前助理，函数会将其编号传给 assistant_replace，进而卸任该助理并使玩家当前无助理。
    Return arguments:
    None -- 无返回值
    """
    assistant_id = random.choice(get_assistant_candidates())
    info_text = _("\n○本周抽签选中了{0}作为{1}的助理\n").format(
        identity.of(assistant_id).name, identity.of(0).name
    )
    ui_hooks.emit_notice(info_text, wait=True, use_text_width=True)
    assistant_replace(assistant_id)


def assistant_replace(new_assistant_id: int) -> None:
    """
    处理玩家助理干员的任命、更换或卸任，并经 ui_hooks 发出分隔线与提示。
    若原有助理，函数先清零其 is_follow 标记，在宿舍为中枢/博士房间时重新安排宿舍，并清零助理服务。
    随后函数发出分隔线，再按目标分三条分支处理。
    目标为原助理时，函数将助理编号设为 0。
    目标处于 handle_unnormal_27 异常状态时，函数追加异常提示并跳过卸任收尾，不改助理编号。
    其余情况，函数任命目标，开启跟随与 2 号服务，更新其助理二段行为标记并追加任命提示。
    原有助理且未触发异常分支时，函数重置目标的 chosen_as_assistant 标记。
    同条件下，函数设置原助理的 not_as_assistant 标记并追加卸任提示。
    最后函数经 ui_hooks.emit_notice 发出累计提示。
    Keyword arguments:
    new_assistant_id -- int，要任命或卸任的目标角色编号
    Return arguments:
    None -- 无返回值
    """
    old_id = relations.assistant_character_id(0)

    old_assistant_data: identity.Identity | None = None
    if old_id != 0:
        old_assistant_data = identity.of(old_id)
        flags.set(old_id, is_follow=0)
        if chara_life.dormitory(
            old_id
        ) == map_handle.get_map_system_path_str_for_list(["中枢", "博士房间"]):
            from Script.System.Dormitory_System import (
                common as dormitory_common,
            )

            dormitory_common.restore_character_dormitory(old_id)
        zero = attr_calculation.get_assistant_services_zero()
        relations.assistant_services.set(old_id, zero)

    ui_hooks.emit_divider("-")
    info_text = ""

    if new_assistant_id == old_id:
        relations.assistant_character_id.set(0, 0)
    elif handle_premise.handle_unnormal_27(new_assistant_id):
        new_assistant_data: identity.Identity = identity.of(new_assistant_id)
        info_text += _("\n{0}的状态异常，无法任命为助理干员\n").format(
            new_assistant_data.name
        )
        old_assistant_data = None
    else:
        relations.assistant_character_id.set(0, new_assistant_id)
        new_assistant_data = identity.of(new_assistant_id)
        flags.set(new_assistant_id, is_follow=1)
        relations.assistant_services.set_item(new_assistant_id, 2, 1)
        second_behavior.character_get_second_behavior(
            new_assistant_id, "not_as_assistant", reset=True
        )
        second_behavior.character_get_second_behavior(
            new_assistant_id, "chosen_as_assistant"
        )
        info_text += _("\n{0}成为助理干员了，并默认开启智能跟随模式\n").format(
            new_assistant_data.name
        )
        if old_assistant_data is not None:
            if relations.assistant_services(old_id).get(10) == 1:
                relations.assistant_services.set_item(new_assistant_id, 10, 1)
    if old_assistant_data is not None:
        second_behavior.character_get_second_behavior(
            new_assistant_id, "chosen_as_assistant", reset=True
        )
        second_behavior.character_get_second_behavior(
            old_assistant_data.cid, "not_as_assistant"
        )
        info_text += _(
            "\n\n{0}不再是助理干员了，已清零助理服务相关的设置\n\n"
        ).format(old_assistant_data.name)
    ui_hooks.emit_notice(info_text, wait=True, use_text_width=True)
