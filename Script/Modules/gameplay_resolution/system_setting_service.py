"""
系统设置纯逻辑服务（system_setting_service）
============================================
本模块提供系统设置与游戏基础设置面板的选项组装、选项循环、数值范围约束、本地配置写入、生殖方式开关与禁止干员列表逻辑。
本模块公开枚举 Kind、Control、Step，数据类 OptionRow、BanRow、BirthTypeRow 与常量 CONTROLS。
本模块公开函数 option_rows、setting_info、cycle、set_draw_number、apply_font_size、apply_dpi、apply_language、
birth_type_rows、birth_type_text、birth_type_on、open_birth_type、close_birth_type、ban_rows 与 toggle_ban。
本模块不执行界面绘制，也不导入 Script.UI、Script.Settle 或 Tk 模块。
"""

import enum
from dataclasses import dataclass
from typing import Any

from Script.Config import game_config, normal_config
from Script.Modules.domains import chara_profile, identity, playthrough, roster
from Script.Modules.gameplay_resolution import roster_lifecycle_service


class Kind(enum.Enum):
    """系统设置主界面的三个设置分类枚举，包含基础设置、难度设置与绘制设置。"""

    BASE = "base"
    DIFFICULTY = "difficulty"
    DRAW = "draw"


class Control(enum.Enum):
    """单条系统设置行右侧按钮的交互控件类型枚举，包含循环切换、数值输入、字体大小、DPI 缩放与生殖方式入口。"""

    CYCLE = "cycle"
    NUMBER = "number"
    FONT_SIZE = "font_size"
    DPI = "dpi"
    BIRTH_TYPE = "birth_type"


class Step(enum.Enum):
    """调用 cycle 切换选项后指示面板下一步动作的枚举，包含完成、锁定提示、输入数量与输入倍率。"""

    DONE = "done"
    LOCKED = "locked"
    ASK_COUNT = "ask_count"
    ASK_RATE = "ask_rate"


@dataclass(frozen=True, slots=True)
class OptionRow:
    """
    系统设置主列表中的单条选项展示数据。
    记录配置编号 cid、名称 name、控件类型 control、按钮显示文本 value、
    选项数量 option_len 与是否展示禁止干员列表入口 ban_list。
    """

    cid: int
    name: str
    control: Control
    value: str
    option_len: int
    ban_list: bool


@dataclass(frozen=True, slots=True)
class BanRow:
    """
    禁止干员列表中的单条角色展示数据。
    记录角色编号 npc_id、含四位角色序号前缀的按钮文本 text 与当前是否处于禁止状态 banned。
    """

    npc_id: int
    text: str
    banned: bool


@dataclass(frozen=True, slots=True)
class BirthTypeRow:
    """
    生殖方式开关子面板中的单条展示数据。
    记录生育方式编号 birth_type、名称 name、是否开启 enabled 与当前状态文案 state。
    """

    birth_type: int
    name: str
    enabled: bool
    state: str


CONTROLS: dict[tuple[Kind, int], Control] = {
    (Kind.BASE, 13): Control.BIRTH_TYPE,
    (Kind.DRAW, 12): Control.FONT_SIZE,
    (Kind.DRAW, 18): Control.DPI,
    (Kind.DRAW, 14): Control.NUMBER,
    (Kind.DRAW, 15): Control.NUMBER,
}
""" 特殊设置项按 (Kind, cid) 映射控件类型的表，未列出的设置项均使用 Control.CYCLE。 """


def _config(kind: Kind) -> tuple[dict[int, Any], dict[int, list[str]]]:
    if kind is Kind.BASE:
        return (
            game_config.config_system_setting,
            game_config.config_system_setting_option,
        )
    if kind is Kind.DIFFICULTY:
        return (
            game_config.config_difficulty_setting,
            game_config.config_difficulty_setting_option,
        )
    return (
        game_config.config_draw_setting,
        game_config.config_draw_setting_option,
    )


def _values(kind: Kind) -> dict[int, int]:
    if kind is Kind.BASE:
        return normal_config.system_setting.base_setting
    if kind is Kind.DIFFICULTY:
        return playthrough.settings(playthrough.DIFFICULTY)
    return normal_config.system_setting.draw_setting


