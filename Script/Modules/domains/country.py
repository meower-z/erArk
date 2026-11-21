"""
大地图的势力与国家：全局键 world.country
=====================================
值是 {表名: {id 的字符串: 数值}} 加上 LAST_WEEK：势力声望（REPUTATION，键为势力id）、国家矿石病感染率
（INFECTION，键为出身地id）、感染率对病人数量的影响系数（RATIO，键为出身地id），
与上周所有国家感染率的总和（LAST_WEEK，还没算过时为 -1.0）。没有这一项时三张表都是空的。
对外的id 是 int，存进键里时换成字符串。写入整值替换这个键，值没变时不写。
"""

from collections.abc import Mapping
from typing import Any, cast

from Script.Config import game_config
from Script.Core import game_type
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import pickled

KEY = "world.country"
""" 势力与国家数据的全局键 """
REPUTATION = "nation_reputation"
""" 势力声望表 """
INFECTION = "country_infection_rate"
""" 国家矿石病感染率表 """
RATIO = "country_infection_patient_ratio"
""" 感染率对病人数量的影响系数表 """
LAST_WEEK = "last_week_all_country_infection_rate"
""" 上周所有国家感染率的总和 """

working.register(
    KEY, {REPUTATION: {}, INFECTION: {}, RATIO: {}, LAST_WEEK: -1.0}
)


def _data() -> Mapping[str, Any]:
    return cast(Mapping[str, Any], working.get(None, KEY))


def _get(table: str, cid: int, default: tuple[Any, ...]) -> Any:
    values = _data()[table]
    if str(cid) in values:
        return values[str(cid)]
    if default:
        return default[0]
    raise KeyError(cid)


def _set(table: str, cid: int, value: float) -> None:
    old = _data()
    if old[table].get(str(cid)) != value or str(cid) not in old[table]:
        working.put(None, KEY, {**old, table: {**old[table], str(cid): value}})


def table(name: str) -> dict[int, Any]:
    """
    一张表
    Keyword arguments:
    name -- REPUTATION、INFECTION 或 RATIO
    Return arguments:
    dict -- id 到数值，键为 int 的新字典
    """
    return {int(cid): value for cid, value in _data()[name].items()}


def reputation(nation_id: int, *default: Any) -> Any:
    """
    势力声望，同 dict 的 [nation_id]，给了 default 时同 dict.get
    Keyword arguments:
    nation_id -- 势力id
    default -- 表里没有这个势力时交回的值，没给时报 KeyError
    Return arguments:
    Any -- 声望
    """
    return _get(REPUTATION, nation_id, default)


def set_reputation(nation_id: int, value: float) -> None:
    """
    把势力声望设为 value，写进当前缓冲区
    Keyword arguments:
    nation_id -- 势力id
    value -- 声望
    """
    _set(REPUTATION, nation_id, value)


def add_reputation(nation_id: int, by: float) -> None:
    """
    势力声望加 by，同 dict 的 [nation_id] += by
    Keyword arguments:
    nation_id -- 势力id，不在表里时报 KeyError
    by -- 增量
    """
    _set(REPUTATION, nation_id, reputation(nation_id) + by)


def infection_rate(country_id: int, *default: Any) -> Any:
    """
    国家矿石病感染率，同 dict 的 [country_id]，给了 default 时同 dict.get
    Keyword arguments:
    country_id -- 出身地id
    default -- 表里没有这个国家时交回的值，没给时报 KeyError
    Return arguments:
    Any -- 感染率
    """
    return _get(INFECTION, country_id, default)


def set_infection_rate(country_id: int, value: float) -> None:
    """
    把国家矿石病感染率设为 value，写进当前缓冲区
    Keyword arguments:
    country_id -- 出身地id
    value -- 感染率
    """
    _set(INFECTION, country_id, value)


def add_infection_rate(country_id: int, by: float) -> None:
    """
    国家矿石病感染率加 by，同 dict 的 [country_id] += by
    Keyword arguments:
    country_id -- 出身地id，不在表里时报 KeyError
    by -- 增量，可以为负
    """
    _set(INFECTION, country_id, infection_rate(country_id) + by)


def patient_ratio(country_id: int, *default: Any) -> Any:
    """
    感染率对病人数量的影响系数，同 dict 的 [country_id]，给了 default 时同 dict.get
    Keyword arguments:
    country_id -- 出身地id
    default -- 表里没有这个国家时交回的值，没给时报 KeyError
    Return arguments:
    Any -- 系数
    """
    return _get(RATIO, country_id, default)


def set_patient_ratio(country_id: int, value: float) -> None:
    """
    把感染率对病人数量的影响系数设为 value，写进当前缓冲区
    Keyword arguments:
    country_id -- 出身地id
    value -- 系数
    """
    _set(RATIO, country_id, value)


def last_week_rate() -> float:
    """
    上周所有国家感染率的总和，还没算过时为 -1.0
    Return arguments:
    float -- 总和
    """
    return cast(float, _data()[LAST_WEEK])


def set_last_week_rate(value: float) -> None:
    """
    把上周所有国家感染率的总和设为 value，写进当前缓冲区
    Keyword arguments:
    value -- 总和
    """
    old = _data()
    if old[LAST_WEEK] != value or type(old[LAST_WEEK]) is not type(value):
        working.put(None, KEY, {**old, LAST_WEEK: value})


def fill() -> None:
    """
    补上表里没有的势力与国家：势力声望为 0，感染率取出身地配置的值，影响系数为感染率的三十分之一，夹在 0.1 到 3.0 之间
    """
    for nation_id in game_config.config_nation:
        if str(nation_id) not in _data()[REPUTATION]:
            set_reputation(nation_id, 0)
    for country_id, birthplace in game_config.config_birthplace.items():
        if str(country_id) not in _data()[INFECTION]:
            set_infection_rate(country_id, birthplace.infect_rate)
            ratio = infection_rate(country_id) / 30
            set_patient_ratio(country_id, min(max(ratio, 0.1), 3.0))


def adopt_old_save(loaded_dict: dict[str, Any], version: int) -> int:
    """
    读档时调用。存档缓存带着 country 属性时删掉它，把它的三张表与 LAST_WEEK 写进当前缓冲区。每次读档都 fill
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 补上或换掉的项数，计法同 save_handle.update_dict_with_default
    """
    found, count = pickled.take(
        loaded_dict, {"country": game_type.Country()}, version
    )
    if found:
        old = vars(found["country"])
        tables = {name: old[name] for name in (REPUTATION, INFECTION, RATIO)}
        data = {
            name: {str(cid): value for cid, value in values.items()}
            for name, values in tables.items()
        }
        working.put(None, KEY, {**data, LAST_WEEK: old[LAST_WEEK]})
    fill()
    return count
