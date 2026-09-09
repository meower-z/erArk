# -*- coding: UTF-8 -*-
"""
本地绝顶口上批次合并显示。

NPC 在一次结算中多个部位同时绝顶时，上游会为每个部位逐条绘制完整的绝顶口上，
在部位数较多时刷屏。本 mod 把同一次结算中的绝顶口上合并显示：
多重绝顶口上先出，同一部位只取最高等级，按强度从高到低排序（同强度随机打乱），
前 3 个部位显示完整代表口上，第 4 个起按强度分组汇总成一行黄色提示；
多部位寸止合并成一行标题 + 随机挑一条无标题正文。

对应上游 PR #253（已被上游拒绝，改由本地 mod 承接）。实现为 wrapper：
包装 Script.Design.second_behavior.second_behavior_effect，在原函数执行期间临时
接管 talk.handle_second_talk，于本角色第一条口上出现的位置绘制合并批次，
并吞掉已被批次接管的行为口上；全部结算效果仍由上游原函数逐项执行。
因此不复制上游函数体，不受上游函数体漂移影响。

与上游 part_max_degree_dict 过滤的分工：上游负责"同一部位内非最高程度的绝顶行为
只结算效果不触发口上"，本 mod 负责跨部位的批次合并显示，两者是超集关系不冲突。
玩家（character_id == 0）完全不进批次，由上游过滤单独负责。
"""

# mod 加载时 Script.Design.second_behavior 还没被导入过，若由 mod 管理器直接以它为根导入，
# 会撞上 settle_behavior -> handle_instruct -> update -> character_behavior -> Script.Settle
# -> item_effect 的循环导入（item_effect 的装饰器要用还没执行完的
# settle_behavior.add_settle_behavior_effect）。先以 handle_npc_ai 为根把整条依赖链完整导入
# 一遍，随后 mod 管理器导入替换目标时即可命中缓存。
from Script.Design import handle_npc_ai as _preload_design_modules  # noqa: F401

SECOND_BEHAVIOR = "Script.Design.second_behavior"

ORGASM_PART_ORDER = ("s", "b", "c", "v", "a", "u", "w", "m", "f", "h")
""" NPC部位绝顶的显示排序，与orgasm_settle的部位遍历顺序保持一致 """
ORGASM_PART_NAME = {"s": "皮肤", "b": "胸部", "c": "阴蒂", "v": "阴道", "a": "肛肠", "u": "尿道", "w": "子宫", "m": "口喉", "f": "兽部", "h": "心理"}
""" NPC部位绝顶显示名 """
ORGASM_DEGREE_TEXT = {0: "小绝顶", 1: "绝顶", 2: "强绝顶", 3: "超强绝顶"}
""" NPC部位绝顶强度顺序到汇总显示名的映射 """

# 前几个部位显示完整代表口上，其余进汇总行
FULL_TALK_PART_LIMIT = 3

# 当前正在被批次接管的角色id，用于同角色重入时不重复挂钩
_BATCH_ACTIVE_CHARACTER_IDS = set()


def _cache():
    """参数：无；返回：Cache对象；用途：获取当前游戏缓存（延迟读取，兼容多周目时缓存对象被整体替换）。"""
    from Script.Core import cache_control

    return cache_control.cache


def _translate(text: str) -> str:
    """参数：text(str)为待翻译文本；返回：str为翻译后文本；用途：延迟取用翻译api，避免加载期依赖注入的全局名。"""
    from Script.Core import get_text

    return get_text._(text)


def _parse_part_orgasm_behavior(second_behavior_id: str):
    """参数：second_behavior_id(str)为二段行为id；返回：tuple(部位前缀str, 强度序号int)或None；用途：复用上游orgasm_settle的解析规则识别部位绝顶行为，未知部位视为非部位绝顶。"""
    from Script.Settle import orgasm_settle

    orgasm_part, orgasm_degree = orgasm_settle.get_orgasm_part_and_degree(second_behavior_id)
    if orgasm_part is None or orgasm_part not in ORGASM_PART_NAME:
        return None
    return orgasm_part, orgasm_degree


def _draw_orgasm_info_text(text: str):
    """参数：text(str)为提示正文；返回：None；用途：绘制高潮批次的黄色汇总提示文本。"""
    from Script.Config import normal_config
    from Script.UI.Moudle import draw

    info_draw = draw.WaitDraw()
    info_draw.style = "gold_enrod"
    info_draw.width = normal_config.config_normal.text_width
    info_draw.text = text
    info_draw.draw()


