"""存档的读写、载入时的数据迁移与补全，以及存档信息文件的读写"""

from __future__ import annotations

import os
import shutil
import datetime
from types import FunctionType
from Script.Core import (
    constant,
    game_path_config,
    game_type,
    get_text,
    io_init,
    old_chara_to_new,
)
from Script.Config import normal_config, game_config, character_config
from Script.Design import attr_calculation, character_handle, map_handle
from Script.UI.Moudle import draw
from Script.System.Pregnancy_System import pregnancy_constant
import json
from typing import TYPE_CHECKING
from Script.Design import game_time
from Script.Modules.domains import abilities, achievement, action_info, activity
from Script.Modules.domains import body_manage, commission, country, diplomacy
from Script.Modules.domains import dirty, dormitory, education, entertainment
from Script.Modules.domains import facility, first_record, flags, fridge, growth
from Script.Modules.domains import h_meters, h_state, history, hypnosis
from Script.Modules.domains import inventory, kitchen, library, location
from Script.Modules.domains import maintenance, medical, modes, needs, official
from Script.Modules.domains import physical_exam, plan, player_ability
from Script.Modules.domains import player_collection, playthrough, pregnancy
from Script.Modules.domains import prison, production, recruit, roster, status
from Script.Modules.domains import tallies, visitor, wardrobe, warehouse
from Script.Modules.domains import chara_life, chara_profile, identity
from Script.Modules.domains import npc_template, relations, scene_state
from Script.Modules.domains import bookmarks
from Script.Modules.save_load import index, legacy_pickle, upgrade

if TYPE_CHECKING:
    from typing import Any

game_path = game_path_config.game_path
_: FunctionType = get_text._
UNSAVED_CACHE = frozenset(
    {
        "map_data",
        "recipe_data",
        "sun_phase",
        "moon_phase",
        "old_character_id",
        "over_behavior_character",
    }
)
""" 旧存档文件 "1" 里可能带着、读档导入前直接丢掉的顶层字段（由数据文件重建） """
UNSAVED_ISLAND = frozenset(
    {
        "warehouse_capacity",
        "people_max",
        "visitor_max",
        "medical_bed_limit",
        "life_zone_max",
        "research_zone_max",
        "soldier_max",
    }
)
""" 旧存档罗德岛对象上可能带着、读档导入前直接丢掉的字段（由数据文件与设施等级重算） """


def get_save_dir_path(save_id: str) -> str:
    """
    按存档id获取存档所在系统路径
    Keyword arguments:
    save_id -- 存档id
    """
    return index.path(save_id)


def judge_save_file_exist(save_id: str) -> bool:
    """
    判断存档id对应的存档是否存在
    Keyword arguments:
    save_id -- 存档id
    """
    return save_id in index.slots()


def establish_save(save_id: str) -> None:
    """
    把当前游戏状态作为 save.json 保存到存档位 save_id（kernel_state.write）
    全局设置不随存档，有改动时另写进游戏目录下的 settings.json
    Keyword arguments:
    save_id -- 存档id
    """
    from Script.Modules.save_load import kernel_state, settings

    head: dict[str, str] = {
        "game_verson": normal_config.config_normal.verson,
        "game_time": game_time.now().isoformat(),
        "character_name": identity.of(0).name,
        "save_time": datetime.datetime.now().isoformat(),
    }
    kernel_state.write(save_id, head)
    settings.save()


_ENTERTAINMENT_CID_MIGRATE = {175: 152, 176: 153, 177: 154, 178: 155}
""" 教育区娱乐改编号（2026-09-09）：旧编号 → 新编号。
    照料卵 / 跟随母亲 / 自由玩耍 / 上课（无课时自习）原来排在大浴场段（17x），改到教育区段（15x）紧接 151 过家家。
    存档里存娱乐编号的三处（日程模板的时段、单孩覆盖、当天的三个娱乐槽位）读档时都过一遍 _migrate_entertainment_cid """


def _migrate_entertainment_cid(value: Any) -> Any:
    """
    把存档里的旧娱乐编号换成新编号
    Keyword arguments:
    value -- 存档里的娱乐cid（也可能是别的类型，原样返回）
    Return arguments:
    value -- 换算后的娱乐cid
    功能: 只在旧编号已经不在 Entertainment.csv 里、新编号在 Entertainment.csv 里时才换：日后大浴场段真的用上 175 时，
          新档里的 175 就是那项浴场娱乐，不该被当成旧编号改掉；新编号不在表里时原样返回，
          由 old_chara_to_new.migrate_age_and_body_type 按表里没有的编号处理
    """
    from Script.Config import game_config

    if (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value in _ENTERTAINMENT_CID_MIGRATE
        and value not in game_config.config_entertainment
        and _ENTERTAINMENT_CID_MIGRATE[value]
        in game_config.config_entertainment
    ):
        return _ENTERTAINMENT_CID_MIGRATE[value]
    return value


def _migrate_child_schedule_template() -> int:
    """
    把内核状态里日程模板各时段存的旧娱乐编号换成新编号
    Return arguments:
    int -- 换掉的时段数
    """
    count = 0
    templates = education.templates()
    for template_data in templates.values():
        slot_data = (
            template_data.get("slot", {})
            if isinstance(template_data, dict)
            else {}
        )
        for slot in list(slot_data):
            new_cid = _migrate_entertainment_cid(slot_data[slot])
            if new_cid != slot_data[slot]:
                slot_data[slot] = new_cid
                count += 1
    if count:
        education.set_templates(templates)
    return count


