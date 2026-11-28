"""
Tk 界面向后端登记的回调函数
===========================
load_order 导入本模块时完成以下登记，本模块不登记内核钩子：
- playthrough：设定表补齐提示。
- save_load.reset：new_round 与 panel 界面实现。
- save_load.style_hooks：文本样式初始化（io_init.init_style）。
- ui_hooks：提示、数值变化、图片、分隔线、清理按钮、富文本口上、逐行等待文本、面板切换、
  隐奸非H开关查询、文本AI处理与主角寻路首段选定。
- choice_prompts：确认提示、忍耐提问、H中被发现选择、普通子事件与多层嵌套子事件的选项渲染。
- hidden_sex_discovered：隐奸与露出模式选择面板邀请。
- settle_hooks：行为结算文本。
"""

from collections.abc import Mapping
from typing import Unpack

from Script.Config import normal_config
from Script.Core import constant, flow_handle, io_init, py_cmd
from Script.Kernel import core
from Script.Modules.domains import playthrough
from Script.Modules.gameplay_resolution import ejaculation_service, ui_hooks
from Script.Modules.gameplay_resolution import hidden_sex_discovered
from Script.Modules.gameplay_resolution import settle_hooks
from Script.Modules.save_load import reset, style_hooks
from Script.Modules.tk_ui import choice_prompts, player_pick
from Script.Modules.tk_ui.event_stream_adapter import STREAM
from Script.Protocol.delta_events import DeltaEntry, DeltaEvent
from Script.Protocol.modal_prompts import ChoicePrompt
from Script.Protocol.narrative_events import (
    EventFacts,
    NarrativeEvent,
    SceneBreak,
    TextBlock,
    TextSpan,
)
from Script.UI.Moudle import draw, rich_text_draw, view


@playthrough.on_filled
def draw_filled(text: str) -> None:
    """
    以金色（gold_enrod 样式）绘制设定表补齐提示文本
    Keyword arguments:
    text -- 要绘制的提示文本
    """
    now_draw = draw.NormalDraw()
    now_draw.style = "gold_enrod"
    now_draw.text = text
    now_draw.draw()


@reset.frontend("new_round")
def build_new_round(
    new: core.GameState, why: Mapping[str, core.JSON]
) -> core.GameState:
    """按继承选择建新周目的缓存"""
    from Script.UI.Panel import new_round

    inherit = why["inherit"]
    if not isinstance(inherit, Mapping):
        raise TypeError(f"inherit {inherit!r} is not a mapping")
    new_round.setup(inherit)
    return new


@reset.frontend("panel")
def back_to_scene(
    new: core.GameState, why: Mapping[str, core.JSON]
) -> core.GameState:
    """回到场景面板，关掉隐奸中显示非H指令的开关"""
    view.now_panel_id = constant.Panel.IN_SCENE
    view.show_non_h_in_hidden_sex = False
    return new


@ui_hooks.on_notice
def draw_notice(
    text: str,
    *,
    wait: bool,
    style: str | None,
    use_text_width: bool,
    **facts: Unpack[EventFacts],
) -> None:
    """
    将提示文本包装为单段落 NarrativeEvent 并交由 STREAM 绘制。
    Keyword arguments:
    text -- str，要绘制的提示文本
    wait -- bool，为真时使用 WaitDraw 等待玩家确认，否则使用 NormalDraw
    style -- str | None，文本样式名，为 None 时保留绘制类默认样式
    use_text_width -- bool，为真时将绘制宽度设为 normal_config.config_normal.text_width
    facts -- EventFacts，可选事件事实关键字参数，传给 STREAM.meta 写入事件元数据
    Return arguments:
    None -- 无返回值
    """
    STREAM.render(
        NarrativeEvent(
            STREAM.meta("ui_hooks.notice", **facts),
            (TextBlock("paragraph", (TextSpan(text),)),),
            pause=wait,
            style=style,
            use_text_width=use_text_width,
        )
    )


