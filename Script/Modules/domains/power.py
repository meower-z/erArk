"""
基地动力的全局键 base.power_strategy、base.power 与 base.power_storage
======================================================================
base.power_strategy 是 {区块id的字符串: 供电策略id}。
表里没有的区块读默认值。UNBUILT_ZONES 里的区块默认断电（2），其余默认标准（0）。
base.power 是发电与蓄电设施（Plant），没有时读 DEFAULT_PLANT。
base.power_storage 是当前储能，没有时读 0.0。写入整值替换这三个键。
最大储能、供能调控员名单与主反应炉等级由别的状态算出，不存。
动力系统管理面板里的修改先记进玩家选择的缓冲区，离开面板时随一个 0 分钟的 Edit 生效。
读档时经 reset.repair 修补超限储能，并在动力区低于 2 级时将副源石反应炉设为 3 台。
"""

from collections.abc import Callable, Mapping
from typing import TypedDict, cast

from Script.Config import game_config
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working
from Script.Modules.domains import facility, warehouse, work
from Script.Modules.save_load import reset

KEY = "base.power_strategy"
""" 供电策略在全局数据里的键 """
PLANT = "base.power"
""" 发电与蓄电设施在全局数据里的键 """
STORAGE = "base.power_storage"
""" 当前储能在全局数据里的键 """
UNBUILT_ZONES = (8, 18, 20)
""" 未实装的区块，默认断电 """
OPERATOR_WORK = 11
""" 供能调控员的职位id """


class Plant(TypedDict):
    """发电与蓄电设施，base.power 的值"""

    aux_reactors: int
    """ 已启用的副源石反应炉数量 """
    clean: tuple[int, ...]
    """ 水力、风力、光伏发电设施的数量 """
    batteries: tuple[int, ...]
    """ 1、2、3 级蓄电池的数量 """
    main_operators: tuple[int, ...]
    """ 火力、水力、风力、光伏的主调控员角色id，0 为空缺 """


DEFAULT_PLANT: Plant = {
    "aux_reactors": 3,
    "clean": (0, 0, 0),
    "batteries": (0, 0, 0),
    "main_operators": (0, 0, 0, 0),
}
""" 没有 base.power 时读到的值 """

working.register(KEY, {})
working.register(PLANT, cast(core.JSON, DEFAULT_PLANT))
working.register(STORAGE, 0.0)


def _put(key: str, new: core.JSON) -> None:
    old = working.get(None, key)
    if (
        old != new
        or not isinstance(new, Mapping)
        and type(old) is not type(new)
    ):
        working.put(None, key, new)


def strategies(game: core.GameState | None = None) -> dict[int, int]:
    """
    表里记下的供电策略
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    dict -- 区块id（int）到供电策略id，只含表里有的区块
    """
    stored = cast(Mapping[str, int], working.get(None, KEY, game))
    return {int(zone): strategy for zone, strategy in stored.items()}


def strategy_of(zone_cid: int, game: core.GameState | None = None) -> int:
    """
    区块当前的供电策略，表里没有时为默认值：UNBUILT_ZONES 里的区块断电（2），其余标准（0）
    Keyword arguments:
    zone_cid -- 区块id
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    int -- 供电策略id
    """
    default = 2 if zone_cid in UNBUILT_ZONES else 0
    stored = cast(Mapping[str, int], working.get(None, KEY, game))
    return stored.get(str(zone_cid), default)


def set_strategy(zone_cid: int, value: int) -> None:
    """
    改一个区块的供电策略：整值替换 base.power_strategy，写进当前缓冲区
    Keyword arguments:
    zone_cid -- 区块id
    value -- 供电策略id
    """
    current = cast(Mapping[str, int], working.get(None, KEY))
    working.put(None, KEY, {**current, str(zone_cid): value})


def plant(game: core.GameState | None = None) -> Plant:
    """
    发电与蓄电设施
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    Plant -- 设施，没有 base.power 时为 DEFAULT_PLANT
    """
    return cast(Plant, working.get(None, PLANT, game))


def set_plant(**fields: int | tuple[int, ...]) -> None:
    """
    改设施的几项，整值替换 base.power，写进当前缓冲区。新值与旧值相同时不写
    Keyword arguments:
    fields -- Plant 的项名与新值
    """
    _put(PLANT, cast(core.JSON, {**plant(), **fields}))


def storage(game: core.GameState | None = None) -> float | int:
    """
    当前储能
    Keyword arguments:
    game -- 给出时只读这个状态，没有时读当前缓冲区
    Return arguments:
    float | int -- 储能，没有 base.power_storage 时为 0.0
    """
    return cast(float | int, working.get(None, STORAGE, game))


def set_storage(value: float | int) -> None:
    """
    把储能设为 value，写进当前缓冲区。值与类型都不变时不写
    Keyword arguments:
    value -- 新储能
    """
    _put(STORAGE, value)


