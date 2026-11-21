"""
save_load 的旧缓存字段导入
========================
读档时，领域模块用 take 从存档缓存的属性表里取出自己的字段，再把值写进 GameState。
取出时按 save_handle.update_dict_with_default 的计法补默认值并计数。
本模块不登记行动、事件或规则，也不在 LOAD_ORDER 里。
"""

from collections.abc import Mapping
from typing import Any

FIRST_VERSION = 12
""" 存档缓存不含这些字段的起始存档版本 """


def _filled(loaded: dict[str, Any], default: Mapping[str, Any]) -> int:
    """
    按 update_dict_with_default 的计法补齐 loaded：缺的项取默认值，类型不符且默认值不是 None、int、float 的
    项换成默认值，默认值是对象时逐属性补齐
    Keyword arguments:
    loaded -- 存档里的值，原地修改
    default -- 默认值
    Return arguments:
    int -- 补上或换掉的项数
    """
    count = 0
    for key, value in default.items():
        if key not in loaded:
            loaded[key] = value
            count += 1
        elif hasattr(value, "__dict__") and hasattr(loaded[key], "__dict__"):
            count += _filled(vars(loaded[key]), vars(value))
        elif (
            type(loaded[key]) is not type(value)
            and value is not None
            and type(value) is not int
            and type(value) is not float
        ):
            loaded[key] = value
            count += 1
    return count


def take(
    loaded_dict: dict[str, Any], default: Mapping[str, Any], version: int
) -> tuple[dict[str, Any], int]:
    """
    从存档缓存的属性表里删掉 default 里的字段，交回补齐后的值。
    版本 FIRST_VERSION 起的存档缓存里没有这些字段，那时交回空表与 0
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表，原地修改
    default -- 字段名到默认值
    version -- 存档的版本，旧存档为 0
    Return arguments:
    tuple -- (字段名到值，补上或换掉的项数)
    """
    found = {
        name: loaded_dict.pop(name) for name in default if name in loaded_dict
    }
    if not found and version >= FIRST_VERSION:
        return {}, 0
    return found, _filled(found, default)
