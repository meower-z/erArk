"""地图查看面板模块，提供地图界面绘制、快捷移动菜单、场景名列表与收藏地点面板的交互展示。"""

from collections.abc import Callable
from types import FunctionType
from Script.UI.Moudle import draw, panel, view
from Script.Core import (
    get_text,
    flow_handle,
    value_handle,
    text_handle,
    constant,
    py_cmd,
)
from Script.Design import character_move
from Script.Config import game_config
from Script.Modules.tk_ui import player_pick
from Script.Modules.domains import activity
from Script.Modules.gameplay_resolution import world_view_service as svc

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1


def move_now(scene_path: list[str]) -> None:
    """
    清屏并控制玩家角色移动到指定场景。
    Keyword arguments:
    scene_path -- list[str]，目标场景路径
    """
    py_cmd.clr_cmd()
    line_feed.draw()
    flow_handle.set_skip_pauses(True)
    character_move.own_charcter_move(scene_path)


def _draw_grid(draw_list: list, per_row: int, width: int) -> None:
    """
    按每行最多 per_row 个对象分组，按最长行均分宽度后逐行绘制。
    Keyword arguments:
    draw_list -- list，待绘制的对象列表
    per_row -- int，每行最多绘制个数
    width -- int，面板绘制宽度
    """
    draw_group = value_handle.list_of_groups(draw_list, per_row)
    now_width = width / max(len(group) for group in draw_group)
    for now_draw_list in draw_group:
        for now_draw in now_draw_list:
            now_draw.width = now_width
            now_draw.draw()
        line_feed.draw()


