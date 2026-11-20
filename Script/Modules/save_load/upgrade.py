"""
save_load 的存档升级
====================
CURRENT 是本游戏写的文件 "2" 的版本。STEPS[n] 把版本 n 的 JSON 对象升到 n + 1。
版本 0 的存档把生理需求与供电策略放在文件 "1" 的缓存对象上，所以 0 升 1 不是 JSON 步骤。
这一升级在 install_save 里分三处。解开缓存后调 fill_v0_defaults，角色替换时调 copy_v0_needs，重建角色后调 adopt_v0。
版本 0 与 1 的存档把动力数据放在罗德岛对象上。install_save 解开缓存后对每个版本调 adopt_power，把它搬进 GameState。
界面的临时状态与玩家的面板选择不随存档：读任何版本的存档时，drop_ui_fields 去掉旧版本留在缓存与罗德岛对象上的它们，
以及不再使用的字段。
读旧存档不改写存档的文件。读完再存，写的是当前版本。本模块不登记行动、事件或规则，也不在 LOAD_ORDER 里。
"""

from collections.abc import Callable
from typing import Any

from Script.Core import game_type, num
from Script.Modules.domains import needs, power
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import settings

CURRENT = 2
""" 本游戏写的文件 "2" 的版本 """


def _v1_to_v2(data: dict[str, Any]) -> dict[str, Any]:
    """
    版本 1 升 2。文件 "2" 的结构不变，原样交回。版本 1 存档的动力数据由 adopt_power 搬进 GameState
    Keyword arguments:
    data -- 版本 1 的 JSON 对象
    Return arguments:
    dict -- 同一个对象
    """
    return data


STEPS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {1: _v1_to_v2}
""" 版本 n 到 n + 1 的升级步骤，键为 n """

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