def _shown(control: Control, labels: list[str], value: int) -> str:
    if control is Control.CYCLE:
        return f"{labels[value]}"
    if control is Control.NUMBER:
        return f"{value}"
    if control is Control.FONT_SIZE:
        return f"{normal_config.config_normal.font_size}"
    if control is Control.DPI:
        return f"{getattr(normal_config.config_normal, 'tk_dpi', 150)}"
    return ""


def _info(text: str) -> str:
    return text.replace("\\n", " \n")


def option_rows(kind: Kind) -> tuple[OptionRow, ...]:
    """
    按配置顺序组装指定分类的选项行元组。
    缺失的设置项会先补值为 0，基础与绘制分类写入 normal_config.system_setting，难度分类只作用于本次读取的字典副本。
    Keyword arguments:
    kind -- Kind，设置分类枚举值
    Return arguments:
    tuple[OptionRow, ...] -- 按配置顺序排列的选项行元组
    """
    configs, options = _config(kind)
    values = _values(kind)
    rows: list[OptionRow] = []
    for cid, config in configs.items():
        if cid not in values:
            values[cid] = 0
        option_len = len(options[cid])
        control = CONTROLS.get((kind, cid), Control.CYCLE)
        rows.append(
            OptionRow(
                cid,
                config.name,
                control,
                _shown(control, options[cid], values[cid]),
                option_len,
                kind is Kind.BASE and cid == 7 and bool(values[cid]),
            )
        )
    return tuple(rows)


def setting_info(kind: Kind, cid: int) -> str:
    """
    读取指定设置项的说明文本，并将字面换行符 \\n 替换为带前导空格的换行符。
    Keyword arguments:
    kind -- Kind，设置分类枚举值
    cid -- int，设置项编号
    Return arguments:
    str -- 整理换行后的选项说明文本
    """
    return _info(_config(kind)[0][cid].info)


def cycle(kind: Kind, cid: int, option_len: int) -> Step:
    """
    推进指定设置项的选项值并返回面板后续动作。
    基础设置 12 号保持原值并返回 Step.LOCKED，其余项递增并在达到上限后回绕为 0。
    难度分类写回 playthrough，绘制设置 2 号同步写入全部角色配置第 1 项，绘制设置 11、14、15 号返回对应输入步骤。
    Keyword arguments:
    kind -- Kind，设置分类枚举值
    cid -- int，设置项编号
    option_len -- int，可选项总数
    Return arguments:
    Step -- 面板需要执行的后续动作枚举
    """
    if kind is Kind.BASE and cid == 12:
        return Step.LOCKED
    values = _values(kind)
    values[cid] = values[cid] + 1 if values[cid] < option_len - 1 else 0
    if kind is Kind.DIFFICULTY:
        playthrough.set_settings(playthrough.DIFFICULTY, values)
    if kind is not Kind.DRAW:
        return Step.DONE
    if cid == 2:
        for character_id in identity.table():
            chara_profile.chara_setting.set_item(character_id, 1, values[cid])
    if cid == 11:
        return Step.ASK_COUNT
    if cid in (14, 15):
        return Step.ASK_RATE
    return Step.DONE


def set_draw_number(cid: int, number: int) -> int:
    """
    校验并写入数值型绘制设置项。
    11 号存储 number 减 1 并限制在 0 到 9 之间，其余编号限制在 1 到 99 之间。
    Keyword arguments:
    cid -- int，绘制设置项编号
    number -- int，输入的整数值
    Return arguments:
    int -- 写入 draw_setting 后的整数值
    """
    if cid == 11:
        value = min(max(number - 1, 0), 9)
    else:
        value = min(max(number, 1), 99)
    normal_config.system_setting.draw_setting[cid] = value
    return value


def apply_font_size(size: int) -> int:
    """
    将字体大小限制在 1 到 50 之间，更新 font_size 与 order_font_size，
    并将 font_size 与按窗口宽度换算的 text_width 写入本地配置。
    Keyword arguments:
    size -- int，目标字体大小
    Return arguments:
    int -- 限制范围后生效的字体大小
    """
    size = min(max(size, 1), 50)
    config = normal_config.config_normal
    config.font_size = size
    config.order_font_size = size - 2
    normal_config.write_local_config(
        {
            "font_size": str(size),
            "text_width": str(int(config.window_width / size * 2)),
        }
    )
    return size


