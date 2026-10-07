# -*- coding: UTF-8 -*-
"""
绝顶口上批次合并显示

NPC 在一次二段行为结算中多个部位同时绝顶时，本体为每个部位各画一段完整口上，部位一多就刷屏。
本 mod 把同一次结算的绝顶口上合并成一批：
- 多重绝顶(plural_orgasm_*)口上先出
- 同一部位只取最高等级，按强度从高到低排序（同强度随机打乱），前 3 个部位出完整口上
- 第 4 个部位起按强度分组汇总成一行黄色提示
- 多部位寸止合并成一行标题，再从有正文的部位里随机挑一条正文（不带标题）
所有结算效果仍由本体逐条执行，本 mod 只改口上显示。玩家(0)不进批次。

接入方式：
1. 包装 second_behavior.second_behavior_effect（mod_info.json 声明）：只为本次调用开一个"批次"，记下待结算的二段行为
2. 本体钩子 mod_hook.second_behavior_talk 在逐条结算循环里问"这一条画不画口上"。批次在第一次被问到时整块绘制，
   之后对已被批次接管的行为回答"不画"。钩子只在本体的离屏早退之后才会被调用，所以离屏角色天然不画批次；
   第一次被问到时还没有任何二段效果执行，批次口上取到的前提状态与本体逐条显示时一致。
对应上游已拒绝的 PR #253。
"""
import random
from typing import Dict, List, Optional, Set, Tuple

# mod 管理器导入替换目标 Script.Design.second_behavior 时，若它是第一个被导入的 Design 模块会撞上循环导入
# （settle_behavior -> ... -> item_effect 的装饰器要用尚未执行完的 settle_behavior）。先从 handle_npc_ai 把整条链导入一遍。
from Script.Design import handle_npc_ai as _preload_design_modules  # noqa: F401
from Script.Core import cache_control, get_text, mod_hook

MOD_ID = "local_orgasm_batch_talk_fix"
""" mod_id，也是钩子挂载者名 """
SECOND_BEHAVIOR = "Script.Design.second_behavior"
""" 被包装函数所在模块 """

ORGASM_PART_ORDER = ("s", "b", "c", "v", "a", "u", "w", "m", "f", "h")
""" 部位显示顺序，与 orgasm_settle 遍历部位的顺序一致 """
ORGASM_PART_NAME = {"s": "皮肤", "b": "胸部", "c": "阴蒂", "v": "阴道", "a": "肛肠", "u": "尿道", "w": "子宫", "m": "口喉", "f": "兽部", "h": "心理"}
""" 部位显示名 """
ORGASM_DEGREE_TEXT = {0: "小绝顶", 1: "绝顶", 2: "强绝顶", 3: "超强绝顶"}
""" 强度序号到汇总行显示名 """
FULL_TALK_PART_LIMIT = 3
""" 出完整口上的部位数，其余进汇总行 """

_ = get_text._
""" 翻译api """


class _Batch:
    """一次 second_behavior_effect 调用里某个 NPC 的口上批次"""

    __slots__ = ("pending_ids", "handled_ids")

    def __init__(self, pending_ids: List[str]):
        """
        初始化批次
        Keyword arguments:
        pending_ids -- 本次待结算的非零二段行为id（按本体字典顺序）
        Return arguments:
        None
        """
        self.pending_ids = pending_ids
        """ 本次待结算的非零二段行为id """
        self.handled_ids: Optional[Set[str]] = None
        """ 已由批次绘制接管的行为id；None 表示批次还没画 """


_open_batches: Dict[int, _Batch] = {}
""" 角色id -> 正在结算中的批次；同角色重入时内层沿用外层批次 """


# ========== 纯函数：选部位、拼汇总行 ==========


def parse_part_orgasm(second_behavior_id: str) -> Optional[Tuple[str, int]]:
    """
    识别部位绝顶行为（沿用本体 orgasm_settle 的解析规则）
    Keyword arguments:
    second_behavior_id -- 二段行为id
    Return arguments:
    Optional[Tuple[str, int]] -- (部位前缀, 强度序号)；不是部位绝顶或部位未知时为 None
    """
    from Script.Settle import orgasm_settle

    orgasm_part, orgasm_degree = orgasm_settle.get_orgasm_part_and_degree(second_behavior_id)
    if orgasm_part not in ORGASM_PART_NAME:
        return None
    return orgasm_part, orgasm_degree


