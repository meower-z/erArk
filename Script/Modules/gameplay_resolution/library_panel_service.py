"""
图书馆管理面板纯规则服务（library_panel_service）
=================================================
本模块提供图书馆管理面板所需的借出查询、催还处理、阅读推荐、读书会排期与借阅历史逻辑。
本模块公开常量 READING、RECOMMEND_CAP、WEEK_DAYS，数据类 LentBook、RecommendOption 与 HistoryCard。
本模块公开函数 lent_books、urge_return、recommend_left、recommend_option、toggle_recommend、
party_rows、pick_party_day、history_holders 与 history_card。
本模块不执行界面绘制，也不导入 Script.UI、Script.Settle 或 Tk 模块。
"""

import datetime
from dataclasses import dataclass
from types import FunctionType
from typing import Any

from Script.Config import game_config
from Script.Core import get_text
from Script.Modules.domains import chara_life, entertainment, identity, library

_: FunctionType = get_text._
""" 翻译api """

READING = 101
""" 读书娱乐编号，对应 Entertainment.csv 中的读书活动（101），用于读书会排期与催还书娱乐安排。 """
RECOMMEND_CAP = 3
""" 阅读推荐类别的可选上限（3）。 """
WEEK_DAYS = 7
""" 每周天数常量（7），对应星期编号 0 至 6。 """


@dataclass(frozen=True, slots=True)
class LentBook:
    """
    已借出书籍列表中的单条展示数据。
    本类记录当前持书角色编号 holder_id 与包含序号、书籍小类、书名和借阅者姓名的本地化行文本 text。
    """

    holder_id: int
    text: str


@dataclass(frozen=True, slots=True)
class RecommendOption:
    """
    阅读推荐书籍类别的单条按钮展示数据。
    本类记录包含类别编号、大类与小类名称及推荐标记的本地化按钮文本 text，以及是否已推荐标志 picked。
    """

    text: str
    picked: bool


@dataclass(frozen=True, slots=True)
class HistoryCard:
    """
    单个角色的借书卡汇总与历史记录数据。
    本类记录角色姓名 name、借阅总本数 total_books、累计阅读 total_reads 与最新在前的 records。
    """

    name: str
    total_books: int
    total_reads: int
    records: tuple[str, ...]


def lent_books() -> tuple[LentBook, ...]:
    """
    查询当前由非玩家角色借出的全部书籍并组装展示条目。
    按配置顺序遍历非 0 书籍类型，并按各类型集合存储顺序遍历书籍，仅保留持书角色编号大于 0 的记录。
    Return arguments:
    tuple[LentBook, ...] -- 含持书角色编号与带三位递增序号的本地化展示文本元组
    """
    holders = library.holders()
    rows: list[LentBook] = []
    for type_id, type_data in game_config.config_book_type.items():
        if type_id == 0:
            continue
        for book_id in game_config.config_book_type_data[type_id]:
            book_name = game_config.config_book[book_id].name
            holder_id = holders[book_id]
            if holder_id > 0:
                number = str(len(rows) + 1).rjust(3, "0")
                text = f"  [{number}]({type_data.son_type_name}){book_name}"
                text += _("  (被{0}借走)").format(identity.of(holder_id).name)
                rows.append(LentBook(holder_id, text))
    return tuple(rows)


def urge_return(chara_id: int) -> str:
    """
    对指定角色执行催还书处理并返回提示文本。
    将该角色的 book_return_possibility 增加 100，并将其 entertainment_type 全部槽位设为 READING（101）。
    Keyword arguments:
    chara_id -- int，待催还书籍的角色编号
    Return arguments:
    str -- 包含角色姓名的本地化催还提示文本
    """
    name = identity.of(chara_id).name
    chara_life.book_return_possibility.set(
        chara_id, chara_life.book_return_possibility(chara_id) + 100
    )
    chara_life.entertainment_type.set(
        chara_id, [READING] * len(chara_life.entertainment_type(chara_id))
    )
    return _("\n{0}将在空闲时间前往图书馆还书\n").format(name)


def recommend_left() -> int:
    """
    计算当前剩余可选的推荐书籍类别数量。
    返回值为 RECOMMEND_CAP 减去当前已推荐类别数；当存档中已推荐超过 3 项时可返回负数。
    Return arguments:
    int -- 当前剩余可选推荐数量
    """
    return RECOMMEND_CAP - len(library.recommended())


def recommend_option(type_id: int) -> RecommendOption:
    """
    根据书籍类型编号组装阅读推荐按钮的展示文本与选中状态。
    文本格式为两位类别编号加大类与小类名称，当前已推荐时追加本地化推荐标记。
    Keyword arguments:
    type_id -- int，书籍类型编号
    Return arguments:
    RecommendOption -- 含按钮文本与是否已推荐标志的选项对象
    """
    type_data = game_config.config_book_type[type_id]
    text = (
        f"[{str(type_data.cid).rjust(2, '0')}]："
        f"{type_data.father_type_name}-{type_data.son_type_name}"
    )
    picked = type_id in library.recommended()
    if picked:
        text += _(" (已推荐)")
    return RecommendOption(text, picked)


