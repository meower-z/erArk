"""
服装面板纯数据服务（cloth_panel_service）
=========================================
构建服装面板展示所需的纯数据，包括只读服装富文本、H 模式穿脱切换布局、
脱衣选项文案，以及交互对象单件衣物在穿着与已脱下之间的状态切换。
本模块仅依赖配置、领域数据与无界面工具，不导入任何界面、窗口或 Tk 模块。
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import FunctionType

from Script.Config import game_config, normal_config
from Script.Core import get_text, text_handle
from Script.Modules.domains import activity, dirty, flags, identity, modes
from Script.Modules.domains import wardrobe
from Script.Modules.gameplay_resolution import cloth_see
from Script.System.Item_System import condom_handle

_: FunctionType = get_text._
""" 翻译接口。 """

OFF_CLOTHES_PER_LINE = 8
""" 服装文本与切换布局中已脱下衣物每行显示的件数上限（8）。 """


@dataclass(frozen=True, slots=True)
class SwitchLabel:
    """H 模式布局中的纯文本片段（部位标题、真空行、全裸行或已脱下标题），面板按面板宽度以普通文本绘制。"""

    text: str


@dataclass(frozen=True, slots=True)
class SwitchMarkup:
    """H 模式布局中的精液污浊富文本片段（<semen>(...)</semen>），由面板交由富文本绘制器解析绘制。"""

    text: str


@dataclass(frozen=True, slots=True)
class SwitchClothItem:
    """H 模式布局中的单件衣物按钮项，记录衣物 id、部位编号以及当前是否穿着（True 为穿着，False 为已脱下）。"""

    cloth_id: int
    clothing_type: int
    is_wear: bool


@dataclass(frozen=True, slots=True)
class SwitchLineBreak:
    """H 模式布局中的行尾换行标记，面板遇到该标记时绘制换行。"""


LINE_BREAK = SwitchLineBreak()
""" 全局复用的 SwitchLineBreak 换行标记单例。 """

SwitchToken = SwitchLabel | SwitchMarkup | SwitchClothItem | SwitchLineBreak
""" H 模式服装布局元素的联合类型别名，包含纯文本、富文本、衣物按钮项与换行标记四类。 """


@dataclass(frozen=True, slots=True)
class UndressOption:
    """单条脱衣选项的展示数据，包含完整展示文案与是否可选标志（无受影响衣物时为 False）。"""

    text: str
    selectable: bool


def _target_cid() -> int:
    """返回玩家（角色 0）当前交互对象的角色 id。"""
    return identity.of(activity.target(0)).cid


def _cloth_name(cloth_id: int) -> str:
    """从服装模板配置中读取指定衣物 id 的名称。"""
    return game_config.config_clothing_tem[cloth_id].name


def _underwear_hidden(clothing_type: int, seen: Mapping[int, bool]) -> bool:
    """判断已穿着的胸衣（部位 6）或内裤（部位 9）是否需隐藏：非调试模式且 cloth_see.seen 判定不可见时返回 True。"""
    return (
        clothing_type in cloth_see.UNDERWEAR
        and not modes.debug()
        and not seen[clothing_type]
    )


def _vacuum_shown(cloth: wardrobe.ClothView, clothing_type: int) -> bool:
    """判断部位 6 或 9 未穿衣物时是否显示真空提示：调试模式开启或已保存的 cloth_see 为真时返回 True。"""
    return (
        clothing_type in cloth_see.UNDERWEAR
        and not cloth.cloth_wear[clothing_type]
        and (modes.debug() or bool(cloth.cloth_see[clothing_type]))
    )


def _semen_markup(
    cloth_semen: dict,
    clothing_type: int,
    type_name: str,
    cloth_id: int,
    last_cloth_id: int,
) -> str:
    """
    生成单件已穿衣物的精液污浊片段（无精液时为空串）：详细模式（draw_setting[10]）仅末件取 dirty_full，
    否则每件取 dirty，键为“<部位名>精液污浊<等级>”。
    """
    if cloth_semen[clothing_type][1] == 0:
        return ""
    detailed = normal_config.system_setting.draw_setting[10]
    if detailed and cloth_id != last_cloth_id:
        return ""
    table = "dirty_full" if detailed else "dirty"
    text_cid = (
        f"{_(type_name, revert_translation=True)}"
        f"精液污浊{cloth_semen[clothing_type][2]}"
    )
    return f"<semen>({game_config.ui_text_data[table][text_cid]})</semen>"


def _condom_markup(target_cid: int, clothing_type: int, type_name: str) -> str:
    """
    生成服装部位悬挂用过避孕套的富文本片段（数量为 0 时为空串）：详细模式按 get_decoration_level 取 condom_dirty，
    否则显示“挂着N个用过的避孕套”。
    """
    count = condom_handle.get_decoration_count(target_cid, 1, clothing_type)
    if not count:
        return ""
    if normal_config.system_setting.draw_setting[10]:
        level = condom_handle.get_decoration_level(count)
        text_cid = f"{_(type_name, revert_translation=True)}避孕套装饰{level}"
        text = game_config.ui_text_data["condom_dirty"][text_cid]
    else:
        text = _("挂着{0}个用过的避孕套").format(str(count))
    return f"<semen>({text})</semen>"


def _needs_line_end(text: str) -> bool:
    """判断文本非空且不以换行符结尾时返回 True。"""
    return text != "" and text[-1] != "\n"


def _is_naked(cloth: wardrobe.ClothView) -> bool:
    """判断角色所有配置服装部位均未穿着任何衣物时返回 True。"""
    return not any(
        cloth.cloth_wear[clothing_type]
        for clothing_type in game_config.config_clothing_type
    )


def build_cloth_display_text() -> str:
    """
    构建玩家交互对象的只读服装展示富文本（只读不写入任何状态）。
    按可见部位输出穿着衣物、精液污浊与避孕套片段，在下衣（部位 8）前或为空时换行，
    详细模式下精液污浊等级非零的部位后换行，并按可见性附加真空提示；全裸时仅显示“  全裸”，
    仅当玩家或交互对象处于 H 中时按每行 8 件追加“  [已脱下]:”列表。
    Return arguments:
    str -- 组装完成的服装富文本字符串
    """
    target_cid = _target_cid()
    cloth = wardrobe.of(target_cid)
    seen = cloth_see.seen(target_cid)
    cloth_semen = dirty.view(target_cid).cloth_semen
    detailed = normal_config.system_setting.draw_setting[10]
    text = ""
    for clothing_type, type_config in game_config.config_clothing_type.items():
        type_name = type_config.name
        wear = cloth.cloth_wear[clothing_type]
        if wear:
            if _underwear_hidden(clothing_type, seen):
                continue
            if clothing_type == 8 and _needs_line_end(text):
                text += "\n"
            text += f"  [{type_name}]:"
            for cloth_id in wear:
                text += f" {_cloth_name(cloth_id)}"
                text += _semen_markup(
                    cloth_semen, clothing_type, type_name, cloth_id, wear[-1]
                )
            condom = _condom_markup(target_cid, clothing_type, type_name)
            if (
                condom
                and cloth_semen[clothing_type][1] != 0
                and _needs_line_end(text)
            ):
                text += "\n"
            text += condom
        if clothing_type == 8 and not wear:
            text += "\n"
        elif (
            _needs_line_end(text)
            and detailed
            and cloth_semen[clothing_type][2] != 0
        ):
            text += "\n"
        if _vacuum_shown(cloth, clothing_type):
            text += _("  [{0}]: 真空").format(type_name)
    if _needs_line_end(text):
        text += "\n"
    if _is_naked(cloth):
        text = _("  全裸\n")
    off_text = _("  [已脱下]:")
    count = 0
    for cloth_type in cloth.cloth_off:
        for cloth_id in cloth.cloth_off[cloth_type]:
            off_text += f" {_cloth_name(cloth_id)}"
            count += 1
            if count % OFF_CLOTHES_PER_LINE == 0:
                off_text += "\n           "
    if off_text[-1] != "\n":
        off_text += "\n"
    if count != 0 and (flags.get(0, "is_h") or flags.get(target_cid, "is_h")):
        text += off_text
    return text


def build_switch_cloth_layout() -> tuple[SwitchToken, ...]:
    """
    按绘制顺序构建玩家交互对象的 H 模式穿脱切换布局（只读不写入任何状态）。
    已穿衣物生成按钮项及精液污浊片段（不含避孕套片段），在下衣（部位 8）前及详细模式污浊等级非零部位后换行；
    全裸时保留真空提示并追加全裸行，所有已脱衣物不论是否处于 H 均按每行 8 件列于“  [已脱下]:”后。
    Return arguments:
    tuple -- 按绘制顺序排列的 SwitchToken 布局片段元组
    """
    target_cid = _target_cid()
    cloth = wardrobe.of(target_cid)
    seen = cloth_see.seen(target_cid)
    cloth_semen = dirty.view(target_cid).cloth_semen
    detailed = normal_config.system_setting.draw_setting[10]
    tokens: list[SwitchToken] = []
    row: list[SwitchToken] = []
    for clothing_type, type_config in game_config.config_clothing_type.items():
        type_name = type_config.name
        wear = cloth.cloth_wear[clothing_type]
        if wear:
            if _underwear_hidden(clothing_type, seen):
                continue
            if clothing_type == 8 and row:
                tokens += [*row, LINE_BREAK]
                row = []
            row.append(SwitchLabel(f"  [{type_name}]:"))
            for cloth_id in wear:
                row.append(SwitchClothItem(cloth_id, clothing_type, True))
                markup = _semen_markup(
                    cloth_semen, clothing_type, type_name, cloth_id, wear[-1]
                )
                if markup:
                    row.append(SwitchMarkup(markup))
        if clothing_type == 8 and not wear:
            if row:
                tokens += [*row, LINE_BREAK]
                row = []
        elif row and detailed and cloth_semen[clothing_type][2] != 0:
            tokens += [*row, LINE_BREAK]
            row = []
        if _vacuum_shown(cloth, clothing_type):
            row.append(SwitchLabel(_("  [{0}]: 真空").format(type_name)))
    if row:
        tokens += [*row, LINE_BREAK]
    if _is_naked(cloth):
        tokens.append(SwitchLabel(_("  全裸\n")))
    off_items = [
        SwitchClothItem(cloth_id, cloth_type, False)
        for cloth_type in cloth.cloth_off
        for cloth_id in cloth.cloth_off[cloth_type]
    ]
    for start in range(0, len(off_items), OFF_CLOTHES_PER_LINE):
        if start == 0:
            tokens.append(SwitchLabel(_("  [已脱下]:")))
        tokens += [*off_items[start : start + OFF_CLOTHES_PER_LINE], LINE_BREAK]
    return tuple(tokens)


def undress_option_labels() -> list[str]:
    """
    返回按选项序号 0..3 排列的四条已翻译脱衣选项标签（只穿内衣、只穿袜子手套等、全裸、把内裤收走）。
    Return arguments:
    list -- 长度为 4 的选项标签字符串列表
    """
    return [
        _("脱到只穿内衣      "),
        _("脱到只穿袜子手套等"),
        _("脱到全裸          "),
        _("把内裤收走        "),
    ]


def build_undress_option(choice: int, label: str) -> UndressOption:
    """
    构建交互对象第 choice 项（0: 8/5，1: 8/9/5/6，2: 全部位，3: 内裤9）脱衣选项；
    无衣物时提示“无可脱的衣服/无可收的内裤”且不可选。
    Keyword arguments:
    choice -- 脱衣选项序号（0..3）
    label -- 选项展示标签
    Return arguments:
    UndressOption -- 含“<序号><标签> ：会脱掉/会收走 <衣物名>”或空提示及是否可选的选项对象
    """
    take_off, nothing_to_take_off = _(" ：会脱掉"), _(" ：无可脱的衣服")
    rules = {
        0: ((8, 5), take_off, nothing_to_take_off),
        1: ((8, 9, 5, 6), take_off, nothing_to_take_off),
        2: (
            tuple(game_config.config_clothing_type),
            take_off,
            nothing_to_take_off,
        ),
        3: ((9,), _(" ：会收走"), _(" ：无可收的内裤")),
    }
    text = f"{text_handle.id_index(choice)}{label}"
    parts, verb, empty = rules[choice]
    cloth = wardrobe.of(activity.target(0))
    names = [
        _cloth_name(cloth_id)
        for part in parts
        for cloth_id in cloth.cloth_wear[part]
    ]
    if not names:
        return UndressOption(text + empty, False)
    return UndressOption(
        text + verb + "".join(f" {name}" for name in names), True
    )


def toggle_target_cloth(
    cloth_id: int, clothing_type: int, is_wear: bool
) -> None:
    """
    在当前写缓冲中将交互对象单件衣物在 cloth_wear 与 cloth_off 间移换（源列表无该衣物时不操作，需调用方开启写缓冲）。
    Keyword arguments:
    cloth_id -- 要切换穿脱状态的衣物 id
    clothing_type -- 衣物所属部位编号
    is_wear -- True 时从已穿移至已脱下，False 时从已脱下移至已穿
    """
    target_cid = _target_cid()
    cloth = wardrobe.of(target_cid)
    if is_wear:
        source, dest, held = "cloth_wear", "cloth_off", cloth.cloth_wear
    else:
        source, dest, held = "cloth_off", "cloth_wear", cloth.cloth_off
    if cloth_id in held[clothing_type]:
        wardrobe.remove(target_cid, source, clothing_type, cloth_id)
        wardrobe.append(target_cid, dest, clothing_type, cloth_id)
