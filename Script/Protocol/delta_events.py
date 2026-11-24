"""
数值变化事件协议的数据类型定义模块，仅导入 Python 标准库与 narrative_events。
本模块定义两个不可变数据类与一个数值类型别名 DeltaValue。
DeltaEntry 描述一项数值变化。
DeltaEvent 描述一组数值变化及其显示选项。
两个数据类在构造时校验全部字段。
"""

import math
from dataclasses import dataclass

from Script.Protocol.narrative_events import EventMeta

type DeltaValue = int | float | str | None
""" 数值变化字段的取值类型，运行时接受非布尔整数、有限浮点数、字符串与 None。 """


def _require(ok: bool, message: str) -> None:
    """
    条件不成立时抛出 ValueError。
    Keyword arguments:
    ok -- bool，校验条件
    message -- str，异常信息
    Return arguments:
    None -- 无返回值
    """
    if not ok:
        raise ValueError(message)


def _value(value: object) -> bool:
    """
    判断取值是否为合法的 DeltaValue。
    Keyword arguments:
    value -- object，待判断的取值
    Return arguments:
    bool -- None、字符串、非布尔整数或有限浮点数时为 True，其余为 False
    """
    if isinstance(value, bool):
        return False
    if value is None or isinstance(value, (str, int)):
        return True
    return isinstance(value, float) and math.isfinite(value)


def _label(value: object) -> bool:
    """
    判断取值是否为去除首尾空白后非空的字符串。
    Keyword arguments:
    value -- object，待判断的取值
    Return arguments:
    bool -- 去除首尾空白后非空的字符串返回 True，其余返回 False
    """
    return isinstance(value, str) and value.strip() != ""


@dataclass(frozen=True, slots=True)
class DeltaEntry:
    """
    不可变数值变化项，包含对象名 target_label、字段名 field 与变化量 delta。
    before 与 after 为可选的变化前后值，默认均为 None。
    unit 为数值单位，默认为空字符串。
    """

    target_label: str
    field: str
    delta: DeltaValue
    before: DeltaValue = None
    after: DeltaValue = None
    unit: str = ""

    def __post_init__(self) -> None:
        """校验 target_label、field、三项数值与 unit 的类型和取值，不满足时抛出 ValueError。"""
        _require(
            _label(self.target_label),
            f"target_label {self.target_label!r} is not a non-blank str",
        )
        _require(
            _label(self.field), f"field {self.field!r} is not a non-blank str"
        )
        for name in ("delta", "before", "after"):
            value = getattr(self, name)
            _require(_value(value), f"{name} {value!r} is not a DeltaValue")
        _require(isinstance(self.unit, str), f"unit {self.unit!r} is not a str")


@dataclass(frozen=True, slots=True)
class DeltaEvent:
    """
    不可变数值变化事件，包含元数据 meta、变化项元组 entries 与三个可选显示字段。
    pause 表示是否在文本后等待确认。
    use_text_width 表示是否按文本宽度排版。
    summary_text 为整段显示文本，为 None 时由适配器按变化项生成文本。
    """

    meta: EventMeta
    entries: tuple[DeltaEntry, ...]
    pause: bool = False
    use_text_width: bool = False
    summary_text: str | None = None

    def __post_init__(self) -> None:
        """校验 meta、非空 entries、两个布尔开关与 summary_text，不满足时抛出 ValueError。"""
        _require(
            isinstance(self.meta, EventMeta),
            f"meta {self.meta!r} is not an EventMeta",
        )
        _require(
            isinstance(self.entries, tuple)
            and self.entries != ()
            and all(isinstance(e, DeltaEntry) for e in self.entries),
            f"entries {self.entries!r} is not a non-empty tuple of DeltaEntry",
        )
        _require(
            isinstance(self.pause, bool), f"pause {self.pause!r} is not a bool"
        )
        _require(
            isinstance(self.use_text_width, bool),
            f"use_text_width {self.use_text_width!r} is not a bool",
        )
        _require(
            self.summary_text is None
            or (isinstance(self.summary_text, str) and self.summary_text != ""),
            f"summary_text {self.summary_text!r} is not None or a non-empty str",
        )
