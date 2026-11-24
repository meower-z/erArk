"""
Tk 界面向后端登记的回调函数
===========================
本模块向 playthrough 登记设定表补齐时的提示绘制函数。
本模块向 save_load.reset 登记 new_round 与 panel 两步的界面实现。
本模块向 gameplay_resolution.ui_hooks 登记提示文本、数值变化与图片绘制函数，
以及面板切换函数、确认提问函数与隐奸中显示非H指令开关查询函数。
本模块向 gameplay_resolution.achievement_service 登记新达成成就的提示绘制函数。
本模块向 gameplay_resolution.ejaculation_service 登记射精文本的绘制函数。
本模块向 gameplay_resolution.hidden_sex_service 登记隐奸被发现面板的绘制函数。
本模块向 gameplay_resolution.pregnancy_hooks 登记生产与破壳面板绘制函数。
本模块不登记内核钩子。
load_order 导入本模块时完成上述登记。
"""

from collections.abc import Mapping

from Script.Config import normal_config
from Script.Core import constant, flow_handle, get_text
from Script.Kernel import core
from Script.Modules.domains import playthrough
from Script.Modules.gameplay_resolution import achievement_service
from Script.Modules.gameplay_resolution import ejaculation_service, ui_hooks
from Script.Modules.gameplay_resolution import hidden_sex_service
from Script.Modules.gameplay_resolution import pregnancy_hooks
from Script.Modules.save_load import reset
from Script.Modules.tk_ui.event_stream_adapter import STREAM
from Script.Protocol.delta_events import DeltaEntry, DeltaEvent
from Script.Protocol.narrative_events import NarrativeEvent, TextBlock, TextSpan
from Script.UI.Moudle import draw, view

_ = get_text._
""" 文本翻译函数，指向 get_text._。 """


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
    text: str, *, wait: bool, style: str | None, use_text_width: bool
) -> None:
    """
    将提示文本包装为单段落 NarrativeEvent 并交由 STREAM 绘制。
    Keyword arguments:
    text -- str，要绘制的提示文本
    wait -- bool，为真时使用 WaitDraw 等待玩家确认，否则使用 NormalDraw
    style -- str | None，文本样式名，为 None 时保留绘制类默认样式
    use_text_width -- bool，为真时将绘制宽度设为 normal_config.config_normal.text_width
    Return arguments:
    None -- 无返回值
    """
    STREAM.render(
        NarrativeEvent(
            STREAM.meta("ui_hooks.notice"),
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
) -> None:
    """
    将数值变化项包装为 DeltaEvent 并交由 STREAM 绘制。
    Keyword arguments:
    entries -- tuple[DeltaEntry, ...]，数值变化项元组
    source -- str，事件来源标识
    summary_text -- str | None，整段显示文本，为 None 时由适配器按变化项生成
    wait -- bool，为真时使用 WaitDraw 等待玩家确认，否则使用 NormalDraw
    use_text_width -- bool，为真时将绘制宽度设为 normal_config.config_normal.text_width
    Return arguments:
    None -- 无返回值
    """
    STREAM.render(
        DeltaEvent(
            STREAM.meta(source),
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


@ui_hooks.on_confirm
def draw_confirm(text: str) -> bool:
    """
    依次使用 WaitDraw 绘制提问文本，并绘制两次换行、[确定]与[返回]两个居中按钮及一次换行。
    两个居中按钮的宽度均取 int(normal_config.config_normal.text_width / 2)。
    绘制完成后调用 flow_handle.askfor_all 等待玩家在两个按钮间选择。
    Keyword arguments:
    text -- str，要向玩家提问的文本
    Return arguments:
    bool -- 选中结果等于[确定]按钮响应文本时返回 True，否则返回 False
    """
    line_feed = draw.NormalDraw()
    line_feed.text = "\n"
    line_feed.width = 1
    ask_draw = draw.WaitDraw()
    ask_draw.text = text
    ask_draw.draw()
    line_feed.draw()
    line_feed.draw()
    width = normal_config.config_normal.text_width
    yes_draw = draw.CenterButton(_("[确定]"), _("确定"), int(width / 2))
    yes_draw.draw()
    back_draw = draw.CenterButton(_("[返回]"), _("返回"), int(width / 2))
    back_draw.draw()
    line_feed.draw()
    answer = flow_handle.askfor_all(
        [yes_draw.return_text, back_draw.return_text]
    )
    return answer == yes_draw.return_text


@achievement_service.on_unlocked
def draw_unlocked(new_ids: list[int]) -> None:
    """
    调用 achievement_panel.draw_achievement_notice 绘制新达成成就的获得提示。
    Keyword arguments:
    new_ids -- list[int]，新达成的成就编号列表
    Return arguments:
    None -- 无返回值
    """
    from Script.UI.Panel import achievement_panel

    achievement_panel.draw_achievement_notice(new_ids)


@ejaculation_service.on_banner
def draw_banner(text: str) -> None:
    """
    按六步顺序绘制射精文本：换行、分隔线、换行、WaitDraw 文本与两次换行。
    分隔线与 WaitDraw 均采用 normal_config.config_normal.text_width，WaitDraw 使用 semen 样式并等待玩家确认。
    Keyword arguments:
    text -- str，要绘制的射精文本
    Return arguments:
    None -- 无返回值
    """
    width = normal_config.config_normal.text_width
    line_feed = draw.NormalDraw()
    line_feed.text = "\n"
    line_feed.width = 1
    line_feed.draw()
    draw.LineDraw("-", width).draw()
    line_feed.draw()
    now_draw = draw.WaitDraw()
    now_draw.text = text
    now_draw.width = width
    now_draw.style = "semen"
    now_draw.draw()
    line_feed.draw()
    line_feed.draw()


@hidden_sex_service.on_discovered
def draw_hidden_sex_discovered(
    discoverer_id: int, from_hidden_sex_flag: bool
) -> None:
    """
    按配置文本宽度创建并绘制 sex_be_discovered_panel.Sex_Be_Discovered_Panel 面板。
    Keyword arguments:
    discoverer_id -- int，发现者角色编号
    from_hidden_sex_flag -- bool，是否由隐奸被发现触发
    Return arguments:
    None -- 无返回值
    """
    from Script.System.Sex_System import sex_be_discovered_panel

    sex_be_discovered_panel.Sex_Be_Discovered_Panel(
        normal_config.config_normal.text_width,
        discoverer_id,
        from_hidden_sex_flag=from_hidden_sex_flag,
    ).draw()


@pregnancy_hooks.on_born
def draw_born_event(
    character_id: int,
    *,
    egg_mode: bool = False,
    egg_id_list: list[int] | None = None,
) -> None:
    """
    按传入参数构造 born_event_panel.Born_Panel 并调用其 draw 方法绘制生产或破壳事件面板。
    Keyword arguments:
    character_id -- int，母亲角色编号
    egg_mode -- bool，为 True 时表示卵生破壳模式，默认为 False
    egg_id_list -- list[int] | None，本次破壳的卵编号列表，默认为 None
    Return arguments:
    None -- 无返回值
    """
    from Script.System.Pregnancy_System import born_event_panel

    born_event_panel.Born_Panel(
        character_id, egg_mode=egg_mode, egg_id_list=egg_id_list
    ).draw()
