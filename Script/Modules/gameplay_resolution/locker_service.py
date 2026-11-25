"""
衣柜检查服务（locker_service）
==============================
提供衣柜检查所需的只读查询、偷取写入以及具名编辑 locker_shoot。
仅依赖配置、内核、领域数据、clothing 与 map_handle 以及无界面玩法模块，不导入界面、窗口或翻译接口。
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import cast

from Script.Config import game_config
from Script.Core import constant, game_type
from Script.Design import clothing, map_handle
from Script.Kernel import core
from Script.Modules.domains import activity, chara_life, dirty, identity
from Script.Modules.domains import player_collection, roster, wardrobe
from Script.Modules.gameplay_resolution import edits, ejaculation_service

PANTIES = 9
"""内裤对应的服装部位编号（9）。"""
SOCKS = 10
"""袜子对应的服装部位编号（10）。"""
COLLECTION = {PANTIES: "npc_panties_tem", SOCKS: "npc_socks_tem"}
"""可偷取服装部位编号到玩家收藏品列表映射字段名的对照表。"""
SHOOT_EDIT = "locker_shoot"
"""在衣柜衣物上射精所使用的具名编辑名称。"""


@dataclass(frozen=True, slots=True)
class Site:
    """玩家当前所处场景及其衣柜路由信息的只读记录。"""

    path: str
    """玩家当前所在场景的地图路径字符串。"""
    scene: game_type.Scene
    """当前路径对应的场景数据对象。"""
    locker_type: int
    """当前场景对应的衣柜类型编号（2 为大浴场更衣室，3 为宿舍）。"""


@dataclass(frozen=True, slots=True)
class Stolen:
    """批量偷取衣柜衣物时获得的一件衣物记录。"""

    owner_name: str
    """衣物所属干员的名称。"""
    cloth_name: str
    """所偷取衣物的模板名称。"""


@dataclass(frozen=True, slots=True)
class LockerPart:
    """衣柜内容展示中的单个非空服装部位信息。"""

    clothing_type: int
    """服装部位编号。"""
    cloth_names: tuple[str, ...]
    """该部位中在服装模板表内可查到的衣物名称元组。"""
    semen: int
    """该部位衣柜衣物当前的精液量（毫升）。"""


@dataclass(frozen=True, slots=True)
class ShootOption:
    """衣柜射精部位选项的数据记录。"""

    label: str
    """部位名称与当前该部位全部衣物名称拼接而成的标签文本。"""
    semen: int
    """该部位衣柜衣物当前的精液量（毫升）。"""


def site_here() -> Site:
    """
    读取玩家（角色 0）当前所在场景的路径、场景数据与衣柜类型。
    含 Locker_Room 标签时取更衣室衣柜（2），其余取宿舍衣柜（3）。
    博士房间无独立衣柜，同居助理的宿舍地址指向博士房间，使用宿舍衣柜。
    Return arguments:
    Site -- 当前位置的路径、场景数据与衣柜类型记录
    """
    path = map_handle.get_map_system_path_str_for_list(activity.position(0))
    scene = constant.scene_data[path]
    locker_type = clothing.get_cloth_locker_type_by_scene(scene.scene_tag)
    return Site(path, scene, locker_type)


def locker_here(npc_id: int) -> tuple[int, dict[int, list[int]]]:
    """
    按玩家当前所在场景的衣柜类型，读取指定干员对应的衣柜可变副本。
    修改返回的字典不会直接改动已保存的衣柜数据。
    Keyword arguments:
    npc_id -- 目标干员的角色编号
    Return arguments:
    tuple[int, dict[int, list[int]]] -- 衣柜类型编号与部位到衣物编号列表的副本
    """
    locker_type = site_here().locker_type
    return locker_type, clothing.get_cloth_locker_by_type(npc_id, locker_type)


def owners(site: Site) -> list[int]:
    """
    按在编名单顺序扫描当前场景衣柜中存有衣物的干员编号（跳过玩家 0）。
    场景含 Dormitory 或 Dr_room 时筛选宿舍地址匹配且宿舍衣柜非空者；
    否则含 Locker_Room 时列出全部大浴场衣柜非空者；其余场景返回空列表。
    Keyword arguments:
    site -- 当前位置记录
    Return arguments:
    list[int] -- 衣柜非空的干员角色编号列表
    """
    tags = site.scene.scene_tag
    dormitory = "Dormitory" in tags or "Dr_room" in tags
    if not dormitory and "Locker_Room" not in tags:
        return []
    slot = (
        "cloth_locker_in_dormitory" if dormitory else "cloth_locker_in_shower"
    )
    return [
        npc_id
        for npc_id in roster.active()
        if npc_id
        and (not dormitory or chara_life.dormitory(npc_id) == site.path)
        and any(
            len(getattr(wardrobe.of(npc_id), slot)[t])
            for t in game_config.config_clothing_type
        )
    ]


def has_part(npc_ids: Iterable[int], locker_type: int, part: int) -> bool:
    """
    检查给定干员列表在指定衣柜类型的某一部位中是否至少有一人存有衣物。
    部位列表非空即视为存在（包含模板表中未收录的编号）。
    Keyword arguments:
    npc_ids -- 待检查的干员角色编号可迭代对象
    locker_type -- 衣柜类型编号（2 更衣室，3 宿舍）
    part -- 服装部位编号
    Return arguments:
    bool -- 任一干员该部位非空时返回 True，否则返回 False
    """
    lockers = (
        getattr(wardrobe.of(i), clothing.CLOTH_LOCKER_ATTR_NAME[locker_type])
        for i in npc_ids
    )
    return any(len(locker[part]) for locker in lockers)


def steal_all(
    npc_ids: Iterable[int], scene_tag: list[str], part: int
) -> tuple[Stolen, ...]:
    """
    按给定顺序批量偷取多位干员在当前场景衣柜指定部位的全部衣物并写入缓冲。
    仅收集服装模板表中存在的编号并跳过未知编号，但仍清空非空部位；
    结束后统一执行一次 player_collection.extend_list_map（无收获时亦写一次）。
    Keyword arguments:
    npc_ids -- 干员角色编号可迭代对象
    scene_tag -- 当前场景标签列表
    part -- 要偷取的服装部位编号（PANTIES 或 SOCKS）
    Return arguments:
    tuple[Stolen, ...] -- 实际偷得的干员名与衣物名记录元组
    """
    locker_type = clothing.get_cloth_locker_type_by_scene(scene_tag)
    tem = game_config.config_clothing_tem
    stolen: list[tuple[int, int]] = []
    found: list[Stolen] = []
    for npc_id in npc_ids:
        name = identity.of(npc_id).name
        held = clothing.get_cloth_locker_by_type(npc_id, locker_type)[part]
        if not len(held):
            continue
        for cloth_id in held:
            if cloth_id not in tem:
                continue
            stolen.append((npc_id, cloth_id))
            found.append(Stolen(name, tem[cloth_id].name))
        clothing.empty_cloth_locker_part(npc_id, locker_type, part)
    player_collection.extend_list_map(COLLECTION[part], stolen)
    return tuple(found)


def steal_last(
    npc_id: int, locker_type: int, part: int, held: Sequence[int]
) -> str | None:
    """
    从调用方持有的部位快照中偷取最后一件衣物，写入收藏品并清空整个部位。
    快照为空时返回 None 且不写入；先查模板名称，未知编号会在写入前抛出 KeyError。
    Keyword arguments:
    npc_id -- 目标干员角色编号
    locker_type -- 衣柜类型编号（2 更衣室，3 宿舍）
    part -- 服装部位编号（PANTIES 或 SOCKS）
    held -- 调用方持有的该部位衣物编号快照序列
    Return arguments:
    str | None -- 偷得衣物的模板名称，快照为空时返回 None
    """
    if not len(held):
        return None
    cloth_id = held[-1]
    name = game_config.config_clothing_tem[cloth_id].name
    player_collection.append_list_map(COLLECTION[part], npc_id, cloth_id)
    clothing.empty_cloth_locker_part(npc_id, locker_type, part)
    return name


def filled_parts(locker: Mapping[int, Sequence[int]]) -> list[int]:
    """
    按服装类型配置表的顺序返回衣柜中存有衣物的全部部位编号。
    Keyword arguments:
    locker -- 部位编号到衣物编号序列的映射
    Return arguments:
    list[int] -- 非空服装部位编号列表
    """
    return [t for t in game_config.config_clothing_type if len(locker[t])]


def contents(
    npc_id: int, locker: Mapping[int, Sequence[int]]
) -> tuple[LockerPart, ...]:
    """
    按服装类型配置表顺序整理干员衣柜中所有非空部位的名称列表与精液量。
    模板表中不存在的衣物编号会被跳过，仅读取非空部位的当前精液量。
    Keyword arguments:
    npc_id -- 目标干员角色编号
    locker -- 部位编号到衣物编号序列的映射
    Return arguments:
    tuple[LockerPart, ...] -- 非空部位的内容记录元组
    """
    tem = game_config.config_clothing_tem
    semen = dirty.view(npc_id).cloth_locker_semen
    return tuple(
        LockerPart(
            part,
            tuple(tem[i].name for i in locker[part] if i in tem),
            semen[part][1],
        )
        for part in filled_parts(locker)
    )


def shoot_option(npc_id: int, locker_type: int, part: int) -> ShootOption:
    """
    实时读取干员衣柜指定部位的衣物与精液量，生成射精目标选项数据。
    标签由部位名、冒号与各衣物名拼接而成，遇到未知衣物编号会抛出 KeyError。
    Keyword arguments:
    npc_id -- 目标干员角色编号
    locker_type -- 衣柜类型编号（2 更衣室，3 宿舍）
    part -- 服装部位编号
    Return arguments:
    ShootOption -- 包含选项标签与当前精液量的记录
    """
    held = clothing.get_cloth_locker_by_type(npc_id, locker_type)[part]
    tem = game_config.config_clothing_tem
    label = game_config.config_clothing_type[part].name + ":"
    label += "".join(f" {tem[i].name}" for i in held)
    return ShootOption(label, dirty.view(npc_id).cloth_locker_semen[part][1])


def shoot_args(
    part: int, locker_type: int, target: int
) -> dict[str, core.JSON]:
    """
    组装具名编辑 locker_shoot 所需的参数字典。
    Keyword arguments:
    part -- 目标服装部位编号
    locker_type -- 衣柜类型编号（2 更衣室，3 宿舍）
    target -- 目标干员角色编号
    Return arguments:
    dict[str, core.JSON] -- 含 part、locker、target 三个键的参数字典
    """
    return {"part": part, "locker": locker_type, "target": target}


@edits.edit(SHOOT_EDIT)
def shoot_in_locker(who: int, args: Mapping[str, core.JSON]) -> None:
    """
    具名编辑 locker_shoot 的执行入口，在 0 分钟编辑开始时结算衣柜射精流程。
    按参数中的部位、衣柜类型与目标角色调用 ejaculation_service.ejaculation_flow。
    Keyword arguments:
    who -- 发起编辑的角色编号
    args -- 由 shoot_args 生成的编辑参数映射
    """
    ejaculation_service.ejaculation_flow(
        part_cid=int(cast(int, args["part"])),
        part_type=int(cast(int, args["locker"])),
        target_character_id=int(cast(int, args["target"])),
        draw_flag=True,
    )
