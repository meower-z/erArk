# -*- coding: UTF-8 -*-
"""
本轮群交摘要页

分三步，前两步不 import 游戏，可单测：
- build_rows：把本轮记录整理成每个 NPC 一行的数据
- layout：把行排成 (文本, 样式) 片段，列宽按本页实际内容取最大值，人少人多都对齐
- draw_page：逐段画出来，最后一行用 WaitDraw 画并等玩家点击

版式：

    ──────────────────────── 本轮群交结算 ────────────────────────
      夜莺  <寸止释放>  三重绝顶  阴道 强绝顶 ・ 胸部、阴蒂 绝顶
      九                          胸部 小绝顶
      槐琥  <寸止!>               阴道×2、阴蒂
      可颂  <累>
    ──────────────────────────────────────────────────────────────
      绝顶 2 人 ・ 寸止中 1 人 ・ 体力耗尽 1 人         (点击继续)
"""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from wcwidth import wcswidth

from . import records

Segment = Tuple[str, str]
""" (文本, 样式名) """

DEGREE_STYLE = {0: "light_pink", 1: "hot_pink", 2: "deep_pink", 3: "levelex"}
""" 绝顶档位的颜色：越强越深 """
EDGE_STYLE = "pale_cerulean"
""" 仍在憋着的寸止部位的颜色，与绝顶的粉色系分开 """
FRAME_STYLE = "deep_gray"
""" 横线、分隔符、页脚的颜色 """
TITLE_STYLE = "gold_enrod"
""" 标题颜色 """
INDENT = "  "
""" 行首缩进 """
GAP = "  "
""" 列间距 """


@dataclass(frozen=True)
class SummaryRow:
    """
    摘要页的一行
    Keyword arguments:
    name -- 角色名
    name_style -- 姓名样式
    tag -- 状态标记（如 <寸止释放>），没有时为空串
    tag_style -- 状态标记样式
    orgasm -- 本轮 {部位: 最高档位序号}
    holding -- 仍憋着的 {部位: 寸止次数}
    tired -- 是否因体力耗尽退出
    """

    name: str
    name_style: str
    tag: str = ""
    tag_style: str = "standard"
    orgasm: Dict[str, int] = field(default_factory=dict)
    holding: Dict[str, int] = field(default_factory=dict)
    tired: bool = False


def name_style(character_data) -> str:
    """
    姓名样式：有自定义颜色的角色用角色名当样式名
    加载角色 CSV 时本体已按角色名注册了同名字体样式；text_color 本身是颜色值，不是样式名，直接用会整段不画
    Keyword arguments:
    character_data -- 角色对象（要有 name / text_color）
    Return arguments:
    str -- 样式名
    """
    return character_data.name if character_data.text_color else "standard"


def build_rows(turn, character_data: dict) -> List[SummaryRow]:
    """
    整理摘要页的行；寸止标记的余量在此刻按实时状态计算，与状态栏一致
    Keyword arguments:
    turn -- 本轮状态 state.TurnState
    character_data -- cache.character_data
    Return arguments:
    List[SummaryRow] -- 每个要列出的 NPC 一行，按角色id升序
    """
    rows = []
    for character_id in records.summary_row_ids(turn.orgasm_record, turn.edge_record, turn.break_reason):
        character = character_data[character_id]
        reason = turn.break_reason.get(character_id)
        edge_counts = turn.edge_record.get(character_id, {})
        orgasm_parts = turn.orgasm_record.get(character_id, {})

        def read_margin(character=character):
            return records.edge_margin(character_data[0].ability[30], character.h_state.orgasm_edge_count)

        tag, tag_style = records.edge_status_tag(reason, edge_counts, orgasm_parts, read_margin)
        # 已兑现成绝顶的部位只在绝顶侧显示，寸止侧只列仍憋着的
        _released, holding = records.split_edge_parts(edge_counts, orgasm_parts, reason is not None)
        rows.append(SummaryRow(character.name, name_style(character), tag, tag_style or "standard", dict(orgasm_parts), holding, reason == "tired"))
    return rows


