# -*- coding: UTF-8 -*-
"""
三个批量指令的效果：对每名参与者做一次，再画一行结果提示
三个指令都不推进时间、不走行为结算。
"""

from Script.Config import game_config, normal_config
from Script.Core import cache_control, get_text
from Script.UI.Moudle import draw

from . import members

_ = get_text._
""" 翻译api """

TOY_BODY_ITEM_IDS = (0, 1, 2, 3)
""" 全员戴上玩具装备的身体道具id：乳头夹、阴蒂夹、V震动棒、A震动棒 """
MIN_HYPNOSIS_BOOST_MEMBERS = 2
""" 全员催眠增强至少需要的完全催眠参与者人数 """


def edge_all() -> None:
    """
    全员寸止：给尚未寸止的参与者开启寸止，并清零其各部位寸止次数
    Keyword arguments:
    无
    Return arguments:
    None
    """
    member_ids = members.member_ids()
    changed = sum(_turn_on_edge(cache_control.cache.character_data[cid]) for cid in member_ids)
    _draw(_("\n已为{0}/{1}名干员开启寸止模式\n").format(changed, len(member_ids)))


def equip_toys_all() -> None:
    """
    全员戴上玩具：给参与者戴上 TOY_BODY_ITEM_IDS 里还没戴的道具
    Keyword arguments:
    无
    Return arguments:
    None
    """
    member_ids = members.member_ids()
    item_counts = [_equip_toys(cache_control.cache.character_data[cid]) for cid in member_ids]
    changed_members = sum(1 for count in item_counts if count)
    _draw(_("\n已为{0}/{1}名干员戴上玩具，共新增{2}件\n").format(changed_members, len(member_ids), sum(item_counts)))


def hypnosis_boost_all() -> None:
    """
    全员催眠增强：给完全催眠的参与者开启敏感度上升与苦痛快感化；不改变当前催眠状态
    人数不足时只画提示（前提已挡住按钮，这里防直接调用）
    Keyword arguments:
    无
    Return arguments:
    None
    """
    member_ids = members.complete_hypnosis_member_ids()
    if len(member_ids) < MIN_HYPNOSIS_BOOST_MEMBERS:
        _draw(_("\n当前完全催眠的群交干员不足{0}人，无法执行全员催眠增强\n").format(MIN_HYPNOSIS_BOOST_MEMBERS))
        return
    sensitivity_count = 0
    pain_count = 0
    for cid in member_ids:
        hypnosis = cache_control.cache.character_data[cid].hypnosis
        if not hypnosis.increase_body_sensitivity:
            hypnosis.increase_body_sensitivity = True
            sensitivity_count += 1
        if not hypnosis.pain_as_pleasure:
            hypnosis.pain_as_pleasure = True
            pain_count += 1
    _draw(_("\n已为{0}名完全催眠干员设置敏感度上升与苦痛快感化（新增敏感度上升{1}人，新增苦痛快感化{2}人）\n").format(len(member_ids), sensitivity_count, pain_count))


def _turn_on_edge(character_data) -> bool:
    """
    角色尚未寸止时开启寸止，并把各快感部位的寸止次数清零（同本体"开启寸止"结算）
    Keyword arguments:
    character_data -- 角色数据
    Return arguments:
    bool -- 是否新开启
    """
    h_state = character_data.h_state
    if h_state.orgasm_edge != 0:
        return False
    h_state.orgasm_edge = 1
    for state_id, state_config in game_config.config_character_state.items():
        if state_config.type == 0:
            h_state.orgasm_edge_count[state_id] = 0
    return True


def _equip_toys(character_data) -> int:
    """
    戴上 TOY_BODY_ITEM_IDS 里还没戴的道具
    Keyword arguments:
    character_data -- 角色数据
    Return arguments:
    int -- 新戴上的件数
    """
    count = 0
    for body_item_id in TOY_BODY_ITEM_IDS:
        slot = character_data.h_state.body_item[body_item_id]
        if not slot[1]:
            slot[1] = True
            slot[2] = None
            count += 1
    return count


def _draw(text: str) -> None:
    """
    画一行结果提示
    Keyword arguments:
    text -- 提示文本
    Return arguments:
    None
    """
    info_draw = draw.NormalDraw()
    info_draw.text = text
    info_draw.width = normal_config.config_normal.text_width
    info_draw.draw()