@ui_hooks.on_delta
def draw_delta(
    entries: tuple[DeltaEntry, ...],
    *,
    source: str,
    summary_text: str | None,
    wait: bool,
    use_text_width: bool,
    **facts: Unpack[EventFacts],
) -> None:
    """
    将数值变化项包装为 DeltaEvent 并交由 STREAM 绘制。
    Keyword arguments:
    entries -- tuple[DeltaEntry, ...]，数值变化项元组
    source -- str，事件来源标识
    summary_text -- str | None，整段显示文本，为 None 时由适配器按变化项生成
    wait -- bool，为真时使用 WaitDraw 等待玩家确认，否则使用 NormalDraw
    use_text_width -- bool，为真时将绘制宽度设为 normal_config.config_normal.text_width
    facts -- EventFacts，可选事件事实关键字参数，传给 STREAM.meta 写入事件元数据
    Return arguments:
    None -- 无返回值
    """
    STREAM.render(
        DeltaEvent(
            STREAM.meta(source, **facts),
            entries,
            pause=wait,
            use_text_width=use_text_width,
            summary_text=summary_text,
        )
    )


@ui_hooks.on_image
def draw_image(img_name: str) -> None:
    """
    使用 draw.ImageDraw 绘制指定图片。
    Keyword arguments:
    img_name -- str，要绘制的图片名
    Return arguments:
    None -- 无返回值
    """
    draw.ImageDraw(img_name).draw()


@ui_hooks.on_divider
def draw_divider(char: str = "-") -> None:
    """
    将分隔字符包装为 SceneBreak 并交由 STREAM 绘制。
    Keyword arguments:
    char -- str，分隔线平铺字符，默认为 "-"
    Return arguments:
    None -- 无返回值
    """
    STREAM.render(SceneBreak(STREAM.meta("ui_hooks.divider"), char))


style_hooks.on_styles_changed(io_init.init_style)


@ui_hooks.on_clear_buttons
def clear_buttons() -> None:
    """
    调用 py_cmd.clr_cmd 清理全部已绑定命令与默认流程处理函数。
    Return arguments:
    None -- 无返回值
    """
    py_cmd.clr_cmd()


@ui_hooks.on_route_leg
def pick_route_leg(
    behavior_id: str,
    minutes: int,
    state: int,
    fields: dict[str, object],
    args: dict[str, object] | None,
) -> None:
    """
    将主角寻路首段参数转发给 player_pick.choose 以选定行动。
    Keyword arguments:
    behavior_id -- str，本段移动使用的行为编号
    minutes -- int，本段移动所需的分钟数
    state -- int，本段移动开始时写入的角色状态编号
    fields -- dict[str, object]，本段移动开始时写入主角数据的字段映射
    args -- dict[str, object] | None，行动附加参数字典，无附加参数时为 None
    Return arguments:
    None -- 无返回值（player_pick.choose 抛出 player_pick.Chosen 时不返回）
    """
    player_pick.choose(
        behavior_id, minutes, state=state, fields=fields, args=args
    )


@ui_hooks.on_rich_talk
def draw_rich_talk(
    text: str,
    *,
    base_style: str = "standard",
    wait_flag: bool = True,
    trailing_wait: bool = False,
) -> None:
    """
    依次绘制空白换行、按配置文本宽度逐项绘制富文本口上片段，并在需要时追加换行等待。
    Keyword arguments:
    text -- str，要绘制的富文本口上文本
    base_style -- str，无行内标签时的基础样式名，默认为 "standard"
    wait_flag -- bool，为真时在换行处等待玩家确认，默认为 True
    trailing_wait -- bool，为真时在末尾绘制一次带等待的 " \\n"，默认为 False
    Return arguments:
    None -- 无返回值
    """
    line_feed_draw = draw.NormalDraw()
    line_feed_draw.text = "\n"
    line_feed_draw.draw()
    for rich_draw in rich_text_draw.get_rich_text_draw_list(
        text, base_style=base_style, wait_flag=wait_flag
    ):
        rich_draw.width = normal_config.config_normal.text_width
        rich_draw.draw()
    if trailing_wait:
        wait_draw = draw.LineFeedWaitDraw()
        wait_draw.text = " \n"
        wait_draw.draw()


@ui_hooks.on_line_wait_text
def draw_line_wait_text(text: str, style: str) -> None:
    """
    按配置文本宽度使用 draw.LineFeedWaitDraw 以指定样式逐行绘制文本并在每段后等待确认。
    Keyword arguments:
    text -- str，要绘制的文本
    style -- str，文本样式名
    Return arguments:
    None -- 无返回值
    """
    now_draw = draw.LineFeedWaitDraw()
    now_draw.width = normal_config.config_normal.text_width
    now_draw.text = text
    now_draw.style = style
    now_draw.draw()