_OFFICIAL_EVENT_UID_MIGRATE = {
    "萝莉1": "期末17",
    "萝莉20": "期末18",
    "萝莉26": "期末19",
}
""" 挪了桶的养成事件（Plan 32 L22）：旧uid → 新uid。
    写成绩单的萝莉 1 / 20 / 26 挪进期末桶后换了uid，而事件按uid逐角色去重（official_event_handle.judge_event_done）：
    旧档履历里记的是旧uid，不改名的话，经历过它们的孩子会在学期切换时再遇到一次同文同选项的期末 17 / 18 / 19，
    养成总览的履历也会因查不到配置而漏掉这几条 """


def _migrate_official_event_history(history_data: dict) -> int:
    """
    把事件履历里挪了桶的事件的旧uid改成新uid
    Keyword arguments:
    history_data -- 事件履历：CHILD_GROWTH.event_history 以uid为键，official.history() 的全局履历
    以「uid@角色id」为键（无主体时就是uid）
    Return arguments:
    int -- 改了名的条数
    功能: 只在旧uid已不在配置里、且新键还没有记录时才改（与 _migrate_entertainment_cid 同样的保护），重复读档是幂等的；
          新键已有记录时旧键原样留着，履历面板查不到配置会跳过它
    """
    from Script.Config import game_config

    count = 0
    for key in list(history_data):
        if not isinstance(key, str):
            continue
        uid, sep, suffix = key.partition("@")
        if (
            uid not in _OFFICIAL_EVENT_UID_MIGRATE
            or uid in game_config.config_official_event
        ):
            continue
        new_key = _OFFICIAL_EVENT_UID_MIGRATE[uid] + sep + suffix
        if new_key in history_data:
            continue
        history_data[new_key] = history_data.pop(key)
        count += 1
    return count


def _drop_unknown_books(loaded_dict: dict) -> int:
    """
    去掉存档里书籍配置中没有的书与书籍类型的引用，再跑一次不改任何东西
    Keyword arguments:
    loaded_dict -- 读档载入的旧存档属性表（character_data 已按身份表补齐）
    Return arguments:
    int -- 改动的处数
    功能描述:
        图书馆（library）：借阅表去掉这些书（谁借着都一样），阅读推荐去掉这些类型；
        每个角色：借书集合去掉这些书，借书卡上这些书没还的记录记为此刻（读档时是存档时刻）还了，
        正在读的书是这些书时书号与书名归零。
        阅读进度不动：成就按读完的书数统计
    """
    holders = library.holders()
    books = {b: h for b, h in holders.items() if b in game_config.config_book}
    types = library.recommended() & set(game_config.config_book_type)
    count = len(holders) - len(books) + len(library.recommended() - types)
    if count:
        library.put_holders(books)
        library.set_recommended(types)
    now_time = game_time.now()
    for cid in loaded_dict["character_data"]:
        with chara_life.borrow_book_id_set.editing(cid) as borrowed:
            unknown = borrowed - game_config.config_book.keys()
            borrowed.difference_update(unknown)
            count += len(unknown)
        with chara_life.borrow_book_history.editing(cid) as history:
            for record in history:
                if (
                    record.get("book_id") not in game_config.config_book
                    and record.get("return_time") is None
                ):
                    record["return_time"] = now_time
                    count += 1
        behavior = activity.behavior(cid)
        if behavior.book_id and behavior.book_id not in game_config.config_book:
            activity.update_behavior(cid, book_id=0, book_name="")
            count += 1
    return count


def _normalize_save_path(path_text: Any) -> Any:
    """
    将存档中的路径文本转换为当前系统的路径格式
    Keyword arguments:
    path_text -- 可能包含其他系统路径分隔符的值
    Return arguments:
    str/object -- 字符串路径会被归一化，其他类型原样返回
    """
    foreign_sep = "\\" if os.sep == "/" else "/"
    if isinstance(path_text, str) and foreign_sep in path_text:
        return path_text.replace(foreign_sep, os.sep)
    return path_text


def _normalize_life(loaded_dict: dict[str, Any]) -> None:
    """
    读档时整理角色键里的场景路径与娱乐编号。在角色数据搬进 GameState 之后调用
    chara_life.PATHS 里的场景路径换成本系统的路径分隔符。
    当天三个娱乐时段的编号经 _migrate_entertainment_cid 换算
    Keyword arguments:
    loaded_dict -- 旧存档的属性表
    """
    for cid in loaded_dict["character_data"]:
        for key in chara_life.PATHS:
            key.set(cid, _normalize_save_path(key(cid)))
        with chara_life.entertainment_type.editing(cid) as slots:
            slots[:] = [_migrate_entertainment_cid(one) for one in slots]


def _normalize_save_path_keys(path_dict: Any) -> Any:
    """
    归一化以场景或地图路径为键的存档字典
    Keyword arguments:
    path_dict -- 以路径文本为键的字典
    Return arguments:
    dict/object -- 有外来分隔符时返回归一化后的字典，否则原样返回
    """
    if not isinstance(path_dict, dict):
        return path_dict
    if not any(_normalize_save_path(key) != key for key in path_dict):
        return path_dict
    return {
        _normalize_save_path(key): value for key, value in path_dict.items()
    }


