"""
纯数据选项提示协议类型定义模块。
定义选项项 ChoiceOption、选项提示 ChoicePrompt 与选择结果 ChoiceResult 三个不可变数据类。
本模块仅导入 Python 标准库。
"""

from dataclasses import dataclass


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
    单个可选项的不可变数据类。
    option_id 为非空字符串选项标识。label 为字符串显示文本，允许为空字符串。
    """

    option_id: str
    label: str

    def __post_init__(self) -> None:
        """校验 option_id 与 label：非 str 抛 TypeError，option_id 为空抛 ValueError。"""
        _require_id(self.option_id, "option_id")
        if not isinstance(self.label, str):
            raise TypeError(
                f"label must be str, got {type(self.label).__name__}"
            )


@dataclass(frozen=True, slots=True)
class ChoicePrompt:
    """
    一次选项提示的不可变数据类。
    prompt_id 为非空字符串提示标识。
    options 为非空 ChoiceOption 元组，且各选项的 option_id 互不重复。
    """

    prompt_id: str
    options: tuple[ChoiceOption, ...]

    def __post_init__(self) -> None:
        """校验 prompt_id 与 options，类型不符抛 TypeError，空值或重复 option_id 抛 ValueError。"""
        _require_id(self.prompt_id, "prompt_id")
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