@ui_hooks.on_panel_switch
def set_panel(panel_id: int) -> None:
    """
    将 view 记录的当前面板编号设为 panel_id。
    Keyword arguments:
    panel_id -- int，目标面板编号
    Return arguments:
    None -- 无返回值
    """
    view.now_panel_id = panel_id


@ui_hooks.on_hidden_sex_show_non_h
def show_non_h_in_hidden_sex() -> bool:
    """
    读取 view 记录的隐奸中显示非H指令的开关并以布尔值返回。
    Return arguments:
    bool -- 当前开关状态对应的布尔值
    """
    return bool(view.show_non_h_in_hidden_sex)


@choice_prompts.renderer(ui_hooks.CONFIRM_PROMPT_ID)
def draw_confirm(prompt: ChoicePrompt) -> str:
    """
    依次使用 WaitDraw 绘制 prompt.text、两次换行、prompt.options 对应的居中按钮及一次换行。
    每个按钮显示 "[{option.label}]"，响应文本为 option.label，宽度为 int(normal_config.config_normal.text_width / 2)。
    绘制完成后调用 flow_handle.askfor_all 等待玩家选择，并返回选中按钮对应的 option_id。
    Keyword arguments:
    prompt -- ChoicePrompt，待绘制的确认选项提示
    Return arguments:
    str -- 玩家所选选项的 option_id
    """
    line_feed = draw.NormalDraw()
    line_feed.text = "\n"
    line_feed.width = 1
    ask_draw = draw.WaitDraw()
    ask_draw.text = prompt.text
    ask_draw.draw()
    line_feed.draw()
    line_feed.draw()
    width = int(normal_config.config_normal.text_width / 2)
    option_ids = {}
    for option in prompt.options:
        button = draw.CenterButton(f"[{option.label}]", option.label, width)
        button.draw()
        option_ids[button.return_text] = option.option_id
    line_feed.draw()
    return option_ids[flow_handle.askfor_all(list(option_ids))]


@ui_hooks.on_text_ai
def use_text_ai(
    character_id: int,
    behavior_id: str,
    original_text: str,
    *,
    translator: bool,
) -> str:
    """
    将参数与 chat_ai_panel.OUTPUT 转发给 handle_chat_ai.judge_use_text_ai。
    在调用时按需导入两模块，避免启动时加载两个客户端库或在配置就绪前读取文本宽度。
    Keyword arguments:
    character_id -- int，角色编号
    behavior_id -- str，行为编号
    original_text -- str，待处理的原始文本
    translator -- bool，为真时以翻译模式处理，为假时以生成模式处理
    Return arguments:
    str -- judge_use_text_ai 返回的最终文本
    """
    from Script.Design import handle_chat_ai
    from Script.UI.Panel import chat_ai_panel

    return handle_chat_ai.judge_use_text_ai(
        character_id,
        behavior_id,
        original_text,
        chat_ai_panel.OUTPUT,
        translator=translator,
    )


@choice_prompts.renderer(ejaculation_service.ENDURE_PROMPT_ID)
def draw_endure_choice(prompt: ChoicePrompt) -> str:
    """
    依次绘制配置文本宽度的 "-" 分隔线、一次换行、同宽 NormalDraw 文本 prompt.text、一次换行、各选项居中按钮与一次换行。
    每个 CenterButton 的显示文本为 "[{option.label}]"，响应文本为 option.label，
    宽度为 int(normal_config.config_normal.text_width / 3)。
    绘制完成后调用 flow_handle.askfor_all 等待玩家选择，并返回选中按钮对应的 option_id。
    Keyword arguments:
    prompt -- ChoicePrompt，待绘制的忍耐射精选项提示
    Return arguments:
    str -- 玩家所选选项的 option_id
    """
    width = normal_config.config_normal.text_width
    line_feed = draw.NormalDraw()
    line_feed.text = "\n"
    line_feed.width = 1
    draw.LineDraw("-", width).draw()
    line_feed.draw()
    ask_draw = draw.NormalDraw()
    ask_draw.text = prompt.text
    ask_draw.width = width
    ask_draw.draw()
    line_feed.draw()
    option_ids = {}
    for option in prompt.options:
        button = draw.CenterButton(
            f"[{option.label}]", option.label, int(width / 3)
        )
        button.draw()
        option_ids[button.return_text] = option.option_id
    line_feed.draw()
    return option_ids[flow_handle.askfor_all(list(option_ids))]