def _migrate_first_record_flat_fields(cid: int, character: object) -> None:
    """
    将旧存档FIRST_RECORD中的平铺处女字段迁移进first_part_sex_dict
    Keyword arguments:
    cid -- 角色id
    character -- 反序列化得到的角色对象（旧档判据：first_record无first_part_sex_dict属性，二次载入幂等）
    Return arguments:
    None
    """
    first_record = getattr(character, "first_record", None)
    if first_record is None or hasattr(first_record, "first_part_sex_dict"):
        return
    default_time = datetime.datetime(1, 1, 1)
    # 先补齐9个新dict默认值
    first_record.first_part_sex_dict = {}
    first_record.first_shoot_body_dict = {}
    first_record.first_strong_orgasm_dict = {}
    first_record.first_super_orgasm_dict = {}
    first_record.first_plural_orgasm_dict = {}
    first_record.fall_talent_time_dict = {}
    first_record.first_mark_dict = {}
    first_record.first_h_mode_dict = {}
    first_record.first_special_record_dict = {}
    # 仅NPC：V处女平铺字段转入键6，随后重置回默认值（字段保留给玩家童贞用，不delattr）
    if cid != 0 and getattr(first_record, "first_sex_id", -1) != -1:
        first_record.first_part_sex_dict[6] = {
            "id": first_record.first_sex_id,
            "time": first_record.first_sex_time,
            "place": list(first_record.first_sex_place),
            "posture": first_record.first_sex_posture,
            "item": getattr(first_record, "first_sex_item", -1),
        }
        first_record.first_sex_id = -1
        first_record.first_sex_time = default_time
        first_record.first_sex_place = ["0"]
        first_record.first_sex_posture = ""
        first_record.first_sex_item = -1
    # A处女平铺字段转入键8
    if getattr(first_record, "first_a_sex_id", -1) != -1:
        first_record.first_part_sex_dict[8] = {
            "id": first_record.first_a_sex_id,
            "time": first_record.first_a_sex_time,
            "place": list(first_record.first_a_sex_place),
            "posture": first_record.first_a_sex_posture,
            "item": getattr(first_record, "first_a_sex_item", -1),
        }
    # U处女平铺字段转入键9（旧道具编号1采尿器改记为2）
    if getattr(first_record, "first_u_sex_id", -1) != -1:
        old_u_item = getattr(first_record, "first_u_sex_item", -1)
        first_record.first_part_sex_dict[9] = {
            "id": first_record.first_u_sex_id,
            "time": first_record.first_u_sex_time,
            "place": list(first_record.first_u_sex_place),
            "posture": first_record.first_u_sex_posture,
            "item": 2 if old_u_item == 1 else old_u_item,
        }
    # W处女平铺字段转入键7
    if getattr(first_record, "first_w_sex_id", -1) != -1:
        first_record.first_part_sex_dict[7] = {
            "id": first_record.first_w_sex_id,
            "time": first_record.first_w_sex_time,
            "place": list(first_record.first_w_sex_place),
            "posture": first_record.first_w_sex_posture,
            "item": -1,
        }
    # M处女时间转入键2（旧档只有时间，无对象/姿势/道具信息）
    if getattr(first_record, "first_m_sex_time", default_time).year > 1:
        first_record.first_part_sex_dict[2] = {
            "id": -1,
            "time": first_record.first_m_sex_time,
            "place": ["0"],
            "posture": "",
            "item": -1,
        }
    # 清理已转入 first_part_sex_dict 的旧平铺字段
    for old_attr in (
        "first_a_sex_id",
        "first_a_sex_time",
        "first_a_sex_place",
        "first_a_sex_posture",
        "first_a_sex_item",
        "first_u_sex_id",
        "first_u_sex_time",
        "first_u_sex_place",
        "first_u_sex_posture",
        "first_u_sex_item",
        "first_w_sex_id",
        "first_w_sex_time",
        "first_w_sex_place",
        "first_w_sex_posture",
        "first_m_sex_time",
    ):
        if hasattr(first_record, old_attr):
            delattr(first_record, old_attr)


def _clear_soft_egg_race_pregnancy(
    cid: int, character: object, soft_egg_enabled: bool = True
) -> None:
    """
    清除旧存档里无壳卵生种族角色正在进行的胎生孕程
    无壳卵生（birth_type=12）实装前的旧存档里，该种族角色可能持有受精、妊娠或临盆素质。
    读档时清除素质 20（受精）、21（妊娠）、22（临盆）、26（孕肚）、35（无意识妊娠），
    并把本次胎数、同卵双胞胎与妊娠加速累计归零，不影响 23（产后）、24（育儿）、27（泌乳）与已出生孩子。
    非无壳卵生或未在孕程中的角色不做改动。
    无壳卵生开关关闭时该种族按单胎胎生运行，本函数直接跳过，避免读档时误清正常孕程。
    版本 16 之前的素质表在角色对象上，版本 16 起经 abilities.talent 读写。
    Keyword arguments:
    cid -- 角色id
    character -- 存档里的角色对象
    soft_egg_enabled -- 无壳卵生开关是否开启，关闭时跳过
    Return arguments:
    无
    """
    if not soft_egg_enabled:
        return
    talent = getattr(character, "talent", abilities.talent(cid))
    if not isinstance(talent, dict | abilities.Table):
        return
    race_config = game_config.config_race.get(identity.of(cid).race)
    if race_config is None or getattr(race_config, "birth_type", 1) != 12:
        return
    if not any(talent.get(talent_id, 0) for talent_id in (20, 21, 22)):
        return
    for talent_id in (20, 21, 22, 26, 35):
        talent[talent_id] = 0
    pregnancy_data = vars(character).get("pregnancy")
    if pregnancy_data is not None:
        pregnancy_data.fetus_count = 0
        pregnancy_data.identical_twins = False
        pregnancy_data.acceleration_days = 0.0
    else:
        pregnancy.update(
            cid,
            fetus_count=0,
            identical_twins=False,
            acceleration_days=0.0,
        )