def select_batch_parts(behavior_ids: List[str]) -> List[Tuple[str, str, int]]:
    """
    同一部位只留最高等级，按强度从高到低排序，同强度随机打乱
    Keyword arguments:
    behavior_ids -- 待结算的二段行为id
    Return arguments:
    List[Tuple[str, str, int]] -- [(部位前缀, 二段行为id, 强度序号)]
    """
    highest_by_part: Dict[str, Tuple[str, int]] = {}
    for behavior_id in behavior_ids:
        parsed = parse_part_orgasm(behavior_id)
        if parsed is None:
            continue
        part, degree = parsed
        if part not in highest_by_part or degree > highest_by_part[part][1]:
            highest_by_part[part] = (behavior_id, degree)

    parts_by_degree: Dict[int, List[Tuple[str, str]]] = {}
    for part, (behavior_id, degree) in highest_by_part.items():
        parts_by_degree.setdefault(degree, []).append((part, behavior_id))
    ordered = []
    for degree in sorted(parts_by_degree, reverse=True):
        same_degree = parts_by_degree[degree]
        if len(same_degree) > 1:
            random.shuffle(same_degree)
        ordered.extend((part, behavior_id, degree) for part, behavior_id in same_degree)
    return ordered


def build_summary_text(character_name: str, ordered_parts: List[Tuple[str, str, int]]) -> str:
    """
    把第 FULL_TALK_PART_LIMIT+1 个起的部位按强度分组拼成一行
    Keyword arguments:
    character_name -- 角色名
    ordered_parts -- select_batch_parts 的结果
    Return arguments:
    str -- 汇总行文本；不需要汇总时为空串
    """
    names_by_degree: Dict[int, List[str]] = {}
    for part, _behavior_id, degree in ordered_parts[FULL_TALK_PART_LIMIT:]:
        names_by_degree.setdefault(degree, []).append(_(ORGASM_PART_NAME[part]))
    if not names_by_degree:
        return ""
    groups = ["{0}{1}".format("、".join(names_by_degree[degree]), _(ORGASM_DEGREE_TEXT[degree])) for degree in sorted(names_by_degree, reverse=True)]
    return _("\n{0}{1}\n\n").format(character_name, "，".join(groups))


# ========== 绘制 ==========


def _draw_info_line(text: str) -> None:
    """
    绘制黄色汇总提示并等待玩家
    Keyword arguments:
    text -- 提示文本
    Return arguments:
    None
    """
    from Script.Config import normal_config
    from Script.UI.Moudle import draw

    info_draw = draw.WaitDraw()
    info_draw.style = "gold_enrod"
    info_draw.width = normal_config.config_normal.text_width
    info_draw.text = text
    info_draw.draw()


def _draw_talk_body_only(character_id: int, behavior_id: str) -> None:
    """
    只画二段行为口上正文、不画标题（handle_talk_draw 的标题由 second_behavior_id 触发，传空串即跳过）
    Keyword arguments:
    character_id -- 角色id
    behavior_id -- 二段行为id
    Return arguments:
    None
    """
    from Script.Design import talk

    talk_data, _premise_dict = talk.handle_talk_sub(character_id, behavior_id, {})
    talk_text, talk_id, common_behavior_id = talk.choice_talk_from_talk_data(talk_data, behavior_id)
    talk.handle_talk_draw(character_id, talk_text, talk_id, "", common_behavior_id)


def _draw_edge_merge(character_id: int, edge_ids: List[str]) -> None:
    """
    多部位寸止：一行合并标题 + 从有正文的部位里随机挑一条正文
    Keyword arguments:
    character_id -- 角色id
    edge_ids -- 本次的寸止行为id（至少 2 个）
    Return arguments:
    None
    """
    from Script.Design import talk

    id_by_part = {behavior_id.split("_orgasm_edge", 1)[0]: behavior_id for behavior_id in edge_ids}
    ordered_parts = [part for part in ORGASM_PART_ORDER if part in id_by_part]
    part_names = "、".join(_(ORGASM_PART_NAME[part]) for part in ordered_parts)
    character_name = cache_control.cache.character_data[character_id].name
    _draw_info_line(_("\n{0}{1}{2}\n\n").format(character_name, part_names, _("绝顶寸止")))
    with_body = [id_by_part[part] for part in ordered_parts if talk.handle_talk_sub(character_id, id_by_part[part], {})[0]]
    if with_body:
        _draw_talk_body_only(character_id, random.choice(with_body))