def _width(text: str) -> int:
    """
    显示宽度（全角 2，半角 1），与本体 text_handle.get_text_index 同一口径
    Keyword arguments:
    text -- 文本
    Return arguments:
    int -- 宽度
    """
    width = wcswidth(text)
    return width if width >= 0 else sum(max(wcswidth(ch), 0) for ch in text)


def _pad(text: str, width: int) -> str:
    """
    右侧补空格到指定显示宽度
    Keyword arguments:
    text -- 文本
    width -- 目标宽度
    Return arguments:
    str -- 补齐后的文本
    """
    return text + " " * max(width - _width(text), 0)


def kind_of(row: SummaryRow) -> Segment:
    """
    类别列：N重绝顶 / 空；颜色取本行最高绝顶档位的颜色
    只有一个部位绝顶的行留空：明细列的"部位 档位"已说明是绝顶，再写"绝顶"会和"小绝顶"等字样重复
    只寸止的行留空：标记列的 <寸止> 已说明在憋着，明细列的寸止色部位说明憋着哪里
    Keyword arguments:
    row -- 行数据
    Return arguments:
    Segment -- (文本, 样式)
    """
    if len(row.orgasm) > 1:
        return records.orgasm_kind(len(row.orgasm)), DEGREE_STYLE.get(max(row.orgasm.values()), "hot_pink")
    return "", "standard"


def detail_of(row: SummaryRow) -> List[Segment]:
    """
    明细列：绝顶部位按档位从高到低分组（部位白字、档位彩字），之后接仍憋着的寸止部位
    例：阴道、肛肠 超强绝顶 ・ 子宫 强绝顶   寸止 胸部×3
    Keyword arguments:
    row -- 行数据
    Return arguments:
    List[Segment] -- 片段列表，没有内容时为空
    """
    segments: List[Segment] = []
    groups = records.group_by_value(row.orgasm)
    for index, degree in enumerate(sorted(groups, reverse=True)):
        if index:
            segments.append((" ・ ", FRAME_STYLE))
        segments.append((records.part_names(groups[degree]) + " ", "standard"))
        segments.append((records.DEGREE_TEXT.get(degree, ""), DEGREE_STYLE.get(degree, "hot_pink")))
    if row.holding:
        # 只寸止的行标记列已是 <寸止>，不再加前缀
        if segments:
            segments.append(("   寸止 ", FRAME_STYLE))
        by_count = records.group_by_value(row.holding)
        texts = []
        for count in sorted(by_count, reverse=True):
            # 同次数的每个部位都带 ×N，否则"阴蒂、阴道×3"会被读成阴蒂只有一次
            suffix = f"×{count}" if count > 1 else ""
            texts.append(records.part_names(by_count[count], suffix + "、") + suffix)
        segments.append(("、".join(texts), EDGE_STYLE))
    return segments


def sort_key(row: SummaryRow) -> tuple:
    """
    排序：绝顶的人在前（部位多、档位高的更靠前），其次寸止中，最后只有标记的；同组内保持角色id顺序
    Keyword arguments:
    row -- 行数据
    Return arguments:
    tuple -- 排序键
    """
    if row.orgasm:
        return (0, -len(row.orgasm), -max(row.orgasm.values()))
    if row.holding:
        return (1, 0, 0)
    return (2, 0, 0)


