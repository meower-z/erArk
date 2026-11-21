"""
save_load 的旧存档导入
======================
读旧存档时，这里的函数整理文件 "1" 解开后的对象：补上缺的属性，把旧版本留下的属性抄走、写进当前缓冲区或删掉。
"""

from typing import Any

from Script.Config import game_config
from Script.Core import game_type, num
from Script.Modules.domains import (
    economy,
    facility,
    needs,
    power,
    pregnancy,
    work,
)
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import settings

V0_NEEDS = {
    "tired_point": "tired",
    "hunger_point": "hunger",
    "urinate_point": "urine",
}
""" 旧存档角色对象上的生理需求属性名到 body.needs 的项 """
V0_MILK = "milk"
""" 旧存档里乳汁在角色妊娠数据（pregnancy）上的属性名 """
V0_STRATEGY = "power_supply_strategy"
""" 旧存档里供电策略在罗德岛对象上的属性名 """
UI_FIELDS = (
    "back_save_panel",
    "wframe_mouse",
    "input_cache_draft",
    "input_cache_browsing",
    "input_position",
    "now_panel_id",
    "npc_image_index",
    "text_wait",
    "show_non_h_in_hidden_sex",
    "instruct_type_filter",
    "instruct_sex_type_filter",
    "instruct_type_filter_cache",
    "instruct_index_filter",
    "scene_panel_show",
    "all_npc_position_panel_select_type",
    "all_npc_position_panel_move_type",
    "pregnancy_panel_sort_type",
    "pregnancy_panel_filter_type",
    "now_init_map_id",
    "output_text_style",
    "text_style_position",
    "text_style_cache",
    "text_one_by_one_rich_cache",
    "image_id",
    "cmd_data",
    "is_collection",
)
""" 旧版本存在缓存对象上的界面临时状态、玩家的面板选择与不再使用的字段：Cache 没有它们 """
ISLAND_UI_FIELDS = (
    "makefood_data",
    "makefood_filter_type",
    "makefood_filter_difficulty",
    "makefood_filter_time",
    "makefood_sort_type",
    "makefood_sort_order",
    "makefood_cook_mode",
    "makefood_make_count",
    "now_show_book_cid_of_type",
    "reader_now",
)
""" 旧版本存在罗德岛对象上的界面临时状态与玩家的面板选择：Rhodes_Island 没有它们 """
PICKLED_NEEDS = {
    "hit_point": "hit",
    "hit_point_max": "hit_max",
    "mana_point": "mana",
    "mana_point_max": "mana_max",
    "sanity_point": "sanity",
    "sanity_point_max": "sanity_max",
    "angry_point": "angry",
    "sleep_point": "sleep",
    "desire_point": "desire",
    "drunk_point": "drunk",
}
""" 版本 3 之前的存档里，角色对象上的属性名到 body.needs 的项 """
PICKLED_EXACT = {
    "hit_point",
    "hit_point_max",
    "mana_point",
    "mana_point_max",
    "sanity_point",
    "sleep_point",
    "drunk_point",
}
""" PICKLED_NEEDS 里读档时换成精确值（num.exact）的属性 """
REPLACED_COPIES = {
    "hit_point",
    "mana_point",
    "sanity_point",
    "sanity_point_max",
    "angry_point",
    "sleep_point",
    "desire_point",
}
""" 角色替换时从旧角色对象抄到新角色对象的属性。体力与气力上限取新角色的模板，醉酒值不抄 """
PICKLED_MILK_MAX = "milk_max"
""" 版本 3 之前的存档里，乳汁上限在角色妊娠数据（pregnancy）上的属性名 """
STALE = "last_hunger_time"
""" 版本 3 之前的存档里，角色对象上没有代码读的属性（最后一次结算饥饿的时间），读档时删掉 """


