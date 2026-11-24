# -*- coding: UTF-8 -*-
"""
静态检查系统 - 位置/场景/跟随/助理/交互对象领域检查
本模块实现 PLACE 组的 26 条不变量检查（PLACE-01、PLACE-02、PLACE-04、PLACE-08 ~ PLACE-25、PLACE-27 ~ PLACE-31），
覆盖角色位置、门锁状态、移动路径、收藏地点、宿舍、交互对象、助理、跟随、装袋搬运等状态的一致性约束。

约定与踩坑说明（写在此处，避免散落在各检查函数注释里重复）：
1. `["0", "0"]` 不是哨兵值，是真实场景「罗德岛出口」，也是 `activity.position` 的默认值，
   离线角色被置为它是合法的稳定状态。
2. 新生儿写入身份表（`identity.characters`）但不进在编名单（`roster.active()`）、也不移动，
   所以面向在图角色的检查必须以 `LIVE = roster.active() | {0}` 为域，不能用全体身份表。
3. 当前地图更新会把不存在的场景内的角色迁到区域入口或["0", "0"]，位置检查仍检查迁移后的实际状态，
   不预设异常成因。
4. 全部字段访问一律使用 getattr/dict.get 加默认值防御，避免因旧存档缺字段或类型不符抛异常。
   若结构假设本身是不变量的一部分（例如字段类型或是否存在），比较结果记为不变量失败，不让检查器崩溃。
5. 本模块的全部检查项均不依赖 game_config（PLACE-20 的服务值域上界、PLACE-11 的房间档位等均用字面枚举值），
   因此无需对配置表缺失做降级处理。
"""

from __future__ import annotations

from typing import TypeGuard

from Script.Core import constant
from Script.Design import map_handle
from Script.Modules.domains import action_info, activity, education, flags
from Script.Modules.domains import growth, roster, visitor, work, modes
from Script.Modules.domains import bookmarks
from ..check_registry import CheckFailure, register_check, make_failure

from typing import TYPE_CHECKING
from Script.Modules.domains import chara_life, relations, scene_state
from Script.Modules.domains import identity

if TYPE_CHECKING:
    from Script.Core import game_type

# 列表路径 -> 场景/地图键；内部用os.sep拼接，禁止自己写'/'.join
P = map_handle.get_map_system_path_str_for_list

# PLACE-20: 助理服务键 -> CSV给出的选项下标上界（据AssistantServices.csv:6-14逐项对应）
_ASSISTANT_SERVICE_MAX = {2: 1, 3: 1, 4: 3, 5: 3, 6: 3, 7: 1, 8: 1, 9: 4, 10: 1}
# PLACE-21: 期望的助理服务键全集
_ASSISTANT_SERVICE_KEYS = {2, 3, 4, 5, 6, 7, 8, 9, 10}


def _valid_scene_path(
    value: object, scene_data: dict[str, game_type.Scene]
) -> TypeGuard[list[str]]:
    """
    参数:
        value: 待校验的路径字段原始值（期望是字符串列表）
        scene_data (dict): constant.scene_data
    返回值:
        bool: value是字符串列表且拼接后是scene_data合法键时为True，否则False（类型不符时直接返回False，不抛异常）
    功能:
        供多个"路径必须是现有场景"类检查复用的合法性判断，不接受空列表
    """
    return (
        isinstance(value, list)
        and all(isinstance(p, str) for p in value)
        and P(value) in scene_data
    )


def _valid_scene_path_or_empty(
    value: object, scene_data: dict[str, game_type.Scene]
) -> bool:
    """
    参数:
        value: 待校验的路径字段原始值（期望是字符串列表）
        scene_data (dict): constant.scene_data
    返回值:
        bool: value是字符串列表，且为空列表或拼接后是scene_data合法键时为True
    功能:
        供移动路径类字段（允许空列表代表"当前无该状态"）复用的合法性判断
    """
    return (
        isinstance(value, list)
        and all(isinstance(p, str) for p in value)
        and (not value or P(value) in scene_data)
    )


def _live_ids() -> set:
    """
    返回值:
        set: 在图角色id集合，等于 roster.active() 并入玩家id 0
    功能:
        计算"在图角色"域，供多条以LIVE为迭代范围的检查复用；npc_id_got缺失时按空集处理
    """
    return roster.active() | {0}


def _offline_flags(cid: int) -> bool:
    """
    参数:
        cid: 角色id
    返回值:
        bool: 该角色带有被装袋/外勤中/逃跑中三个离线标记之一时为True
    功能:
        供多条检查复用的"是否带明确离线标记"判定
    """
    return bool(
        flags.get(cid, "be_bagged")
        or flags.get(cid, "field_commission")
        or flags.get(cid, "escaping")
    )