def _table(rows: List[SummaryRow]) -> List[List[Segment]]:
    """
    把各行排成对齐的表：姓名 | 标记 | 类别 | 明细；某一列整页为空时不占宽度，行尾不留空格
    Keyword arguments:
    rows -- 行数据
    Return arguments:
    List[List[Segment]] -- 每行一个片段列表（不含换行）
    """
    ordered = sorted(rows, key=sort_key)
    kinds = [kind_of(row) for row in ordered]
    name_width = max(_width(row.name) for row in ordered)
    tag_width = max(_width(row.tag) for row in ordered)
    kind_width = max(_width(kind[0]) for kind in kinds)
    lines = []
    for row, (kind_text, kind_style) in zip(ordered, kinds):
        cells = [(row.name, row.name_style, name_width)]
        if tag_width:
            cells.append((row.tag, row.tag_style, tag_width))
        if kind_width:
            cells.append((kind_text, kind_style, kind_width))
        detail = detail_of(row)
        # 行尾连续的空列不补宽
        while not detail and len(cells) > 1 and not cells[-1][0]:
            cells.pop()
        line: List[Segment] = [(INDENT, "standard")]
        for index, (text, style, width) in enumerate(cells):
            if index:
                line.append((GAP, "standard"))
            is_last = index == len(cells) - 1 and not detail
            line.append((text if is_last else _pad(text, width), style))
        if detail:
            line.append((GAP, "standard"))
            line += detail
        lines.append(line)
    return lines


def _footer(rows: List[SummaryRow], width: int, hint: str) -> List[Segment]:
    """
    页脚：本轮人数统计，右侧点击提示
    Keyword arguments:
    rows -- 行数据
    width -- 页宽
    hint -- 点击提示文本
    Return arguments:
    List[Segment] -- 片段列表
    """
    counts = (
        ("绝顶", sum(1 for row in rows if row.orgasm)),
        ("寸止中", sum(1 for row in rows if row.holding)),
        ("体力耗尽", sum(1 for row in rows if row.tired)),
    )
    stat = INDENT + " ・ ".join(f"{label} {count} 人" for label, count in counts if count)
    return [(stat + " " * max(width - _width(stat) - _width(hint), len(GAP)) + hint, FRAME_STYLE)]


def layout(rows: List[SummaryRow], max_width: int, title: str, hint: str) -> List[List[Segment]]:
    """
    排出整页：标题横线、表格、横线、页脚；最后一个元素是页脚，由调用方画成等待点击
    页宽跟着本页内容走（不铺满整行）：人少时整页紧凑，窗口比 text_width 窄时横线也不会折行
    Keyword arguments:
    rows -- 行数据（非空）
    max_width -- 页宽上限（text_width）
    title -- 标题文本
    hint -- 点击提示文本
    Return arguments:
    List[List[Segment]] -- 每行一个片段列表（不含换行）
    """
    table = _table(rows)
    stat_width = _width(_footer(rows, 0, "")[0][0])
    content_width = max([_width("".join(text for text, _style in line)) for line in table] + [stat_width + _width(GAP + hint), _width(title) + 16])
    width = min(content_width + _width(INDENT), max_width)
    side = (width - _width(title) - 2) // 2
    title_line = [("─" * side + " ", FRAME_STYLE), (title, TITLE_STYLE), (" " + "─" * (width - side - _width(title) - 2), FRAME_STYLE)]
    return [title_line] + table + [[("─" * width, FRAME_STYLE)], _footer(rows, width, hint)]


def draw_page(rows: List[SummaryRow]) -> None:
    """
    画摘要页，最后等玩家点击；没有行时什么都不画，不弹空页
    页脚放进 WaitDraw 本身：WaitDraw 文本为空时不等待点击
    Keyword arguments:
    rows -- build_rows 的结果
    Return arguments:
    None
    """
    if not rows:
        return
    from Script.Config import normal_config
    from Script.Core import get_text
    from Script.UI.Moudle import draw

    _ = get_text._
    lines = layout(rows, normal_config.config_normal.text_width, _("本轮群交结算"), _("(点击继续)"))
    # 空一行，与上方的结算文本分开
    for line in [[]] + lines[:-1]:
        for text, style in line + [("\n", "standard")]:
            segment = draw.NormalDraw()
            segment.style = style
            segment.text = text
            segment.draw()
    footer_text, footer_style = lines[-1][0]
    wait_draw = draw.WaitDraw()
    wait_draw.style = footer_style
    wait_draw.text = footer_text + "\n"
    wait_draw.draw()