def fill_v0_defaults(loaded_dict: dict[str, Any]) -> None:
    """
    旧存档解开后补齐属性：缺生理需求属性的角色补上旧构造函数给的 0，缺供电策略的罗德岛补上空表
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    for character in loaded_dict.get("character_data", {}).values():
        for name in V0_NEEDS:
            if not hasattr(character, name):
                setattr(character, name, 0)
        pregnancy = getattr(character, "pregnancy", None)
        if pregnancy is not None and not hasattr(pregnancy, V0_MILK):
            setattr(pregnancy, V0_MILK, 0)
    island = loaded_dict.get("rhodes_island")
    if island is not None and not hasattr(island, V0_STRATEGY):
        setattr(island, V0_STRATEGY, {})


def copy_v0_needs(old: object, new: object) -> bool:
    """
    角色替换时，把旧存档角色对象上的疲劳、饥饿、尿意属性抄到新角色对象上
    Keyword arguments:
    old -- 旧角色
    new -- 新角色
    Return arguments:
    bool -- 旧角色带着这些属性（旧存档）时为 True，否则什么也不抄，为 False
    """
    if not hasattr(old, "tired_point"):
        return False
    for name in V0_NEEDS:
        setattr(new, name, getattr(old, name))
    return True


def adopt_v0(loaded_dict: dict[str, Any]) -> None:
    """
    旧存档重建角色之后，把角色对象上的四项生理需求（换成精确值）与罗德岛的供电策略表（区块id换成字符串）
    写进当前缓冲区，再删掉对象上的这些属性。重建后的妊娠数据没有乳汁属性时，乳汁读 0
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    for cid, character in loaded_dict["character_data"].items():
        if not hasattr(character, "tired_point"):
            continue
        values = {
            stat: num.exact(getattr(character, name))
            for name, stat in V0_NEEDS.items()
        }
        values["milk"] = num.exact(getattr(character.pregnancy, V0_MILK, 0))
        needs.set(cid, **values)
        for name in V0_NEEDS:
            delattr(character, name)
        if hasattr(character.pregnancy, V0_MILK):
            delattr(character.pregnancy, V0_MILK)
    island = loaded_dict["rhodes_island"]
    strategy = getattr(island, V0_STRATEGY)
    table = {str(zone): value for zone, value in strategy.items()}
    working.put(None, power.KEY, table)
    delattr(island, V0_STRATEGY)


V1_POWER = (
    "power_use",
    "power_max",
    "power_storage",
    "power_storage_max",
    "power_operator_ids_list",
    "main_power_facility_operator_ids",
    "orundum_reactor_list",
    "other_power_facility_list",
    "battery_list",
    "now_used_extra_clean_energy_module_count",
    "now_used_extra_battery_count",
)
""" 版本 0 与 1 的存档里罗德岛对象上的动力属性名 """