def _draw_second_talk_without_title(character_id: int, behavior_id: str):
    """参数：character_id(int)为角色id，behavior_id(str)为二段行为id；返回：None；用途：只绘制二段行为正文不绘制标题地文（等价于给handle_second_talk传draw_title=False，标题由handle_talk_draw的second_behavior_id触发，置空即跳过）。"""
    from Script.Design import talk

    now_talk_data, _premise_dict = talk.handle_talk_sub(character_id, behavior_id, {})
    talk_text, now_talk_id, common_behavior_id = talk.choice_talk_from_talk_data(now_talk_data, behavior_id)
    talk.handle_talk_draw(character_id, talk_text, now_talk_id, "", common_behavior_id)


def select_batch_parts(active_behavior_ids: list) -> list:
    """参数：active_behavior_ids(list)为本次待结算的非零二段行为id列表；返回：list[(部位前缀str, 二段行为id str, 强度序号int)]为排序后的部位代表列表；用途：同一部位只保留最高等级，并按强度从高到低排序、同强度随机打乱。"""
    import random

    # 同一部位只保留最高等级参与显示
    highest_rank_by_part = {}
    for behavior_id in active_behavior_ids:
        parse_data = _parse_part_orgasm_behavior(behavior_id)
        if parse_data is None:
            continue
        part_prefix, degree_rank = parse_data
        old_data = highest_rank_by_part.get(part_prefix)
        if old_data is None or degree_rank > old_data[1]:
            highest_rank_by_part[part_prefix] = (behavior_id, degree_rank)

    # 按强度从高到低排序，同强度随机打破平局
    ordered_part_data = []
    grouped_part_data = {}
    for part_prefix, (behavior_id, degree_rank) in highest_rank_by_part.items():
        grouped_part_data.setdefault(degree_rank, []).append((part_prefix, behavior_id))
    for degree_rank in sorted(grouped_part_data, reverse=True):
        same_rank_data = grouped_part_data[degree_rank]
        if len(same_rank_data) > 1:
            random.shuffle(same_rank_data)
        ordered_part_data.extend((part_prefix, behavior_id, degree_rank) for part_prefix, behavior_id in same_rank_data)
    return ordered_part_data


def build_summary_text(character_name: str, ordered_part_data: list) -> str:
    """参数：character_name(str)为角色名，ordered_part_data(list)为select_batch_parts的排序结果；返回：str为汇总行文本，无需汇总时返回空串；用途：把未入前FULL_TALK_PART_LIMIT名的部位按强度分组拼成一行提示。"""
    summary_groups = {}
    for part_prefix, behavior_id, degree_rank in ordered_part_data[FULL_TALK_PART_LIMIT:]:
        summary_groups.setdefault(degree_rank, []).append(_translate(ORGASM_PART_NAME[part_prefix]))
    if not summary_groups:
        return ""
    summary_text_list = []
    for degree_rank in sorted(summary_groups, reverse=True):
        summary_text_list.append("{0}{1}".format("、".join(summary_groups[degree_rank]), _translate(ORGASM_DEGREE_TEXT[degree_rank])))
    return _translate("\n{0}{1}\n\n").format(character_name, "，".join(summary_text_list))


def _draw_orgasm_batch(character_id: int, active_behavior_ids: list, draw_second_talk) -> set:
    """参数：character_id(int)为角色id，active_behavior_ids(list)为本次将要结算的非零二段行为id列表，draw_second_talk(Callable)为未被接管时用于绘制单条口上的原函数；返回：set为已由批次绘制接管的二段行为id集合；用途：绘制一次NPC高潮批的代表口上、汇总行与合并寸止。"""
    import random

    cache_obj = _cache()
    character_data = cache_obj.character_data[character_id]
    # 收藏模式下不在收藏名单内的角色不显示口上，交回原循环由其内部检查静默处理
    if cache_obj.is_collection and character_id:
        player_data = cache_obj.character_data[0]
        if character_id not in player_data.collection_character:
            return set()
    handled_behavior_ids = set()

    # 多重绝顶先于各部位代表显示
    for behavior_id in active_behavior_ids:
        if behavior_id.startswith("plural_orgasm_"):
            draw_second_talk(character_id, behavior_id)
            handled_behavior_ids.add(behavior_id)

    # 计算参与显示的部位代表并排序
    ordered_part_data = select_batch_parts(active_behavior_ids)
    for behavior_id in active_behavior_ids:
        if _parse_part_orgasm_behavior(behavior_id) is not None:
            handled_behavior_ids.add(behavior_id)

    # 前几个部位显示完整代表口上
    for part_prefix, behavior_id, degree_rank in ordered_part_data[:FULL_TALK_PART_LIMIT]:
        draw_second_talk(character_id, behavior_id)

    # 未入前几名的部位按强度分组汇总成一行
    summary_text = build_summary_text(character_data.name, ordered_part_data)
    if summary_text:
        _draw_orgasm_info_text(summary_text)

    # 多部位寸止合并标题，并只从有正文的部位中随机选择一个代表正文
    edge_behavior_ids = [behavior_id for behavior_id in active_behavior_ids if behavior_id.endswith("_orgasm_edge")]
    if len(edge_behavior_ids) > 1:
        handled_behavior_ids.update(edge_behavior_ids)
        edge_behavior_by_part = {behavior_id.split("_orgasm_edge", 1)[0]: behavior_id for behavior_id in edge_behavior_ids}
        ordered_edge_ids = [edge_behavior_by_part[part_prefix] for part_prefix in ORGASM_PART_ORDER if part_prefix in edge_behavior_by_part]
        part_names = "、".join(_translate(ORGASM_PART_NAME[behavior_id.split("_orgasm_edge", 1)[0]]) for behavior_id in ordered_edge_ids)
        _draw_orgasm_info_text(_translate("\n{0}{1}{2}\n\n").format(character_data.name, part_names, _translate("绝顶寸止")))
        from Script.Design import talk

        available_edge_ids = [behavior_id for behavior_id in ordered_edge_ids if talk.handle_talk_sub(character_id, behavior_id, {})[0]]
        if available_edge_ids:
            _draw_second_talk_without_title(character_id, random.choice(available_edge_ids))

    return handled_behavior_ids


