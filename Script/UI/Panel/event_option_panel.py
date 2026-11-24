"""事件选项面板（含多层嵌套与子事件选项）"""

from types import FunctionType
from Script.Core import (
    get_text,
    flow_handle,
    text_handle,
    py_cmd,
)
from Script.Design import talk
from Script.UI.Moudle import draw, panel
from Script.Config import game_config, normal_config
from Script.Modules.gameplay_resolution import event_option_service
from Script.Protocol.modal_prompts import ChoiceResult

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


class Event_option_Panel:
    """
    总面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, character_id: int, width: int) -> None:
        """初始化绘制对象"""
        self.character_id = character_id
        """ 绘制的角色id """
        self.width: int = width
        """ 绘制的最大宽度 """
        self.handle_panel: panel.PageHandlePanel | None = None
        """ 当前名字列表控制面板 """

    def draw(self) -> None:
        """绘制对象"""
        prompt = event_option_service.build_son_event_prompt(self.character_id)
        if prompt is None:
            return
        son_event_list = [
            [option.option_id, self.character_id] for option in prompt.options
        ]

        line_feed.draw()
        self.handle_panel = panel.PageHandlePanel(
            [], SonEventDraw, 20, 1, self.width, True, True, 0
        )

        while 1:
            py_cmd.clr_cmd()

            self.handle_panel.text_list = son_event_list
            self.handle_panel.update()
            return_list = []
            self.handle_panel.draw()
            return_list.extend(self.handle_panel.return_list)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn in return_list:
                break


class multi_layer_event_option_Panel:
    """
    多层嵌套的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(
        self,
        character_id: int,
        width: int,
        event_parent_chid_id: int,
        event_parent_value: int,
    ) -> None:
        """初始化绘制对象"""
        self.character_id = character_id
        """ 绘制的角色id """
        self.width: int = width
        """ 绘制的最大宽度 """
        self.event_parent_chid_id = event_parent_chid_id
        """ 嵌套父子事件的序号id（非事件id） """
        self.event_parent_value = event_parent_value
        """ 嵌套父子事件的值 """
        self.handle_panel: panel.PageHandlePanel = panel.PageHandlePanel(
            [], SonEventDraw, 20, 1, self.width, True, True, 0
        )
        """ 当前名字列表控制面板 """

    def draw(self) -> None:
        """绘制对象"""
        prompt = event_option_service.build_multi_layer_event_prompt(
            self.character_id,
            self.event_parent_chid_id,
            self.event_parent_value,
        )
        if prompt is None:
            return

        line_feed.draw()
        draw_event_list = [
            [option.option_id, self.character_id] for option in prompt.options
        ]

        while 1:
            py_cmd.clr_cmd()

            self.handle_panel.text_list = draw_event_list
            self.handle_panel.update()
            return_list = []
            self.handle_panel.draw()
            return_list.extend(self.handle_panel.return_list)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn in return_list:
                break


class SonEventDraw:
    """
    显示子事件选项对象
    Keyword arguments:
    value_list -- 事件id,人物id
    width -- 最大宽度
    is_button -- 绘制按钮
    num_button -- 绘制数字按钮
    button_id -- 数字按钮id
    """

    def __init__(
        self,
        value_list: list,
        width: int,
        is_button: bool,
        num_button: bool,
        button_id: int,
    ) -> None:
        """初始化绘制对象"""
        self.event_id = value_list[0]
        """ 事件id """
        self.character_id = value_list[1]
        """ 绘制的角色id """
        self.son_event = game_config.config_event[self.event_id]
        """ 子事件 """
        self.draw_text: str = ""
        """ 绘制文本 """
        self.width: int = width
        """ 最大宽度 """
        self.num_button: bool = num_button
        """ 绘制数字按钮 """
        self.button_id: int = button_id
        """ 数字按钮的id """
        self.button_return: str = str(button_id)
        """ 按钮返回值 """
        name_draw: draw.NormalDraw | draw.CenterButton = draw.NormalDraw()
        option_text = talk.code_text_to_draw_text(
            event_option_service.option_label(self.son_event.text),
            self.character_id,
        )
        if is_button:
            if num_button:
                index_text = text_handle.id_index(button_id)
                button_text = f"{index_text}{option_text}"
                name_draw = draw.LeftButton(
                    button_text,
                    self.button_return,
                    self.width,
                    cmd_func=self.run_son_event,
                )
            else:
                button_text = f"[{option_text}]"
                name_draw = draw.CenterButton(
                    button_text,
                    option_text,
                    self.width,
                    cmd_func=self.run_son_event,
                )
                self.button_return = option_text
            self.draw_text = button_text
        else:
            name_draw = draw.CenterDraw()
            name_draw.text = f"[{option_text}]"
            name_draw.width = self.width
            self.draw_text = name_draw.text
        self.now_draw = name_draw
        """ 绘制的对象 """

    def draw(self) -> None:
        """绘制对象"""
        self.now_draw.draw()

    def run_son_event(self) -> None:
        """点击后运行对应的子事件"""
        event_option_service.apply_event_choice(
            self.character_id,
            ChoiceResult(
                event_option_service.SON_EVENT_PROMPT_ID, self.event_id
            ),
        )
