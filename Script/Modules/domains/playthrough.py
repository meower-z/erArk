"""
本周目的设定与周目数：全局键 save.settings 与 calendar.round
=========================================================
save.settings 是 {表名: {设定id的字符串: 值}}，表名见 TABLES：难度（difficulty 类）、生殖方式（birth 类，
生育方式编号到 0 关闭 / 1 开启）、初期奖励与世界设定。没有这一项时四张表都是空的。
calendar.round 是当前周目数，没有这一项时为 1。
对外的设定id 是 int，存进键里时换成字符串。写入整值替换一个键，值没变时不写。
"""

from collections.abc import Mapping
from types import FunctionType
from typing import Any, cast

from Script.Core import get_text
from Script.Design import attr_calculation
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import pickled
from Script.UI.Moudle import draw

_: FunctionType = get_text._
""" 翻译api """

SETTINGS = "save.settings"
""" 本周目设定的全局键 """
ROUND = "calendar.round"
""" 周目数的全局键 """
DIFFICULTY = "difficulty"
""" 难度设定表 """
BIRTH_TYPE = "birth_type"
""" 生殖方式设定表 """
FIRST_BONUS = "first_bonus"
""" 初期奖励表 """
WORLD = "world"
""" 世界设定表 """
TABLES = (DIFFICULTY, BIRTH_TYPE, FIRST_BONUS, WORLD)
""" 设定表的名字 """
PICKLED = {
    "difficulty_setting": DIFFICULTY,
    "birth_type_setting": BIRTH_TYPE,
    "first_bonus": FIRST_BONUS,
    "world_setting": WORLD,
}
""" 存档缓存（版本 12 之前）里的属性名到设定表 """

working.register(SETTINGS, {table: {} for table in TABLES})
working.register(ROUND, 1)


def _tables(game: core.GameState | None) -> Mapping[str, Mapping[str, Any]]:
    return cast(
        Mapping[str, Mapping[str, Any]], working.get(None, SETTINGS, game)
    )


def settings(table: str, game: core.GameState | None = None) -> dict[int, Any]:
    """
    一张设定表
    Keyword arguments:
    table -- TABLES 里的表名
    game -- 给出时读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 设定id 到值，键为 int 的新字典
    """
    return {int(cid): value for cid, value in _tables(game)[table].items()}


def setting(table: str, cid: int, *default: Any) -> Any:
    """
    一项设定，同 dict 的 [cid]，给了 default 时同 dict.get(cid, default)
    Keyword arguments:
    table -- TABLES 里的表名
    cid -- 设定id
    default -- 表里没有这一项时交回的值，没给时报 KeyError
    Return arguments:
    Any -- 值
    """
    values = _tables(None)[table]
    if str(cid) in values:
        return values[str(cid)]
    if default:
        return default[0]
    raise KeyError(cid)


def set_settings(table: str, values: Mapping[int, Any]) -> None:
    """
    换掉一张设定表，写进当前缓冲区
    Keyword arguments:
    table -- TABLES 里的表名
    values -- 设定id 到值
    """
    old = _tables(None)
    new = {str(cid): value for cid, value in values.items()}
    if old[table] != new:
        working.put(None, SETTINGS, {**old, table: new})


def set_setting(table: str, cid: int, value: Any) -> None:
    """
    把一项设定设为 value，写进当前缓冲区
    Keyword arguments:
    table -- TABLES 里的表名
    cid -- 设定id
    value -- 值
    """
    set_settings(table, {**settings(table), cid: value})


def reset_difficulty_and_birth() -> None:
    """难度表与生殖方式表换成配置里的默认值，写进当前缓冲区"""
    set_settings(DIFFICULTY, attr_calculation.get_difficulty_setting_zero())
    set_settings(BIRTH_TYPE, attr_calculation.get_birth_type_setting_zero())


def game_round(game: core.GameState | None = None) -> int:
    """
    当前周目数
    Keyword arguments:
    game -- 给出时读这个状态，没有时读当前缓冲区
    Return arguments:
    int -- 周目数
    """
    return cast(int, working.get(None, ROUND, game))


def set_game_round(value: int) -> None:
    """
    把周目数设为 value，写进当前缓冲区
    Keyword arguments:
    value -- 周目数
    """
    if game_round() != value:
        working.put(None, ROUND, value)


def _fill(values: dict[int, int], default: dict[int, int], text: str) -> int:
    """
    表的项数与默认表不同时补上缺的项并绘制 text
    Keyword arguments:
    values -- 存档里的表，原地修改
    default -- 默认表
    text -- 提示
    Return arguments:
    int -- 补上的项数
    """
    if len(values) == len(default):
        return 0
    missing = [key for key in default if key not in values]
    for key in missing:
        values[key] = default[key]
    now_draw = draw.NormalDraw()
    now_draw.style = "gold_enrod"
    now_draw.text = text
    now_draw.draw()
    return len(missing)


CARRIED_KEYS = (
    SETTINGS,
    ROUND,
    "world.country",
    "mode.time_stop",
    "mode.group_sex",
    "mode.sex_class",
    "needs.sleep_noise",
    "world.achievement",
    "events.triggered",
    "events.triggered_today",
    "log.instructions",
    "plan.sleep_save",
)
""" 新周目沿用的全局键，由 carry_for_new_round 读出、restore_carried 写回 """


def carry_for_new_round(game: core.GameState) -> dict[str, core.JSON]:
    """读出 CARRIED_KEYS 里的全局键，供新周目继承"""
    return {key: working.get(None, key, game) for key in CARRIED_KEYS}


def restore_carried(carried: Mapping[str, core.JSON]) -> None:
    """把新周目带过来的全局键写进当前缓冲区"""
    for key, value in carried.items():
        working.put(None, key, value)


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用，要在 all_system_setting 被取走之前。存档缓存带着 PICKLED 的四张表与 game_round 时删掉它们，
    写进当前缓冲区；难度与生殖方式表为空时从存档的设置对象里取（更旧的存档存在那里）。
    每次读档都给难度表与生殖方式表补上缺的项，项数与默认表不同时绘制提示
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 补上或换掉的项数，计法同 save_handle.update_dict_with_default 与表的逐项补齐
    """
    default: dict[str, Any] = {name: {} for name in PICKLED}
    found, count = pickled.take(
        loaded_dict, {**default, "game_round": 1}, version
    )
    if found:
        system = loaded_dict.get("all_system_setting")
        for name in ("difficulty_setting", "birth_type_setting"):
            if not found[name]:
                found[name] = dict(getattr(system, name, None) or {})
        for name, table in PICKLED.items():
            set_settings(table, found[name])
        set_game_round(found["game_round"])
    for table, zero, text in (
        (
            DIFFICULTY,
            attr_calculation.get_difficulty_setting_zero(),
            _("\n难度设置已更新，如有需要请手动修改\n"),
        ),
        (
            BIRTH_TYPE,
            attr_calculation.get_birth_type_setting_zero(),
            _("\n生殖方式设置已更新，如有需要请手动修改\n"),
        ),
    ):
        values = settings(table)
        count += _fill(values, zero, text)
        set_settings(table, values)
    return count