def _normalize_loaded_save_paths(loaded_dict: dict[str, Any]) -> None:
    """
    归一化反序列化旧存档中已知的结构性路径字段
    Keyword arguments:
    loaded_dict -- 旧存档的属性表
    Return arguments:
    None
    """
    scene_data = loaded_dict.get("scene_data")
    if isinstance(scene_data, dict):
        loaded_dict["scene_data"] = _normalize_save_path_keys(scene_data)

    # 无壳卵生开关：本函数早于 playthrough.adopt_old_save 执行，从存档自身读：
    # 版本 12 之前的旧存档在文件 "1" 的属性表里，版本 12 起在换入的 GameState 里，更旧的存档在设置对象里
    # 旧存档没有该设置项，.get兜底为开启，正是旧存档迁移应有的行为
    loaded_birth_setting = loaded_dict.get(
        "birth_type_setting"
    ) or playthrough.settings(playthrough.BIRTH_TYPE)
    if not loaded_birth_setting:
        loaded_birth_setting = getattr(
            loaded_dict.get("all_system_setting"),
            "birth_type_setting",
            None,
        )
    soft_egg_enabled = True
    if isinstance(loaded_birth_setting, dict):
        soft_egg_enabled = bool(
            loaded_birth_setting.get(pregnancy_constant.BIRTH_TYPE_EGG_SOFT, 1)
        )

    character_data = loaded_dict.get("character_data")
    if isinstance(character_data, dict):
        for cid, character in character_data.items():
            # 这里早于 old_chara_to_new 的迁移运行。旧存档的角色对象上可能有 pre_dormitory。
            # chara_life.PATHS 里的场景路径由 _normalize_life 整理
            if not hasattr(character, "permanent_dormitory") and hasattr(
                character, "pre_dormitory"
            ):
                character.pre_dormitory = _normalize_save_path(
                    character.pre_dormitory
                )
            ability_data = getattr(character, "pl_ability", None)
            if ability_data is not None and hasattr(
                ability_data, "air_hypnosis_position"
            ):
                ability_data.air_hypnosis_position = _normalize_save_path(
                    ability_data.air_hypnosis_position
                )
            # 避孕套系统旧存档兼容：补全玩家收藏品与角色污浊结构体中缺失的字段
            pl_collection = getattr(character, "pl_collection", None)
            if pl_collection is not None and not hasattr(
                pl_collection, "used_condoms"
            ):
                pl_collection.used_condoms = []
            dirty_data = getattr(character, "dirty", None)
            if dirty_data is not None and not hasattr(
                dirty_data, "condom_decoration"
            ):
                dirty_data.condom_decoration = {}
            # 旧存档妊娠与养成结构体兼容：有属性时才回填与规范，读档后由领域 adopt 搬进内核状态
            pregnancy_data = vars(character).get("pregnancy")
            if pregnancy_data is not None and hasattr(
                pregnancy_data, "__dict__"
            ):
                default_preg = game_type.PREGNANCY()
                for attr_name in vars(default_preg):
                    if not hasattr(pregnancy_data, attr_name):
                        setattr(
                            pregnancy_data,
                            attr_name,
                            getattr(default_preg, attr_name),
                        )
                pregnancy_data.acceleration_days = min(
                    pregnancy_data.acceleration_days,
                    pregnancy_constant.ACCELERATION_MAX_DAY,
                )
                pregnancy_data.growth_acceleration_days = min(
                    pregnancy_data.growth_acceleration_days,
                    pregnancy_constant.GROW_TO_GIRL_DAY - 1,
                )
                for egg_data in pregnancy_data.eggs.values():
                    if "acceleration_days" in egg_data:
                        egg_data["acceleration_days"] = min(
                            egg_data["acceleration_days"],
                            pregnancy_constant.ACCELERATION_MAX_DAY,
                        )
            growth_data = vars(character).get("child_growth")
            if growth_data is not None and hasattr(growth_data, "__dict__"):
                growth.normalize_legacy(growth_data)
            elif growth.has(cid):
                with growth.editing(cid, create=False) as kernel_growth:
                    if kernel_growth is not None:
                        growth.normalize_legacy(kernel_growth)
            _clear_soft_egg_race_pregnancy(cid, character, soft_egg_enabled)
            if pl_collection is not None and not hasattr(
                pl_collection, "held_eggs"
            ):
                pl_collection.held_eggs = {}
            if pl_collection is not None and not hasattr(
                pl_collection, "next_held_egg_id"
            ):
                pl_collection.next_held_egg_id = 0
            # 无壳卵生旧存档兼容：补全玩家收藏品中的体外无壳卵字典
            if pl_collection is not None and not hasattr(
                pl_collection, "soft_eggs"
            ):
                pl_collection.soft_eggs = {}
            if pl_collection is not None and not hasattr(
                pl_collection, "next_soft_egg_id"
            ):
                pl_collection.next_soft_egg_id = 0
            # 睡觉中被吵醒旧存档兼容：补全角色行动信息中缺失的被吵醒状态结束时间
            action_info_data = getattr(character, "action_info", None)
            if action_info_data is not None and not hasattr(
                action_info_data, "sleep_disturbed_end_time"
            ):
                action_info_data.sleep_disturbed_end_time = datetime.datetime(
                    1, 1, 1
                )
            # 性行为履历旧存档兼容：平铺处女字段合并进first_part_sex_dict
            _migrate_first_record_flat_fields(cid, character)


