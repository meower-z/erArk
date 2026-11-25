"""
地图查看服务（world_view_service）
==================================
提供地图查看面板所需的查询与收藏读写，包括当前查看地图校正、上下级路径计算、
跨区块入口判定、地图格子分类、设施提示候选、场景名列表、收藏地点列表与收藏开关。
本模块不导入 Script.UI、Script.Settle 或 Tk 相关模块。
"""

from dataclasses import dataclass
from enum import Enum

from Script.Config import game_config
from Script.Core import constant, game_type
from Script.Design import attr_text, map_handle
from Script.Modules.domains import activity, bookmarks, scene_state


class CellKind(Enum):
    """地图格子的显示与交互类别枚举（纯文本、玩家所在、可进入地点、不可进入地点）。"""

    TEXT = "text"
    HERE = "here"
    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class MapCell:
    """地图单行中的一个文本段，包含展示文本、样式、格子类别、目标场景路径与干员占用标记。"""

    text: str
    style: str
    kind: CellKind
    scene_path: list[str]
    occupied: bool = False


@dataclass(frozen=True, slots=True)
class MapView:
    """单张地图的查看数据，包含地图名、设施提示候选、居中缩进、格子行、场景数与上下级切换标记。"""

    name: str
    tips: list[str]
    indent: int
    rows: list[list[MapCell]]
    scene_count: int
    can_go_up: bool
    can_go_down: bool


@dataclass(frozen=True, slots=True)
class SceneEntry:
    """当前地图场景名列表中的单个条目，包含场景编号、名称、完整场景路径与玩家所在标记。"""

    scene_id: str
    name: str
    scene_path: list[str]
    here: bool


@dataclass(frozen=True, slots=True)
class Bookmark:
    """收藏地点列表中的单个条目，包含场景路径、展示标签与玩家所在标记。"""

    scene_path: list[str]
    label: str
    here: bool


def settle_view(now_map: list[str], first_position: list[str]) -> list[str]:
    """
    校正当前查看的地图路径。路径不少于两段且末段为 "0" 时去掉末段。玩家离开初始位置且路径非空时返回玩家所在地图。
    Keyword arguments:
    now_map -- list[str]，当前查看的地图路径
    first_position -- list[str]，打开面板时玩家的初始场景路径
    Return arguments:
    list[str] -- 校正后的地图路径
    """
    if len(now_map) >= 2 and now_map[-1] == "0":
        now_map = now_map[:-1]
    if activity.position(0) != first_position and len(now_map):
        now_map = map_handle.get_map_for_path(activity.position(0))
    return now_map


def parent_map(now_map: list[str]) -> list[str]:
    """
    返回指定路径对应的上级地图路径。
    Keyword arguments:
    now_map -- list[str]，地图或场景路径
    Return arguments:
    list[str] -- 上级地图路径
    """
    return map_handle.get_map_for_path(now_map)


def child_map(now_map: list[str]) -> list[str]:
    """
    返回当前地图中朝向玩家所在位置的下一级地图路径。
    Keyword arguments:
    now_map -- list[str]，当前查看的地图路径
    Return arguments:
    list[str] -- 追加玩家在该地图内所属场景编号后的下级地图路径
    """
    scene_id = map_handle.get_map_scene_id_for_scene_path(
        now_map, activity.position(0)
    )
    return [*now_map, scene_id]


def opens_map(scene_path: list[str]) -> bool:
    """
    判断移动到目标场景后是否继续保持地图面板开启。目标位于另一区块且末段场景编号为 "0" 时返回 True。
    Keyword arguments:
    scene_path -- list[str]，目标场景路径
    Return arguments:
    bool -- 满足跨区块入口条件时为 True，否则为 False
    """
    return activity.position(0)[-2] != scene_path[-2] and scene_path[-1] == "0"


def _tips(map_name: str) -> list[str]:
    for facility_id, facility_data in game_config.config_facility.items():
        if facility_data.name == map_name:
            tip_ids = game_config.config_tip_data_by_facility.get(
                facility_id, []
            )
            return [game_config.config_tip_data[i].info for i in tip_ids]
    return []


