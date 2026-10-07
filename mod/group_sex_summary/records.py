# -*- coding: UTF-8 -*-
"""
本轮绝顶/寸止记录的纯函数：合并、断因、寸止余量、标记、部位名

本模块不 import 任何 Script 模块，可以脱离游戏单测（tests/test_records.py）。
记录的形状：
- orgasm_record  {角色id: {部位: 本轮最高档位序号}}
- edge_record    {角色id: {部位: 本轮寸止次数}}
- break_reason   {角色id: "tired" | "release" | "fail"}
"""
from typing import Callable, Dict, List, Optional, Tuple

PART_ORDER = ("s", "b", "c", "v", "a", "u", "w", "m", "f", "h")
""" 部位显示顺序，与 local_orgasm_batch_talk_fix 的 ORGASM_PART_ORDER 一致 """
PART_NAME = {"s": "皮肤", "b": "胸部", "c": "阴蒂", "v": "阴道", "a": "肛肠", "u": "尿道", "w": "子宫", "m": "口喉", "f": "兽部", "h": "心理"}
""" 部位显示名，与 local_orgasm_batch_talk_fix 措辞一致 """
DEGREE_TEXT = {0: "小绝顶", 1: "绝顶", 2: "强绝顶", 3: "超强绝顶"}
""" 档位序号（orgasm_settle.orgasm_degree_order 的 rank）-> 显示文本 """
PLURAL_COUNT_NAME = ["双重", "三重", "四重", "五重", "六重", "七重", "八重", "九重", "十重"]
""" 多重绝顶前缀，同 talk.second_behavior_info_text 的文本表（下标 = 部位数 - 2） """

BREAK_PRIORITY = {"tired": 3, "release": 2, "fail": 1}
""" 寸止断因优先级：太累退出 > 主动释放 > 判定失败；同一角色一轮内只升不降 """
BREAK_TAG = {
    "tired": ("<累>", "little_dark_slate_blue"),
    "release": ("<寸止释放>", "gold_enrod"),
    "fail": ("<寸止失败>", "gold_enrod"),
}
""" 断因 -> (摘要标记, 样式)；<累> 与状态栏的体力耗尽标记同色 """

EDGE_SUFFIX = "_orgasm_edge"
""" 寸止二段行为id的后缀：{部位}_orgasm_edge """


def merge_second_behavior(orgasm_record: dict, edge_record: dict, character_id: int, second_behavior: dict, parse_part_degree: Callable) -> None:
    """
    把一次结算里置位的绝顶/寸止二段行为并入本轮记录：绝顶按部位取最高档，寸止按部位累加次数
    Keyword arguments:
    orgasm_record -- 本轮绝顶记录（就地修改）
    edge_record -- 本轮寸止记录（就地修改）
    character_id -- 角色id
    second_behavior -- 该角色的二段行为字典 {二段行为id: 是否触发}
    parse_part_degree -- 二段行为id -> (部位, 档位序号)，不是绝顶id时部位为 None
    Return arguments:
    None
    """
    for second_behavior_id, value in second_behavior.items():
        if not value:
            continue
        if second_behavior_id.endswith(EDGE_SUFFIX):
            part = second_behavior_id[: -len(EDGE_SUFFIX)]
            part_count = edge_record.setdefault(character_id, {})
            part_count[part] = part_count.get(part, 0) + 1
            continue
        part, degree_rank = parse_part_degree(second_behavior_id)
        if part is None:
            continue
        part_degree = orgasm_record.setdefault(character_id, {})
        if part not in part_degree or degree_rank > part_degree[part]:
            part_degree[part] = degree_rank


def mark_break_reason(break_reason: dict, character_id: int, reason: str) -> None:
    """
    记一次寸止断因，按 BREAK_PRIORITY 只升不降
    Keyword arguments:
    break_reason -- 本轮断因表（就地修改）
    character_id -- 角色id
    reason -- "tired" / "release" / "fail"
    Return arguments:
    None
    """
    if BREAK_PRIORITY.get(reason, 0) >= BREAK_PRIORITY.get(break_reason.get(character_id, ""), 0):
        break_reason[character_id] = reason


def edge_margin(skill_lv: int, orgasm_edge_count: dict) -> int:
    """
    寸止余量：玩家寸止技巧×3 减各部位寸止次数的平方和；越小越憋不住，<0 表示已超过能控制的极限
    本体状态栏的 <寸止> 档位与 judge_orgasm_edge_success 的提示分档用的是同一个式子，两处共用这一份
    Keyword arguments:
    skill_lv -- 玩家寸止技巧等级 ability[30]
    orgasm_edge_count -- {部位: 寸止次数}
    Return arguments:
    int -- 余量
    """
    return skill_lv * 3 - sum(value * value for value in orgasm_edge_count.values())


def is_near_limit(margin: int) -> bool:
    """
    寸止成功但余量 <=2：状态栏带感叹号的两档，此时本体提示是"到极限了"或"随时可能释放"，玩家需要当场看到
    Keyword arguments:
    margin -- 寸止余量
    Return arguments:
    bool -- 是否接近极限
    """
    return margin <= 2


def holding_edge_tag(margin: int) -> Tuple[str, str]:
    """
    仍在憋着的角色的寸止标记，三档与状态栏 character_info_head 的 <寸止> 标记一致
    Keyword arguments:
    margin -- 寸止余量
    Return arguments:
    Tuple[str, str] -- (标记文本, 样式)
    """
    if margin >= 3:
        return "<寸止>", "hot_pink"
    if margin >= 0:
        return "<寸止!>", "red"
    return "<寸止!!>", "levelex"


