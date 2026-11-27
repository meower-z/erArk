"""
玩家选择钩子（pick_hooks）
==========================
本模块提供玩家选择调用入口 choose、back、drafting 与槽位登记函数 on_pick。
未登记时，drafting 返回 nullcontext() 以直接运行代码块。
未登记时，choose 与 back 抛出 RuntimeError。
Script.Modules.tk_ui.player_pick 在导入时调用 on_pick 填入这三个槽位。
本模块不导入界面模块。
"""

from collections.abc import Callable, Mapping, Sequence
from contextlib import AbstractContextManager, nullcontext
from typing import Any, NoReturn, Protocol

from Script.Modules.gameplay_resolution import intent


class Choose(Protocol):
    """定下玩家行动的函数签名协议。"""

    def __call__(
        self,
        behavior_id: str,
        minutes: int,
        *,
        kind: str = ...,
        target: int | None = ...,
        state: int | str | None = ...,
        fields: Mapping[str, object] | None = ...,
        args: Mapping[str, object] | None = ...,
        move: intent.Move | None = ...,
        say: str | None = ...,
        premises: Sequence[str] = ...,
        judge: str | None = ...,
    ) -> NoReturn:
        """
        定下玩家的行动。
        Keyword arguments:
        behavior_id -- str，行为编号
        minutes -- int，名义分钟数
        kind -- str，行动种类
        target -- int | None，目标角色编号，None 为自己
        state -- int | str | None，开始状态，None 取 behavior_id
        fields -- Mapping[str, object] | None，写入玩家的字段映射
        args -- Mapping[str, object] | None，种类附加参数
        move -- intent.Move | None，开始时的移动
        say -- str | None，开始绘制的文本
        premises -- Sequence[str]，开始门检查的前提序列
        judge -- str | None，开始门检查的判定名
        Return arguments:
        NoReturn -- 不正常返回，由实现抛出异常
        """


type Back = Callable[[], NoReturn]
""" 取消当前玩家选择的函数类型别名，不接收参数且不正常返回。 """
type Drafting = Callable[[str], AbstractContextManager[None]]
""" 玩家选择草稿上下文函数的类型别名，接收来源标识并返回上下文管理器。 """


def _unregistered(*args: Any, **kwargs: Any) -> NoReturn:
    """
    未登记玩家选择实现时的默认槽位函数，直接抛出 RuntimeError。
    Keyword arguments:
    args -- 位置参数，此默认实现不使用
    kwargs -- 关键字参数，此默认实现不使用
    Return arguments:
    NoReturn -- 不正常返回，直接抛出 RuntimeError
    """
    raise RuntimeError("no player pick handler registered in pick_hooks")


def _plain(origin: str) -> AbstractContextManager[None]:
    """
    默认的玩家选择草稿上下文函数，直接返回空上下文管理器。
    Keyword arguments:
    origin -- str，写入来源标识，此默认实现不使用该参数
    Return arguments:
    AbstractContextManager[None] -- 空上下文管理器 nullcontext()
    """
    return nullcontext()


_choose: Choose = _unregistered
""" 当前生效的定下行动槽位，默认为 _unregistered。 """
_back: Back = _unregistered
""" 当前生效的取消选择槽位，默认为 _unregistered。 """
_drafting: Drafting = _plain
""" 当前生效的选择草稿上下文槽位，默认为 _plain。 """


def on_pick(choose: Choose, back: Back, drafting: Drafting) -> None:
    """
    同时登记三个玩家选择槽位的处理函数。
    后续调用会替换先前登记的处理函数。
    Keyword arguments:
    choose -- Choose，要登记的定下行动函数
    back -- Back，要登记的取消选择函数
    drafting -- Drafting，要登记的选择草稿上下文函数
    Return arguments:
    None -- 无返回值
    """
    global _choose, _back, _drafting
    _choose, _back, _drafting = choose, back, drafting


def _call_choose(*args: Any, **kwargs: Any) -> NoReturn:
    """
    在调用时读取当前 _choose 槽位并将参数原样转发给它。
    Keyword arguments:
    args -- 位置参数，原样转发给当前 _choose 槽位
    kwargs -- 关键字参数，原样转发给当前 _choose 槽位
    Return arguments:
    NoReturn -- 不正常返回，由当前 _choose 槽位抛出异常
    """
    _choose(*args, **kwargs)


choose: Choose = _call_choose
""" 定下玩家行动的公开入口，标注为 Choose 类型，在调用时经 _call_choose 读取 _choose 槽位。 """


def back() -> NoReturn:
    """
    在调用时读取并执行当前 _back 槽位，以取消当前玩家选择。
    Return arguments:
    NoReturn -- 不正常返回，由当前 _back 槽位抛出异常
    """
    _back()


def drafting(origin: str) -> AbstractContextManager[None]:
    """
    在调用时读取当前 _drafting 槽位并返回玩家选择草稿上下文管理器。
    Keyword arguments:
    origin -- str，写入来源标识，原样传给当前 _drafting 槽位
    Return arguments:
    AbstractContextManager[None] -- 当前 _drafting 槽位返回的上下文管理器
    """
    return _drafting(origin)
