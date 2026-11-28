"""
纯数据选项提示协议类型定义模块。
定义选项可用状态类型别名 OptionAvailability，
以及选项项 ChoiceOption、选项提示 ChoicePrompt 与选择结果 ChoiceResult 三个不可变数据类。
本模块仅导入 Python 标准库。
"""

from dataclasses import dataclass
from typing import Literal, get_args

type OptionAvailability = Literal["open", "blocked", "current"]
"""
选项可用状态字面量类型。"open" 表示玩家可选。"blocked" 表示展示但不可选。
"current" 表示当前所处状态且展示但不可选。
"""


def _require_id(value: object, field: str) -> None:
    """
    校验标识字段为非空字符串。value 不是 str 时抛出 TypeError，为空字符串时抛出 ValueError。
    Keyword arguments:
    value -- object，待校验的字段值
    field -- str，出错提示使用的字段名
    Return arguments:
    None -- 无返回值
    """
    if not isinstance(value, str):
        raise TypeError(f"{field} must be str, got {type(value).__name__}")
    if not value:
        raise ValueError(f"{field} must not be empty")


@dataclass(frozen=True, slots=True)
class ChoiceOption:
    """
    单个选项的不可变数据类。
    option_id 为非空字符串选项标识。
    label 为字符串显示文本，允许为空字符串。
    availability 为选项可用状态，默认为 "open"。
    note 为前端在不可选项旁展示的说明文本，默认为空字符串。
    """

    option_id: str
    label: str
    availability: OptionAvailability = "open"
    note: str = ""

    def __post_init__(self) -> None:
        """
        校验 option_id、label、note 与 availability 的字段类型和取值。
        option_id、label 或 note 不是 str 时抛出 TypeError。
        option_id 为空或 availability 不在 OptionAvailability 允许取值中时抛出 ValueError。
        """
        _require_id(self.option_id, "option_id")
        for field in ("label", "note"):
            value = getattr(self, field)
            if not isinstance(value, str):
                raise TypeError(
                    f"{field} must be str, got {type(value).__name__}"
                )
        if self.availability not in get_args(OptionAvailability.__value__):
            raise ValueError(f"unknown availability {self.availability!r}")


@dataclass(frozen=True, slots=True)
class ChoicePrompt:
    """
    一次选项提示的不可变数据类。
    prompt_id 为非空字符串提示标识。
    options 为非空 ChoiceOption 元组。
    options 中各选项的 option_id 互不重复。
    options 中至少包含一项 availability 为 "open" 的选项。
    text 为前端显示在选项上方的正文字符串，默认为空字符串。
    title 为前端显示在正文上方的标题字符串，默认为空字符串。
    """

    prompt_id: str
    options: tuple[ChoiceOption, ...]
    text: str = ""
    title: str = ""

    def __post_init__(self) -> None:
        """
        校验 prompt_id、text、title 与 options 的字段类型和取值约束。
        字段类型不符或 options 元素不是 ChoiceOption 时抛出 TypeError。
        prompt_id 为空、options 为空、option_id 重复或 options 中不含 availability 为 "open" 的选项时抛出 ValueError。
        """
        _require_id(self.prompt_id, "prompt_id")
        for field in ("text", "title"):
            value = getattr(self, field)
            if not isinstance(value, str):
                raise TypeError(
                    f"{field} must be str, got {type(value).__name__}"
                )
        if not isinstance(self.options, tuple):
            raise TypeError(
                f"options must be tuple, got {type(self.options).__name__}"
            )
        if not self.options:
            raise ValueError("options must not be empty")
        for option in self.options:
            if not isinstance(option, ChoiceOption):
                raise TypeError(
                    f"options must hold ChoiceOption, got {type(option).__name__}"
                )
        ids = [option.option_id for option in self.options]
        if len(set(ids)) != len(ids):
            raise ValueError(f"option_id values must be unique: {ids}")
        if all(option.availability != "open" for option in self.options):
            raise ValueError(f"no open option among {ids}")


@dataclass(frozen=True, slots=True)
class ChoiceResult:
    """
    一次选择结果的不可变数据类。
    prompt_id 为非空字符串提示标识。selected_option_id 为非空字符串所选选项标识。
    """

    prompt_id: str
    selected_option_id: str

    def __post_init__(self) -> None:
        """校验 prompt_id 与 selected_option_id，非 str 抛 TypeError，为空抛 ValueError。"""
        _require_id(self.prompt_id, "prompt_id")
        _require_id(self.selected_option_id, "selected_option_id")
