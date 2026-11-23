"""
催眠服务（hypnosis_service）
============================
提供催眠理智消耗、催眠深度增长与上限、催眠完成判定、深度颜色样式及无意识状态名称列表。
本模块不直接导入界面模块。
完成判定产生的提示文本经 ui_hooks.emit_notice 派发。
"""

import os
import random
from types import FunctionType

from Script.Config import game_config
from Script.Core import constant, get_text
from Script.Design import handle_ability, handle_talent, hypnosis_state
from Script.Modules.domains import abilities, activity, flags, hypnosis
from Script.Modules.domains import identity, player_ability, scene_state
from Script.Modules.gameplay_resolution import ui_hooks

_: FunctionType = get_text._
""" 翻译api """

unconscious_list = [
    _("无"),
    _("睡眠"),
    _("醉酒"),
    _("时停"),
    _("平然催眠"),
    _("空气催眠"),
    _("体控催眠"),
    _("心控催眠"),
]
""" 按角色 unconscious_h 标志值（0 至 7）索引的无意识状态名称列表。 """


def calculate_hypnosis_sanity_cost(character_id: int) -> int:
    """
    按目标角色的素质计算催眠所需的理智消耗。
    按素质 73、72、71 的优先级依次返回 1、30、25。
    以上素质均未持有时返回 20。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    int -- 预计消耗的理智值
    """
    talent = abilities.talent(character_id)
    base_cost = 10
    if talent[73]:
        return 1
    elif talent[72]:
        return base_cost + 20
    elif talent[71]:
        return base_cost + 15
    else:
        return base_cost + 10


def hypnosis_degree_calculation(target_character_id: int) -> float:
    """
    计算单次催眠对目标角色的催眠深度增长值。
    目标为玩家（编号 0）或当前深度达到上限时返回 0。
    否则按玩家素质取基础系数，持有素质 334 时取 6，未持有 334 但持有 333 时取 4，其余取 2。
    目标 aromatherapy 标志为 6 时，基础系数加 5。
    结果乘以目标能力 19 的调整值及 0.5 至 1.5 的随机系数后保留一位小数。
    返回值不截断至催眠深度上限。
    Keyword arguments:
    target_character_id -- int，目标角色编号
    Return arguments:
    float -- 催眠深度增长值
    """
    talent = abilities.talent(0)

    if target_character_id == 0:
        return 0

    hypnosis_degree_limit = hypnosis_degree_limit_calculation()
    if hypnosis.degree(target_character_id) >= hypnosis_degree_limit:
        return 0

    base_addition = 1

    hypnosis_degree_adjust: float = 2
    if talent[334]:
        hypnosis_degree_adjust = 6
    elif talent[333]:
        hypnosis_degree_adjust = 4

    if flags.get(target_character_id, "aromatherapy") == 6:
        hypnosis_degree_adjust += 5

    hypnosis_degree_adjust *= handle_ability.get_ability_adjust(
        abilities.ability(target_character_id)[19]
    )

    hypnosis_degree_adjust *= random.uniform(0.5, 1.5)

    final_addition = base_addition * hypnosis_degree_adjust
    final_addition = round(final_addition, 1)

    return final_addition


def hypnosis_degree_limit_calculation() -> int:
    """
    按玩家持有的催眠素质计算可施加的催眠深度上限。
    遍历 config_hypnosis_talent_of_pl 取玩家已持有素质对应的最大 max_hypnosis_degree。
    未持有对应素质时返回 0。
    Keyword arguments:
    无
    Return arguments:
    int -- 催眠深度上限
    """

    hypnosis_degree_limit = 0
    for cid in game_config.config_hypnosis_talent_of_pl:
        hypnosis_data = game_config.config_hypnosis_talent_of_pl[cid]
        if abilities.talent(0)[hypnosis_data.hypnosis_talent_id]:
            hypnosis_degree_limit = max(
                hypnosis_degree_limit, hypnosis_data.max_hypnosis_degree
            )

    return hypnosis_degree_limit


def evaluate_hypnosis_completion(character_id: int) -> int:
    """
    判断并结算目标角色的催眠完成状态。
    先执行目标催眠素质获取检测，再将目标催眠深度与当前催眠类型所需深度比较。
    深度不足时经 ui_hooks.emit_notice 发出不等待确认的深度不足提示并返回 0。
    深度达标且类型为 2 时，场景 close_type 不为 1 会发出等待确认的「不能锁门」提示并返回 0。
    类型为 2 且场景可锁门时，未锁门则写入关门标志并发出等待确认的「已锁门」提示，随后记录 air_hypnosis_position。
    类型为 1 或 2 完成时会清空催眠行为模式并将 unconscious_h 设为类型编号加 3。
    完成判定通过时返回 1。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    int -- 1 表示完成，0 表示未完成
    """
    character_data: identity.Identity = identity.of(character_id)
    handle_talent.npc_gain_hypnosis_talent(character_id)
    now_hypnosis_type = player_ability.get(0, "hypnosis_type")
    hypnosis_degree_need = game_config.config_hypnosis_type[
        now_hypnosis_type
    ].hypnosis_degree
    if hypnosis.degree(character_id) >= hypnosis_degree_need:
        if now_hypnosis_type == 2:
            now_position = activity.position(0)
            now_scene_str = os.sep.join(now_position)
            now_scene_data = constant.scene_data[now_scene_str]
            if now_scene_data.close_type != 1:
                ui_hooks.emit_notice(
                    _("\n当前地点不能锁门，无法进行空气催眠\n"), wait=True
                )
                return 0
            elif scene_state.close_flag(now_scene_str) == 0:
                scene_state.set_close_flag(
                    now_scene_str, now_scene_data.close_type
                )
                ui_hooks.emit_notice(
                    _("\n为了防止有人打扰，将门锁上了\n"), wait=True
                )
            player_ability.set(0, air_hypnosis_position=activity.position(0))
        if now_hypnosis_type == 1 or now_hypnosis_type == 2:
            hypnosis_state.clear_hypnosis_behavior_mode(character_id)
            flags.set(character_id, unconscious_h=now_hypnosis_type + 3)
        return 1
    else:
        draw_text = _(
            "\n{0}的催眠深度未达到{1}%，无法进入{2}催眠状态，需要切换更低的催眠模式或加深催眠程度\n"
        ).format(
            character_data.name,
            hypnosis_degree_need,
            game_config.config_hypnosis_type[now_hypnosis_type].name,
        )
        ui_hooks.emit_notice(draw_text, wait=False)
        return 0


def get_hypnosis_degree_color(hypnosis_degree: float) -> str:
    """
    根据催眠深度返回对应的文本样式名称。
    按等于 0、小于 50、小于 100、小于 200 与 200 及以上顺序依次返回 standard、pink、hot_pink、deep_pink 与 purple。
    Keyword arguments:
    hypnosis_degree -- float，催眠深度
    Return arguments:
    str -- 对应的文本样式名称
    """
    if hypnosis_degree == 0:
        font_color = "standard"
    elif hypnosis_degree < 50:
        font_color = "pink"
    elif hypnosis_degree < 100:
        font_color = "hot_pink"
    elif hypnosis_degree < 200:
        font_color = "deep_pink"
    else:
        font_color = "purple"
    return font_color