def load_save(save_id: str) -> dict[str, Any]:
    """
    读取读档导入用的旧存档属性表。save.json 槽位返回空字典，旧槽位经 legacy_pickle 解开文件 "1"。
    结果必含 rhodes_island 对象，并丢掉 UNSAVED_CACHE 与 UNSAVED_ISLAND 中的字段。
    npc_tem_data 里存为 None 的项按配置模板补回，配置里没有该键时删去
    Keyword arguments:
    save_id -- 存档id
    Return arguments:
    dict -- 属性名到值
    """
    loaded: dict[str, Any] = {}
    if not index.is_json(save_id):
        loaded = legacy_pickle.cache(index.file(save_id, index.CACHE_FILE))
    island = loaded.setdefault("rhodes_island", legacy_pickle.LegacyObject())
    for name in UNSAVED_CACHE & loaded.keys():
        del loaded[name]
    for name in UNSAVED_ISLAND & vars(island).keys():
        del vars(island)[name]
    templates = loaded.get("npc_tem_data")
    if isinstance(templates, dict):
        config = character_config.character_tem_list
        for key in [k for k, v in templates.items() if v is None]:
            if key in config:
                templates[key] = config[key]
            else:
                del templates[key]
    return loaded


def input_load_save(save_id: str) -> None:
    """
    读档：内核的 GameState 换成存档里的（kernel_state.load，读档的步骤见 save_load.reset）；
    玩家选行动时调用则中止这次选择
    Keyword arguments:
    save_id -- 存档id
    """
    from Script.Modules.save_load import kernel_state

    kernel_state.load(save_id)


