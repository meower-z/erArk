"""
Tk 界面向后端登记的回调函数
===========================
本模块向 playthrough 登记设定表补齐时的提示绘制函数。
本模块向 save_load.reset 登记 new_round 与 panel 两步的界面实现。
本模块不登记内核钩子。load_order 导入本模块时完成上述登记。
"""

from collections.abc import Mapping

from Script.Core import constant
from Script.Kernel import core
from Script.Modules.domains import playthrough
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