def split_edge_parts(edge_counts: dict, orgasm_parts: dict, broken: bool) -> Tuple[dict, dict]:
    """
    把寸止记录拆成"已兑现成绝顶"与"仍憋着"两半，避免同一部位同时出现在绝顶侧和寸止侧
    憋住的量被释放时（判定失败或主动释放），本体会把同一部位再按普通绝顶结算一遍，所以两份记录会重叠。
    寸止断过的角色整轮憋住的量都已兑现：判定失败时本体不写 {部位}_orgasm_edge，不能只靠绝顶记录去认
    Keyword arguments:
    edge_counts -- 该角色的 {部位: 寸止次数}
    orgasm_parts -- 该角色的 {部位: 档位序号}
    broken -- 该角色本轮是否有寸止断因
    Return arguments:
    Tuple[dict, dict] -- ({已兑现部位: 次数}, {仍憋着部位: 次数})
    """
    if broken:
        return edge_counts, {}
    released = {part: count for part, count in edge_counts.items() if part in orgasm_parts}
    holding = {part: count for part, count in edge_counts.items() if part not in orgasm_parts}
    return released, holding


def edge_status_tag(reason: Optional[str], edge_counts: dict, orgasm_parts: dict, read_margin: Callable[[], int]) -> Tuple[str, str]:
    """
    摘要行的寸止标记：断过的角色显示断因；憋住后又兑现的显示 <寸止释放>；仍憋着的按实时余量显示三档；没寸止过的不显示
    兑现后本体会清零 orgasm_edge_count，实时余量恒为最宽松档，所以兑现过的不能再按余量显示
    Keyword arguments:
    reason -- 该角色的断因，没有时为 None
    edge_counts -- 该角色本轮 {部位: 寸止次数}
    orgasm_parts -- 该角色本轮 {部位: 档位序号}
    read_margin -- 只在仍憋着时调用，读取该角色此刻的寸止余量
    Return arguments:
    Tuple[str, str] -- (标记文本, 样式)，不显示时为 ("", "")
    """
    if reason:
        return BREAK_TAG[reason]
    if not edge_counts:
        return "", ""
    released, _holding = split_edge_parts(edge_counts, orgasm_parts, False)
    if released:
        return BREAK_TAG["release"]
    return holding_edge_tag(read_margin())


def part_names(parts: List[str], joiner: str = "、") -> str:
    """
    按 PART_ORDER 排序并连接部位名；不在排序表里的部位（如玩家的 p）排到末尾，不丢弃，否则"N重"的数字会对不上
    Keyword arguments:
    parts -- 部位键列表
    joiner -- 连接符
    Return arguments:
    str -- 部位名文本
    """
    known = [part for part in PART_ORDER if part in parts]
    unknown = [part for part in parts if part not in PART_ORDER]
    return joiner.join(PART_NAME.get(part, part) for part in known + unknown)


def group_by_value(part_map: dict) -> Dict[int, List[str]]:
    """
    把 {部位: 值} 按值分组
    Keyword arguments:
    part_map -- {部位: 值}
    Return arguments:
    Dict[int, List[str]] -- {值: [部位]}
    """
    groups = {}
    for part, value in part_map.items():
        groups.setdefault(value, []).append(part)
    return groups


def orgasm_kind(part_count: int) -> str:
    """
    按同时绝顶的部位数给出"绝顶"或"N重绝顶"，超过十重时封顶为十重
    Keyword arguments:
    part_count -- 部位数（>=1）
    Return arguments:
    str -- 类别文本
    """
    if part_count <= 1:
        return "绝顶"
    return PLURAL_COUNT_NAME[min(part_count, len(PLURAL_COUNT_NAME) + 1) - 2] + "绝顶"


def summary_row_ids(orgasm_record: dict, edge_record: dict, break_reason: dict) -> List[int]:
    """
    摘要页要列出的角色：本轮有绝顶或寸止记录的，加上太累退出的（即使没有记录也要显示 <累>）；玩家永不列入
    释放与失败两种断因不用单独并入：它们只在处理过绝顶/寸止时才会被记下，已经在两份记录里
    Keyword arguments:
    orgasm_record -- 本轮绝顶记录
    edge_record -- 本轮寸止记录
    break_reason -- 本轮断因表
    Return arguments:
    List[int] -- 升序角色id
    """
    tired_ids = {character_id for character_id, reason in break_reason.items() if reason == "tired"}
    return sorted((set(orgasm_record) | set(edge_record) | tired_ids) - {0})


def is_edge_release_event(orgasm_edge: int, orgasm_edge_count: dict) -> bool:
    """
    这次绝顶结算是不是一次寸止释放事件
    orgasm_edge 置 2 后会一直保持到玩家再次开关寸止，期间的普通绝顶结算也读到 2；
    只有 release_orgasm_edge_now 触发的那次调用，orgasm_edge_count 还是满的（它在调用返回后才清空）
    Keyword arguments:
    orgasm_edge -- 角色 h_state.orgasm_edge
    orgasm_edge_count -- 角色 h_state.orgasm_edge_count
    Return arguments:
    bool -- 是否为释放事件
    """
    return orgasm_edge == 2 and any(orgasm_edge_count.values())