@register_check("PLACE-01", "角色字典键与cid一致")
def check_character_dict_key_matches_cid() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表，身份表每个键都等于对应 Identity 的 cid 时返回空列表
    功能:
        校验身份表（identity.table()）的每个键都等于对应 Identity 的 cid 字段，
        防止场景内角色、交互目标、助理引用等按 id 索引却指向身份不一致的记录
    """
    failures = []
    character_data = identity.table()
    for dict_key, c in character_data.items():
        c_cid = getattr(c, "cid", None)
        if dict_key != c_cid:
            involved = [dict_key]
            if isinstance(c_cid, int) and c_cid != dict_key:
                involved.append(c_cid)
            failures.append(
                make_failure(
                    "PLACE-01",
                    "角色字典键与cid一致",
                    f"character_data字典键={dict_key}，但角色对象自身cid={c_cid}，name={getattr(c, 'name', '')}，"
                    f"adv={getattr(c, 'adv', None)}，position={activity.position(c.cid)}",
                    involved,
                )
            )
    return failures


@register_check("PLACE-02", "场景/地图自描述键一致")
def check_scene_and_map_self_key_consistency() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验 constant.scene_data[k].scene_path == k 且 constant.map_data[k].map_path == k。
        加载器直接以对象自身路径为键，不一致只可能来自损坏或半截迁移
    """
    failures = []
    scene_data = constant.scene_data
    for k, v in scene_data.items():
        scene_path = getattr(v, "scene_path", None)
        if k != scene_path:
            failures.append(
                make_failure(
                    "PLACE-02",
                    "场景/地图自描述键一致",
                    (
                        f"scene_data字典键={k}，但场景对象自身scene_path={scene_path}，"
                        f"scene_name={getattr(v, 'scene_name', '')}"
                    ),
                )
            )
    map_data = constant.map_data
    for k, m in map_data.items():
        map_path = getattr(m, "map_path", None)
        if k != map_path:
            failures.append(
                make_failure(
                    "PLACE-02",
                    "场景/地图自描述键一致",
                    f"map_data字典键={k}，但地图对象自身map_path={map_path}，map_name={getattr(m, 'map_name', '')}",
                )
            )
    return failures