def install_save(save_id: str, version: int) -> None:
    """
    读档的 Reset 步骤：由 load_save 读出旧存档属性表后调 npc_template.lift 与 identity.adopt_old_save，
    版本 0 补默认值，24 个 adopt（含 bookmarks，19 计数）搬罗德岛属性与收藏地点。
    ID 迁移后 flags、action_info、player_ability、player_collection 搬四项。修编号后 abilities（计数）与
    inventory、wardrobe、body_manage、status 搬入。替换后搬 relations、chara_life、chara_profile，
    逐角色更新配置与服装后再搬 adopt_v0、adopt_pickled、npc_template（存局内模板并删 6/7 号素质，计数）、
    activity（计数）、pregnancy、growth。
    h_meters 等六模块与周目等七模块（含 modes、history）计数，最后收尾会话。
    Keyword arguments:
    save_id -- 存档id
    version -- 存档的版本，旧存档为 0
    """
    from Script.System.Medical_System import medical_service

    update_count = 0

    loaded_dict = npc_template.lift(load_save(save_id))
    identity.adopt_old_save(loaded_dict)
    _normalize_loaded_save_paths(loaded_dict)
    if version == 0:
        upgrade.fill_v0_defaults(loaded_dict)
    upgrade.adopt_power(loaded_dict)
    update_count += upgrade.adopt_facility(loaded_dict, version)
    upgrade.adopt_economy(loaded_dict)
    upgrade.adopt_work(loaded_dict)
    warehouse.adopt_old_save(loaded_dict)
    medical.adopt_island(loaded_dict)
    for domain in (production, kitchen, commission, visitor, location):
        update_count += domain.adopt_old_save(loaded_dict, version)
    for domain in (recruit, official, diplomacy, dormitory, library):
        update_count += domain.adopt_old_save(loaded_dict, version)
    for domain in (entertainment, tallies, fridge, prison, education):
        update_count += domain.adopt_old_save(loaded_dict, version)
    for domain in (maintenance, physical_exam, bookmarks):
        update_count += domain.adopt_old_save(loaded_dict, version)

    draw_text = _("\n开始检测存档的数据结构是否需要跨版本更新\n")
    now_draw = draw.LeftDraw()
    now_draw.text = draw_text
    now_draw.draw()

    # 检测是否为旧版存档（npc_tem_data是List而不是Dict）
    if isinstance(loaded_dict.get("npc_tem_data"), list):
        draw_text = _("\n检测到旧版存档，开始迁移角色ID系统...\n")
        now_draw = draw.LeftDraw()
        now_draw.text = draw_text
        now_draw.draw()

        migrate_count = old_chara_to_new.migrate_old_save_data(loaded_dict)

        draw_text = _("\n角色ID迁移完成，共处理{0}条数据\n").format(
            migrate_count
        )
        now_draw = draw.LeftDraw()
        now_draw.text = draw_text
        now_draw.draw()
        update_count += migrate_count

    for chara_domain in (flags, action_info, player_ability, player_collection):
        chara_domain.adopt_old_save(loaded_dict)

    # 更新角色预设
    update_count += old_chara_to_new.update_tem_character(loaded_dict)
    # 修正编号错误的角色数据
    update_count += old_chara_to_new.fix_wrong_character(loaded_dict)
    update_count += abilities.adopt_old_save(loaded_dict)
    for domain in (inventory, wardrobe, body_manage, status):
        domain.adopt_old_save(loaded_dict)

    # ========== 角色替换迁移（新旧角色ID映射） ==========
    # 用于将旧角色的数据迁移到新角色，例如：1478号梅捷缇克缇 → 4056号缇缇
    character_replacement_map = {
        891: 4212,  # NPC娜斯提 → 干员娜斯提
        1040: 4052,  # 蒂拉 → 寻澜
        1478: 4056,  # 梅捷缇克缇 → 缇缇
    }
    # 检测是否需要进行角色替换迁移
    need_migration = False
    for old_id in character_replacement_map.keys():
        if old_id in loaded_dict["character_data"]:
            need_migration = True
            break

    if need_migration:
        draw_text = _("\n检测到需要进行角色替换迁移...\n")
        now_draw = draw.LeftDraw()
        now_draw.text = draw_text
        now_draw.draw()

        migration_count = old_chara_to_new.migrate_character_replacement(
            loaded_dict, character_replacement_map
        )

        if migration_count > 0:
            draw_text = _("\n角色替换迁移完成，共迁移{0}个角色\n").format(
                migration_count
            )
            now_draw = draw.LeftDraw()
            now_draw.text = draw_text
            now_draw.draw()
            update_count += migration_count

    preferences = upgrade.drop_ui_fields(loaded_dict)

    # 把版本 21 之前存档的角色对象上的社会关系、住处、工作、娱乐与称呼等属性搬进角色键
    for domain in (relations, chara_life, chara_profile):
        domain.adopt_old_save(loaded_dict)
    _normalize_life(loaded_dict)

    # 遍历更新全角色属性
    cloth_update_count = 0
    color_update_count = 0
    for key in loaded_dict["character_data"]:
        one = identity.of(key)
        # 角色素质、经验、宝珠、能力、设置的更新
        update_count += old_chara_to_new.update_character_config_data(one, key)
        # 当前角色模板数据（使用Dict方式访问，兼容新旧存档）
        tem_character = loaded_dict["npc_tem_data"].get(key)
        if tem_character is None:
            # 如果找不到，尝试用adv
            tem_character = loaded_dict["npc_tem_data"].get(one.adv, None)
        if tem_character is None:
            # 处理找不到模板的情况（玩家跳过，NPC创建空白模板）
            if key == 0:
                continue
            tem_character = character_handle.create_empty_character_tem()
            tem_character.Name = one.name
            tem_character.AdvNpc = one.adv
            loaded_dict["npc_tem_data"][key] = tem_character
        # 更新角色服装
        cloth_update_count += old_chara_to_new.update_chara_cloth(
            one, tem_character
        )
        # 更新角色口上颜色
        if key != 0 and tem_character.TextColor != one.text_color:
            identity.update(key, text_color=tem_character.TextColor)
            text_color_list = (one.adv, one.name, tem_character.TextColor)
            character_config.add_text_color_data_to_config_data(text_color_list)
            update_count += 1
            color_update_count += 1
        # 更新角色的口上大小
        if key != 0 and tem_character.Talk_Size != one.talk_size:
            identity.update(key, talk_size=tem_character.Talk_Size)
            update_count += 1
        # 更新角色势力与出身地
        if key != 0 and tem_character.Nation != relations.nation(key):
            relations.nation.set(key, tem_character.Nation)
            update_count += 1
        if key != 0 and tem_character.Birthplace != relations.birthplace(key):
            relations.birthplace.set(key, tem_character.Birthplace)
            update_count += 1
        # 更新到玩家收藏品列表
        if key != 0 and player_collection.ensure_npc(key):
            update_count += 1
        # 被监禁的角色检查是否在囚犯列表中，需要排除正在逃跑的人
        if (
            flags.get(key, "imprisonment")
            and not flags.get(key, "escaping")
            and not prison.is_prisoner(key)
        ):
            prison.imprison(key, game_time.now(), 0)
            update_count += 1
    if cloth_update_count:
        now_draw = draw.LeftDraw()
        draw_text = _("\n共有{0}个角色的服装数据已重置\n").format(
            cloth_update_count
        )
        now_draw.text = draw_text
        now_draw.draw()

    # 更新字体颜色
    if color_update_count:
        io_init.init_style()
        now_draw = draw.LeftDraw()
        draw_text = _("\n共有{0}个角色的口上颜色已更新\n").format(
            color_update_count
        )
        now_draw.text = draw_text
        now_draw.draw()

    # 库存里没有的配置资源记为 0
    for all_cid in game_config.config_resouce:
        if all_cid not in warehouse.stock():
            warehouse.set(all_cid, 0)
            update_count += 1
    # 教育区娱乐改编号（2026-09-09）：日程模板各时段里存的旧编号换成新编号
    update_count += _migrate_child_schedule_template()
    if version == 0:
        upgrade.adopt_v0(loaded_dict)
    upgrade.adopt_pickled(loaded_dict)
    update_count += npc_template.adopt_old_save(loaded_dict)
    update_count += activity.adopt_old_save(loaded_dict)
    pregnancy.adopt_old_save(loaded_dict, version)
    growth.adopt_old_save(loaded_dict, version)
    for chara_domain in (h_meters, h_state, dirty, hypnosis, first_record):
        update_count += chara_domain.adopt_old_save(loaded_dict)
    update_count += h_meters.adopt_world(loaded_dict, version)
    young_child_session: old_chara_to_new.YoungChildSession = {}
    update_count += old_chara_to_new.migrate_age_and_body_type(
        loaded_dict, young_child_session
    )
    update_count += roster.adopt_old_save(loaded_dict, version)
    # 挪了桶的养成事件：全局履历里的旧uid改成新uid
    event_history = official.history()
    update_count += _migrate_official_event_history(event_history)
    official.set_history(event_history)
    # 更新罗德岛的设施等级
    for all_cid in game_config.config_facility:
        # 没有记录的设施改为初始等级0
        if all_cid not in facility.levels():
            facility.set_level(all_cid, 1)
            update_count += 1
    # 更新罗德岛的设施开启状态
    for all_cid in game_config.config_facility_open:
        # 没有记录的设施改为初始关闭
        if all_cid not in facility.opens():
            facility.set_open(all_cid, False)
        # 已关闭的查询是否可以被已有角色开启
        if not facility.is_open(all_cid):
            if game_config.config_facility_open[all_cid].NPC_id != 0:
                for chara_cid in roster.active():
                    if (
                        identity.of(chara_cid).adv
                        == game_config.config_facility_open[all_cid].NPC_id
                    ):
                        facility.set_open(all_cid)
                        break
    # 去掉书籍配置里没有的书与书籍类型的引用
    update_count += _drop_unknown_books(loaded_dict)

    # 更新各项设置；系统设置是全局的，不随存档载入（还没有 settings.json 时，存档的设置成为全局设置）
    update_count += playthrough.adopt_old_save(loaded_dict, version)
    update_count += update_settings(loaded_dict)
    from Script.Modules.save_load import settings

    settings.adopt(loaded_dict.pop("all_system_setting", None), preferences)

    # 更新大地图势力数据，再搬走模式开关、成就、事件与指令记录、计划
    update_count += country.adopt_old_save(loaded_dict, version)
    update_count += modes.adopt_old_save(loaded_dict, version)
    update_count += needs.adopt_old_save(loaded_dict, version)
    update_count += achievement.adopt_old_save(loaded_dict, version)
    update_count += history.adopt_old_save(loaded_dict, version)
    update_count += plan.adopt_old_save(loaded_dict, version)

    # 更新游戏地图
    update_count += update_map(loaded_dict)
    scene_state.adopt_old_save(loaded_dict)

    # 更新医疗系统存档结构
    medical_service.update_medical_save_data_structure(loaded_dict)

    # 最后输出
    finish_draw = draw.NormalDraw()
    draw_text = _("\n检测完毕，共有{0}条数据完成了更新\n").format(update_count)
    finish_draw.text = draw_text
    finish_draw.draw()

    # 有101/102阶段的孩子参与的群交、时停与H，各按自己的结束结算收尾（须在读档导入完成后调用）
    old_chara_to_new.end_young_child_session(young_child_session)