def adopt_power(loaded_dict: dict[str, Any]) -> None:
    """
    罗德岛对象带着 V1_POWER 里的属性（版本 0 与 1 的存档）时，把动力数据写进当前缓冲区，再从对象上删掉这些属性
    副反应炉数量、清洁能源设施、蓄电池与主调控员写进 base.power，储能写进 base.power_storage
    缺的属性取 DEFAULT_PLANT 里的值，储能缺时为 0.0。对象上没有这些属性时什么也不写
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    island = loaded_dict.get("rhodes_island")
    attrs = vars(island) if island is not None else {}
    found = {name: attrs.pop(name) for name in V1_POWER if name in attrs}
    if not found:
        return
    power.set_plant(
        aux_reactors=found.get("orundum_reactor_list", [1, 3])[1],
        clean=tuple(found.get("other_power_facility_list", (0, 0, 0))),
        batteries=tuple(found.get("battery_list", (0, 0, 0))),
        main_operators=tuple(
            found.get("main_power_facility_operator_ids", (0, 0, 0, 0))
        ),
    )
    power.set_storage(found.get("power_storage", 0.0))


PICKLED_FACILITY = ("facility_level", "facility_open", "effectiveness")
""" 版本 4 之前的存档里，罗德岛对象上存设施等级、开放情况与基地效率的属性名 """


def adopt_facility(loaded_dict: dict[str, Any], version: int) -> int:
    """
    把罗德岛对象上 PICKLED_FACILITY 里的属性写进当前缓冲区，再从对象上删掉。对象上没有的属性不写。
    等级表与开放情况表的设施id 换成字符串后，写进 base.facility_level 与 base.facility_open。
    效率照原值写进 base.effectiveness
    Keyword arguments:
    loaded_dict -- 解开的存档缓存的属性表
    version -- 存档的版本，旧存档为 0
    Return arguments:
    int -- 版本 4 之前的存档缺了的属性个数，版本 4 的存档为 0
    """
    island = loaded_dict.get("rhodes_island")
    attrs = vars(island) if island is not None else {}
    found = {
        name: attrs.pop(name) for name in PICKLED_FACILITY if name in attrs
    }
    keys = {
        "facility_level": facility.LEVEL,
        "facility_open": facility.OPEN,
    }
    for name, key in keys.items():
        if name in found:
            table = {str(cid): value for cid, value in found[name].items()}
            working.put(None, key, table)
    if "effectiveness" in found:
        working.put(None, facility.EFFECTIVENESS, found["effectiveness"])
    return len(PICKLED_FACILITY) - len(found) if version < 4 else 0


V5_WORK = (
    "all_work_npc_set",
    "work_people_now",
    "hr_operator_ids_list",
    "current_warden_id",
)
""" 版本 6 之前的存档里罗德岛对象上的岗位名册与监狱长属性名 """


def adopt_work(loaded_dict: dict[str, Any]) -> None:
    """
    罗德岛对象带着 V5_WORK 里的属性（版本 6 之前的存档）时，把岗位名册与监狱长写进当前缓冲区，再从对象上删掉这些属性。
    名册只写有人且岗位id在配置里的岗位，名单按刷新时的顺序：在编干员（npc_id_got）里的按它的遍历顺序在前，
    不在编的按原集合的顺序在后。在岗人数与招聘专员名单由名册算出，不写。对象上没有这些属性时什么也不写
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    island = loaded_dict.get("rhodes_island")
    attrs = vars(island) if island is not None else {}
    found = {name: attrs.pop(name) for name in V5_WORK if name in attrs}
    if not found:
        return
    rank = {cid: i for i, cid in enumerate(loaded_dict.get("npc_id_got", ()))}
    work.set_rosters(
        {
            work_id: sorted(ids, key=lambda cid: rank.get(cid, len(rank)))
            for work_id, ids in found.get("all_work_npc_set", {}).items()
            if work_id in game_config.config_work_type
        }
    )
    work.set_warden(found.get("current_warden_id", 0))


def drop_ui_fields(loaded_dict: dict[str, Any]) -> dict[str, Any]:
    """
    去掉存档缓存与罗德岛对象上 UI_FIELDS、ISLAND_UI_FIELDS 里的属性
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    Return arguments:
    dict -- 其中玩家的面板选择（settings.PREFERENCES 里、类型与默认值相同的），名字到值
    """
    default = game_type.System_Setting()
    island = vars(loaded_dict["rhodes_island"])
    found = {
        name: loaded_dict.pop(name) for name in UI_FIELDS if name in loaded_dict
    }
    found.update(
        {name: island.pop(name) for name in ISLAND_UI_FIELDS if name in island}
    )
    return {
        name: value
        for name, value in found.items()
        if name in settings.PREFERENCES
        and type(value) is type(getattr(default, name))
    }