@register_check("PLACE-04", "角色位置必须是现有场景")
def check_character_position_is_existing_scene() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验身份表（identity.characters）中每个角色（全域，不限LIVE）的position拼成的路径必须是scene_data的键。
        级别为warning，只报告角色位置未落在现有场景中的事实，不推断地图迁移原因。
        save_handle地图更新会迁移失效场景内的角色，若命中角色在LIVE中应优先处理
    """
    failures = []
    character_data = identity.table()
    scene_data = constant.scene_data
    npc_id_got: set[int] = roster.active()
    for cid, c in character_data.items():
        position = activity.position(c.cid)
        if _valid_scene_path(position, scene_data):
            continue
        behavior = activity.behavior(c.cid)
        failures.append(
            make_failure(
                "PLACE-04",
                "角色位置必须是现有场景",
                (
                    f"[warning] 角色位置未指向现有场景；角色id={cid} name={getattr(c, 'name', '')}，"
                    f"position={position}，是否在npc_id_got中={cid in npc_id_got}，"
                    f"behavior_id={getattr(behavior, 'behavior_id', None)}，"
                    f"move_src={getattr(behavior, 'move_src', None)}，"
                    f"move_target={getattr(behavior, 'move_target', None)}，"
                    f"move_final_target={getattr(behavior, 'move_final_target', None)}，"
                    f"be_bagged={flags.get(cid, 'be_bagged')}，"
                    f"field_commission={flags.get(cid, 'field_commission')}，"
                    f"escaping={flags.get(cid, 'escaping')}"
                ),
                [cid],
            )
        )
    return failures


@register_check("PLACE-08", "离线角色必须退出在编名册")
def check_scene_roster_only_registered_and_offline_must_exit() -> (
    list[CheckFailure]
):
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验带有明确离线标记（be_bagged、field_commission、escaping）的角色均不在在编名册（roster.active()）中
    """
    failures = []
    character_data = identity.table()
    npc_id_got: set[int] = roster.active()

    # (b) 带明确离线标记的角色必须已退出npc_id_got
    for cid, c in character_data.items():
        if _offline_flags(cid) and cid in npc_id_got:
            failures.append(
                make_failure(
                    "PLACE-08",
                    "离线角色必须退出在编名册",
                    (
                        f"角色id={cid} name={getattr(c, 'name', '')}带有离线标记(be_bagged="
                        f"{flags.get(cid, 'be_bagged')}，"
                        f"field_commission={flags.get(cid, 'field_commission')}，"
                        f"escaping={flags.get(cid, 'escaping')})，"
                        f"但仍在npc_id_got中；position={activity.position(c.cid)}，"
                        f"vistor={flags.get(cid, 'vistor')}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("PLACE-09", "空房间不该锁着门")
def check_locked_room_not_empty() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验 scene_state.closed() 中每个已关门场景的在场角色（scene_state.occupants(path)）均不为空。
        关门由屋内角色发起并在正常离开时解锁，空房间仍处于关门状态意味着有角色未经移动流程离场（例如在屋内直接离线）留下了未解的锁
    """
    failures = []
    for path, close_flag in scene_state.closed().items():
        sc = constant.scene_data.get(path)
        if not scene_state.occupants(path):
            failures.append(
                make_failure(
                    "PLACE-09",
                    "空房间不该锁着门",
                    (
                        f"场景{path}({getattr(sc, 'scene_name', '')})的close_flag="
                        f"{close_flag}非0，"
                        f"但场景里没有角色，close_type={getattr(sc, 'close_type', None)}，"
                        f"scene_tag={getattr(sc, 'scene_tag', None)}，"
                        f"room_area={getattr(sc, 'room_area', None)}"
                    ),
                )
            )
    return failures


@register_check("PLACE-10", "门类型与门状态枚举合法")
def check_door_type_and_flag_enum_valid() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验close_type ∈ {0,1,2}（无门/普通门/隔间门），且close_flag只能是0或本场景的close_type。
        取close_flag in {0, close_type}而非close_flag<=close_type，避免放过close_type==2且close_flag==1的错位
    """
    failures = []
    for sc in constant.scene_data.values():
        close_type = getattr(sc, "close_type", 0)
        close_flag = scene_state.close_flag(sc.scene_path)
        if close_type not in (0, 1, 2) or close_flag not in (0, close_type):
            failures.append(
                make_failure(
                    "PLACE-10",
                    "门类型与门状态枚举合法",
                    (
                        f"场景{getattr(sc, 'scene_path', '?')}("
                        f"{getattr(sc, 'scene_name', '')})的close_type="
                        f"{close_type}，"
                        f"close_flag={close_flag}不满足close_type∈{{0,1,2}}且close_flag∈{{0,close_type}}；"
                        f"room_area={getattr(sc, 'room_area', None)}，"
                        f"occupants={scene_state.occupants(sc.scene_path)}"
                    ),
                )
            )
    return failures


@register_check("PLACE-11", "房间容量档位枚举合法")
def check_room_area_enum_valid() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验room_area只能是0/1/2/3（对应满员判定的10/50/100/9999四档）。不检查"人数<=容量"——
        容量只是常规寻路准入策略，玩家豁免、character_move_scene与handle_chara_on_line均不查容量，合法越界可达
    """
    failures = []
    scene_data = constant.scene_data
    for sc in scene_data.values():
        room_area = getattr(sc, "room_area", 0)
        if room_area not in (0, 1, 2, 3):
            failures.append(
                make_failure(
                    "PLACE-11",
                    "房间容量档位枚举合法",
                    (
                        f"场景{getattr(sc, 'scene_path', '?')}({getattr(sc, 'scene_name', '')})的room_area={room_area}"
                        f"不在合法枚举{{0,1,2,3}}中；"
                        f"当前人数={len(scene_state.occupants(sc.scene_path))}"
                    ),
                )
            )
    return failures


@register_check("PLACE-12", "移动路径字段必须是现有场景")
def check_move_path_fields_are_existing_scenes() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验 behavior.move_src/move_target/move_final_target 只要非空，就必须拼成 constant.scene_data 的合法键。
        空列表合法（寻路失败时会先写behavior_id=move再写空move_target）。级别为warning：
        唯一已知命中源与PLACE-04同因（老存档地图更新后场景键被删却未迁移角色）
    """
    failures = []
    character_data = identity.table()
    scene_data = constant.scene_data
    for cid, c in character_data.items():
        behavior = activity.behavior(cid)
        for field_name in ("move_src", "move_target", "move_final_target"):
            value = getattr(behavior, field_name, [])
            if _valid_scene_path_or_empty(value, scene_data):
                continue
            failures.append(
                make_failure(
                    "PLACE-12",
                    "移动路径字段必须是现有场景",
                    (
                        f"[warning] 角色id={cid} name={getattr(c, 'name', '')}的behavior.{field_name}={value}既非空列表"
                        f"也不是合法场景路径；"
                        f"position={activity.position(c.cid)}，"
                        f"behavior_id={getattr(behavior, 'behavior_id', None)}"
                        f"，"
                        f"move_src={getattr(behavior, 'move_src', None)}，"
                        f"move_target={getattr(behavior, 'move_target', None)}，"
                        f"move_final_target={getattr(behavior, 'move_final_target', None)}，"
                        f"start_time={getattr(behavior, 'start_time', None)}，"
                        f"duration={getattr(behavior, 'duration', None)}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("PLACE-13", "移动历史长度与内容合法")
def check_past_move_position_list_valid() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验action_info.past_move_position_list最多10条，每条都必须是合法场景路径。该字段只在标准移动入口
        追加、超10立即pop(0)，长度超限一定是绕过character_move_scene的写入
    """
    failures = []
    character_data = identity.table()
    scene_data = constant.scene_data
    for cid, c in character_data.items():
        past_list = action_info.get(cid, "past_move_position_list")
        bad_items = [
            p for p in past_list if not _valid_scene_path(p, scene_data)
        ]
        if len(past_list) > 10 or bad_items:
            failures.append(
                make_failure(
                    "PLACE-13",
                    "移动历史长度与内容合法",
                    (
                        f"角色id={cid} name={getattr(c, 'name', '')}的action_info.past_move_position_list长度="
                        f"{len(past_list)}"
                        f"（应≤10），其中非法项={bad_items}；position={activity.position(c.cid)}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("PLACE-14", "收藏地点必须是合法场景")
def check_collect_position_list_valid() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验收藏地点（map.bookmarks）的每一项都是场景路径列表且存在于 constant.scene_data，
        否则地图收藏面板点一下就会跳进不存在的场景
    """
    failures: list[CheckFailure] = []
    scene_data = constant.scene_data
    collect_list = bookmarks.places()
    bad_items = [
        pos for pos in collect_list if not _valid_scene_path(pos, scene_data)
    ]
    if bad_items:
        failures.append(
            make_failure(
                "PLACE-14",
                "收藏地点必须是合法场景",
                f"map.bookmarks中存在非法场景路径: {bad_items}；完整列表长度={len(collect_list)}，"
                f"玩家当前position={activity.position(0)}",
            )
        )
    return failures


@register_check("PLACE-15", "宿舍字段必须是合法场景或哨兵值")
def check_dormitory_field_valid_or_sentinel() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验 LIVE 域内角色的 dormitory（场景路径字符串）只允许是 constant.scene_data 的键，或未分配哨兵 ""/"无"。
        两个哨兵都必须放行：宿舍管理允许在线角色暂时落在""空白位，初始化与访客分房合法使用"无"
    """
    failures = []
    character_data = identity.table()
    scene_data = constant.scene_data
    for cid in _live_ids():
        c = character_data.get(cid)
        if c is None:
            continue
        dormitory = chara_life.dormitory(cid)
        if dormitory in ("", "无") or dormitory in scene_data:
            continue
        failures.append(
            make_failure(
                "PLACE-15",
                "宿舍字段必须是合法场景或哨兵值",
                (
                    f"角色id={cid} name={getattr(c, 'name', '')}的dormitory={dormitory!r}既不是合法场景键也不是哨兵值('"
                    f"' / '无')；"
                    f"permanent_dormitory={chara_life.permanent_dormitory(cid)!r}，"
                    f"position={activity.position(c.cid)}，"
                    f"work_type={chara_life.work_type(cid)}，是否为访客={visitor.is_visitor(cid)}"
                ),
                [cid],
            )
        )
    return failures


@register_check("PLACE-16", "交互对象id必须存在")
def check_target_character_id_exists() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验每个角色的交互对象id（activity.target）必须存在于身份表（identity.characters）。
        自指（==cid）是"无交互对象"的默认值，对NPC而言==0表示目标是玩家，两者均合法
    """
    failures = []
    character_data = identity.table()
    for cid, c in character_data.items():
        target_id = activity.target(c.cid)
        if target_id not in character_data:
            behavior = activity.behavior(c.cid)
            failures.append(
                make_failure(
                    "PLACE-16",
                    "交互对象id必须存在",
                    (
                        f"角色id={cid} name={getattr(c, 'name', '')}的target_character_id={target_id}在character_data中"
                        f"不存在"
                        f"（自指=无交互对象、0=以玩家为交互对象均合法，此处既非自指也非现存id）；"
                        f"behavior_id={getattr(behavior, 'behavior_id', None)}，is_h={flags.get(cid, 'is_h')}，"
                        f"position={activity.position(c.cid)}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("PLACE-17", "H状态角色的交互对象必须同场")
def check_h_state_target_same_scene() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验LIVE域内处于sp_flag.is_h的角色，其交互对象必须存在且与自己position相同。不放宽到
        "所有角色的持久目标都必须同场"——引擎明确容忍普通目标离场，从不重置交互对象。
        级别为warning：H结束到NPC AI清理is_h之间存在一拍误报窗口
    """
    failures = []
    character_data = identity.table()
    pl = character_data.get(0)
    bagging_id = (
        flags.get(pl.cid, "bagging_chara_id") if pl is not None else None
    )
    for cid in _live_ids():
        c = character_data.get(cid)
        if c is None:
            continue
        if not flags.get(cid, "is_h"):
            continue
        target_id = activity.target(c.cid)
        target = character_data.get(target_id)
        if target is not None and activity.position(
            target.cid
        ) == activity.position(c.cid):
            continue
        behavior = activity.behavior(c.cid)
        target_desc = (
            f"（目标name={getattr(target, 'name', '')}，target.position={activity.position(target.cid)}）"
            if target is not None
            else "，目标在character_data中不存在"
        )
        failures.append(
            make_failure(
                "PLACE-17",
                "H状态角色的交互对象必须同场",
                (
                    f"[warning] 角色id={cid} name={getattr(c, 'name', '')}处于sp_flag.is_h=True，"
                    f"其target_character_id={target_id}"
                    f"{target_desc}，自身position={activity.position(c.cid)}；"
                    f"behavior_id={getattr(behavior, 'behavior_id', None)}，"
                    f"unconscious_h={flags.get(cid, 'unconscious_h')}，pl.sp_flag.bagging_chara_id={bagging_id}"
                ),
                [cid] + ([target_id] if target is not None else []),
            )
        )
    return failures


@register_check("PLACE-18", "助理字段只属于玩家")
def check_assistant_field_only_for_player() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验只有id 0可以有非零assistant_character_id；NPC上非零都是脏数据（面板与前提只读玩家那一份，
        NPC上的值永远失效却会随存档迁移传播）
    """
    failures = []
    character_data = identity.table()
    pl = character_data.get(0)
    pl_aid = relations.assistant_character_id(0) if pl is not None else None
    for cid, c in character_data.items():
        if cid == 0:
            continue
        aid = relations.assistant_character_id(cid)
        if aid != 0:
            failures.append(
                make_failure(
                    "PLACE-18",
                    "助理字段只属于玩家",
                    (
                        f"非玩家角色id={cid} name={getattr(c, 'name', '')}的assistant_character_id={aid}非0（该字段仅玩"
                        f"家使用）；"
                        f"玩家自身assistant_character_id={pl_aid}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("PLACE-19", "当前助理必须有效且在线")
def check_current_assistant_valid_and_online() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验玩家助理id（relations.assistant_character_id(0)）非0时，该id必须存在于身份表
        （identity.characters）、在编名单（roster.active()）中、未死亡且不带任何离线标记。
        先查存在再读取活动状态，避免id无效时报错
    """
    failures: list[CheckFailure] = []
    character_data = identity.table()
    npc_id_got: set[int] = roster.active()
    pl = character_data.get(0)
    if pl is None:
        return failures
    aid = relations.assistant_character_id(0)
    if aid == 0:
        return failures
    assistant = character_data.get(aid)
    if assistant is None:
        failures.append(
            make_failure(
                "PLACE-19",
                "当前助理必须有效且在线",
                (
                    f"玩家assistant_character_id={aid}指向的角色不在character_data中；"
                    f"玩家position={activity.position(pl.cid)}"
                ),
                [aid],
            )
        )
        return failures
    in_got = aid in npc_id_got
    dead = activity.dead(assistant.cid)
    offline = _offline_flags(aid)
    if not (in_got and not dead and not offline):
        failures.append(
            make_failure(
                "PLACE-19",
                "当前助理必须有效且在线",
                (
                    f"玩家当前助理id={aid} name={getattr(assistant, 'name', '')} "
                    f"position={activity.position(assistant.cid)}，"
                    f"是否在npc_id_got中={in_got}，dead={dead}，be_bagged={flags.get(aid, 'be_bagged')}，"
                    f"field_commission={flags.get(aid, 'field_commission')}，"
                    f"escaping={flags.get(aid, 'escaping')}，"
                    f"玩家position={activity.position(pl.cid)}"
                ),
                [aid],
            )
        )
    return failures


@register_check("PLACE-20", "助理服务值域合法")
def check_assistant_services_value_range() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验assistant_services中每个已知服务键的值不得超过CSV给出的选项下标上界，且不得为负。
        不排除bool值——服务2的写入点本身就是Python bool，True==1语义有效，消费端做的都是真值判断
    """
    failures = []
    character_data = identity.table()
    pl = character_data.get(0)
    pl_aid = relations.assistant_character_id(0) if pl is not None else None
    for cid, c in character_data.items():
        services = relations.assistant_services(cid)
        out_of_range = {
            k: v
            for k, v in services.items()
            if k in _ASSISTANT_SERVICE_MAX
            and not (0 <= v <= _ASSISTANT_SERVICE_MAX[k])
        }
        if out_of_range:
            failures.append(
                make_failure(
                    "PLACE-20",
                    "助理服务值域合法",
                    (
                        f"角色id={cid} name={getattr(c, 'name', '')}的assistant_services中以下键值超出合法范围: "
                        f"{out_of_range}"
                        f"（上界表{_ASSISTANT_SERVICE_MAX}），完整assistant_services={services}，"
                        f"是否为当前助理={cid == pl_aid}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("PLACE-21", "助理服务键集完整")
def check_assistant_services_key_set_complete() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验每个角色的assistant_services应恰好包含服务键2..10。级别为warning：assistant_panel.py与
        handle_premise_assistant.py均用setdefault兜底缺键，老存档迁移可能暂时缺键
    """
    failures = []
    character_data = identity.table()
    for cid, c in character_data.items():
        services = relations.assistant_services(cid)
        keys = set(services.keys())
        if keys != _ASSISTANT_SERVICE_KEYS:
            failures.append(
                make_failure(
                    "PLACE-21",
                    "助理服务键集完整",
                    (
                        f"[warning] 角色id={cid} name={getattr(c, 'name', '')}的assistant_services键集合与期望不符："
                        f"缺失键={sorted(_ASSISTANT_SERVICE_KEYS - keys)}，"
                        f"多余键={sorted(keys - _ASSISTANT_SERVICE_KEYS)}，"
                        f"完整assistant_services={services}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("PLACE-22", "同居服务与宿舍一致")
def check_cohabitation_service_matches_dormitory() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验当前助理开启服务7（同居）时，其宿舍应为"中枢/博士房间"。级别为warning。判定范围有两处限制：
        当前助理同时任命为监狱长(work_type==191)是合法状态，予以豁免；不要求permanent_dormitory非空
        （chara_life.dormitory（键life.dormitory）初值即""，该子句守不住任何真实约束）
    """
    failures: list[CheckFailure] = []
    character_data = identity.table()
    pl = character_data.get(0)
    if pl is None:
        return failures
    aid = relations.assistant_character_id(0)
    if aid == 0:
        return failures
    assistant = character_data.get(aid)
    if assistant is None:
        return failures  # 助理id本身无效由PLACE-19负责报告，本条不重复报
    services = relations.assistant_services(aid)
    if services.get(7, 0) != 1:
        return failures
    if chara_life.work_type(aid) == 191:
        return failures  # 豁免监狱长：任命为监狱长会改宿舍但不清同居服务位，是合法且持久的状态
    expected_dormitory = P(["中枢", "博士房间"])
    dormitory = chara_life.dormitory(aid)
    if dormitory != expected_dormitory:
        failures.append(
            make_failure(
                "PLACE-22",
                "同居服务与宿舍一致",
                (
                    f"[warning] 当前助理id={aid} name={getattr(assistant, 'name', '')}已开启同居服务(assistant_services"
                    f"[7]=1)，"
                    f"但dormitory={dormitory}（期望{expected_dormitory}），"
                    f"permanent_dormitory={chara_life.permanent_dormitory(aid)}，"
                    f"work_type={chara_life.work_type(aid)}，"
                    f"work.warden()={work.warden()}"
                ),
                [aid],
            )
        )
    return failures


@register_check("PLACE-23", "跟随模式取值合法")
def check_follow_mode_value_valid() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验sp_flag.is_follow只能取0-4。debug_panel.py可写任意值，调试会话下本条必噪，故modes.debug()
        为True时直接跳过整条检查
    """
    if bool(modes.debug()):
        return []
    failures = []
    character_data = identity.table()
    pl = character_data.get(0)
    pl_aid = relations.assistant_character_id(0) if pl is not None else 0
    for cid, c in character_data.items():
        is_follow = flags.get(cid, "is_follow")
        if is_follow not in (0, 1, 2, 3, 4):
            behavior = activity.behavior(c.cid)
            services = relations.assistant_services(cid)
            failures.append(
                make_failure(
                    "PLACE-23",
                    "跟随模式取值合法",
                    (
                        f"角色id={cid} name={getattr(c, 'name', '')}的sp_flag.is_follow={is_follow}超出合法范围[0,4]；"
                        f"是否为当前助理={cid == pl_aid}，assistant_services[2]={services.get(2)}，"
                        f"behavior_id={getattr(behavior, 'behavior_id', None)}"
                    ),
                    [cid],
                )
            )
    return failures


@register_check("PLACE-24", "玩家不跟随自己")
def check_player_not_following_self() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验id 0的sp_flag.is_follow必须为0。跟随语义是NPC跟随玩家，玩家带上跟随位没有任何合法产生路径
        （唯一能写坏的是debug面板，这正是本条想抓的对象），modes.debug()为True时将消息降级为warning
    """
    failures: list[CheckFailure] = []
    character_data = identity.table()
    pl = character_data.get(0)
    if pl is None:
        return failures
    is_follow = flags.get(0, "is_follow")
    if is_follow != 0:
        debug_mode = bool(modes.debug())
        prefix = (
            "[warning] （调试模式下降级，疑似debug面板写入）"
            if debug_mode
            else ""
        )
        behavior = activity.behavior(pl.cid)
        failures.append(
            make_failure(
                "PLACE-24",
                "玩家不跟随自己",
                (
                    f"{prefix}玩家(id 0)的sp_flag.is_follow={is_follow}，应恒为0；"
                    f"position={activity.position(pl.cid)}，"
                    f"behavior_id={getattr(behavior, 'behavior_id', None)}，"
                    f"move_target={getattr(behavior, 'move_target', None)}，"
                    f"debug_mode={debug_mode}"
                ),
                [0],
            )
        )
    return failures


@register_check("PLACE-25", "跟随者必须在册、活着、在线")
def check_follower_must_be_registered_alive_online() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验sp_flag.is_follow != 0的角色必须是非玩家、在npc_id_got中、未死亡、且不带离线标记。级别为warning：
        访客到期离开的手写下线流程不清is_follow，"一键全跟随"又不过滤访客，可组合出持久的遗留状态，
        属遗留垃圾而非崩溃源（角色若回归，handle_chara_on_line会整体重建sp_flag）
    """
    failures = []
    character_data = identity.table()
    npc_id_got: set[int] = roster.active()
    for cid, c in character_data.items():
        is_follow = flags.get(cid, "is_follow")
        if is_follow == 0:
            continue
        dead = activity.dead(c.cid)
        offline = _offline_flags(cid)
        in_got = cid in npc_id_got
        if cid != 0 and in_got and not dead and not offline:
            continue
        vistor = flags.get(cid, "vistor")
        known_bug_note = (
            "；已知缺陷：访客到期离开(visitor_service.visitor_leave)未清is_follow，若vistor==2大概率是该已知路径"
            if vistor == 2
            else ""
        )
        failures.append(
            make_failure(
                "PLACE-25",
                "跟随者必须在册、活着、在线",
                (
                    f"[warning] 角色id={cid} name={getattr(c, 'name', '')}的sp_flag.is_follow={is_follow}非0，"
                    f"但是否为玩家自身={cid == 0}，"
                    f"是否在npc_id_got中={in_got}，dead={dead}，position={activity.position(c.cid)}，"
                    f"be_bagged={flags.get(cid, 'be_bagged')}，"
                    f"field_commission={flags.get(cid, 'field_commission')}，"
                    f"escaping={flags.get(cid, 'escaping')}，vistor={vistor}，"
                    f"是否在访客名册中={visitor.is_visitor(cid)}"
                    f"{known_bug_note}"
                ),
                [cid],
            )
        )
    return failures


@register_check("PLACE-27", "装袋搬运双向一致")
def check_bagging_consistency() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验"装袋搬走"状态的双向一致性：(1) 只有玩家(id 0)可以持有非零bagging_chara_id；
        (2) 全体be_bagged=True的角色集合必须恰好等于{玩家当前装袋的角色id}（未装袋时为空集）；
        (3) 被装袋角色必须已完成离线三件套：退出 roster.active()、position 归为 ["0", "0"]、不在任何场景的在场角色中。
        "position==['0','0']"单独不具区分力（那是真实场景"罗德岛出口"），与"不在任何场景的在场角色中"合取后才有效
    """
    failures: list[CheckFailure] = []
    character_data = identity.table()
    scene_data = constant.scene_data
    npc_id_got: set[int] = roster.active()
    pl = character_data.get(0)
    if pl is None:
        return failures

    # (1) 非玩家角色不得持有bagging_chara_id
    for cid, c in character_data.items():
        if cid == 0:
            continue
        bagging_id = flags.get(cid, "bagging_chara_id")
        if bagging_id != 0:
            failures.append(
                make_failure(
                    "PLACE-27",
                    "装袋搬运双向一致",
                    (
                        f"非玩家角色id={cid} name={getattr(c, 'name', '')}的sp_flag.bagging_chara_id={bagging_id}非0，"
                        f"只有玩家可持有该字段"
                    ),
                    [cid],
                )
            )

    pl_bagging_id = flags.get(0, "bagging_chara_id") or 0

    # (2) be_bagged集合必须恰好等于{玩家当前装袋对象}
    be_bagged_ids = {
        cid
        for cid, c in character_data.items()
        if flags.get(c.cid, "be_bagged")
    }
    expected_ids = {pl_bagging_id} if pl_bagging_id else set()
    if be_bagged_ids != expected_ids:
        failures.append(
            make_failure(
                "PLACE-27",
                "装袋搬运双向一致",
                (
                    f"玩家sp_flag.bagging_chara_id={pl_bagging_id}，"
                    f"理论被搬者集合应为{sorted(expected_ids)}，"
                    f"但实际be_bagged=True的角色"
                    f"集合为{sorted(be_bagged_ids)}（name: "
                    f"{[(cid, getattr(character_data.get(cid), 'name', '?')) for cid in sorted(be_bagged_ids)]}）"
                ),
                sorted(be_bagged_ids | expected_ids),
            )
        )

    # (3) 被装袋角色必须已完成离线三件套
    if pl_bagging_id:
        bid = pl_bagging_id
        target = character_data.get(bid)
        if target is None:
            failures.append(
                make_failure(
                    "PLACE-27",
                    "装袋搬运双向一致",
                    (
                        f"玩家sp_flag.bagging_chara_id={bid}指向的角色不在character_data中，"
                        f"pl.position={activity.position(pl.cid)}"
                    ),
                    [bid],
                )
            )
        else:
            be_bagged = flags.get(bid, "be_bagged")
            in_got = bid in npc_id_got
            position = activity.position(target.cid)
            scenes_with_bid = [
                p for p in scene_data if bid in scene_state.occupants(p)
            ]
            if not (
                be_bagged
                and not in_got
                and position == ["0", "0"]
                and not scenes_with_bid
            ):
                failures.append(
                    make_failure(
                        "PLACE-27",
                        "装袋搬运双向一致",
                        (
                            f"被装袋角色id={bid} name={getattr(target, 'name', '')}未完成离线三件套："
                            f"be_bagged={be_bagged}，"
                            f"是否仍在npc_id_got中={in_got}，position={position}，仍出现在场景={scenes_with_bid}"
                            f"（已知隐患：Script/Settle/default.py的handle_t_be_bagged效果id "
                            f"451在Behavior_Effect.csv中无引用，是死代码）"
                        ),
                        [bid],
                    )
                )
    return failures


@register_check("PLACE-28", "登记宿舍不得停留在与当前宿舍相同的值")
def check_permanent_dormitory_not_equal_to_dormitory() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验LIVE域内角色的「登记宿舍」（角色键 life.permanent_dormitory）非空时不等于当前宿舍（life.dormitory）。
        角色临时住进客房、监牢、博士房间、舍管房或关押区休息室期间，登记宿舍记着原来的普通宿舍。
        角色住在普通宿舍时登记宿舍为空。
        离开特殊房间时，restore_character_dormitory 清空登记宿舍。登记宿舍等于当前宿舍，说明离开时没有清空。
        级别为warning
    """
    failures = []
    character_data = identity.table()
    for cid in _live_ids():
        c = character_data.get(cid)
        if c is None:
            continue
        permanent = chara_life.permanent_dormitory(cid)
        dormitory = chara_life.dormitory(cid)
        if permanent != "" and permanent == dormitory:
            failures.append(
                make_failure(
                    "PLACE-28",
                    "登记宿舍不得停留在与当前宿舍相同的值",
                    f"[warning] 角色id={cid} name={getattr(c, 'name', '')}的登记宿舍(permanent_dormitory)"
                    f"={permanent!r}与当前dormitory相同，说明离开特殊房间时的恢复点未清空该字段；"
                    f"position={activity.position(c.cid)}",
                    [cid],
                )
            )
    return failures


@register_check("PLACE-29", "登记宿舍非空时必须是合法的普通宿舍房间")
def check_permanent_dormitory_is_valid_normal_room() -> list[CheckFailure]:
    """
    参数: 无
    返回值: List[CheckFailure]: 失败记录列表
    功能:
        校验LIVE域内角色的「登记宿舍」（角色键 life.permanent_dormitory）非空且不等于当前宿舍时，是一间开放的普通宿舍。
        这是与PLACE-28互斥的另一种失败模式。
        开放的普通宿舍取自 Script/System/Dormitory_System/common.py 的 get_open_dormitory_room_occupancy()，
        函数级导入以避开加载顺序问题。特殊房间（客房、监牢、博士房间、舍管房、关押区休息室）不算普通宿舍。
        register_permanent_dormitory() 写入的登记宿舍是角色当时住的开放普通宿舍。
        写入之后那间宿舍关闭时，这条也会报（占用表只统计当前开放的房间），这是可接受的噪声。级别为warning
    """
    failures = []
    character_data = identity.table()
    from Script.System.Dormitory_System import common as dormitory_common

    normal_rooms = set(dormitory_common.get_open_dormitory_room_occupancy())
    for cid in _live_ids():
        c = character_data.get(cid)
        if c is None:
            continue
        permanent = chara_life.permanent_dormitory(cid)
        dormitory = chara_life.dormitory(cid)
        if permanent == "" or permanent == dormitory:
            continue
        if permanent not in normal_rooms:
            failures.append(
                make_failure(
                    "PLACE-29",
                    "登记宿舍非空时必须是合法的普通宿舍房间",
                    f"[warning] 角色id={cid} name={getattr(c, 'name', '')}的登记宿舍(permanent_dormitory)"
                    f"={permanent!r}不在开放普通宿舍房间池中(len={len(normal_rooms)})，当前dormitory={dormitory!r}，"
                    f"position={activity.position(c.cid)}",
                    [cid],
                )
            )
    return failures


# 教育场景只校验静态标签和名称，不以设施开放状态筛选。
def _education_tags() -> set[str]:
    """参数: 无；返回值: set[str]；功能: 从教育常量取班级教室与体育场地标签，不硬编码房间数量。"""
    from Script.System.Education_System import education_constant

    return set(education_constant.CLASSROOM_TAG_BY_COURSE_TYPE.values()) | {
        data[0] for data in education_constant.PE_PLACE_DATA.values()
    }


def _has_scene_tag(scene: object, tag: str) -> bool:
    """参数: scene(场景对象)、tag(str)；返回值: bool；功能: 防御式读取场景标签列表。"""
    tags = getattr(scene, "scene_tag", None)
    return isinstance(tags, (list, tuple, set)) and tag in tags


@register_check("PLACE-30", "教室标签索引")
def check_place_30() -> list[CheckFailure]:
    """参数: 无；返回值: List[CheckFailure]；功能: 教育标签索引内路径须存在且带该标签，场景带标签时也须出现在索引中。"""
    from Script.Core import constant

    scenes = constant.scene_data
    places = getattr(constant, "place_data", None)
    if not isinstance(places, dict):
        return []
    failures = []
    for tag in sorted(_education_tags()):
        paths = places.get(tag, [])
        if not isinstance(paths, (list, tuple, set)):
            continue
        for index, path in enumerate(paths):
            if (
                not isinstance(path, str)
                or path not in scenes
                or not _has_scene_tag(scenes[path], tag)
            ):
                failures.append(
                    make_failure(
                        "PLACE-30",
                        "教室标签索引",
                        f"cid=None key=place_data[{tag!r}][{index}] value={path!r}；路径不存在或场景未带{tag!r}标签",
                        [],
                    )
                )
        for path, scene in scenes.items():
            if _has_scene_tag(scene, tag) and path not in paths:
                failures.append(
                    make_failure(
                        "PLACE-30",
                        "教室标签索引",
                        (
                            f"cid=None key=scene_data[{path!r}].scene_tag value={getattr(scene, 'scene_tag', None)!r}；"
                            f"place_data[{tag!r}]漏列此路径"
                        ),
                        [],
                    )
                )
    return failures


def _check_room_name(
    scenes: dict[str, game_type.Scene],
    tags: set[str],
    name: object,
    cid: int | None,
    key: str,
    failures: list[CheckFailure],
) -> None:
    """参数: scenes(dict)、tags(标签集合)、name(场景名)、cid(角色id或None)、key(str)、failures(list)；返回值: None；
    功能: 检查一次名称引用是否唯一解析。"""
    paths = [
        path
        for path, scene in scenes.items()
        if isinstance(name, str)
        and getattr(scene, "scene_name", None) == name
        and any(_has_scene_tag(scene, tag) for tag in tags)
    ]
    if len(paths) != 1:
        failures.append(
            make_failure(
                "PLACE-31",
                "教室名称无歧义",
                f"cid={cid!r} key={key} value={name!r}；匹配场景数={len(paths)}，路径={paths!r}，标签={sorted(tags)!r}",
                [cid] if type(cid) is int else [],
            )
        )


@register_check("PLACE-31", "教室名称无歧义")
def check_place_31() -> list[CheckFailure]:
    """参数: 无；返回值: List[CheckFailure]；
    功能: 全局课表与个人0–3课型的场景名须唯一对应匹配教育标签的场景，未开放或关闭不报错。"""
    from Script.System.Education_System import education_constant

    scenes = constant.scene_data
    failures: list[CheckFailure] = []
    classroom_tags = set(
        education_constant.CLASSROOM_TAG_BY_COURSE_TYPE.values()
    )
    schedule = education.class_schedule()
    for name in schedule:
        _check_room_name(
            scenes,
            classroom_tags,
            name,
            None,
            f"base.class_schedule[{name!r}]",
            failures,
        )
    for cid in identity.ids():
        selected = getattr(growth.of(cid), "selected_course", None)
        if not isinstance(selected, dict):
            continue
        for day, periods in selected.items():
            if not isinstance(periods, dict):
                continue
            for period, cell in periods.items():
                if not isinstance(cell, list) or len(cell) != 2:
                    continue
                course_type, target = cell
                if (
                    type(course_type) is not int
                    or course_type not in (0, 1, 2, 3)
                    or not isinstance(target, str)
                ):
                    continue
                if course_type == education_constant.COURSE_TYPE_PE:
                    data = education_constant.PE_PLACE_DATA.get(target)
                    tags = {data[0]} if data is not None else set()
                else:
                    tags = {
                        education_constant.CLASSROOM_TAG_BY_COURSE_TYPE[
                            course_type
                        ]
                    }
                _check_room_name(
                    scenes,
                    tags,
                    target,
                    cid,
                    f"selected_course[{day!r}][{period!r}]",
                    failures,
                )
    return failures
