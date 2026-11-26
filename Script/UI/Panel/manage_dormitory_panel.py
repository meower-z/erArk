"""
宿舍管理面板（manage_dormitory_panel）
======================================
提供宿舍管理系统界面的绘制与交互分发。
"""

from types import FunctionType
from typing import Any

from Script.Config import normal_config
from Script.Core import constant, flow_handle, get_text
from Script.Modules.gameplay_resolution import (
    dormitory_manager_service as managers,
    dormitory_room_service as rooms,
)
from Script.System.Dormitory_System import common
from Script.UI.Moudle import draw, view

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


def _button(
    return_list: list[str], cls: type, *args: Any, **kwargs: Any
) -> str:
    """绘制按钮控件并将其返回码加入 return_list 后返回。"""
    button = cls(*args, **kwargs)
    button.draw()
    return_list.append(button.return_text)
    return button.return_text


def _back(return_list: list[str], style: str = "standard") -> str:
    """绘制居中返回按钮并把返回码加入 return_list。"""
    return _button(
        return_list,
        draw.CenterButton,
        _("[返回]"),
        _("返回"),
        window_width,
        normal_style=style,
    )


class Manage_Dormitory_Panel:
    """宿舍管理系统界面面板，含宿舍总览与调整宿舍管理员两页。"""

    def __init__(self, width: int) -> None:
        """初始化面板宽度、当前页签、详情开关与临时空白位状态。"""
        self.width: int = width
        """ 面板内容区的显示宽度。 """
        self.now_panel: str = _("宿舍总览")
        """ 当前选中的顶层页签名称。 """
        self.show_dormitory_detail: bool = False
        """ 是否在宿舍总览页展开具体居住情况。 """
        self.temp_blank = rooms.TempBlank()
        """ 本面板实例持有的临时空白位对象。 """
        self.dormitory_select_state: dict[str, Any] = {}
        """ 干员选择界面的筛选状态字典。 """

    def draw(self) -> None:
        """运行宿舍管理面板主循环，返回时重置未分配层管理员。"""
        panel_list = [_("宿舍总览"), _("调整宿舍管理员")]
        title_draw = draw.TitleLineDraw(_("宿舍管理系统"), self.width)
        while 1:
            return_list: list[str] = []
            title_draw.draw()
            for now_panel in panel_list:
                panel_width = int(self.width / len(panel_list))
                if now_panel == self.now_panel:
                    now_draw = draw.CenterDraw()
                    now_draw.text = f"[{now_panel}]"
                    now_draw.style = "onbutton"
                    now_draw.width = panel_width
                    now_draw.draw()
                else:
                    _button(
                        return_list,
                        draw.CenterButton,
                        f"[{now_panel}]",
                        f"\n{now_panel}",
                        panel_width,
                        cmd_func=self.change_panel,
                        args=(now_panel,),
                    )
            line_feed.draw()
            draw.LineDraw("+", self.width).draw()
            if self.now_panel == _("宿舍总览"):
                self._draw_overview_page(return_list)
            elif self.now_panel == _("调整宿舍管理员"):
                self._draw_manage_dormitory_manager_page(return_list)
            line_feed.draw()
            line_feed.draw()
            locked = self._is_character_dormitory_page_locked()
            back = _back(return_list, "deep_gray" if locked else "standard")
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back:
                if locked:
                    self._draw_temp_blank_lock_hint()
                    continue
                reset_count = managers.reset_unassigned_managers()
                if reset_count > 0:
                    self._wait(
                        _(
                            "\n○已将{0}名未分配楼层的宿舍管理员重置为无岗位\n"
                        ).format(reset_count)
                    )
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def change_panel(self, now_panel: str) -> None:
        """切换当前页签，若处于空白位锁定状态则仅显示提示。"""
        if (
            now_panel != self.now_panel
            and self._is_character_dormitory_page_locked()
        ):
            self._draw_temp_blank_lock_hint()
            return
        self.now_panel = now_panel

    def _text(self, text: str) -> None:
        """按面板宽度绘制一段普通文本。"""
        now_draw = draw.NormalDraw()
        now_draw.width = self.width
        now_draw.text = text
        now_draw.draw()

    def _wait(self, text: str, style: str | None = None) -> None:
        """按面板宽度绘制等待玩家确认的提示文本。"""
        now_draw = draw.WaitDraw()
        now_draw.width = self.width
        if style is not None:
            now_draw.style = style
        now_draw.text = text
        now_draw.draw()

    def _show(self, notice: rooms.Notice | None) -> None:
        """依次绘制 Notice 中的普通提示行与等待确认文本。"""
        if notice is None:
            return
        for line in notice.lines:
            self._text(line)
        if notice.wait is not None:
            self._wait(notice.wait)

    def _draw_overview_page(self, return_list: list[str]) -> None:
        """绘制宿舍总览页文本、居住详情展开区与操作按钮。"""
        blank_ids = self.temp_blank.current()
        self._text(rooms.overview_text(blank_ids, managers.layer_managers()))
        line_feed.draw()
        detail_text = _(" ▶[具体居住情况]")
        if self.show_dormitory_detail:
            detail_text = _(" ▼[具体居住情况]")
        _button(
            return_list,
            draw.LeftButton,
            detail_text,
            _("显示具体居住情况"),
            len(detail_text) * 2,
            cmd_func=self.show_dormitory_detail_func,
        )
        line_feed.draw()
        if self.show_dormitory_detail:
            self._text(common.get_dormitory_occupants_text())
            line_feed.draw()
        line_feed.draw()
        actions = [
            (
                _("[选择要调整宿舍的干员]"),
                _("\n打开宿舍调整干员选择"),
                self._prompt_select_character_for_dormitory,
            )
        ]
        if rooms.has_overcrowded_room():
            actions.append(
                (
                    _("[将大于两人的宿舍重新分配]"),
                    _("\n将大于两人的宿舍重新分配"),
                    self._redistribute_overcrowded_dormitories,
                )
            )
        if blank_ids:
            actions.append(
                (
                    _("[自动排序临时空白位]"),
                    _("\n自动排序临时空白位"),
                    self._auto_sort_temp_blank_characters,
                )
            )
        for text, return_text, func in actions:
            _button(
                return_list,
                draw.CenterButton,
                text,
                return_text,
                int(self.width / 3),
                cmd_func=func,
            )
        line_feed.draw()

    def show_dormitory_detail_func(self) -> None:
        """切换宿舍总览页具体居住情况的展开状态。"""
        self.show_dormitory_detail = not self.show_dormitory_detail

    def _prompt_select_character_for_dormitory(self) -> None:
        """打开分页干员选择界面，选取要调整宿舍的在编干员。"""
        from Script.UI.Moudle import panel
        from Script.UI.Panel import common_select_NPC

        now_draw_panel = panel.PageHandlePanel(
            [],
            common_select_NPC.CommonSelectNPCButtonList,
            50,
            5,
            window_width,
            True,
            False,
            0,
        )
        while 1:
            now_draw_panel.text_list = [
                [chara_id, self._choose_new_dormitory, []]
                for chara_id in rooms.selectable_ids()
            ]
            info_text = _("请选择一名干员以调整宿舍（仅显示已拥有干员）：\n")
            return_list, other_return_list, self.dormitory_select_state = (
                common_select_NPC.common_select_npc_button_list_func(
                    now_draw_panel,
                    _("调整干员宿舍"),
                    info_text,
                    self.dormitory_select_state,
                )
            )
            yrn = flow_handle.askfor_all(return_list)
            if yrn in return_list and yrn not in other_return_list:
                break

    def _draw_manage_dormitory_manager_page(
        self, return_list: list[str]
    ) -> None:
        """绘制调整宿舍管理员页的未分配提示、增减入口与各层按钮。"""
        from Script.UI.Panel import manage_basement_panel

        layers = managers.layer_managers()
        unassigned = managers.unassigned_manager_names()
        if unassigned:
            self._text(
                _("\n 以下干员已被任命为宿舍管理员，但尚未分配管理层级：")
                + " ".join(unassigned)
            )
            line_feed.draw()
        _button(
            return_list,
            draw.CenterButton,
            _("[宿舍管理员增减]"),
            _("\n宿舍管理员增减"),
            int(self.width / 4),
            cmd_func=manage_basement_panel.change_npc_work_out,
            args=(self.width, [managers.MANAGER_WORK]),
        )
        line_feed.draw()
        self._text(_("\n 选择层级后可进行任命或撤换：\n"))
        for layer, name in layers:
            if name is not None:
                text = _("[{0}层] 当前管理员：{1}").format(layer, name)
                func = self._remove_manager_for_layer
            else:
                text = _("[{0}层] 当前管理员：未任命").format(layer)
                func = self._appoint_manager_for_layer
            _button(
                return_list,
                draw.LeftButton,
                text,
                f"\n{layer}",
                self.width,
                cmd_func=func,
                args=(layer,),
            )
            line_feed.draw()
        if not layers:
            self._text(_("\n 暂无可管理的开放层。\n"))

    def _choose_new_dormitory(self, character_id: int) -> None:
        """绘制单名干员的目标宿舍选择界面与移入临时空白位按钮。"""
        if not rooms.can_change_room(character_id):
            self._wait(
                _("\n○当前角色处于特殊状态，暂不可手动更换宿舍\n"),
                "gold_enrod",
            )
            return
        blank_ids = self.temp_blank.current()
        choices = rooms.room_choices(character_id)
        title, info = rooms.change_header(character_id, blank_ids)
        while 1:
            return_list: list[str] = []
            draw.TitleLineDraw(title, self.width).draw()
            self._text(info)
            if character_id not in blank_ids:
                _button(
                    return_list,
                    draw.CenterButton,
                    _("[移入临时空白位]"),
                    _("\n移入临时空白位"),
                    int(self.width / 3),
                    cmd_func=self._move_character_to_temp_blank,
                    args=(character_id,),
                )
                line_feed.draw()
            line_feed.draw()
            for index, choice in enumerate(choices, 1):
                _button(
                    return_list,
                    draw.LeftButton,
                    choice.label,
                    f"\n{choice.room_name}",
                    int(self.width / 4),
                    cmd_func=self._set_character_dormitory,
                    args=(character_id, choice.room_path),
                )
                if index % 4 == 0:
                    line_feed.draw()
            line_feed.draw()
            line_feed.draw()
            back = _back(return_list)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back or yrn in return_list:
                break

    def _set_character_dormitory(
        self, character_id: int, dormitory_path: str
    ) -> None:
        """调用房间服务写入目标宿舍并绘制结果提示。"""
        self._show(
            rooms.set_room(character_id, dormitory_path, self.temp_blank)
        )

    def _move_character_to_temp_blank(self, character_id: int) -> None:
        """调用房间服务将干员移入临时空白位并绘制结果提示。"""
        self._show(rooms.move_to_blank(character_id, self.temp_blank))

    def _auto_sort_temp_blank_characters(self) -> None:
        """调用房间服务自动排序临时空白位并绘制结果提示。"""
        self._show(rooms.auto_sort(self.temp_blank))

    def _redistribute_overcrowded_dormitories(self) -> None:
        """调用房间服务重分配超员宿舍并绘制结果提示。"""
        self._show(rooms.redistribute())

    def _appoint_manager_for_layer(self, layer: int) -> None:
        """绘制指定楼层的宿舍管理员候选列表并等待选择。"""
        while 1:
            return_list: list[str] = []
            draw.TitleLineDraw(
                _("选择{0}层宿舍管理员").format(layer), self.width
            ).draw()
            candidates = managers.manager_candidates()
            self._text(
                _(
                    "\n 请选择一名干员任命为宿舍管理员（仅显示宿舍管理员岗位干员）：\n"
                )
            )
            for chara_id, name, label in candidates:
                _button(
                    return_list,
                    draw.LeftButton,
                    label,
                    f"\n{name}",
                    int(self.width / 3),
                    cmd_func=self._do_appoint_manager,
                    args=(layer, chara_id),
                )
            line_feed.draw()
            if not candidates:
                self._text(
                    _(
                        "\n 当前没有可任命的宿舍管理员，请先通过[宿舍管理员增减]将干员调整到该岗位。\n"
                    )
                )
            back = _back(return_list)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back or yrn in return_list:
                break

    def _do_appoint_manager(self, layer: int, character_id: int) -> None:
        """调用管理员服务完成指定楼层任命并绘制结果提示。"""
        self._show(managers.appoint(layer, character_id))

    def _remove_manager_for_layer(self, layer: int) -> None:
        """调用管理员服务撤换指定楼层管理员并绘制结果提示。"""
        self._show(managers.dismiss(layer))

    def _is_character_dormitory_page_locked(self) -> bool:
        """判断当前是否处于临时空白位未安置时的页面锁定状态。"""
        return (
            self.now_panel == _("管理干员所属宿舍")
            and len(self.temp_blank.current()) > 0
        )

    def _draw_temp_blank_lock_hint(self) -> None:
        """绘制临时空白位未清空时的锁定等待提示。"""
        self._wait(
            _(
                "\n○当前有{0}名干员处于临时空白位，请先完成安置后再切换页面或返回\n"
            ).format(len(self.temp_blank.current()))
        )
