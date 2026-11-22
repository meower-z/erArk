"""
save_load 的存档升级
====================
CURRENT 是本游戏写的文件 "2" 的版本。STEPS[n] 把版本 n 的 JSON 对象升到版本 n + 1。
STEPS 从版本 1 开始。版本 0 的存档头里没有标记，kernel_state.read 读它时不跑 STEPS。
STEPS[2] 是 fill_v2_needs。STEPS[1] 与 STEPS[3] 到 STEPS[19] 是 _identity，原样交回文件 "2"。
这几步前后文件 "2" 的结构相同。存档版本仍在这几步上各升 1。CURRENT 较低的旧版游戏因此拒读较新的存档。
读旧存档时处理文件 "1" 解开后对象的常量与函数在 adopt_legacy 里，另有一些在各领域模块的 adopt 函数里。
本模块导入 adopt_legacy 的公开名字，并把它们列在 __all__ 里。调用方经 upgrade 取用这些名字，例如 upgrade.adopt_power。
本模块不登记行动、事件或规则，也不在 LOAD_ORDER 里。
"""

from collections.abc import Callable, Mapping
from typing import Any, cast

from Script.Core.num import Num
from Script.Modules.domains import needs
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load.adopt_legacy import (
    ISLAND_UI_FIELDS,
    PICKLED_EXACT,
    PICKLED_FACILITY,
    PICKLED_MILK_MAX,
    PICKLED_NEEDS,
    REPLACED_COPIES,
    STALE,
    UI_FIELDS,
    V0_MILK,
    V0_NEEDS,
    V0_STRATEGY,
    V1_POWER,
    V4_ECONOMY,
    V5_WORK,
    adopt_economy,
    adopt_facility,
    adopt_pickled,
    adopt_power,
    adopt_v0,
    adopt_work,
    copy_pickled,
    copy_v0_needs,
    drop_ui_fields,
    fill_v0_defaults,
)

__all__ = [
    "CURRENT",
    "ISLAND_UI_FIELDS",
    "PICKLED_EXACT",
    "PICKLED_FACILITY",
    "PICKLED_MILK_MAX",
    "PICKLED_NEEDS",
    "REPLACED_COPIES",
    "STALE",
    "STEPS",
    "UI_FIELDS",
    "V0_MILK",
    "V0_NEEDS",
    "V0_STRATEGY",
    "V1_POWER",
    "V4_ECONOMY",
    "V5_WORK",
    "adopt_economy",
    "adopt_facility",
    "adopt_pickled",
    "adopt_power",
    "adopt_v0",
    "adopt_work",
    "copy_pickled",
    "copy_v0_needs",
    "drop_ui_fields",
    "fill_v0_defaults",
    "fill_v2_needs",
]

CURRENT = 20
""" 本游戏写的文件 "2" 的版本 """


def _identity(data: dict[str, Any]) -> dict[str, Any]:
    """
    原样交回文件 "2" 的 JSON 对象。STEPS 在文件 "2" 结构不变的步骤上用它。
    这些步骤仍各升一个版本，好让 CURRENT 较低的旧版游戏拒读较新的存档
    Keyword arguments:
    data -- 版本 n 的 JSON 对象
    Return arguments:
    dict -- 同一个对象
    """
    return data


def fill_v2_needs(data: dict[str, Any]) -> dict[str, Any]:
    """
    版本 2 升 3：文件 "2" 里每一份 body.needs（各角色数据里的与 roster.offstage 里的）补上 PICKLED_NEEDS 的十项，
    取默认值，已有的项不变。十项的值在文件 "1" 的角色对象上，读档时由 adopt_pickled 写进 body.needs
    Keyword arguments:
    data -- 版本 2 的 JSON 对象，原地修改
    Return arguments:
    dict -- 版本 3 的 JSON 对象
    """
    default = cast(Mapping[str, Num], needs.DEFAULT)
    added = {stat: default[stat] for stat in PICKLED_NEEDS.values()}
    tables = [c["data"] for c in data["characters"].values()]
    tables.extend(data["data"].get(working.OFFSTAGE, {}).values())
    for table in tables:
        if needs.KEY in table:
            table[needs.KEY] = {**added, **table[needs.KEY]}
    return data


STEPS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
    1: _identity,
    2: fill_v2_needs,
    3: _identity,
    4: _identity,
    5: _identity,
    6: _identity,
    7: _identity,
    8: _identity,
    9: _identity,
    10: _identity,
    11: _identity,
    12: _identity,
    13: _identity,
    14: _identity,
    15: _identity,
    16: _identity,
    17: _identity,
    18: _identity,
    19: _identity,
}
""" 版本 n 到 n + 1 的升级步骤。版本 0 升 1 不是 JSON 步骤，见模块说明 """