def exact_stats() -> None:
    """
    读档的 Reset 步骤：空操作占位。
    body.needs、body.status、h.meters、body.dirty 与 player.ability 在读档导入时即换成精确值（num.exact）
    """
    return


def repair_installed() -> None:
    """
    读档的 Reset 步骤，在角色投影之后：游戏状态自检（系统设置14号，默认关闭）对载入后的存档做保守修复，
    包在开关关闭时不会被导入；修复经这一步的缓冲区读写 GameState
    """
    if normal_config.system_setting.base_setting.get(14, 0):
        from Script.Test import Static_Check as static_check_system

        static_check_system.run_load_repair()


def update_dict_with_default(
    loaded_dict: dict[str, Any], default_dict: dict[str, Any]
) -> int:
    """
    递归地赋值字典
    Keyword arguments:
    loaded_dict -- 要赋值的字典
    default_dict -- 默认字典
    """
    update_count = 0
    for key, value in default_dict.items():
        # 跳过Python的内置方法
        if key.startswith("__") and key.endswith("__"):
            continue
        # 如果 key 不在 loaded_dict 中，将其添加到 loaded_dict 中
        if key not in loaded_dict:
            loaded_dict[key] = value
            update_count += 1
        elif hasattr(value, "__dict__"):  # 检查 value 是否是一个类的实例
            update_count += update_dict_with_default(
                loaded_dict[key].__dict__, value.__dict__
            )
        # 存档里的游戏时间是 GameTime（datetime 的子类），默认值是普通 datetime，两者都是时间就保留存档值
        elif isinstance(value, datetime.datetime) and isinstance(
            loaded_dict[key], datetime.datetime
        ):
            continue
        # 如果key的类型不同，且value不为None，类型也不为int或float时，将其设为默认值
        elif (
            type(loaded_dict[key]) is not type(default_dict[key])
            and value is not None
            and type(value) is not int
            and type(value) is not float
        ):
            loaded_dict[key] = value
            update_count += 1
    return update_count


def update_map(loaded_dict: dict[str, Any]) -> int:
    """
    读档时校验地图变动并迁回停留在无效场景中的角色。
    若 loaded_dict 含有旧存档的 scene_data，则将其与 constant.scene_data 对比，统计新增场景及 scene_tag、
    scene_img、room_area 差异。
    存在差异时，若旧表含「贸易\\人气快餐开封菜」则把该处角色迁至「约翰老妈汉堡店」，
    累加已不存在的场景数并提示地图已更新。
    随后逐一检查 loaded_dict["character_data"] 中全部角色的 activity.position，将不在 constant.scene_data
    中的角色迁回同区块入口或 ["0", "0"]
    Keyword arguments:
    loaded_dict -- 读档阶段加载的旧存档属性表
    Return arguments:
    int -- 统计到的场景差异项数与被迁回角色数之和
    """

    update_count = 0
    saved = loaded_dict.get("scene_data") or {}
    for key, value in constant.scene_data.items() if saved else ():
        old = saved.get(key)
        if old is None:
            update_count += 1
            continue
        update_count += value.scene_tag != old.scene_tag
        update_count += value.scene_img != getattr(old, "scene_img", None)
        update_count += value.room_area != getattr(old, "room_area", None)
    # 旧存档场景表与当前 constant.scene_data 有差异时，迁移更名场景内的角色，补计缺失场景数并提示地图已更新
    if update_count:
        # 在2024.7月的版本中将人气快餐开封菜改为了约翰老妈汉堡店
        if "贸易\\人气快餐开封菜" in saved:
            for cid in loaded_dict["character_data"]:
                position = activity.position(cid)
                if position[-1] == "人气快餐开封菜":
                    activity.set_position(
                        cid, [*position[:-1], "约翰老妈汉堡店"]
                    )
        update_count += len(saved.keys() - constant.scene_data.keys())
        now_draw = draw.LeftDraw()
        draw_text = _("\n游戏地图已更新\n")
        now_draw.text = draw_text
        now_draw.draw()

    # 把站在不存在的场景里的角色挪回来
    # 地图改建会移除旧场景（例如把单间「教室」拆成多间理论教室、实践教室与大礼堂），
    # 站在里面的角色若 position 仍指向旧路径，后续访问 constant.scene_data[该路径] 会直接 KeyError
    # 此处在 if update_count 之外无条件执行，因为当前存档不含 scene_data，且旧存档只多出已删除的场景时 update_count
    # 也为 0
    move_back_count = 0
    for character_id in loaded_dict["character_data"]:
        position = activity.position(character_id)
        old_position_str = map_handle.get_map_system_path_str_for_list(position)
        if old_position_str in constant.scene_data:
            continue
        # 回落到同一区块的入口——每个区块都有一个"0"号入口场景；整个区块都没了才回落到地图原点
        new_position = [position[0], "0"] if position else ["0", "0"]
        if (
            map_handle.get_map_system_path_str_for_list(new_position)
            not in constant.scene_data
        ):
            new_position = ["0", "0"]
        activity.set_position(character_id, new_position)
        update_count += 1
        move_back_count += 1
    if move_back_count:
        now_draw = draw.LeftDraw()
        now_draw.text = _(
            "\n有{0}名角色所在的房间已不存在（地图改建），已将她们移动到所属区块的入口\n"
        ).format(move_back_count)
        now_draw.style = "gold_enrod"
        now_draw.draw()

    return update_count


