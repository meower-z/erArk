# -*- coding: UTF-8 -*-
"""教育回归测试用的实时读写句柄（读走 growth.of，写走 growth.editing）"""

from typing import Any

from Script.Core import game_type
from Script.Modules.domains import growth


class _LiveDict(dict[Any, Any]):
    """写穿到 growth.editing 的字典视图，支持测试里的原地赋值与 pop"""

    def __init__(self, cid: int, field: str, initial: dict[Any, Any]) -> None:
        super().__init__(initial)
        self._cid = cid
        self._field = field

    def _sync(self) -> None:
        with growth.editing(self._cid) as g:
            assert g is not None
            setattr(g, self._field, dict(self))

    def __setitem__(self, key: Any, value: Any) -> None:
        super().__setitem__(key, value)
        self._sync()

    def __delitem__(self, key: Any) -> None:
        super().__delitem__(key)
        self._sync()

    def pop(self, *args: Any) -> Any:
        result = super().pop(*args)
        self._sync()
        return result

    def clear(self) -> None:
        super().clear()
        self._sync()

    def update(self, *args: Any, **kwargs: Any) -> None:
        super().update(*args, **kwargs)
        self._sync()


class GrowthRef:
    """面向旧测试脚本的实时养成记录句柄"""

    def __init__(self, cid: int) -> None:
        object.__setattr__(self, "_cid", cid)

    def __getattr__(self, name: str) -> Any:
        cid = object.__getattribute__(self, "_cid")
        data = growth.of(cid)
        if data is None:
            data = game_type.CHILD_GROWTH()
        value = getattr(data, name)
        if isinstance(value, dict):
            return _LiveDict(cid, name, value)
        return value

    def __setattr__(self, name: str, value: Any) -> None:
        cid = object.__getattribute__(self, "_cid")
        with growth.editing(cid) as data:
            assert data is not None
            setattr(data, name, value)


def child_growth(cid: int) -> GrowthRef:
    """确保角色有养成记录并返回实时读写句柄"""
    with growth.editing(cid):
        pass
    return GrowthRef(cid)