@choice_prompts.renderer(hidden_sex_discovered.DISCOVERED_PROMPT_ID)
def draw_discovered_choice(prompt: ChoicePrompt) -> str:
    """
    按配置文本宽度绘制「H中被发现」标题栏、正文、换行及各选项左对齐按钮与换行。
    随后调用 flow_handle.askfor_all 读取并返回玩家选中的 option_id。
    Keyword arguments:
    prompt -- ChoicePrompt，待绘制的「H中被发现」选项提示
    Return arguments:
    str -- 玩家所选选项的 option_id
    """
    width = normal_config.config_normal.text_width
    line_feed = draw.NormalDraw()
    line_feed.text = "\n"
    line_feed.width = 1
    draw.TitleLineDraw(prompt.title, width).draw()
    info_draw = draw.NormalDraw()
    info_draw.text = prompt.text
    info_draw.draw()
    line_feed.draw()
    for option in prompt.options:
        draw.LeftButton(option.label, option.option_id, width).draw()
        line_feed.draw()
    return flow_handle.askfor_all(
        [option.option_id for option in prompt.options]
    )


@hidden_sex_discovered.on_invite
def draw_discovered_invite(mode: hidden_sex_discovered.InviteMode) -> bool:
    """
    按 mode 在调用时导入并绘制隐奸或露出模式选择面板，传入配置文本宽度与被发现标志。
    返回对应面板的 invite_failed 属性。
    Keyword arguments:
    mode -- hidden_sex_discovered.InviteMode，"hidden" 打开隐奸面板，其余打开露出面板
    Return arguments:
    bool -- 面板记录的邀请是否失败标志
    """
    width = normal_config.config_normal.text_width
    if mode == "hidden":
        from Script.UI.Panel import hidden_sex_panel

        hidden = hidden_sex_panel.Select_Hidden_Sex_Mode_Panel(
            width, sex_be_discovered_flag=True
        )
        hidden.draw()
        return hidden.invite_failed
    from Script.UI.Panel import exhibitionism_sex_panel

    shown = exhibitionism_sex_panel.Select_Exhibitionism_Sex_Mode_Panel(
        width, sex_be_discovered_flag=True
    )
    shown.draw()
    return shown.invite_failed


@settle_hooks.on_settle_text
def draw_settle_text(text: str) -> None:
    """
    经 rich_text_draw.get_rich_text_draw_panel 构造富文本面板并调用其 draw 方法绘制行为结算文本。
    Keyword arguments:
    text -- str，要绘制的行为结算文本
    Return arguments:
    None -- 无返回值
    """
    rich_text_draw.get_rich_text_draw_panel(text).draw()


@choice_prompts.renderer(settle_hooks.SON_EVENT_PROMPT_ID)
def ask_son_event(prompt: ChoicePrompt) -> str:
    """
    在调用时导入 event_option_panel，先绘制一次换行，再调用 ask_event_option 完成普通子事件选项询问。
    Keyword arguments:
    prompt -- ChoicePrompt，待绘制的普通子事件选项提示
    Return arguments:
    str -- 玩家所选选项的 option_id
    """
    from Script.UI.Panel import event_option_panel

    event_option_panel.line_feed.draw()
    return event_option_panel.ask_event_option(prompt)


@choice_prompts.renderer(settle_hooks.NESTED_EVENT_PROMPT_ID)
def ask_nested_event(prompt: ChoicePrompt) -> str:
    """
    在调用时导入 event_option_panel，并调用 ask_event_option 完成多层嵌套子事件选项询问。
    Keyword arguments:
    prompt -- ChoicePrompt，待绘制的多层嵌套子事件选项提示
    Return arguments:
    str -- 玩家所选选项的 option_id
    """
    from Script.UI.Panel import event_option_panel

    return event_option_panel.ask_event_option(prompt)
