"""
tk_ui 的指令界面回调
====================
本模块导入时经 instruct_hooks.on_prompts 登记 2 个槽位，并经 instruct_hooks.on_sex_position 登记 1 个槽位。
本模块导入时经 choice_prompts.renderer 登记 ask_close_door、ask_sex_class_ability 与 confirm_poor_music
三个选项渲染函数。
select_condom 在调用时导入 condom_panel。
choose_sex_position 在调用时导入 sex_position_panel。
ask_official_option 在调用时导入 official_event_panel。
"""

from types import FunctionType
from typing import Any

from Script.Config import normal_config
from Script.Core import flow_handle, get_text
from Script.Modules.gameplay_resolution import instruct_hooks
from Script.Modules.tk_ui import choice_prompts
from Script.Protocol.modal_prompts import ChoicePrompt
from Script.UI.Moudle import draw, panel

_: FunctionType = get_text._
""" 翻译api """
width: int = normal_config.config_normal.text_width
""" 屏幕宽度 """


@choice_prompts.renderer(instruct_hooks.CLOSE_DOOR_PROMPT_ID)
def ask_close_door(prompt: ChoicePrompt) -> str:
    """
    以模块 width 用 draw.TitleLineDraw 绘制 _("关门") 标题栏。
    用 panel.OneMessageAndSingleColumnButton 按 prompt.options 顺序填入各选项标签与 prompt.text 并绘制。
    将面板返回键与 prompt.options 按顺序一一对应。
    调用 flow_handle.askfor_all 读取选择，并返回对应选项的 option_id。
    Keyword arguments:
    prompt -- ChoicePrompt，待绘制的关门询问选项提示
    Return arguments:
    str -- 玩家所选选项的 option_id
    """
    draw.TitleLineDraw(_("关门"), width).draw()
    askfor_panel = panel.OneMessageAndSingleColumnButton()
    askfor_panel.set([option.label for option in prompt.options], prompt.text)
    askfor_panel.draw()
    returns = askfor_panel.get_return_list()
    option_ids = dict(zip(returns, prompt.options, strict=True))
    return option_ids[flow_handle.askfor_all(list(option_ids))].option_id


@choice_prompts.renderer(instruct_hooks.SEX_CLASS_ABILITY_PROMPT_ID)
def ask_sex_class_ability(prompt: ChoicePrompt) -> str:
    """
    以模块 width 用 draw.NormalDraw 绘制 prompt.text，再按 prompt.options 顺序绘制居中按钮。
    遇到 option_id 为 "back" 的选项时，先用 draw.NormalDraw 绘制一次换行。
    每个 CenterButton 使用 _("[{0}]").format(option.label) 作为显示文本、
    option.label 作为响应文本与 int(width / 4) 作为宽度。
    绘制完成后调用 flow_handle.askfor_all 读取选择，并返回对应选项的 option_id。
    Keyword arguments:
    prompt -- ChoicePrompt，待绘制的实操课主修科目选项提示
    Return arguments:
    str -- 玩家所选选项的 option_id
    """
    now_draw = draw.NormalDraw()
    now_draw.width = width
    now_draw.text = prompt.text
    now_draw.draw()
    option_ids = {}
    for option in prompt.options:
        if option.option_id == "back":
            line_draw = draw.NormalDraw()
            line_draw.text = "\n"
            line_draw.draw()
        now_button = draw.CenterButton(
            _("[{0}]").format(option.label), option.label, int(width / 4)
        )
        now_button.draw()
        option_ids[now_button.return_text] = option.option_id
    return option_ids[flow_handle.askfor_all(list(option_ids))]


@choice_prompts.renderer(instruct_hooks.POOR_MUSIC_PROMPT_ID)
def confirm_poor_music(prompt: ChoicePrompt) -> str:
    """
    以模块 width 用 draw.WaitDraw 绘制 prompt.text，再按 prompt.options 顺序绘制居中按钮。
    每个 CenterButton 使用 f"[{option.label}]" 作为显示文本、int(width / 3) 作为宽度，
    并使用 "cancel" 与 "confirm" 各自对应的带前导换行译文作为响应文本。
    绘制完成后调用 flow_handle.askfor_all 读取选择，并返回对应选项的 option_id。
    Keyword arguments:
    prompt -- ChoicePrompt，待绘制的音乐能力偏低确认提示
    Return arguments:
    str -- 玩家所选选项的 option_id
    """
    now_draw = draw.WaitDraw()
    now_draw.width = width
    now_draw.text = prompt.text
    now_draw.draw()
    returns = {"cancel": _("\n取消"), "confirm": _("\n确定")}
    option_ids = {}
    for option in prompt.options:
        now_button = draw.CenterButton(
            f"[{option.label}]", returns[option.option_id], int(width / 3)
        )
        now_button.draw()
        option_ids[now_button.return_text] = option.option_id
    return option_ids[flow_handle.askfor_all(list(option_ids))]


def select_condom(mode: str) -> dict[str, object] | None:
    """
    在调用时导入 condom_panel，并以当前文本宽度和 mode 调用 Condom_Select_Panel.draw。
    Keyword arguments:
    mode -- str，避孕套面板操作类型，可选 hang、take_back、drink 或 squeeze
    Return arguments:
    dict[str, object] | None -- 玩家确认的选择字典，取消时为 None
    """
    from Script.UI.Panel import condom_panel

    return condom_panel.Condom_Select_Panel(width, mode).draw()


def ask_official_option(queue_data: dict[str, Any]) -> int:
    """
    在调用时导入 official_event_panel，并以 queue_data 和当前文本宽度调用 Official_Event_Draw.draw。
    Keyword arguments:
    queue_data -- dict[str, Any]，待决断队列中的单条公务事件字典
    Return arguments:
    int -- 玩家选定的选项配置序号，无可用选项时为 0
    """
    from Script.UI.Panel import official_event_panel

    return official_event_panel.Official_Event_Draw(queue_data, width).draw()


def choose_sex_position(sex_type: int, change_position: bool) -> None:
    """
    在调用时导入 sex_position_panel。
    以导入时读取的模块全局 width、sex_type 与 change_position 构造 Sex_Position_Panel。
    随后无参调用该实例的 draw 方法。
    Keyword arguments:
    sex_type -- int，性交类型编号（1 阴道、2 子宫口、3 子宫、4 肛门、5 尿道）
    change_position -- bool，是否为切换体位
    Return arguments:
    None -- 无返回值
    """
    from Script.UI.Panel import sex_position_panel

    sex_position_panel.Sex_Position_Panel(
        width, sex_type, change_position
    ).draw()


instruct_hooks.on_prompts(select_condom, ask_official_option)
instruct_hooks.on_sex_position(choose_sex_position)
