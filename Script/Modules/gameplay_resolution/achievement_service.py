"""
成就结算服务（achievement_service）
===================================
提供按数值判定成就、按类型结算成就、拼装成就获得提示文本，以及经 ui_hooks 发出新达成提示的入口。
本模块不直接导入界面模块。
成就面板与各业务结算入口调用本模块。
"""

from types import FunctionType
from typing import Any

from Script.Config import game_config
from Script.Core import get_text
from Script.Modules.domains import achievement, chara_life, commission, needs
from Script.Modules.domains import playthrough, prison, relations, warehouse
from Script.Modules.gameplay_resolution import achievement_h_rules
from Script.Modules.gameplay_resolution import achievement_rules
from Script.Modules.gameplay_resolution import ui_hooks

_: FunctionType = get_text._
""" 翻译api """


def unlocked_text(achievement_id: int) -> str:
    """
    按成就编号读取 game_config.config_achievement 中的名称与说明，拼装成就获得提示文本。
    Keyword arguments:
    achievement_id -- int，成就编号
    Return arguments:
    str -- 含成就名称与说明的成就获得提示文本
    """
    achievement_data = game_config.config_achievement[achievement_id]
    text = _("\n\n   ○ 获得蚀刻章：{name} ○\n").format(
        name=achievement_data.name
    )
    return text + _("      （{description}）\n\n\n").format(
        description=achievement_data.description
    )


def settle_and_notify(
    achievement_type: str, achievement_id: int = 0
) -> list[int]:
    """
    调用 settle_by_type 结算指定类型的成就。
    对返回列表中的每个新达成成就编号，按顺序经 ui_hooks.emit_notice 发出由 unlocked_text 生成的提示
    （wait=True、style="gold_enrod"）。
    无新达成成就时不发出提示。
    Keyword arguments:
    achievement_type -- str，成就类型名
    achievement_id -- int，非 0 时强制结算该成就编号，默认为 0
    Return arguments:
    list[int] -- 本次新达成的成就编号列表
    """
    new_ids = settle_by_type(achievement_type, achievement_id)
    for new_id in new_ids:
        ui_hooks.emit_notice(
            unlocked_text(new_id), wait=True, style="gold_enrod"
        )
    return new_ids


def get_achievement_judge_by_value(
    achievement_id: int, judge_value: int
) -> bool:
    """
    根据成就ID和判断值判断是否达成成就\n
    输入：\n
    - achievement_id: int，成就ID\n
    - judge_value: int，判断值\n
    返回：\n
    - bool，是否达成成就
    """
    achievement_data = game_config.config_achievement.get(achievement_id)
    if not achievement_data:
        return False
    if achievement.done(achievement_id):
        return False
    if judge_value >= achievement_data.value:
        settle_and_notify(achievement_data.type, achievement_id)
        return True
    return False


def settle_by_type(achievement_type: str, achievement_id: int = 0) -> list[int]:
    """按 achievement_type 结算成就（achievement_id 非 0 时强制结算），不绘制，返回新达成 ID 列表。"""
    pl_needs = needs.of(0)
    func = None
    if achievement_type == _("关系"):
        func = achievement_rules.settle_chara_relationship
    elif achievement_type == _("招募"):
        func = achievement_rules.settle_chara_recruit
    elif achievement_type == _("访客"):
        func = achievement_rules.settle_chara_visitor
    elif achievement_type == _("助理"):
        func = achievement_rules.settle_chara_assistant
    elif achievement_type == _("收藏服装"):
        func = achievement_rules.settle_chara_clothing
    elif achievement_type == _("技能"):
        func = achievement_rules.settle_chara_ability
    elif achievement_type == _("催眠"):
        func = achievement_rules.settle_chara_hypnosis
    elif achievement_type == _("群交"):
        func = achievement_h_rules.settle_chara_group_sex
    elif achievement_type == _("隐奸"):
        func = achievement_h_rules.settle_chara_hidden_sex
    elif achievement_type == _("露出"):
        func = achievement_h_rules.settle_chara_exhibitionism_sex
    elif achievement_type == _("睡奸"):
        func = achievement_h_rules.settle_chara_sleep_sex
    elif achievement_type == _("射精"):
        func = achievement_h_rules.settle_semen_shoot
    vehicles_count = 0
    read_book_count = 0
    if achievement_type == _("载具"):
        for owned, _out in commission.vehicles().values():
            vehicles_count += owned
    elif achievement_type == _("读书"):
        for book_id in chara_life.read_book_progress(0):
            if chara_life.read_book_progress(0)[book_id] >= 100:
                read_book_count += 1
    achievement_type_value_dict: dict[str, list[Any]] = {
        _("周目"): [playthrough.game_round(), [1, 2]],
        _("囚犯"): [len(prison.prisoner_ids()), [121, 122]],
        _("龙门币"): [
            warehouse.amount(1),
            [201, 202, 203],
        ],
        _("购买道具"): [
            len(achievement.get("buy_item_count_list")),
            [211, 212],
        ],
        _("外勤"): [achievement.get("field_commission_count"), [301, 302, 303]],
        _("载具"): [vehicles_count, [311, 312]],
        _("维修"): [achievement.get("equipment_repair_count"), [321, 322, 323]],
        _("保养"): [
            achievement.get("equipment_maintenance_count"),
            [331, 332, 333],
        ],
        _("锻炼"): [
            min(pl_needs["hit_max"], pl_needs["mana_max"]),
            [401, 402, 403],
        ],
        _("时停"): [achievement.get("time_stop_duration"), [601, 602, 603]],
        _("生育"): [
            len(relations.child_id_list(0)),
            [701, 702, 703],
        ],
        _("生产"): [achievement.get("production_count"), [801, 802, 803]],
        _("种植"): [achievement.get("harvest_count"), [811, 812, 813]],
        _("乱伦"): [achievement.get("h_with_daughter_count"), [941, 942]],
        _("公务"): [
            achievement.get("handle_official_business_count"),
            [1001, 1002, 1003],
        ],
        _("读书"): [read_book_count, [1011, 1012, 1013]],
        _("烹饪"): [achievement.get("make_food_count"), [1021, 1022, 1023]],
        _("礼物"): [achievement.get("gift_count"), [1031, 1032]],
        _("身体检查"): [
            achievement.get("health_check_count"),
            [1041, 1042, 1043],
        ],
        _("体检报告"): [
            len(achievement.get("body_report_chara_count_list")),
            [1051, 1052],
        ],
        _("调香"): [achievement.get("aromatherapy_count"), [1061, 1062]],
        _("导航"): [len(achievement.get("visited_nation_list")), [1101, 1102]],
    }
    judge_value, achievement_ids = achievement_type_value_dict.get(
        achievement_type, (None, None)
    )
    achievement_id_list = []
    if achievement_id != 0:
        achievement_id_list = achievement_rules.settle_achievement(
            1, achievement_id, force=True
        )
    elif func is not None:
        achievement_id_list = func()
    elif judge_value is not None and achievement_ids is not None:
        achievement_id_list = achievement_rules.settle_achievement(
            judge_value, achievement_ids
        )
    return achievement_id_list