def toggle_recommend(type_id: int) -> None:
    """
    切换指定书籍类型的推荐阅读状态。
    若该类型已在推荐集合中则将其移除；否则在当前已推荐数量不等于 RECOMMEND_CAP 时将其加入。
    Keyword arguments:
    type_id -- int，待切换推荐状态的书籍类型编号
    Return arguments:
    None -- 无返回值
    """
    recommended = library.recommended()
    if type_id in recommended:
        library.set_recommended(recommended - {type_id})
    elif len(recommended) != RECOMMEND_CAP:
        library.set_recommended(recommended | {type_id})


def party_rows() -> tuple[str, ...]:
    """
    组装一周七天的读书会排期按钮文本元组。
    按星期编号 0 至 6 依次生成含编号与星期名称的文本，当日已安排活动时追加对应娱乐活动名称。
    Return arguments:
    tuple[str, ...] -- 长度为 7 的星期按钮文本元组
    """
    rows = []
    for day in range(WEEK_DAYS):
        text = f"  [{day}]:{game_config.config_week_day[day].name}"
        party_id = entertainment.party_day(day)
        if party_id:
            text += f" ({game_config.config_entertainment[party_id].name})"
        rows.append(text)
    return tuple(rows)


def pick_party_day(week_day: int) -> str | None:
    """
    尝试将指定星期设为读书会日期或取消当日读书会。
    若当日已为读书会则清零并返回 None；若当日被其他活动占用则保持不变并返回拒绝提示；
    若当日空闲则清除其他天的读书会安排并将当日设为 READING（101）。
    Keyword arguments:
    week_day -- int，目标星期编号（0 至 6）
    Return arguments:
    str | None -- 被其他活动占用时返回本地化拒绝提示，其余情况返回 None
    """
    party_id = entertainment.party_day(week_day)
    if party_id == READING:
        entertainment.set_party_day(week_day, 0)
        return None
    if party_id:
        return _("\n这一天已经被选为其他活动了\n")
    for day in range(WEEK_DAYS):
        if entertainment.party_day(day) == READING:
            entertainment.set_party_day(day, 0)
    entertainment.set_party_day(week_day, READING)
    return None


def history_holders() -> tuple[int, ...]:
    """
    查询所有拥有非空借阅历史记录的非玩家角色编号。
    按角色身份表顺序遍历，排除玩家角色 0 以及借阅历史为空的角色。
    Return arguments:
    tuple[int, ...] -- 拥有借阅历史记录的角色编号元组
    """
    return tuple(
        cid
        for cid in identity.table()
        if cid != 0 and chara_life.borrow_book_history(cid)
    )


def history_card(character_id: int) -> HistoryCard:
    """
    读取指定角色的借阅历史并组装借书卡统计与倒序记录文本。
    累计总借阅本数与各条记录的 total_read_count 之和（缺失按 0 计），并将记录按最新在前格式化。
    Keyword arguments:
    character_id -- int，目标角色编号
    Return arguments:
    HistoryCard -- 包含角色姓名、汇总计数与本地化记录文本元组的借书卡对象
    """
    history = chara_life.borrow_book_history(character_id)
    records = tuple(
        _record_text(index, record)
        for index, record in enumerate(reversed(history), 1)
    )
    return HistoryCard(
        identity.of(character_id).name,
        len(history),
        sum(record.get("total_read_count", 0) for record in history),
        records,
    )


def _stamp(value: str | datetime.datetime) -> str:
    """
    将借阅记录中的时间字段格式化为展示文本。
    字符串值直接原样返回，日期时间对象按 %Y年%m月%d日 %H:%M 格式输出。
    Keyword arguments:
    value -- str | datetime.datetime，借阅或归还时间值
    Return arguments:
    str -- 格式化后的时间文本
    """
    if isinstance(value, str):
        return value
    return value.strftime("%Y年%m月%d日 %H:%M")


def _record_text(index: int, record: dict[str, Any]) -> str:
    """
    将单条借阅历史字典格式化为借书卡展示段落。
    包含两位序号、书名（缺省为未知书籍）、有效书籍编号对应的小类名称、借书时间、还书时间与阅读次数。
    Keyword arguments:
    index -- int，倒序展示的 1 起序号
    record -- dict[str, Any]，单条借阅历史字典
    Return arguments:
    str -- 本地化格式的单条借阅记录文本
    """
    book_id = record.get("book_id", 0)
    book_name = record.get("book_name", _("未知书籍"))
    borrow_time = record.get("borrow_time", None)
    return_time = record.get("return_time", None)
    read_count = record.get("total_read_count", 0)
    borrow_text = _stamp(borrow_time) if borrow_time else ""
    return_text = _stamp(return_time) if return_time else _("仍在借阅中")
    text = _("  [{0}] 《{1}》").format(str(index).rjust(2, "0"), book_name)
    if book_id in game_config.config_book:
        type_data = game_config.config_book_type[
            game_config.config_book[book_id].type
        ]
        text += _(" ({0})").format(type_data.son_type_name)
    text += _("\n      借书时间：{0}").format(borrow_text)
    text += _("\n      还书时间：{0}").format(return_text)
    text += _("\n      阅读次数：{0}次\n").format(read_count)
    return text