def copy_pickled(old: object, new: object, hit_max: int, mana_max: int) -> bool:
    """
    角色替换时，旧角色对象还带着版本 3 之前的数值属性时，把 REPLACED_COPIES 里的属性抄到新角色对象上，
    体力与气力上限设为新角色模板的值。读档后面的 adopt_pickled 再把它们写进 body.needs
    Keyword arguments:
    old -- 旧角色
    new -- 新角色
    hit_max -- 新角色模板的体力上限
    mana_max -- 新角色模板的气力上限
    Return arguments:
    bool -- 抄了时为 True。旧角色没有这些属性时什么也不抄，为 False
    """
    if not hasattr(old, "hit_point"):
        return False
    values = {name: getattr(old, name) for name in REPLACED_COPIES}
    values.update(hit_point_max=hit_max, mana_point_max=mana_max)
    for name, value in values.items():
        setattr(new, name, value)
    return True


def adopt_pickled(loaded_dict: dict[str, Any]) -> None:
    """
    重建角色之后，角色对象还带着版本 3 之前的数值属性时（版本 0 到 2 的存档），把 PICKLED_NEEDS 的十项写进当前缓冲区的
    body.needs。PICKLED_EXACT 里的属性换成精确值，对象上缺的属性读 0。乳汁上限不是 200 时写进 body.pregnancy。
    这些属性、妊娠数据上的乳汁上限与 last_hunger_time 从对象上删掉
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    for cid, character in loaded_dict["character_data"].items():
        if not hasattr(character, "hit_point"):
            continue
        values = {}
        for name, stat in PICKLED_NEEDS.items():
            value = getattr(character, name, 0)
            values[stat] = num.exact(value) if name in PICKLED_EXACT else value
            if hasattr(character, name):
                delattr(character, name)
        needs.set(cid, **values)
        milk_max = getattr(character.pregnancy, PICKLED_MILK_MAX, 200)
        if milk_max != 200:
            pregnancy.set_milk_max(cid, milk_max)
        if hasattr(character.pregnancy, PICKLED_MILK_MAX):
            delattr(character.pregnancy, PICKLED_MILK_MAX)
        if hasattr(character, STALE):
            delattr(character, STALE)


V4_ECONOMY = (
    "all_income",
    "shop_open_list",
    "restaurant_data",
    "stall_vendor_data",
    "supply_demand_dict",
    "today_trade_resource_count",
    "trade_operator_ids_list",
    "resource_type_main_trader",
    "resource_type_auto_trade_setting",
)
""" 版本 5 之前的存档里罗德岛对象上的九个经济属性名 """


def _shelf(foods: dict[Any, dict[Any, Any]]) -> dict[str, dict[str, int]]:
    return {
        str(recipe): {str(uid): food.quality for uid, food in row.items()}
        for recipe, row in foods.items()
    }


def adopt_economy(loaded_dict: dict[str, Any]) -> None:
    """
    罗德岛对象带着 V4_ECONOMY 里的属性（版本 5 之前的存档）时，从对象上删掉这些属性，把它们的值写进当前缓冲区。
    货架上每份食物只记食谱、uid 与品质。地摊小贩的货物表 0 号写成商店 economy.STALL。
    交易员名单不写，它由岗位名册算出。对象上没有这些属性时什么也不写
    Keyword arguments:
    loaded_dict -- 存档缓存的属性表
    """
    island = loaded_dict.get("rhodes_island")
    attrs = vars(island) if island is not None else {}
    found = {name: attrs.pop(name) for name in V4_ECONOMY if name in attrs}
    if not found:
        return
    economy.set_income(found.get("all_income", 0))
    for name in found.get("shop_open_list", ()):
        economy.open_shop(name)
    for rid, foods in found.get("restaurant_data", {}).items():
        economy.stock(rid, _shelf(foods))
    if 0 in found.get("stall_vendor_data", {}):
        economy.stock(economy.STALL, _shelf(found["stall_vendor_data"][0]))
    economy.set_supply_demand(found.get("supply_demand_dict", {}))
    economy.set_traded(found.get("today_trade_resource_count", {}))
    for res_type, cid in found.get("resource_type_main_trader", {}).items():
        economy.set_main_trader(res_type, cid)
    table = found.get("resource_type_auto_trade_setting", {})
    for rid, setting in table.items():
        economy.set_auto_trade(rid, setting)
