"""
群交面板（group_sex_panel）
===========================
负责群交信息栏与编辑界面的绘制和输入分发，部位行与控件文案、模板读写与邀请由无界面服务提供。
"""

from collections.abc import Callable
from types import FunctionType
from Script.UI.Moudle import draw, panel, view
from Script.Core import get_text, constant, flow_handle
from Script.Config import normal_config
from Script.Modules.gameplay_resolution import (
    group_sex_editor_service as editor,
)
from Script.Modules.gameplay_resolution import group_sex_invite_service

_: FunctionType = get_text._
""" 翻译api """

line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width = normal_config.config_normal.text_width
""" 屏幕宽度 """


class SeeGroupSexInfoPanel:
    """
    显示群交栏数据面板对象
    Keyword arguments:
    character_id -- 角色id
    width -- 绘制宽度
    column -- 每行状态最大个数
    type_number -- 显示的状态类型
    """

    def __init__(
        self,
        character_id: int,
        width: int,
        column: int,
        type_number: int,
        center_status: bool = True,
    ) -> None:
        """初始化绘制对象"""
        self.character_id = character_id
        """ 要绘制的角色id """
        self.width = width
        """ 面板最大宽度 """
        self.column = column
        """ 每行状态最大个数 """
        self.draw_list: list[
            draw.LittleTitleLineDraw | draw.NormalDraw | list[draw.LeftDraw]
        ] = []
        """ 绘制的文本列表 """
        self.return_list: list[str] = []
        """ 当前面板监听的按钮列表 """
        self.center_status: bool = center_status
        """ 居中绘制状态文本 """
        self.type_number = type_number
        """ 显示的状态类型 """

        type_line = draw.LittleTitleLineDraw(_("群交"), width, ":")
        text_draw = draw.NormalDraw()
        text_draw.text = editor.info_text(character_id)
        if text_draw.text != "":
            self.draw_list.append(type_line)
        self.draw_list.append(text_draw)

    def draw(self) -> None:
        """绘制面板"""
        for label in self.draw_list:
            if isinstance(label, list):
                for value in label:
                    value.draw()
                line_feed.draw()
            else:
                label.draw()