def storage_levels[T](
    name: str, convert: Callable[[float], T], default: T
) -> list[T]:
    """
    储能配置里 1、2、3 级蓄电池的一项
    Keyword arguments:
    name -- 配置项名，如 "电池容量"、"自放电率"
    convert -- 把配置值换成需要的类型
    default -- 配置里没有这一级或换不了类型时的值
    Return arguments:
    list -- 1、2、3 级的值
    """
    values = []
    for level in (1, 2, 3):
        try:
            cid = game_config.config_power_storage_level_index.get(
                name, {}
            ).get(level)
            values.append(
                convert(game_config.config_power_storage[cid].value)
                if cid
                else default
            )
        except Exception:
            values.append(default)
    return values


def storage_max() -> int:
    """
    最大储能，为各级蓄电池的数量乘单体容量（整数）之和
    Return arguments:
    int -- 最大储能
    """
    caps = storage_levels("电池容量", int, 0)
    return sum(
        cap * count
        for cap, count in zip(caps, plant()["batteries"], strict=False)
    )


@reset.repair
def clamp_storage() -> None:
    """储能超过最大储能时降到最大储能，同时登记为读档修补（reset.repair）"""
    top = storage_max()
    if storage() > top:
        set_storage(top)


def store(amount: float) -> None:
    """
    储能加上 amount，结果超过最大储能时取最大储能
    Keyword arguments:
    amount -- 存入的电量
    """
    value = storage() + amount
    top = storage_max()
    set_storage(top if value > top else value)


def main_reactor_level() -> int:
    """
    主源石反应炉等级，即设施1（动力区）的等级，没有记录时为 1
    Return arguments:
    int -- 等级
    """
    return facility.level(1, 1)


@reset.repair
def fix_aux_reactors() -> None:
    """动力区低于 2 级时将副源石反应炉数量设为 3 台，登记为读档修补（reset.repair）"""
    if main_reactor_level() < 2:
        set_plant(aux_reactors=3)


def operator_ids() -> list[int]:
    """
    供能调控员，即岗位名册（work.roster）里岗位为 OPERATOR_WORK 的角色
    Return arguments:
    list -- 角色id，按名册的顺序
    """
    return list(work.roster(OPERATOR_WORK))


def remap_operators(old_to_new: Mapping[int, int]) -> None:
    """
    角色换id时，把主调控员里的旧id换成新id
    Keyword arguments:
    old_to_new -- 旧id到新id，表里没有的id不变
    """
    mains = plant()["main_operators"]
    set_plant(main_operators=tuple(old_to_new.get(cid, cid) for cid in mains))


def appoint_main_operator(kind: int, chara_id: int) -> None:
    """
    任命或撤下一类发电的主调控员。chara_id 不是供能调控员或 kind 越界时不改
    角色已是这一类的主调控员时撤下，否则任命到这一类，并清空该角色在别类的槽位
    Keyword arguments:
    kind -- 0 火力，1 水力，2 风力，3 光伏
    chara_id -- 角色id
    """
    mains = list(plant()["main_operators"])
    if chara_id not in operator_ids() or not 0 <= kind < len(mains):
        return
    mains = [
        0 if i != kind and cid == chara_id else cid
        for i, cid in enumerate(mains)
    ]
    mains[kind] = 0 if mains[kind] == chara_id else chara_id
    set_plant(main_operators=tuple(mains))


def change_aux_reactors(delta: int) -> None:
    """
    增减一台副源石反应炉。增加时不超过动力区等级 × 2 + 3 加资源51的库存，减少时不低于 0
    Keyword arguments:
    delta -- 大于 0 为增加，否则为减少
    """
    aux = plant()["aux_reactors"]
    if delta > 0:
        aux = min(aux + 1, main_reactor_level() * 2 + 3 + warehouse.amount(51))
    elif aux > 0:
        aux -= 1
    set_plant(aux_reactors=aux)


def change_clean(kind: int, delta: int) -> int | None:
    """
    增减一组某类清洁能源设施，数量不低于 0。增加时三类合计已达上限则不增加
    Keyword arguments:
    kind -- 0 水力，1 风力，2 光伏
    delta -- 1 或 -1
    Return arguments:
    int | None -- 增加被上限挡下时为上限（动力区等级 × 2 + 3 加资源53的库存），否则为 None
    """
    clean = list(plant()["clean"])
    if delta > 0:
        limit = main_reactor_level() * 2 + 3 + warehouse.amount(53)
        if sum(clean) >= limit:
            return limit
    clean[kind] = max(0, clean[kind] + delta)
    set_plant(clean=tuple(clean))
    return None


def change_battery(level: int, delta: int) -> int | None:
    """
    增减一台某级蓄电池，数量为 0 时不减。增加被上限挡下时什么也不改，其余情况随后把储能降到不超过最大储能
    Keyword arguments:
    level -- 0、1、2 分别为 1、2、3 级
    delta -- 大于 0 为增加，否则为减少
    Return arguments:
    int | None -- 增加被上限挡下时为上限（动力区等级 × 2 + 8 加资源52的库存），否则为 None
    """
    batteries = list(plant()["batteries"])
    if delta > 0:
        limit = main_reactor_level() * 2 + 8 + warehouse.amount(52)
        if sum(batteries) >= limit:
            return limit
        batteries[level] += 1
    elif batteries[level] > 0:
        batteries[level] -= 1
    set_plant(batteries=tuple(batteries))
    clamp_storage()
    return None