def draw_batch(character_id: int, pending_ids: List[str]) -> Set[str]:
    """
    绘制一个 NPC 的整批绝顶口上
    Keyword arguments:
    character_id -- 角色id
    pending_ids -- 本次待结算的非零二段行为id
    Return arguments:
    Set[str] -- 被批次接管的行为id（本体随后不再逐条画它们的口上）
    """
    from Script.Design import talk

    cache = cache_control.cache
    # 收藏模式下不在收藏名单里的角色本来就不显示口上，交回本体静默处理
    if cache.is_collection and character_id not in cache.character_data[0].collection_character:
        return set()

    handled: Set[str] = set()
    for behavior_id in pending_ids:
        if behavior_id.startswith("plural_orgasm_"):
            talk.handle_second_talk(character_id, behavior_id)
            handled.add(behavior_id)

    ordered_parts = select_batch_parts(pending_ids)
    handled.update(behavior_id for behavior_id in pending_ids if parse_part_orgasm(behavior_id) is not None)
    for _part, behavior_id, _degree in ordered_parts[:FULL_TALK_PART_LIMIT]:
        talk.handle_second_talk(character_id, behavior_id)
    summary_text = build_summary_text(cache.character_data[character_id].name, ordered_parts)
    if summary_text:
        _draw_info_line(summary_text)

    edge_ids = [behavior_id for behavior_id in pending_ids if behavior_id.endswith("_orgasm_edge")]
    if len(edge_ids) > 1:
        handled.update(edge_ids)
        _draw_edge_merge(character_id, edge_ids)
    return handled


# ========== 接入本体 ==========


def filter_second_talk(talk_flag: bool, character_id: int, second_behavior_id: str) -> bool:
    """
    second_behavior_talk 钩子：批次第一次被问到时整块绘制，已接管的行为不再由本体画口上
    Keyword arguments:
    talk_flag -- 本体的判定
    character_id -- 角色id
    second_behavior_id -- 二段行为id
    Return arguments:
    bool -- 新判定
    """
    batch = _open_batches.get(character_id)
    if batch is None:
        return talk_flag
    if batch.handled_ids is None:
        batch.handled_ids = draw_batch(character_id, batch.pending_ids)
    if second_behavior_id in batch.handled_ids:
        return False
    return talk_flag


def patched_second_behavior_effect(character_id: int, change_data, second_behavior_list: list = [], orgasm_settle_flag: bool = False):
    """
    包装本体 second_behavior_effect：为 NPC 的这次结算开一个口上批次，结算本身全部交给本体
    Keyword arguments:
    character_id -- 角色id
    change_data -- 状态变更记录对象
    second_behavior_list -- 仅结算该范围内的二段行为，空列表表示全部
    orgasm_settle_flag -- 是否为高潮结算调用
    Return arguments:
    本体函数的返回值
    """
    if character_id and character_id not in _open_batches:
        second_behavior = cache_control.cache.character_data[character_id].second_behavior
        pending_ids = [behavior_id for behavior_id, value in second_behavior.items() if value and (not second_behavior_list or behavior_id in second_behavior_list)]
        _open_batches[character_id] = _Batch(pending_ids)
        try:
            return call_original(SECOND_BEHAVIOR, "second_behavior_effect", character_id, change_data, second_behavior_list, orgasm_settle_flag)
        finally:
            del _open_batches[character_id]
    return call_original(SECOND_BEHAVIOR, "second_behavior_effect", character_id, change_data, second_behavior_list, orgasm_settle_flag)


mod_hook.second_behavior_talk.unregister(MOD_ID)
mod_hook.second_behavior_talk.register(filter_second_talk, owner=MOD_ID)
