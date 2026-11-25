"""
能力升级列表与规则服务（ability_up_service）
============================================
本模块提供能力分组列表、升级需求解析、额外条件判定与升级写入。
本模块公开常量 MARK_TYPE、MAX_LEVEL 与类型别名 Route，
数据类 AbilityButton、AbilityGroup 与 Needs。
本模块公开函数 ability_groups、level_up_lists、needs、verdict 与
level_up。
本模块不执行界面绘制，也不导入 Script.UI、Script.Settle 或 Tk 模块。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import FunctionType
from typing import Literal

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import attr_calculation, handle_ability
from Script.Modules.domains import abilities, identity, modes
from Script.Modules.gameplay_resolution import achievement_service
from Script.Modules.gameplay_resolution import mark_change_service as marks

_: FunctionType = get_text._
""" 翻译api """

MARK_TYPE = 2
""" 刻印类能力对应的能力类型编号。 """
MAX_LEVEL = 8
""" 普通能力的最高升级等级。 """

Route = Literal["ability", "up", "down", "locked"]
""" 能力列表按钮的目标动作路由字面量类型。 """


@dataclass(frozen=True, slots=True)
class AbilityButton:
    """
    单个能力按钮项，含能力编号 ability_id、显示文本 text、
    动作路由 route 与高亮标志 highlight。
    """

    ability_id: int
    text: str
    route: Route
    highlight: bool


@dataclass(frozen=True, slots=True)
class AbilityGroup:
    """按类型归组的能力按钮集合，含能力类型 ability_type 与按钮元组 buttons。"""

    ability_type: int
    buttons: tuple[AbilityButton, ...]


@dataclass(frozen=True, slots=True)
class Needs:
    """单组升级需求检查结果，含提示行 rows、满足标志 met 与宝珠消耗映射 cost。"""

    rows: tuple[str, ...]
    met: bool
    cost: Mapping[int, int]


def _need(text: str) -> tuple[str, int, int]:
    """将“类型字母+编号|数值”格式的需求串拆为三元组。"""
    head, value = text.split("|")[0], text.split("|")[1]
    return head[0], int(head[1:]), int(value)


def _amount(cid: int, kind: str, type_id: int) -> int:
    """按类型字母读取角色能力、宝珠或经验当前值，其余类型返回 0。"""
    if kind == "A":
        return abilities.ability(cid).get(type_id, 0)
    if kind == "J":
        return abilities.juel(cid).get(type_id, 0)
    if kind == "E":
        return abilities.experience(cid).get(type_id, 0)
    return 0


def _change_flags(cid: int, ability_id: int) -> tuple[bool, bool]:
    """判断角色指定能力或刻印当前可升级与可降级状态。"""
    level = abilities.ability(cid)[ability_id]
    down_data = game_config.config_mark_down_data_by_ability
    if (
        ability_id in game_config.config_mark_up_data_by_ability
        or ability_id in down_data
    ):
        can_up = marks.can_raise(ability_id, level) and marks.raise_ok(
            cid, ability_id, level
        )
        can_down = (
            ability_id in down_data
            and level > 0
            and marks.lower_ok(cid, ability_id, level)
        )
        return can_up, can_down
    if level >= MAX_LEVEL:
        return False, False
    ok = True
    for text in game_config.config_ability_up_data.get(ability_id, {}).get(
        level, []
    ):
        kind, type_id, value = _need(text)
        if _amount(cid, kind, type_id) < value:
            ok = False
            break
    extra = handle_ability.extra_ability_check(
        ability_id=ability_id, character_id=cid, draw_flag=False
    )
    if extra == 0:
        ok = False
    if modes.debug():
        ok = True
    return ok, False


def _can_change(cid: int, ability_id: int) -> tuple[bool, bool]:
    """安全调用 _change_flags，出现异常时返回双假元组。"""
    try:
        return _change_flags(cid, ability_id)
    except Exception:
        return False, False


def _mark_button(cid: int, ability_id: int, level: int) -> AbilityButton:
    """按刻印等级与升降级条件构建单个刻印按钮数据。"""
    text = f" {game_config.config_ability[ability_id].name}   {level} "
    if marks.can_raise(ability_id, level):
        can_up = _can_change(cid, ability_id)[0]
        return AbilityButton(
            ability_id, text + "(+)" if can_up else text, "up", can_up
        )
    if ability_id in game_config.config_mark_down_data_by_ability and level > 0:
        can_down = _can_change(cid, ability_id)[1]
        return AbilityButton(
            ability_id, text + "(-)" if can_down else text, "down", can_down
        )
    return AbilityButton(ability_id, text, "locked", False)


def _ability_button(
    cid: int, ability_type: int, ability_id: int, level: int
) -> AbilityButton:
    """按能力类型补齐间距并结合评级与升级条件构建普通能力按钮。"""
    text = f" {game_config.config_ability[ability_id].name} "
    if ability_type in (3, 4, 5):
        text += "  "
    if ability_type not in (2, 4, 6):
        text += "  "
        if ability_type in (3, 5):
            text += "  "
    text += f"{attr_calculation.judge_grade(level)} {level}"
    can_up = _can_change(cid, ability_id)[0]
    return AbilityButton(
        ability_id, text + "(+)" if can_up else text, "ability", can_up
    )


def ability_groups(cid: int) -> tuple[AbilityGroup, ...]:
    """
    按配置顺序生成角色的能力按钮分组，对角色 0 跳过刻印并按性别过滤。
    Keyword arguments:
    cid -- int，角色编号
    Return arguments:
    tuple[AbilityGroup, ...] -- 各能力类型的按钮分组元组
    """
    ability = abilities.ability(cid)
    sex = identity.of(cid).sex
    groups: list[AbilityGroup] = []
    for ability_type, type_set in game_config.config_ability_type_data.items():
        if ability_type == MARK_TYPE:
            if cid == 0:
                continue
            buttons = tuple(
                _mark_button(cid, ability_id, ability[ability_id])
                for ability_id in type_set
            )
        else:
            buttons = tuple(
                _ability_button(
                    cid, ability_type, ability_id, ability[ability_id]
                )
                for ability_id in type_set
                if (sex, game_config.config_ability[ability_id].sex_need)
                not in ((0, 1), (1, 0))
            )
        groups.append(AbilityGroup(ability_type, buttons))
    return tuple(groups)


def level_up_lists(ability_id: int, level: int) -> tuple[list[str], list[str]]:
    """
    读取指定能力在当前等级的主升级需求列表与次升级需求列表。
    Keyword arguments:
    ability_id -- int，能力编号
    level -- int，能力当前等级
    Return arguments:
    tuple[list[str], list[str]] -- 主需求列表与次需求列表
    """
    main = game_config.config_ability_up_data[ability_id][level]
    second = game_config.config_ability_up2_data.get(ability_id, {})
    return main, second.get(level, [])


def needs(cid: int, need_list: list[str]) -> Needs:
    """
    校验单组升级需求并生成本地化需求行、满足标志与宝珠消耗表。
    Keyword arguments:
    cid -- int，角色编号
    need_list -- list[str]，需求字符串列表
    Return arguments:
    Needs -- 含本地化需求行、是否全部满足与宝珠消耗映射的结果
    """
    rows: list[str] = []
    cost: dict[int, int] = {}
    met = True
    for text in need_list:
        kind, type_id, value = _need(text)
        if kind == "A":
            name = game_config.config_ability[type_id].name
            have = abilities.ability(cid)[type_id]
            row = _("需要能力 : {0} 至少为{1}，当前为{2}\n")
        elif kind == "J":
            name = game_config.config_juel[type_id].name
            have = abilities.juel(cid)[type_id]
            row = _("需要宝珠 : {0} 至少为{1}，当前为{2}\n")
            cost[type_id] = value
        else:
            name = game_config.config_experience[type_id].name
            have = abilities.experience(cid)[type_id]
            row = _("需要经验 : {0} 至少为{1}，当前为{2}\n")
        rows.append(row.format(name, value, have))
        if have < value:
            met = False
    return Needs(tuple(rows), met, cost)


def verdict(
    cid: int, ability_id: int, main_ok: bool, second_ok: bool
) -> tuple[bool, bool]:
    """
    执行额外条件检查并结合调试模式确定主次需求的最终判定结果。
    Keyword arguments:
    cid -- int，角色编号
    ability_id -- int，能力编号
    main_ok -- bool，主需求初步满足标志
    second_ok -- bool，次需求初步满足标志
    Return arguments:
    tuple[bool, bool] -- 最终的主需求与次需求满足标志
    """
    extra = handle_ability.extra_ability_check(
        ability_id=ability_id, character_id=cid, draw_flag=True
    )
    if extra == 0:
        main_ok = second_ok = False
    if modes.debug():
        main_ok = second_ok = True
    return main_ok, second_ok


def level_up(cid: int, ability_id: int, cost: Mapping[int, int]) -> None:
    """
    扣除升级所需宝珠、提升能力 1 级并结算技能类成就。
    Keyword arguments:
    cid -- int，角色编号
    ability_id -- int，能力编号
    cost -- Mapping[int, int]，待扣除的宝珠编号与数量映射
    Return arguments:
    None -- 无返回值
    """
    juel = abilities.juel(cid)
    for juel_id, count in cost.items():
        juel[juel_id] -= count
    abilities.ability(cid)[ability_id] += 1
    achievement_service.settle_and_notify(_("技能"))
