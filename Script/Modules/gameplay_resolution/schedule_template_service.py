"""
日程模板文本与套用服务（schedule_template_service）
===================================================
提供日程模板表格文本、各选择页按钮列表与批量套用功能。
本模块不导入 Script.UI 与 Script.Settle。
"""

from collections.abc import Collection, Iterable
from types import FunctionType

from Script.Core import get_text
from Script.Design import attr_calculation
from Script.Modules.domains import identity
from Script.System.Education_System import (
    education_constant,
    schedule_template_handle,
)

_: FunctionType = get_text._
""" 翻译函数 """
ROW_SIZE = 6
""" 活动、模板与孩子选择页每行排列的按钮数量。 """
COLUMN_WIDTHS = (
    education_constant.COLUMN_WIDTH_ID,
    education_constant.COLUMN_WIDTH_NAME,
    education_constant.COLUMN_WIDTH_SLOT,
    education_constant.COLUMN_WIDTH_SLOT,
    education_constant.COLUMN_WIDTH_SLOT,
)
""" 模板表编号、模板名与三个时段五列的显示列宽元组。 """
Button = tuple[int, str]
""" 按钮条目类型，以整数标识与显示标签组成二元组。 """


def _rows(buttons: list[Button]) -> list[list[Button]]:
    """
    按每行固定数量把按钮列表拆分为多行。
    Keyword arguments:
    buttons -- list[Button]，待分组的按钮列表
    Return arguments:
    list[list[Button]] -- 按 ROW_SIZE 分组后的按钮行列表，空列表返回空列表
    """
    return [
        buttons[start : start + ROW_SIZE]
        for start in range(0, len(buttons), ROW_SIZE)
    ]


def _table_line(cells: Iterable[str]) -> str:
    """
    按显示列宽补齐五列单元格并拼接前导缩进。
    中文字符占两列，按字符数补齐无法对齐各列。
    Keyword arguments:
    cells -- Iterable[str]，恰好五列的单元格文本序列
    Return arguments:
    str -- 含前导缩进且各列补齐后的表格行前缀
    """
    return education_constant.COLUMN_INDENT + "".join(
        attr_calculation.pad_display_width(text, width)
        for text, width in zip(cells, COLUMN_WIDTHS, strict=True)
    )


def _slot_names(template_data: dict) -> list[str]:
    """
    读取模板三个时段的活动名称，缺省时段按 0 处理。
    编号 0 显示为自由选择娱乐活动，表示该时段保留每日随机娱乐。
    Keyword arguments:
    template_data -- dict，单套模板的数据字典
    Return arguments:
    list[str] -- 上午、下午、晚上三个时段的活动显示名列表
    """
    slots = template_data.get(education_constant.TEMPLATE_KEY_SLOT, {})
    return [
        schedule_template_handle.get_activity_name(slots.get(slot, 0))
        for slot in range(education_constant.SLOT_COUNT)
    ]


def head_text() -> str:
    """
    构造模板表表头文本，包含五列对齐标题、套用中列与末尾换行。
    Return arguments:
    str -- 对齐后的模板表表头字符串
    """
    cells = (_("编号"), _("模板名"), _("上午"), _("下午"), _("晚上"))
    return _table_line(cells) + _("套用中") + "\n"


def template_rows() -> list[Button]:
    """
    按模板编号升序构造全部有效模板的展示行，并跳过缺失数据的编号。
    Return arguments:
    list[Button] -- (模板编号, 含各时段活动与套用人数的行文本) 列表
    """
    rows: list[Button] = []
    for template_id in schedule_template_handle.get_all_template_id():
        template_data = schedule_template_handle.get_template_data(template_id)
        if template_data is None:
            continue
        cells = (
            str(template_id),
            template_data[education_constant.TEMPLATE_KEY_NAME],
            *_slot_names(template_data),
        )
        use_count = schedule_template_handle.get_template_use_count(template_id)
        rows.append(
            (template_id, _table_line(cells) + _("{0} 人").format(use_count))
        )
    return rows


def template_name(template_id: int) -> str | None:
    """
    读取指定模板的名称，模板不存在时返回 None。
    Keyword arguments:
    template_id -- int，模板编号
    Return arguments:
    str | None -- 模板名称，或不存在时返回 None
    """
    template_data = schedule_template_handle.get_template_data(template_id)
    if template_data is None:
        return None
    return template_data[education_constant.TEMPLATE_KEY_NAME]