def _cell(
    now_map: list[str], here: str, draw_text: game_type.MapDrawText
) -> MapCell:
    if not vars(draw_text).get("is_button"):
        return MapCell(draw_text.text, draw_text.style, CellKind.TEXT, [])
    scene_path = map_handle.get_scene_path_for_map_scene_id(
        now_map, draw_text.text
    )
    if draw_text.text == here:
        return MapCell(draw_text.text, "gold_enrod", CellKind.HERE, scene_path)
    full_scene_str = map_handle.get_map_system_path_str_for_list(scene_path)
    if map_handle.judge_scene_accessible(full_scene_str, 0, False) != "open":
        return MapCell(draw_text.text, "deep_gray", CellKind.CLOSED, scene_path)
    occupied = bool(scene_state.occupants(full_scene_str))
    style = "green" if occupied else "standard"
    return MapCell(draw_text.text, style, CellKind.OPEN, scene_path, occupied)


def map_view(now_map: list[str], width: int) -> MapView:
    """
    组装指定地图的查看数据，包括地图名、匹配设施的提示列表、居中缩进、逐行格子、场景数与上下级切换标记。
    Keyword arguments:
    now_map -- list[str]，当前查看的地图路径
    width -- int，面板绘制宽度
    Return arguments:
    MapView -- 组装后的地图查看数据
    """
    map_data = constant.map_data[
        map_handle.get_map_system_path_str_for_list(now_map)
    ]
    map_draw = map_data.map_draw
    if hasattr(map_draw, "max_width"):
        max_width = map_draw.max_width
    else:
        max_width = max((line.width for line in map_draw.draw_text), default=0)
    position = activity.position(0)
    here = map_handle.get_map_scene_id_for_scene_path(now_map, position)
    name = attr_text.get_map_path_text(now_map)
    return MapView(
        name=name,
        tips=_tips(name),
        indent=int((width - max_width) / 2),
        rows=[
            [_cell(now_map, here, draw_text) for draw_text in line.draw_list]
            for line in map_draw.draw_text
        ],
        scene_count=len(map_data.path_edge),
        can_go_up=now_map != [],
        can_go_down=map_handle.get_map_for_path(position) != now_map,
    )


def scene_entries(now_map: list[str]) -> list[SceneEntry]:
    """
    按地图 path_edge 的键顺序返回场景条目列表，无 path_edge 时返回空列表。
    玩家在该地图中的场景编号不在 path_edge 的键中时抛出 KeyError。
    Keyword arguments:
    now_map -- list[str]，当前查看的地图路径
    Return arguments:
    list[SceneEntry] -- 当前地图的场景条目列表
    """
    map_path_str = map_handle.get_map_system_path_str_for_list(now_map)
    path_edge = constant.map_data[map_path_str].path_edge
    if not path_edge:
        return []
    here = map_handle.get_map_scene_id_for_scene_path(
        now_map, activity.position(0)
    )
    if here not in path_edge:
        raise KeyError(here)
    entries = []
    for scene_id in path_edge:
        scene = map_handle.get_scene_data_for_map(map_path_str, scene_id)
        entries.append(
            SceneEntry(
                scene_id=scene_id,
                name=scene.scene_name,
                scene_path=map_handle.get_map_system_path_for_str(
                    scene.scene_path
                ),
                here=scene_id == here,
            )
        )
    return entries


def bookmark_entries() -> list[Bookmark]:
    """
    返回全部已收藏地点的条目列表，并标出与玩家当前位置一致的条目。
    Return arguments:
    list[Bookmark] -- 按收藏顺序排列的地点条目列表
    """
    position = activity.position(0)
    return [
        Bookmark(
            scene_path=place,
            label=map_handle.get_map_system_path_str_for_list(place),
            here=place == position,
        )
        for place in bookmarks.places()
    ]


def here_bookmarked() -> bool:
    """
    判断玩家当前位置是否在收藏地点列表中。
    Return arguments:
    bool -- 已收藏时为 True，否则为 False
    """
    return activity.position(0) in bookmarks.places()


def bookmark_here(collect: bool) -> None:
    """
    在收藏地点列表中添加或删除玩家当前位置。
    Keyword arguments:
    collect -- bool，为 True 时加入收藏，为 False 时取消收藏
    """
    if collect:
        bookmarks.add(activity.position(0))
    else:
        bookmarks.remove(activity.position(0))
