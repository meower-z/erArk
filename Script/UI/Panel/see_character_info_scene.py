"""
场景内角色信息入口与切换循环面板模块。
提供场景角色名单按钮、含上下切换的角色信息浏览循环与场景查看入口。
"""

from types import FunctionType
from Script.UI.Moudle import draw, view
from Script.Core import constant, flow_handle
from Script.Core import get_text, py_cmd, text_handle
from Script.UI.Panel import see_character_info_panel
from Script.Modules.tk_ui import player_pick
from Script.Modules.domains import activity, identity
from Script.Modules.gameplay_resolution import character_info_service as svc

_: FunctionType = get_text._
""" 本地化翻译函数。 """
line_feed = see_character_info_panel.line_feed
""" 用于输出单个换行的共享绘制对象。 """


class SeeCharacterInfoByNameDrawInScene:
    """场景角色列表中的单个角色名称项。"""

    def __init__(
        self,
        text: str,
        width: int,
        is_button: bool,
        num_button: bool,
        button_id: int,
    ) -> None:
        """按按钮与编号开关构造角色名称绘制对象。"""
        self.character_id: int = int(text)
        self.draw_text: str = ""
        self.width: int = width
        self.is_button: bool = is_button
        self.num_button: bool = num_button
        self.button_id: int = button_id
        self.button_return: str = str(button_id)
        character_name = identity.of(self.character_id).name
        name_draw: draw.NormalDraw | draw.CenterButton
        name_draw = draw.NormalDraw()
        if is_button:
            if num_button:
                index_text = text_handle.id_index(button_id)
                button_text = f"{index_text} {character_name}"
                name_draw = draw.CenterButton(
                    button_text,
                    self.button_return,
                    self.width,
                    cmd_func=self.see_character,
                )
            else:
                button_text = f"[{character_name}]"
                name_draw = draw.CenterButton(
                    button_text,
                    character_name,
                    self.width,
                    cmd_func=self.see_character,
                )
                self.button_return = character_name
            self.draw_text = button_text
        else:
            character_name = text_handle.align(
                f"[{character_name}]", "center", 0, 1, self.width
            )
            name_draw.text = character_name
            self.draw_text = character_name
        name_draw.width = self.width
        self.now_draw = name_draw

    def draw(self) -> None:
        """绘制角色名称文本或按钮，非按钮时启用高亮样式。"""
        if isinstance(self.now_draw, draw.NormalDraw):
            self.now_draw.style = "onbutton"
        self.now_draw.draw()

    def see_character(self) -> None:
        """将当前角色设为玩家交互目标并清屏。"""
        with player_pick.drafting("scene target"):
            activity.set_target(0, self.character_id)
        py_cmd.clr_cmd()


class SeeCharacterInfoHandleInScene:
    """带上下人切换与返回按钮的角色信息浏览循环。"""

    def __init__(
        self, character_id: int, width: int, character_list: list[int]
    ) -> None:
        """记录初始角色、显示宽度与可切换角色列表。"""
        self.character_id: int = character_id
        self.width: int = width
        self.return_list: list[str] = []
        self.character_list: list[int] = character_list

    def draw(self) -> None:
        """循环绘制角色信息面板并处理标签与人物切换输入。"""
        old_button_draw = draw.CenterButton(
            _("[上一人]"),
            _("上一人"),
            self.width / 3,
            cmd_func=self.old_character,
        )
        next_button_draw = draw.CenterButton(
            _("[下一人]"),
            _("下一人"),
            self.width / 3,
            cmd_func=self.next_character,
        )
        back_draw = draw.CenterButton(_("[返回]"), _("返回"), self.width / 3)
        now_panel_id = _("基础属性")
        while 1:
            self.return_list = []
            now_character_panel = (
                see_character_info_panel.SeeCharacterInfoPanel(
                    self.character_id, self.width
                )
            )
            now_character_panel.change_panel(now_panel_id)
            now_character_panel.draw()
            line_feed.draw()
            old_button_draw.draw()
            back_draw.draw()
            next_button_draw.draw()
            line_feed.draw()
            self.return_list.extend(now_character_panel.return_list)
            self.return_list.append(old_button_draw.return_text)
            self.return_list.append(back_draw.return_text)
            self.return_list.append(next_button_draw.return_text)
            yrn = flow_handle.askfor_all(self.return_list)
            py_cmd.clr_cmd()
            line_feed.draw()
            if yrn == back_draw.return_text:
                break
            elif yrn in now_character_panel.draw_data:
                now_panel_id = yrn

    def old_character(self) -> None:
        """将当前查看角色切换到列表中的上一人。"""
        self.character_id = svc.previous_in_scene(
            self.character_id, self.character_list
        )

    def next_character(self) -> None:
        """将当前查看角色切换到列表中的下一人。"""
        self.character_id = svc.next_in_scene(
            self.character_id, self.character_list
        )


class SeeCharacterInfoInScenePanel:
    """查看当前场景内角色信息的面板入口。"""

    def __init__(self, target_id: int, width: int) -> None:
        """收集同场景其他角色并构造场景角色浏览循环。"""
        self.target_id: int = target_id
        self.width: int = width
        self.handle_panel = SeeCharacterInfoHandleInScene(
            target_id, width, svc.scene_others()
        )

    def draw(self) -> None:
        """运行角色浏览循环并在结束后切回场景主面板。"""
        self.handle_panel.draw()
        view.now_panel_id = constant.Panel.IN_SCENE
