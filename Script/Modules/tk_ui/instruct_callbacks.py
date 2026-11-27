"""
tk_ui 的指令界面回调
====================
本模块在导入时调用 instruct_hooks.on_instruct，把四个指令界面槽位接到 view 与 flow_handle。
show_non_h 写入 view.show_non_h_in_hidden_sex。
stash_filter 与 stashed_filter 读写 view.instruct_type_filter_cache。
skip_pauses 在调用时查找并调用 flow_handle.set_skip_pauses。
"""

from Script.Core import flow_handle
from Script.Modules.gameplay_resolution import instruct_hooks
from Script.UI.Moudle import view


def show_non_h(shown: bool) -> None:
    """
    将 view.show_non_h_in_hidden_sex 设为 shown。
    Keyword arguments:
    shown -- bool，隐奸中显示非H指令开关的新值
    Return arguments:
    None -- 无返回值
    """
    view.show_non_h_in_hidden_sex = shown


def skip_pauses(enabled: bool) -> None:
    """
    在调用时查找 flow_handle.set_skip_pauses 并以 enabled 调用它。
    Keyword arguments:
    enabled -- bool，为真时开启跳过暂停模式
    Return arguments:
    None -- 无返回值
    """
    flow_handle.set_skip_pauses(enabled)


def stash_filter(filters: dict[int, bool]) -> None:
    """
    将 view.instruct_type_filter_cache 设为 filters。
    Keyword arguments:
    filters -- dict[int, bool]，指令类型到是否展示的映射
    Return arguments:
    None -- 无返回值
    """
    view.instruct_type_filter_cache = filters


def stashed_filter() -> dict[int, bool]:
    """
    返回 view.instruct_type_filter_cache 当前引用的字典。
    Return arguments:
    dict[int, bool] -- view.instruct_type_filter_cache 当前引用的字典
    """
    return view.instruct_type_filter_cache


instruct_hooks.on_instruct(
    show_non_h, skip_pauses, stash_filter, stashed_filter
)
