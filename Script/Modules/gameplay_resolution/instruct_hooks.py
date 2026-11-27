"""
指令界面钩子（instruct_hooks）
==============================
本模块提供指令界面调用入口 show_non_h、skip_pauses、stash_filter、stashed_filter 与槽位登记函数 on_instruct。
未登记时，show_non_h、skip_pauses 与 stash_filter 不执行操作。
未登记时，stashed_filter 返回新的空字典。
Script.Modules.tk_ui.instruct_callbacks 在导入时调用 on_instruct 填入这四个槽位。
本模块不导入界面模块。
"""

from collections.abc import Callable

type Toggle = Callable[[bool], None]
""" 接收单个布尔值且无返回值的开关函数类型别名。 """
type FilterStash = Callable[[dict[int, bool]], None]
""" 接收指令类型过滤状态字典并暂存的函数类型别名。 """
type FilterStashed = Callable[[], dict[int, bool]]
""" 返回暂存的指令类型过滤状态字典的函数类型别名。 """


def _ignore(value: object) -> None:
    """
    未登记时的默认写入函数，不执行操作。
    Keyword arguments:
    value -- object，写入值，此默认实现不使用
    Return arguments:
    None -- 无返回值
    """


def _nothing_stashed() -> dict[int, bool]:
    """
    未登记时的默认暂存读取函数，返回新的空字典。
    Return arguments:
    dict[int, bool] -- 空字典
    """
    return {}


_show_non_h: Toggle = _ignore
""" 当前生效的隐奸中显示非H指令开关写入槽位，默认为 _ignore。 """
_skip_pauses: Toggle = _ignore
""" 当前生效的跳过暂停模式开关槽位，默认为 _ignore。 """
_stash_filter: FilterStash = _ignore
""" 当前生效的指令类型过滤状态暂存槽位，默认为 _ignore。 """
_stashed_filter: FilterStashed = _nothing_stashed
""" 当前生效的指令类型过滤状态读取槽位，默认为 _nothing_stashed。 """


def on_instruct(
    show_non_h: Toggle,
    skip_pauses: Toggle,
    stash_filter: FilterStash,
    stashed_filter: FilterStashed,
) -> None:
    """
    同时登记四个指令界面槽位的处理函数。
    后续调用会替换先前登记的处理函数。
    Keyword arguments:
    show_non_h -- Toggle，写入隐奸中显示非H指令开关的函数
    skip_pauses -- Toggle，控制跳过暂停模式开关的函数
    stash_filter -- FilterStash，暂存指令类型过滤状态的函数
    stashed_filter -- FilterStashed，读取暂存的指令类型过滤状态的函数
    Return arguments:
    None -- 无返回值
    """
    global _show_non_h, _skip_pauses, _stash_filter, _stashed_filter
    _show_non_h, _skip_pauses = show_non_h, skip_pauses
    _stash_filter, _stashed_filter = stash_filter, stashed_filter


def show_non_h(shown: bool) -> None:
    """
    在调用时读取当前 _show_non_h 槽位，写入隐奸中显示非H指令的开关。
    Keyword arguments:
    shown -- bool，为真时在隐奸中显示非H指令
    Return arguments:
    None -- 无返回值
    """
    _show_non_h(shown)


def skip_pauses(enabled: bool) -> None:
    """
    在调用时读取当前 _skip_pauses 槽位，开启或关闭跳过暂停模式。
    Keyword arguments:
    enabled -- bool，为真时开启跳过暂停模式
    Return arguments:
    None -- 无返回值
    """
    _skip_pauses(enabled)


def stash_filter(filters: dict[int, bool]) -> None:
    """
    在调用时读取当前 _stash_filter 槽位，暂存指令类型过滤状态。
    Keyword arguments:
    filters -- dict[int, bool]，指令类型到是否展示的映射
    Return arguments:
    None -- 无返回值
    """
    _stash_filter(filters)


def stashed_filter() -> dict[int, bool]:
    """
    在调用时读取当前 _stashed_filter 槽位，返回暂存的指令类型过滤状态。
    Return arguments:
    dict[int, bool] -- 暂存的指令类型到是否展示的映射
    """
    return _stashed_filter()