def update_settings(loaded_dict: dict[str, Any]) -> int:
    """
    读档时按需收下存档里的 AI 设置，并补全全局口上选择、AI 设置与本存档的体检、监禁调教设置
    Keyword arguments:
    loaded_dict -- 旧存档的属性字典
    Return arguments:
    int -- 补全的口上选择、体检与监禁调教设置项总数（不含全局 AI 设置）
    """
    update_count = 0
    # 角色口上选择设置是全局的：补上缺的角色与本存档女儿的默认值
    character_text_version = (
        attr_calculation.get_system_setting_zero().character_text_version
    )
    for daughter_cid in relations.child_id_list(0):
        character_text_version.setdefault(daughter_cid, 1)
    global_text_version = normal_config.system_setting.character_text_version
    missing = character_text_version.keys() - global_text_version.keys()
    for key in missing:
        global_text_version[key] = character_text_version[key]
    if missing:
        update_count += len(missing)
        now_draw = draw.NormalDraw()
        draw_text = _("\n角色口上选择设置已更新，如有需要请手动修改\n")
        now_draw.style = "gold_enrod"
        now_draw.text = draw_text
        now_draw.draw()
    # 弹出 ai_setting 交给 adopt_ai 准备并待 Reset 生效，补全项不计入存档更新数
    from Script.Modules.save_load import settings

    if settings.adopt_ai(loaded_dict.pop("ai_setting", None)):
        now_draw = draw.NormalDraw()
        draw_text = _("\n文本生成AI设置已更新，如有需要请手动修改\n")
        now_draw.style = "gold_enrod"
        now_draw.text = draw_text
        now_draw.draw()
    # 更新体检设置
    zero_physical_exam_setting = (
        attr_calculation.get_physical_exam_setting_zero()
    )
    exam_setting = physical_exam.settings()
    if len(exam_setting) != len(zero_physical_exam_setting):
        for key in zero_physical_exam_setting:
            if key not in exam_setting:
                exam_setting[key] = zero_physical_exam_setting[key]
                update_count += 1
        physical_exam.set_settings(exam_setting)
        now_draw = draw.NormalDraw()
        draw_text = _("\n体检设置已更新，如有需要请手动修改\n")
        now_draw.style = "gold_enrod"
        now_draw.text = draw_text
        now_draw.draw()
    # 更新监禁调教设置
    if len(prison.settings()) != len(
        game_config.config_confinement_training_setting
    ):
        update_count += prison.fill_missing_settings()
        now_draw = draw.NormalDraw()
        draw_text = _("\n监禁调教设置已更新，如有需要请手动修改\n")
        now_draw.style = "gold_enrod"
        now_draw.text = draw_text
        now_draw.draw()
    return update_count


def remove_save(save_id: str) -> None:
    """
    删除存档id对应存档
    Keyword arguments:
    save_id -- 存档id
    """
    save_path = get_save_dir_path(save_id)
    if os.path.isdir(save_path):
        shutil.rmtree(save_path)


def _get_save_info_path() -> str:
    """
    获取 save_info.json 的路径（用于记录界面相关的简单配置）
    """
    save_dir = os.path.join("save")
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)
    return os.path.join(save_dir, "save_info.json")


def load_save_info_file() -> dict:
    """
    读取 save/save_info.json 并返回字典，文件不存在时返回空字典
    """
    path = _get_save_info_path()
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_save_info_file(data: dict) -> None:
    """
    将 data 字典写入 save/save_info.json（覆盖写）
    """
    path = _get_save_info_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        # 忽略写入错误，避免影响保存流程
        pass


def get_last_save_page() -> int:
    """方便的包装，返回保存的 last_save_page，默认 0"""
    info = load_save_info_file()
    try:
        return int(info.get("last_save_page", 0))
    except Exception:
        return 0


def set_last_save_page(page: int) -> None:
    """方便的包装，写入 last_save_page 到 save_info.json"""
    info = load_save_info_file()
    info["last_save_page"] = int(page)
    save_save_info_file(info)


def get_last_save_id() -> str:
    """返回上次保存的存档 id，默认空字符串"""
    info = load_save_info_file()
    try:
        v = info.get("last_save_id", "")
        return str(v) if v is not None else ""
    except Exception:
        return ""


def set_last_save_id(save_id: str) -> None:
    """写入上次保存的存档 id 到 save_info.json"""
    info = load_save_info_file()
    info["last_save_id"] = str(save_id)
    save_save_info_file(info)