class Edit_Group_Sex_Temple_Panel:
    """
    总面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """

    def _note(self, text: str) -> None:
        """换行后以面板全宽绘制带尾部空格的说明文本。"""
        line_feed.draw()
        info_draw = draw.NormalDraw()
        info_draw.text = text + "              "
        info_draw.width = self.width
        info_draw.draw()

    def _toggle(
        self,
        return_list: list[str],
        text: str,
        key: str,
        func: Callable[[], None],
    ) -> None:
        """按文案长度绘制左对齐切换按钮，并将返回码加入监听列表。"""
        button = draw.LeftButton(
            f"▶{text}", key, len(text) * 4 + 1, cmd_func=func
        )
        button.draw()
        return_list.append(button.return_text)

    def draw(self) -> None:
        """绘制对象"""
        title_draw = draw.TitleLineDraw("编辑群交行动", self.width)

        while True:
            title_draw.draw()
            return_list: list[str] = []
            info_draw = draw.NormalDraw()
            info_draw.text = _("当前群交状态：\n")
            info_draw.text += _("○群交时同一角色无法同时占用多个部位\n")
            info_draw.text += _(
                "○插入和侍奉只能二选一，插入为单人，侍奉可最多四人\n\n"
            )
            info_draw.width = self.width
            info_draw.draw()
            for row in editor.part_rows():
                name_draw = draw.NormalDraw()
                name_draw.text = row.label
                name_draw.width = int(
                    self.width / (2 if row.key == editor.SERVE else 4)
                )
                name_draw.draw()
                for text, width, func in (
                    (row.target_text, 4, self.show_target_chara_list),
                    (row.state_text, 5, self.show_status_list),
                ):
                    button = draw.CenterButton(
                        f"▶{text}",
                        row.label + text,
                        int(self.width / width),
                        cmd_func=func,
                        args=("A", row.key),
                    )
                    button.draw()
                    return_list.append(button.return_text)
                line_feed.draw()

            line_feed.draw()
            reset_button = draw.CenterButton(
                _("▶重置模板"),
                _("重置模板"),
                self.width // 8,
                cmd_func=self.reset_template,
            )
            reset_button.draw()
            return_list.append(reset_button.return_text)

            state = editor.controls()
            line_feed.draw()
            self._note(
                _(
                    "轮流用副模板：在当前状态之外新增一套副模板，可在两套模板之间切换，或者使用轮流群交指令，可轮流进行一次双模板中的群交指令\n"
                )
            )
            self._toggle(
                return_list,
                state.b_text,
                _("轮流用副模板"),
                editor.change_b_temple_flag,
            )
            if state.b_on:
                change_temple_button = draw.CenterButton(
                    _("切换模板"),
                    _("切换"),
                    len(state.b_text) * 4 + 1,
                    cmd_func=editor.change_temple,
                )
                change_temple_button.draw()
                return_list.append(change_temple_button.return_text)

            self._note(
                _(
                    "锁定群交模板：锁定后使用指令时不会再自动调整状态，仅可在当前编辑面板中修改\n"
                )
            )
            self._toggle(
                return_list,
                state.lock_text,
                _("锁定群交模板"),
                editor.change_lock_flag,
            )

            self._note(_("调整干员行动：没有在上述位置中的干员会\n"))
            self._toggle(
                return_list,
                state.npc_ai_text,
                _("调整干员行动"),
                editor.change_npc_ai,
            )

            self._note(
                _(
                    "邀请其他干员：邀请不在场的干员来这里参加群交，只能邀请实行值足够同意的\n"
                )
            )
            invite_button = draw.LeftButton(
                f"▶{_('邀请')}",
                _("邀请其他干员"),
                len(state.npc_ai_text) * 4 + 1,
                cmd_func=self.show_invite_npc_panel,
            )
            invite_button.draw()
            return_list.append(invite_button.return_text)

            line_feed.draw()
            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                editor.reset_unfinish_select()
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def _back(self, return_list: list[str]) -> None:
        """绘制空行与居中返回按钮，并将返回码加入监听列表。"""
        line_feed.draw()
        line_feed.draw()
        back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
        back_draw.draw()
        return_list.append(back_draw.return_text)
        line_feed.draw()

    def show_target_chara_list(self, temple_id: str, body_part: str) -> None:
        """绘制可选择的交互对象角色列表"""
        choices = editor.target_choices(temple_id, body_part)
        while True:
            line = draw.LineDraw("-", self.width)
            line.draw()
            line_feed.draw()
            return_list: list[str] = []
            for count, choice in enumerate(choices, 1):
                if choice.watch_only:
                    watch_draw = draw.LeftDraw()
                    watch_draw.width = int(self.width / 5)
                    watch_draw.style = "deep_gray"
                    watch_draw.text = f" {choice.text}（体力不足，只能旁观）"
                    watch_draw.draw()
                else:
                    name_draw = draw.LeftButton(
                        choice.text,
                        choice.name,
                        int(self.width / 5),
                        normal_style=(
                            "gold_enrod" if choice.selected else "standard"
                        ),
                        cmd_func=editor.set_target_chara,
                        args=(temple_id, body_part, choice.cid),
                    )
                    name_draw.draw()
                    return_list.append(name_draw.return_text)
                if count % 5 == 0:
                    line_feed.draw()
            self._back(return_list)
            yrn = flow_handle.askfor_all(return_list)
            if yrn in return_list:
                break

    def show_status_list(self, temple_id: str, body_part: str) -> None:
        """绘制可选择的状态列表"""
        choices = editor.status_choices(temple_id, body_part)
        while True:
            line = draw.LineDraw("-", self.width)
            line.draw()
            line_feed.draw()
            return_list: list[str] = []
            for count, (status_id, text, name) in enumerate(choices, 1):
                name_draw = draw.LeftButton(
                    text,
                    name,
                    int(self.width / 5),
                    cmd_func=editor.set_status,
                    args=(temple_id, body_part, status_id),
                )
                name_draw.draw()
                return_list.append(name_draw.return_text)
                if count % 5 == 0:
                    line_feed.draw()
            self._back(return_list)
            yrn = flow_handle.askfor_all(return_list)
            if yrn in return_list:
                break

    def reset_template(self) -> None:
        """重置当前模板中的所有位的角色和指令状态"""
        editor.reset_template()
        info_draw = draw.NormalDraw()
        info_draw.text = _("当前模板已重置\n")
        info_draw.width = self.width
        info_draw.draw()

    def show_invite_npc_panel(self) -> None:
        """绘制可邀请的NPC列表"""
        from Script.UI.Panel import common_select_NPC

        now_draw_panel: panel.PageHandlePanel = panel.PageHandlePanel(
            [],
            common_select_NPC.CommonSelectNPCButtonList,
            50,
            5,
            window_width,
            True,
            False,
            0,
        )
        scene_ids = editor.scene_occupants()
        select_state: dict[str, int | str] = {}
        while True:
            candidates, invited = group_sex_invite_service.invite_candidates(
                scene_ids
            )
            now_draw_panel.text_list = [
                [chara_id, self.invite_npc, invited] for chara_id in candidates
            ]
            return_list, __, select_state = (
                common_select_NPC.common_select_npc_button_list_func(
                    now_draw_panel,
                    _("邀请干员参加群交"),
                    _("当前可邀请的干员有：\n"),
                    select_state,
                )
            )
            yrn = flow_handle.askfor_all(return_list)
            if yrn == _("返回"):
                break

    def invite_npc(self, character_id: int) -> None:
        """邀请NPC"""
        info_draw = draw.WaitDraw()
        info_draw.text = group_sex_invite_service.invite(character_id)
        info_draw.width = self.width
        info_draw.draw()
