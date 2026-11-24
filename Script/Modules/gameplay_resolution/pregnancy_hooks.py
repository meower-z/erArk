"""
妊娠结算界面回调（pregnancy_hooks）
===================================
本模块提供生产与破壳事件回调的登记与派发入口。
本模块仅导入标准库 typing.Protocol，不直接导入界面、Tk 或输入输出模块。
未登记回调时，emit_born 不执行任何操作。
"""

from typing import Protocol


class BornCallback(Protocol):
    """生产与破壳事件回调的函数签名协议。"""

    def __call__(
        self,
        character_id: int,
        *,
        egg_mode: bool = False,
        egg_id_list: list[int] | None = None,
    ) -> None:
        """
        接收母亲角色编号与破壳选项，处理一次生产或破壳事件。
        Keyword arguments:
        character_id -- int，母亲角色编号
        egg_mode -- bool，为 True 时表示卵生破壳模式，默认为 False
        egg_id_list -- list[int] | None，本次破壳的卵编号列表，默认为 None
        Return arguments:
        None -- 无返回值
        """


_on_born: list[BornCallback] = []
""" 按登记顺序保存的生产与破壳事件回调列表。 """


def on_born(fn: BornCallback) -> BornCallback:
    """
    登记一个生产与破壳事件回调，可作为装饰器使用。
    Keyword arguments:
    fn -- BornCallback，要登记的回调函数
    Return arguments:
    BornCallback -- 原样返回传入的 fn
    """
    _on_born.append(fn)
    return fn


def emit_born(
    character_id: int,
    *,
    egg_mode: bool = False,
    egg_id_list: list[int] | None = None,
) -> None:
    """
    按登记顺序调用已登记的生产与破壳事件回调，未登记时不执行操作。
    Keyword arguments:
    character_id -- int，母亲角色编号
    egg_mode -- bool，为 True 时表示卵生破壳模式，默认为 False
    egg_id_list -- list[int] | None，本次破壳的卵编号列表，默认为 None
    Return arguments:
    None -- 无返回值
    """
    for fn in _on_born:
        fn(character_id, egg_mode=egg_mode, egg_id_list=egg_id_list)
