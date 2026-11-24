"""
助理服务（assistant_service）
=============================
提供助理候选角色筛选、每周随机抽选助理与助理替换逻辑。
抽签结果提示、任命提示、状态异常提示与卸任提示经 ui_hooks.emit_notice 发出。
分隔线经 ui_hooks.emit_divider 发出。
本模块不直接导入界面、Tk 或输入输出模块，导入时加载零个 Script.UI.Panel 模块。
2/7 异常判定调用共用的 handle_premise.handle_unnormal_27，本模块供助理面板与跨日结算调用。
"""

import os
import random
from types import FunctionType

from Script.Core import get_text
from Script.Design import attr_calculation, handle_premise, second_behavior
from Script.Modules.domains import chara_life, flags, identity, relations
from Script.Modules.domains import roster, visitor, work
from Script.Modules.gameplay_resolution import ui_hooks

_: FunctionType = get_text._
""" 翻译api """


def get_assistant_candidates() -> list[int]:
    """
    按角色编号升序筛选可担任助理的候选角色编号列表。
    遍历 roster.active_sorted()，依次跳过玩家（编号 0）、2/7 异常角色、监狱长与访客。
    其中 2/7 异常角色按 handle_unnormal_27 判定。
    筛选不按当前助理身份跳过角色。
    Return arguments:
    list[int] -- 符合条件的候选角色编号列表，按角色编号升序排列
    """
    candidates = []
    for npc_id in roster.active_sorted():
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
    从候选列表中随机抽选一名角色作为本周助理并执行替换。
    调用 random.choice 选取候选角色，候选列表为空时抛出 IndexError。
    经 ui_hooks.emit_notice 以等待确认与配置文本宽度发出抽签结果提示，再调用 assistant_replace。
    抽中当前助理时会进入同人卸任分支，使玩家当前无助理。
    Return arguments:
    None -- 无返回值
    """
    assistant_id = random.choice(get_assistant_candidates())
    ui_hooks.emit_notice(
        _("\n○本周抽签选中了{0}作为{1}的助理\n").format(
            identity.of(assistant_id).name, identity.of(0).name
        ),
        wait=True,
        use_text_width=True,
    )
    assistant_replace(assistant_id)


def assistant_replace(new_assistant_id: int) -> None:
    """
    执行助理替换并经 ui_hooks 输出分隔线与等待提示。
    有旧助理时关闭其跟随，仅住中枢/博士房间时调用 restore_character_dormitory，再清零其服务表。
    随后调用 ui_hooks.emit_divider("-")，并按目标分三支处理。
    目标等于旧助理时将玩家助理编号置 0，有旧助理时即卸任。
    目标处于 2/7 异常时保留原助理编号，拼接状态异常提示并跳过卸任步骤。
    其余情况任命目标、开启跟随与服务 2 并保留其余服务项，更新标记并拼接任命提示。
    有旧助理且未跳过卸任步骤时，重置目标 chosen_as_assistant 并为旧助理设 not_as_assistant。
    同时拼接卸任提示。
    标记均经 second_behavior.character_get_second_behavior 更新。
    最后经 ui_hooks.emit_notice 以等待确认与配置文本宽度发出提示。
    Keyword arguments:
    new_assistant_id -- int，目标助理角色编号
    Return arguments:
    None -- 无返回值
    """
    old_id = relations.assistant_character_id(0)
    old_assistant_data: identity.Identity | None = None
    if old_id != 0:
        old_assistant_data = identity.of(old_id)
        flags.set(old_id, is_follow=0)
        if chara_life.dormitory(old_id) == os.sep.join(["中枢", "博士房间"]):
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
