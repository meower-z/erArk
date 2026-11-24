"""
Tk 界面向后端登记的回调函数
===========================
本模块向 playthrough 登记设定表补齐时的提示绘制函数。
本模块向 save_load.reset 登记 new_round 与 panel 两步的界面实现。
本模块向 gameplay_resolution.ui_hooks 登记提示文本绘制函数与分隔线绘制函数。
本模块同时向 gameplay_resolution.ui_hooks 登记面板切换函数与隐奸中显示非H指令的开关查询函数。
本模块向 gameplay_resolution.achievement_service 登记新达成成就的提示绘制函数。
本模块向 gameplay_resolution.ejaculation_service 登记射精文本的绘制函数。
本模块不登记内核钩子。
load_order 导入本模块时完成上述登记。
"""

from collections.abc import Mapping

from Script.Config import normal_config
from Script.Core import constant
from Script.Kernel import core
from Script.Modules.domains import playthrough
from Script.Modules.gameplay_resolution import achievement_service
from Script.Modules.gameplay_resolution import ejaculation_service, ui_hooks
from Script.Modules.save_load import reset
from Script.UI.Moudle import draw, view


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
    按参数构造 WaitDraw 或 NormalDraw 并绘制一条提示文本。
    Keyword arguments:
    text -- str，要绘制的提示文本
    wait -- bool，为真时使用 WaitDraw 等待玩家确认，否则使用 NormalDraw
    style -- str | None，文本样式名，为 None 时保留绘制类默认样式
    use_text_width -- bool，为真时将绘制宽度设为 normal_config.config_normal.text_width
    Return arguments:
    None -- 无返回值
    """
    now_draw = draw.WaitDraw() if wait else draw.NormalDraw()
    if use_text_width:
        now_draw.width = normal_config.config_normal.text_width
    now_draw.text = text
    if style is not None:
        now_draw.style = style
    now_draw.draw()


@ui_hooks.on_divider
def draw_divider(char: str) -> None:
    """
    按 normal_config.config_normal.text_width 构造 LineDraw 并绘制一条分隔线。
    Keyword arguments:
    char -- str，用于重复绘制分隔线的字符
    Return arguments:
    None -- 无返回值
    """
    draw.LineDraw(char, normal_config.config_normal.text_width).draw()


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
