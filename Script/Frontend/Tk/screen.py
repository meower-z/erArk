"""根据屏幕分辨率与配置计算前端窗口尺寸、字号及 Tk DPI 缩放系数的纯计算模块。"""

from Script.Core import game_type
from Script.Protocol import FrontendInitConfig

SCREEN_MARGIN = 30
"""相对屏幕分辨率计算最大窗口宽高时预留的像素边距。"""


def init_config(
    normal: game_type.NormalConfig, screen_width: int, screen_height: int
) -> FrontendInitConfig:
    """
    将配置中的窗口尺寸钳制在屏幕可用范围内并计算字号，生成前端初始配置

    参数：
    normal (game_type.NormalConfig) -- 游戏基础配置对象
    screen_width (int) -- 屏幕像素宽度
    screen_height (int) -- 屏幕像素高度

    返回值类型：FrontendInitConfig -- 钳制后的窗口尺寸、文本宽度、字号与背景色配置
    """
    width = min(normal.window_width, screen_width - SCREEN_MARGIN)
    height = min(normal.window_hight, screen_height - SCREEN_MARGIN)
    return FrontendInitConfig(
        window_width=width,
        window_height=height,
        text_width=normal.text_width,
        font_size=int(width / normal.text_width) * 2,
        background=normal.background,
    )


def scaling(tk_dpi: int, system_dpi: float) -> float:
    """
    计算传给 Tk `tk scaling` 命令的缩放系数

    参数：
    tk_dpi (int) -- 配置中手动指定的 DPI 数值，大于 0 时优先采用
    system_dpi (float) -- Tk 测得的系统每英寸像素数

    返回值类型：float -- Tk 缩放系数
    """
    if tk_dpi > 0:
        return tk_dpi / 100.0
    return system_dpi / 96.0
