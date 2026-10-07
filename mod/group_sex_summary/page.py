# -*- coding: UTF-8 -*-
"""
本轮群交摘要页

分两步：build_rows 把本轮记录整理成每个 NPC 一行的数据（不 import 游戏，可单测）；
draw_page 只负责把这些行画出来。改版式只需要改 draw_page / _draw_row。
当前版式（每行）：右对齐到锚点的姓名 + "：" + 寸止标记 + " " + 绝顶描述 + "/" + 寸止说明
"""
from dataclasses import dataclass
from typing import List

from . import records


@dataclass(frozen=True)
class SummaryRow:
    """
    摘要页的一行
    Keyword arguments:
    name -- 角色名
    name_style -- 姓名样式
    tag_text -- 寸止标记文本（含前导空格），没有时为空串
    tag_style -- 寸止标记样式
    orgasm_desc -- 绝顶描述，没有时为空串
    edge_token -- 仍憋着的寸止说明，没有时为空串
    """

    name: str
    name_style: str
    tag_text: str
    tag_style: str
    orgasm_desc: str
    edge_token: str


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

        tag_text, tag_style = records.edge_status_tag(reason, edge_counts, orgasm_parts, read_margin)
        # 已兑现成绝顶的部位只在绝顶侧显示，寸止说明只列仍憋着的
        _released, holding = records.split_edge_parts(edge_counts, orgasm_parts, reason is not None)
        rows.append(SummaryRow(character.name, name_style(character), tag_text, tag_style, records.orgasm_desc(orgasm_parts), records.edge_token(holding)))
    return rows


def _normal(text: str, style: str = "standard") -> None:
    """
    画一段普通文本
    Keyword arguments:
    text -- 文本
    style -- 样式
    Return arguments:
    None
    """
    from Script.UI.Moudle import draw

    segment = draw.NormalDraw()
    segment.style = style
    segment.text = text
    segment.draw()


def _draw_row(row: SummaryRow, anchor_width: int) -> None:
    """
    画一行
    Keyword arguments:
    row -- 行数据
    anchor_width -- 姓名右对齐的锚点宽度
    Return arguments:
    None
    """
    from Script.UI.Moudle import draw

    name_draw = draw.RightDraw()
    name_draw.width = anchor_width
    name_draw.style = row.name_style
    name_draw.text = row.name
    name_draw.draw()
    _normal("：")
    if row.tag_text:
        _normal(row.tag_text, row.tag_style)
    if row.orgasm_desc or row.edge_token:
        _normal(" ")
        if row.orgasm_desc:
            _normal(row.orgasm_desc)
        if row.orgasm_desc and row.edge_token:
            _normal("/")
        if row.edge_token:
            _normal(row.edge_token, "hot_pink")
    _normal("\n")


def draw_page(rows: List[SummaryRow]) -> None:
    """
    画摘要页：横线、标题、各行、横线，最后等玩家点击；没有行时什么都不画，不弹空页
    换行用单独的 NormalDraw，不拼进 CenterDraw：居中会把换行符一起算进宽度，标题会偏
    页脚文字放进 WaitDraw 本身：WaitDraw 文本为空时不等待点击
    Keyword arguments:
    rows -- build_rows 的结果
    Return arguments:
    None
    """
    if not rows:
        return
    from Script.Config import normal_config
    from Script.Core import get_text, text_handle
    from Script.UI.Moudle import draw

    _ = get_text._
    width = normal_config.config_normal.text_width
    draw.LineDraw("─", width).draw()
    title_draw = draw.CenterDraw()
    title_draw.width = width
    title_draw.text = _("本轮群交结算")
    title_draw.draw()
    title_newline = draw.NormalDraw()
    title_newline.text = "\n"
    title_newline.draw()
    anchor_width = width // 3
    for row in rows:
        _draw_row(row, anchor_width)
    draw.LineDraw("─", width).draw()
    wait_draw = draw.WaitDraw()
    wait_draw.width = width
    wait_draw.text = text_handle.align(_("(点击继续)"), "center", False, 1, width)
    wait_draw.draw()