def patched_second_behavior_effect(
    character_id: int,
    change_data,
    second_behavior_list: list = [],
    orgasm_settle_flag: bool = False,
):
    """参数：character_id(int)为角色id，change_data(CharacterStatusChange)为状态变更记录对象，second_behavior_list(list)为仅计算范围，orgasm_settle_flag(bool)为是否高潮结算调用；返回：原函数返回值；用途：在调用原函数之前把本次结算的绝顶口上合并成一批显示，并在原函数执行期间吞掉已被批次接管的行为口上，其余结算逻辑与效果全部交由上游原函数执行。"""
    from Script.Design import talk

    cache_obj = _cache()
    # 玩家不进批次（上游自带的同部位取最高过滤已覆盖玩家）；
    # 同角色重入时内层不再重复挂钩，避免内外层批次互相串扰
    if not character_id or character_id in _BATCH_ACTIVE_CHARACTER_IDS:
        return call_original(SECOND_BEHAVIOR, "second_behavior_effect", character_id, change_data, second_behavior_list, orgasm_settle_flag)

    character_data = cache_obj.character_data[character_id]
    # 离屏守卫：必须与上游 second_behavior_effect 的位置早退条件保持一致
    # （角色位置与玩家不同、且移动来源也与玩家位置不同时，上游走 must_show_talk_check 分支直接返回，不显示口上）。
    # 上游改这个条件时本守卫要同步改，否则会把离屏角色的绝顶口上画上屏。
    player_position = cache_obj.character_data[0].position
    if character_data.position != player_position and character_data.behavior.move_src != player_position:
        return call_original(SECOND_BEHAVIOR, "second_behavior_effect", character_id, change_data, second_behavior_list, orgasm_settle_flag)

    # 在原函数开始逐条结算之前快照本次待结算的非零二段行为，并立刻绘制合并批次，
    # 保证批次口上取到的是任何二段效果执行之前的角色状态（与上游逐条显示的时点一致）
    pending_behavior_ids = [
        behavior_id
        for behavior_id, behavior_value in character_data.second_behavior.items()
        if behavior_value and (not second_behavior_list or behavior_id in second_behavior_list)
    ]
    original_handle_second_talk = talk.handle_second_talk
    handled_behavior_ids = _draw_orgasm_batch(character_id, pending_behavior_ids, original_handle_second_talk)
    if not handled_behavior_ids:
        return call_original(SECOND_BEHAVIOR, "second_behavior_effect", character_id, change_data, second_behavior_list, orgasm_settle_flag)

    def hooked_handle_second_talk(now_character_id: int, behavior_id: str = "share_blankly", *args, **kwargs):
        """参数：now_character_id(int)为角色id，behavior_id(str)为二段行为id，*args/**kwargs为透传参数；返回：原函数返回值或None；用途：吞掉本角色已被批次接管的行为口上，其余原样透传。"""
        if now_character_id == character_id and behavior_id in handled_behavior_ids:
            return
        return original_handle_second_talk(now_character_id, behavior_id, *args, **kwargs)

    talk.handle_second_talk = hooked_handle_second_talk
    _BATCH_ACTIVE_CHARACTER_IDS.add(character_id)
    try:
        return call_original(SECOND_BEHAVIOR, "second_behavior_effect", character_id, change_data, second_behavior_list, orgasm_settle_flag)
    finally:
        talk.handle_second_talk = original_handle_second_talk
        _BATCH_ACTIVE_CHARACTER_IDS.discard(character_id)