def slot_buttons(template_id: int) -> list[Button]:
    """
    构造指定模板三个时段的编辑按钮，模板不存在时返回空列表。
    Keyword arguments:
    template_id -- int，模板编号
    Return arguments:
    list[Button] -- (时段编号, 带时段名与活动名的按钮标签) 列表
    """
    template_data = schedule_template_handle.get_template_data(template_id)
    if template_data is None:
        return []
    return [
        (slot, _("[{0}：{1}]").format(education_constant.SLOT_NAME[slot], name))
        for slot, name in enumerate(_slot_names(template_data))
    ]


def activity_label(entertainment_id: int) -> str:
    """
    构造单个活动的按钮标签，按需附加年龄限制与未开放标注。
    编号 0 不做场所开放判定，不附加未开放标注。
    Keyword arguments:
    entertainment_id -- int，娱乐配置编号，0 表示自由选择娱乐活动
    Return arguments:
    str -- 带方括号的活动按钮展示文本
    """
    name = schedule_template_handle.get_activity_name(entertainment_id)
    limit_text = schedule_template_handle.get_activity_age_limit_text(
        entertainment_id
    )
    place_closed = bool(
        entertainment_id
    ) and not schedule_template_handle.judge_activity_place_open(
        entertainment_id
    )
    if limit_text and place_closed:
        name = _("{0}（{1}，未开放）").format(name, limit_text)
    elif limit_text:
        name = _("{0}（{1}）").format(name, limit_text)
    elif place_closed:
        name = _("{0}（未开放）").format(name)
    return _("[{0}]").format(name)


def activity_rows() -> list[list[Button]]:
    """
    构造选择活动页的分行按钮列表。
    固定首行与年龄限制行在非空时各自单占一行，空行会被略过。
    其余活动按每行 6 个按钮分组排列。
    Return arguments:
    list[list[Button]] -- 分行后的 (娱乐编号, 活动按钮标签) 列表
    """
    first_row, age_row, other_list = [
        [(cid, activity_label(cid)) for cid in group]
        for group in schedule_template_handle.get_schedule_activity_rows()
    ]
    return [row for row in (first_row, age_row) if row] + _rows(other_list)


def template_choice_rows() -> list[list[Button]]:
    """
    构造选择模板页的分行按钮列表，跳过缺失数据的模板并按每行 6 个分组。
    Return arguments:
    list[list[Button]] -- 分行后的 (模板编号, 模板名按钮标签) 列表
    """
    buttons: list[Button] = []
    for template_id in schedule_template_handle.get_all_template_id():
        name = template_name(template_id)
        if name is not None:
            buttons.append((template_id, _("[{0}]").format(name)))
    return _rows(buttons)


def child_rows(
    child_list: list[int], selected: Collection[int]
) -> list[list[Button]]:
    """
    按候选顺序构造批量套用页的孩子按钮行，已选标记勾选符号并按每行 6 个分组。
    Keyword arguments:
    child_list -- list[int]，按展示顺序排列的候选角色编号列表
    selected -- Collection[int]，当前已选中的角色编号集合
    Return arguments:
    list[list[Button]] -- 分行后的 (角色编号, 带勾选标记的姓名标签) 列表
    """
    buttons: list[Button] = []
    for child_id in child_list:
        mark = "√" if child_id in selected else "  "
        name = identity.of(child_id).name
        buttons.append((child_id, _("[{0}{1}]").format(mark, name)))
    return _rows(buttons)


def batch_apply(template_id: int, selected: Collection[int]) -> str:
    """
    按编号升序将模板套用到所选有效角色，并返回套用结果提示文本。
    Keyword arguments:
    template_id -- int，要套用的模板编号
    selected -- Collection[int]，待套用的角色编号集合
    Return arguments:
    str -- 包含模板名与实际套用人数的结果提示文本
    """
    name = template_name(template_id)
    count = schedule_template_handle.batch_apply_template(
        sorted(selected), template_id
    )
    return _("\n已把[{0}]套用到 {1} 名孩子\n").format(name, count)
