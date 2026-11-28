"""
射精选择的 Tk 界面回调
======================
load_order 导入本模块时经 choice_prompts.renderer
登记 draw_target_choice 与 draw_part_choice。
两函数分别渲染 TARGET_PROMPT_ID 与 PART_PROMPT_ID 对应的选项界面。
本模块不登记内核钩子，也不直接读写游戏状态。
"""

from Script.Config import normal_config
from Script.Core import flow_handle
from Script.Modules.gameplay_resolution import ejaculation_service
from Script.Modules.tk_ui import choice_prompts
from Script.Protocol.modal_prompts import ChoiceOption, ChoicePrompt
from Script.UI.Moudle import draw


def _line_feed() -> None:
    """
    绘制一个文本为 "\n"、宽度为 1 的 NormalDraw 换行对象。
    Return arguments:
    None -- 无返回值
    """
    line_feed = draw.NormalDraw()
    line_feed.text = "\n"
    line_feed.width = 1
    line_feed.draw()


@choice_prompts.renderer(ejaculation_service.TARGET_PROMPT_ID)
def draw_target_choice(prompt: ChoicePrompt) -> str:
    """
    绘制射精对象选择的标题栏、各对象居中按钮与一次换行，并返回所选 option_id。
    每个按钮以 option.label 为显示文本，以首个 "]" 后的角色名为响应文本，
    宽度为 (len(option.label) + 1) * 3，并绑定记录该项 option_id 的命令。
    等待 flow_handle.askfor_all 执行命中按钮的命令后，返回记录的 option_id。
    按钮名称重复时，后绘制按钮的命令绑定生效。
    Keyword arguments:
    prompt -- ChoicePrompt，待绘制的射精对象选项提示
    Return arguments:
    str -- 玩家所选选项的 option_id
    """
    draw.TitleLineDraw(
        prompt.title, normal_config.config_normal.text_width
    ).draw()
    returns = []
    picked: list[str] = []
    for option in prompt.options:
        button = draw.CenterButton(
            option.label,
            option.label.partition("]")[2],
            (len(option.label) + 1) * 3,
            cmd_func=picked.append,
            args=(option.option_id,),
        )
        button.draw()
        returns.append(button.return_text)
    _line_feed()
    flow_handle.askfor_all(returns)
    return picked[-1]


@choice_prompts.renderer(ejaculation_service.PART_PROMPT_ID)
def draw_part_choice(prompt: ChoicePrompt) -> str:
    """
    绘制射精部位选择的标题栏与分组按钮，
    经 flow_handle.askfor_all 读取玩家输入并返回所选 option_id。
    body 与 cloth 分组按全部槽位计数，只绘制可用项，若可用项恰为第 8 的倍数槽位则换行。
    body 组后追加换行，egg 与 normal 分组前各追加换行，egg 每绘制 4 个换行。
    Keyword arguments:
    prompt -- ChoicePrompt，待绘制的射精部位选项提示
    Return arguments:
    str -- 玩家所选选项的 option_id
    """
    draw.TitleLineDraw(
        prompt.title, normal_config.config_normal.text_width
    ).draw()
    groups: dict[str, list[ChoiceOption]] = {}
    for option in prompt.options:
        groups.setdefault(option.option_id.partition("_")[0], []).append(option)
    returns = []
    option_ids = {}

    def button(option: ChoiceOption, return_text: str) -> None:
        """
        按 (len(option.label) + 1) * 2 宽度绘制单个居中按钮，
        并记录其响应文本到 returns 与 option_ids。
        Keyword arguments:
        option -- ChoiceOption，待绘制的选项对象
        return_text -- str，按钮响应文本
        Return arguments:
        None -- 无返回值
        """
        now = draw.CenterButton(
            option.label, return_text, (len(option.label) + 1) * 2
        )
        now.draw()
        returns.append(now.return_text)
        option_ids[now.return_text] = option.option_id

    for kind, prefix in (("body", "\n"), ("cloth", "")):
        for count, option in enumerate(groups.get(kind, ()), 1):
            if option.availability == "open":
                button(option, prefix + option.label.partition("]")[2])
                if count % 8 == 0:
                    _line_feed()
        if kind == "body" and kind in groups:
            _line_feed()
    if "egg" in groups:
        _line_feed()
        for count, option in enumerate(groups["egg"], 1):
            button(option, option.label)
            if count % 4 == 0:
                _line_feed()
    if "normal" in groups:
        _line_feed()
        button(groups["normal"][0], groups["normal"][0].label)
    return option_ids[flow_handle.askfor_all(returns)]