def apply_dpi(dpi: int) -> int:
    """
    将 DPI 缩放值限制在 50 到 300 之间，更新运行时 tk_dpi 并将该值写入本地配置。
    Keyword arguments:
    dpi -- int，目标 DPI 缩放值
    Return arguments:
    int -- 限制范围后生效的 DPI 缩放值
    """
    dpi = min(max(dpi, 50), 300)
    normal_config.config_normal.tk_dpi = dpi
    normal_config.write_local_config({"tk_dpi": str(dpi)})
    return dpi


def apply_language(lang_code: str) -> None:
    """
    更新运行时语言代码并写入本地配置文件。
    Keyword arguments:
    lang_code -- str，语言代码，例如 zh_CN、en_US 或 ko_KR
    Return arguments:
    None -- 无返回值
    """
    normal_config.config_normal.language = lang_code
    normal_config.write_local_config({"language": lang_code})


def birth_type_rows() -> tuple[BirthTypeRow, ...]:
    """
    按生殖方式配置顺序组装开关列表，当前存档缺失的键按开启状态 1 读取。
    Return arguments:
    tuple[BirthTypeRow, ...] -- 生殖方式开关展示行元组
    """
    values = playthrough.settings(playthrough.BIRTH_TYPE)
    rows: list[BirthTypeRow] = []
    for birth_type, config in game_config.config_birth_type_setting.items():
        value = values.get(birth_type, 1)
        labels = game_config.config_birth_type_setting_option[birth_type]
        rows.append(
            BirthTypeRow(birth_type, config.name, bool(value), labels[value])
        )
    return tuple(rows)


def birth_type_text(birth_type: int) -> tuple[str, str]:
    """
    读取指定生殖方式的名称以及整理换行后的说明文本。
    Keyword arguments:
    birth_type -- int，生育方式编号
    Return arguments:
    tuple[str, str] -- 名称与整理换行后的说明文本二元组
    """
    config = game_config.config_birth_type_setting[birth_type]
    return config.name, _info(config.info)


def birth_type_on(birth_type: int) -> bool:
    """
    查询当前存档中指定生殖方式是否处于开启状态，缺失键按开启处理。
    Keyword arguments:
    birth_type -- int，生育方式编号
    Return arguments:
    bool -- 开启返回 True，关闭返回 False
    """
    return bool(playthrough.settings(playthrough.BIRTH_TYPE).get(birth_type, 1))


def open_birth_type(birth_type: int) -> None:
    """
    在当前存档中将指定生殖方式开关设为开启状态 1。
    Keyword arguments:
    birth_type -- int，生育方式编号
    Return arguments:
    None -- 无返回值
    """
    playthrough.set_setting(playthrough.BIRTH_TYPE, birth_type, 1)


def close_birth_type(birth_type: int) -> str:
    """
    在当前存档中关闭指定生殖方式开关，并调用 egg_handle 清除对应存量数据。
    Keyword arguments:
    birth_type -- int，生育方式编号
    Return arguments:
    str -- 存量清理结果的提示文本
    """
    from Script.System.Pregnancy_System import egg_handle

    playthrough.set_setting(playthrough.BIRTH_TYPE, birth_type, 0)
    return egg_handle.clear_birth_type_data(birth_type)


def ban_rows() -> tuple[BanRow, ...]:
    """
    按角色表顺序组装可禁止角色列表，跳过玩家角色 0，并标注各角色是否已禁止。
    Return arguments:
    tuple[BanRow, ...] -- 禁止干员列表展示行元组
    """
    banned = roster.forbidden()
    rows: list[BanRow] = []
    for npc_id in identity.table():
        if npc_id == 0:
            continue
        npc = identity.of(npc_id)
        text = f"[{str(npc.adv).rjust(4, '0')}]：{npc.name}"
        rows.append(BanRow(npc_id, text, npc_id in banned))
    return tuple(rows)


def toggle_ban(npc_id: int) -> bool:
    """
    切换指定角色的禁止状态，禁止已在名册中的干员时执行离岛处理。
    Keyword arguments:
    npc_id -- int，目标角色编号
    Return arguments:
    bool -- 本次操作使在册干员离岛时返回 True，其余情况返回 False
    """
    if roster.is_forbidden(npc_id):
        roster.unforbid(npc_id)
        return False
    roster.forbid(npc_id)
    if not roster.has(npc_id):
        return False
    roster_lifecycle_service.chara_off_line(npc_id)
    return True
