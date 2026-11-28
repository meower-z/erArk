"""子事件选项的分页提问函数与单个选项绘制项。"""

from Script.Config import normal_config
from Script.Core import flow_handle, py_cmd, text_handle
from Script.Protocol.modal_prompts import ChoiceOption, ChoicePrompt
from Script.UI.Moudle import draw, panel

line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1


def ask_event_option(prompt: ChoicePrompt) -> str:
    """
    以每页 20 项、单列、从 0 编号的分页列表绘制 prompt.options，等待玩家选出子事件并返回其 option_id。
    先绘制一次换行，再在循环中清除已绑定命令、刷新并绘制当前页、追加一次换行，并调用 flow_handle.askfor_all。
    若输入对应当前页某个 EventOptionDraw 按钮则返回其 option_id，否则继续循环以绘制翻页后的页面。
    Keyword arguments:
    prompt -- ChoicePrompt，待绘制并询问的子事件选项提示
    Return arguments:
    str -- 玩家所选选项的 option_id
    """
    line_feed.draw()
    handle_panel = panel.PageHandlePanel(
        list(prompt.options),
        EventOptionDraw,
        20,
        1,
        normal_config.config_normal.text_width,
        True,
        True,
        0,
    )
    while True:
        py_cmd.clr_cmd()
        handle_panel.update()
        handle_panel.draw()
        line_feed.draw()
        yrn = flow_handle.askfor_all(handle_panel.return_list)
        chosen = {
            value.button_return: value.option_id
            for value in handle_panel.draw_list
            if isinstance(value, EventOptionDraw)
        }
        if yrn in chosen:
            return chosen[yrn]


class EventOptionDraw:
    """
    供 PageHandlePanel 绘制单个子事件选项按钮的绘制项，固定生成左对齐编号按钮。
    is_button 与 num_button 为配合 PageHandlePanel.update 的调用签名而接收，实例内不使用。
    Keyword arguments:
    option -- ChoiceOption，待绘制的单个子事件选项
    width -- int，按钮的最大绘制宽度
    is_button -- bool，PageHandlePanel 传入的按钮标记，本类不使用
    num_button -- bool，PageHandlePanel 传入的数字按钮标记，本类不使用
    button_id -- int，当前页内分配给该选项的数字按钮编号
    """

    def __init__(
        self,
        option: ChoiceOption,
        width: int,
        is_button: bool,
        num_button: bool,
        button_id: int,
    ) -> None:
        """按选项数据与页内编号构造左对齐子事件选项按钮。"""
        self.option_id: str = option.option_id
        """ 该按钮对应的子事件选项标识。 """
        self.button_return: str = str(button_id)
        """ 按钮触发时返回给 askfor_all 的编号字符串。 """
        self.draw_text: str = f"{text_handle.id_index(button_id)}{option.label}"
        """ 带编号前缀的选项按钮显示文本。 """
        self.now_draw = draw.LeftButton(
            self.draw_text, self.button_return, width
        )
        """ 负责实际绘制选项的 LeftButton 实例。 """

    def draw(self) -> None:
        """绘制对象"""
        self.now_draw.draw()
