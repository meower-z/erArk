"""
生产与破壳的 Tk 界面回调
========================
load_order 导入本模块时经 choice_prompts.renderer 登记 draw_wait_choice，
并经 pregnancy_hooks.on_name_input 登记 ask_child_name。
两函数分别渲染生产与破壳的等待按钮，以及调用既有的角色取名输入框。
本模块不登记内核钩子，也不读写游戏状态。
"""

from Script.Config import normal_config
from Script.Core import flow_handle
from Script.Modules.gameplay_resolution import born_service, pregnancy_hooks
from Script.Modules.tk_ui import choice_prompts
from Script.Protocol.modal_prompts import ChoicePrompt
from Script.UI.Moudle import draw


@choice_prompts.renderer(born_service.WAIT_PROMPT_ID)
def draw_wait_choice(prompt: ChoicePrompt) -> str:
    """
    绘制生产与破壳等待提示的单枚左对齐按钮并等待玩家确认。
    以首项的 label 为按钮文本、"\n" 为响应文本、配置文本宽度为按钮宽度调用 draw.LeftButton。
    经 flow_handle.askfor_all(["\n"]) 读取应答后，返回该选项的 option_id。
    Keyword arguments:
    prompt -- ChoicePrompt，待渲染的等待选项提示
    Return arguments:
    str -- 首项选项的 option_id
    """
    option = prompt.options[0]
    draw.LeftButton(
        option.label, "\n", normal_config.config_normal.text_width
    ).draw()
    flow_handle.askfor_all(["\n"])
    return option.option_id


@pregnancy_hooks.on_name_input
def ask_child_name(ask_text: str) -> str:
    """
    在调用时按需导入 input_name_panel，并经 input_name_func 展示取名输入框返回角色名。
    Keyword arguments:
    ask_text -- str，传给取名输入框的询问文本
    Return arguments:
    str -- 玩家输入并通过校验的角色名称
    """
    from Script.UI.Panel import input_name_panel

    return input_name_panel.input_name_func(ask_text)
