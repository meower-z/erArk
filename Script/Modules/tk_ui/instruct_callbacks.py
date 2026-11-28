"""
tk_ui 的指令界面回调
====================
本模块导入时仅经 instruct_hooks.on_prompts 登记 select_condom 槽位。
本模块导入时经 choice_prompts.renderer 登记 ask_close_door、ask_sex_class_ability、
confirm_poor_music、ask_official_option 与 choose_sex_position 五个选项渲染函数。
select_condom 在调用时导入 condom_panel。
"""

from types import FunctionType

from Script.Config import normal_config
from Script.Core import constant, flow_handle, get_text, py_cmd, text_handle
from Script.Modules.gameplay_resolution import instruct_hooks
from Script.Modules.tk_ui import choice_prompts, player_pick
from Script.Protocol.modal_prompts import ChoicePrompt
from Script.UI.Moudle import draw, panel, view

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


@choice_prompts.renderer(instruct_hooks.OFFICIAL_OPTION_PROMPT_ID)
def ask_official_option(prompt: ChoicePrompt) -> str:
    """
    绘制公务事件选项界面并读取玩家选择。
    依次绘制宽度为 1 的换行、prompt.title 小标题线与 prompt.text 正文，
    再复制 prompt.options 并以 player_pick.ui_random.shuffle 洗牌。
    洗牌包含置灰的不可选项，以免选项位置泄露配置表原序。
    非 "open" 项以 deep_gray 绘制无编号文本并附带非空 note。
    "open" 项依次绘制 LeftButton 与换行，按钮编号仅作显示序号。
    末尾绘制 "-" 分隔线，经 flow_handle.askfor_all 读取选择并调用 py_cmd.clr_cmd，返回所选项的 option_id。
    Keyword arguments:
    prompt -- ChoicePrompt，公务事件选项提示
    Return arguments:
    str -- 玩家所选选项的 option_id
    """
    line_feed = draw.NormalDraw()
    line_feed.text = "\n"
    line_feed.width = 1
    line_feed.draw()
    draw.LittleTitleLineDraw(prompt.title, width, count_title_width=True).draw()
    text_draw = draw.NormalDraw()
    text_draw.width = width
    text_draw.text = prompt.text
    text_draw.draw()
    shown = list(prompt.options)
    player_pick.ui_random.shuffle(shown)
    option_ids = {}
    for option in shown:
        if option.availability != "open":
            gray_draw = draw.NormalDraw()
            gray_draw.width = width
            gray_draw.style = "deep_gray"
            gray_draw.text = _("   ○ {0}").format(option.label)
            if option.note:
                gray_draw.text += _("（{0}）").format(option.note)
            gray_draw.text += "\n"
            gray_draw.draw()
            continue
        button_text = text_handle.id_index(len(option_ids) + 1) + option.label
        now_draw = draw.LeftButton(
            button_text, f"\nOEVENT_{option.option_id}", width
        )
        now_draw.draw()
        line_feed.draw()
        option_ids[now_draw.return_text] = option.option_id
    draw.LineDraw("-", width).draw()
    answer = flow_handle.askfor_all(list(option_ids))
    py_cmd.clr_cmd()
    return option_ids[answer]


@choice_prompts.renderer(instruct_hooks.SEX_POSITION_PROMPT_ID)
def choose_sex_position(prompt: ChoicePrompt) -> str:
    """
    绘制性交体位选择界面并读取玩家选择。
    以 width 绘制 prompt.title 标题栏与换行，再按 prompt.options 顺序逐项绘制。
    "back" 项先绘两次换行，再绘显示为 f"[{option.label}]"、
    返回键为 option.label 的 CenterButton。
    其余 "open" 项绘返回键为 option_id 的 LeftButton。
    "current" 与 "blocked" 项分别以 gold_enrod 与 deep_gray 样式绘 NormalDraw 文本。
    每项末尾绘一次换行。
    经 askfor_all 读取选择后，两条退出路径均将 view.now_panel_id 置为 IN_SCENE
    并返回 option_id。
    Keyword arguments:
    prompt -- ChoicePrompt，性交体位选项提示
    Return arguments:
    str -- 玩家所选选项的 option_id
    """
    line_feed = draw.NormalDraw()
    line_feed.text = "\n"
    line_feed.width = 1
    draw.TitleLineDraw(prompt.title, width).draw()
    line_feed.draw()
    styles = {"current": "gold_enrod", "blocked": "deep_gray"}
    option_ids = {}
    for option in prompt.options:
        if option.option_id == "back":
            line_feed.draw()
            line_feed.draw()
            back_draw = draw.CenterButton(
                f"[{option.label}]", option.label, width
            )
            back_draw.draw()
            option_ids[back_draw.return_text] = option.option_id
        elif option.availability == "open":
            button_draw = draw.LeftButton(option.label, option.option_id, width)
            button_draw.draw()
            option_ids[button_draw.return_text] = option.option_id
        else:
            text_draw = draw.NormalDraw()
            text_draw.text = option.label
            text_draw.style = styles[option.availability]
            text_draw.draw()
        line_feed.draw()
    answer = flow_handle.askfor_all(list(option_ids))
    view.now_panel_id = constant.Panel.IN_SCENE
    return option_ids[answer]


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


instruct_hooks.on_prompts(select_condom)