class SeeMapPanel:
    """
    用于查看当前地图界面面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_map: list[str] = svc.parent_map(activity.position(0))
        """ 当前查看的地图坐标 """

    def draw(self) -> None:
        """绘制对象"""
        move_menu_panel_data: dict[
            int, MapSceneNameDraw | CollectionSceneNamePanel
        ] = {
            0: MapSceneNameDraw(self.now_map, self.width),
            1: CollectionSceneNamePanel(self.now_map, self.width),
        }
        move_menu_panel = MoveMenuPanel(self.width)
        first_position = activity.position(0)
        while 1:
            line_feed.draw()
            if view.now_panel_id != constant.Panel.SEE_MAP:
                break
            self.now_map = svc.settle_view(self.now_map, first_position)
            map_view = svc.map_view(self.now_map, self.width)
            title_draw = draw.TitleLineDraw(
                _("当前区块:") + _(map_view.name), self.width
            )
            title_draw.draw()
            if map_view.tips:
                tip_draw = draw.CenterDraw()
                tip_draw.text = "○" + player_pick.ui_random.choice(
                    map_view.tips
                )
                tip_draw.width = self.width
                line_feed.draw()
                tip_draw.draw()
                line_feed.draw()
                line_feed.draw()
            return_list = self.draw_rows(map_view)
            now_index = map_view.scene_count
            move_menu_panel.update()
            move_menu_panel.draw()
            return_list.extend(move_menu_panel.return_list)
            if move_menu_panel.now_type in move_menu_panel_data:
                now_move_menu = move_menu_panel_data[move_menu_panel.now_type]
                now_move_menu.update(self.now_map)
                now_move_menu.draw()
                now_index = now_move_menu.end_index + 1
                return_list.extend(now_move_menu.return_list)
            line = draw.LineDraw("=", self.width)
            line.draw()
            if map_view.can_go_up:
                now_index = self.draw_button(
                    now_index, _("查看上级地图"), return_list, self.up_map
                )
            else:
                now_draw = draw.NormalDraw()
                now_draw.text = " " * int(self.width / 4)
                now_draw.width = self.width / 4
                now_draw.draw()
            back_text = str(now_index)
            now_index = self.draw_button(now_index, _("返回"), return_list)
            if map_view.can_go_down:
                now_index = self.draw_button(
                    now_index, _("查看下级地图"), return_list, self.down_map
                )
            self.draw_button(
                now_index, _("干员位置一览"), return_list, self.all_npc_position
            )
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            py_cmd.clr_cmd()
            if yrn == back_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def draw_rows(self, map_view: svc.MapView) -> list[str]:
        """
        按行绘制居中缩进与地图格子，返回地点按钮的返回值列表。
        Keyword arguments:
        map_view -- MapView，地图查看数据
        Return arguments:
        list[str] -- 地点按钮的返回值列表
        """
        return_list = []
        for row in map_view.rows:
            fix_draw = draw.NormalDraw()
            fix_draw.text = " " * map_view.indent
            fix_draw.width = map_view.indent
            fix_draw.draw()
            for cell in row:
                if cell.kind in (svc.CellKind.OPEN, svc.CellKind.CLOSED):
                    now_draw = draw.Button(
                        cell.text,
                        cell.text,
                        normal_style=cell.style,
                        cmd_func=self.move_now,
                        args=(cell.scene_path,),
                    )
                    now_draw.width = self.width
                    now_draw.draw()
                    return_list.append(now_draw.return_text)
                else:
                    text_draw = draw.NormalDraw()
                    text_draw.style = cell.style
                    text_draw.text = cell.text
                    text_draw.draw()
            line_feed.draw()
        return return_list

    def draw_button(
        self,
        now_index: int,
        text: str,
        return_list: list[str],
        cmd_func: Callable[[], None] | None = None,
    ) -> int:
        """
        绘制宽为面板四分之一的编号居中按钮并加入监听列表。
        Keyword arguments:
        now_index (int)、text (str) -- 按钮编号与显示文本
        return_list (list[str])、cmd_func (Callable[[], None] | None) -- 监听列表与回调
        Return arguments:
        int -- 下一个按钮编号
        """
        button = draw.CenterButton(
            text_handle.id_index(now_index) + text,
            str(now_index),
            self.width / 4,
            cmd_func=cmd_func,
        )
        button.draw()
        return_list.append(button.return_text)
        return now_index + 1

    def up_map(self) -> None:
        """清屏并将当前查看地图切换为上级地图。"""
        py_cmd.clr_cmd()
        self.now_map = svc.parent_map(self.now_map)

    def down_map(self) -> None:
        """清屏并将当前查看地图切换为朝向玩家所在位置的下级地图。"""
        py_cmd.clr_cmd()
        self.now_map = svc.child_map(self.now_map)

    def all_npc_position(self) -> None:
        """查看所有干员位置"""
        py_cmd.clr_cmd()
        from Script.UI.Panel import all_npc_position_panel

        now_panel = all_npc_position_panel.All_Npc_Position_Panel(self.width)
        now_panel.draw()

    def move_now(self, scene_path: list[str]) -> None:
        """
        清屏并控制玩家角色移动，跨区块进入入口场景时保持地图开启。
        Keyword arguments:
        scene_path -- list[str]，目标场景路径
        """
        py_cmd.clr_cmd()
        line_feed.draw()
        flow_handle.set_skip_pauses(True)
        character_move.own_charcter_move(
            scene_path, open_map=svc.opens_map(scene_path)
        )


class MoveMenuPanel:
    """
    快捷移动菜单面板
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 最大绘制宽度 """
        self.return_list: list[str] = []
        """ 监听的按钮列表 """
        self.now_type: int = 0
        """ 当前的移动菜单类型 """
        self.draw_list: list[draw.Drawable] = []
        """ 绘制的对象列表 """
        self.move_type_id_data: dict[str, int] = {
            game_config.config_move_menu_type[i].name: i
            for i in game_config.config_move_menu_type
        }
        """ 移动类型名字对应配表id """

    def update(self) -> None:
        """更新绘制面板"""
        line = draw.LineDraw(".", self.width)
        self.draw_list = []
        self.return_list = []
        self.draw_list.append(line)
        menu_draw = panel.CenterDrawButtonListPanel()
        move_name_list = [
            game_config.config_move_menu_type[i].name
            for i in game_config.config_move_menu_type
        ]
        move_name_draw_list = [f"[{name}]" for name in move_name_list]
        menu_draw.set(
            move_name_draw_list,
            move_name_list,
            self.width,
            len(game_config.config_move_menu_type),
            move_name_draw_list[self.now_type],
            self.change_type,
        )
        self.draw_list.append(menu_draw)
        self.return_list.extend(menu_draw.return_list)

    def change_type(self, to_type: str) -> None:
        """
        改变当前快捷移动菜单类型
        Keyword arguments:
        to_type -- 指定的新类型id
        """
        self.now_type = self.move_type_id_data[to_type]
        py_cmd.clr_cmd()

    def draw(self) -> None:
        """绘制面板"""
        for now_draw in self.draw_list:
            now_draw.draw()
        line = draw.LineDraw("-.-", self.width)
        line.draw()


class MapSceneNameDraw:
    """
    绘制指定地图地图场景id对应场景名列表
    Keyword arguments:
    now_map -- 地图路径
    width -- 绘制宽度
    """

    def __init__(self, now_map: list[str], width: int) -> None:
        """
        初始化地图场景名列表绘制对象
        Keyword arguments:
        now_map -- 地图路径
        width -- 绘制宽度
        """
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_map: list[str] = now_map
        """ 当前查看的地图坐标 """
        self.return_list: list[str] = []
        """ 当前面板的按钮返回 """
        self.end_index: int = 0
        """ 结束按钮id """

    def update(self, now_map: list[str]) -> None:
        """
        更新面板当前查看的地图路径。
        Keyword arguments:
        now_map -- list[str]，当前查看的地图路径
        """
        self.now_map = now_map

    def draw(self) -> None:
        """按当前地图场景列表绘制每行最多 8 个的快捷移动按钮，玩家所在场景以金色文本展示。"""
        self.return_list = []
        entries = svc.scene_entries(self.now_map)
        draw_list: list[draw.LeftDraw | draw.LeftButton] = []
        for entry in entries:
            if entry.scene_id == "0":
                now_id_text = f"→0:{_(entry.name)}"
            else:
                now_id_text = f"→{_(entry.name)}"
            now_draw: draw.LeftDraw | draw.LeftButton
            if entry.here:
                now_draw = draw.LeftDraw()
                now_draw.text = now_id_text
                now_draw.width = self.width
                now_draw.style = "gold_enrod"
            else:
                now_draw = draw.LeftButton(
                    now_id_text,
                    now_id_text,
                    self.width,
                    cmd_func=move_now,
                    args=(entry.scene_path,),
                )
                self.return_list.append(now_draw.return_text)
            draw_list.append(now_draw)
        if draw_list:
            _draw_grid(draw_list, 8, self.width)
        self.end_index = len(entries) - 1


class CollectionSceneNamePanel:
    """
    绘制收藏对象所在场景快捷寻路按钮列表
    Keyword arguments:
    now_map -- 地图路径
    width -- 绘制宽度
    """

    def __init__(self, now_map: list[str], width: int) -> None:
        """
        初始化绘制对象，记下绘制宽度与地图路径
        Keyword arguments:
        now_map -- 地图路径
        width -- 绘制宽度
        """
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_map: list[str] = now_map
        """ 当前查看的地图坐标 """
        self.return_list: list[str] = []
        """ 当前面板的按钮返回 """
        self.end_index: int = 0
        """ 结束按钮id """

    def update(self, now_map: list[str]) -> None:
        """
        更新面板记录的当前地图路径。
        Keyword arguments:
        now_map -- list[str]，当前查看的地图路径
        """
        self.now_map = now_map

    def draw(self) -> None:
        """存在收藏地点时绘制每行最多 4 个的快捷移动按钮与收藏切换按钮，无收藏地点时不绘制。"""
        self.return_list = []
        entries = svc.bookmark_entries()
        if not entries:
            return
        self.end_index = len(entries) - 1
        draw_list: list[draw.LeftDraw | draw.LeftButton] = []
        for entry in entries:
            draw_text = f"→{entry.label}"
            now_draw: draw.LeftDraw | draw.LeftButton
            if entry.here:
                now_draw = draw.LeftDraw()
                now_draw.text = _(draw_text)
                now_draw.width = self.width
                now_draw.style = "gold_enrod"
            else:
                now_draw = draw.LeftButton(
                    _(draw_text),
                    draw_text,
                    self.width,
                    cmd_func=move_now,
                    args=(entry.scene_path,),
                )
                self.return_list.append(now_draw.return_text)
            draw_list.append(now_draw)
        _draw_grid(draw_list, 4, self.width)
        line_feed.draw()
        collect_flag = not svc.here_bookmarked()
        if collect_flag:
            btn_text = _(" [收藏当前地点] ")
        else:
            btn_text = _(" [取消收藏当前地点] ")
        collection_button = draw.CenterButton(
            btn_text,
            btn_text,
            self.width / 4,
            cmd_func=self.settle_collection_place,
            args=(collect_flag,),
        )
        collection_button.draw()
        self.return_list.append(collection_button.return_text)
        line_feed.draw()

    def settle_collection_place(self, collect_flag: bool) -> None:
        """
        收藏或取消收藏玩家当前所在地点。
        Keyword arguments:
        collect_flag -- bool，为 True 时加入收藏，为 False 时取消收藏
        """
        svc.bookmark_here(collect_flag)
