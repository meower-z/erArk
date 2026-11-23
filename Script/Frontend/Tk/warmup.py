"""Tk 前端启动阶段的常用字形、字体变体与进度条图片预热模块。"""

import time
from collections.abc import Iterable

from Script.Config import game_config
from Script.Core import constant, get_text, perf_hook
from Script.Frontend.Tk import image_cache
from Script.Frontend.Tk.window import Window

MAP_LINE_QUOTA = 40
"""预热样本中直接收录的非空地图行数量上限。"""
GLYPHS_PER_LINE = 60
"""去重字形合并为预热样本行时每行的最大字符数。"""
FIXED_GLYPHS = (
    "场景当前位置的角色一览:收起展开状态栏服装身体图片详细污浊(锁)预热样本："
    "体力气力理智熟练欲望快感绝顶0123456789ABCabc[]（），。！？→○◆·—/%+-|"
)
"""主界面常见词、数字与标点组成的固定预热字符集。"""
VARIANT_SAMPLE = "预热字体变体样本0123456789体力气力理智"
"""用于预热粗体、下划线与斜体变体的样本字符串。"""
VARIANTS = (("bold",), ("underline",), ("italic",))
"""预热阶段需要额外测量的字体样式修饰元组序列。"""


def _map_lines(glyphs: set[str]) -> list[str]:
    lines: list[str] = []
    for map_data in constant.map_data.values():
        map_draw = getattr(map_data, "map_draw", None)
        if map_draw is None:
            continue
        for draw_line in map_draw.draw_text:
            text = "".join(
                getattr(item, "text", "") for item in draw_line.draw_list
            )
            if not text.strip():
                continue
            glyphs.update(text)
            if len(lines) < MAP_LINE_QUOTA:
                lines.append(text)
    return lines


def _config_names() -> Iterable[str]:
    for source in (
        game_config.config_character_state,
        game_config.config_clothing_type,
        game_config.config_organ,
        game_config.config_body_part,
        game_config.config_instruct_type,
        game_config.config_instruct_sex_type,
    ):
        for config_data in source.values():
            name = getattr(config_data, "name", "")
            if name:
                yield get_text._(name)
    for name in constant.handle_instruct_name_data.values():
        yield get_text._(name)


def sample_lines() -> list[str]:
    """
    收集地图行、固定字符集与配置译名中的去重字形并拼装为预热样本行

    参数：无

    返回值类型：list[str] -- 待写入文本框的预热样本行列表
    """
    glyphs: set[str] = set()
    try:
        lines = _map_lines(glyphs)
    except Exception:
        lines = []
    glyphs.update(FIXED_GLYPHS)
    try:
        for name in _config_names():
            glyphs.update(name)
    except Exception:
        pass
    glyphs.difference_update("\n\r\t\x00 ")
    ordered = sorted(glyphs)
    lines.extend(
        "".join(ordered[index : index + GLYPHS_PER_LINE])
        for index in range(0, len(ordered), GLYPHS_PER_LINE)
    )
    return lines


def _bar_images() -> list[str]:
    try:
        names = {
            name
            for bar in game_config.config_bar.values()
            for name in (bar.ture_bar, bar.null_bar)
        }
    except Exception:
        return []
    return sorted(name for name in names if name in image_cache.image_data)


def warm_up(window: Window, family: str, size: int) -> None:
    """
    向文本框写入样本行、字体变体与进度条图片并触发同步度量，打印耗时后清理样本内容与临时标签

    参数：
    window (Window) -- Tk 主窗口对象
    family (str) -- 预热使用的字体名称
    size (int) -- 预热使用的字号

    返回值类型：None
    """
    textbox = window.textbox
    tags = [f"warm_up_{index}" for index in range(len(VARIANTS) + 1)]
    textbox.tag_configure(tags[0], font=(family, size))
    for line in sample_lines():
        textbox.insert("end", line + "\n", (tags[0],))
    for tag, variant in zip(tags[1:], VARIANTS, strict=True):
        textbox.tag_configure(tag, font=(family, size, *variant))
        textbox.insert("end", VARIANT_SAMPLE + "\n", (tag,))
    for name in _bar_images():
        textbox.image_create("end", image=image_cache.image_data[name])
    textbox.insert("end", "\n")
    start = time.perf_counter()
    try:
        textbox.tk.call(str(textbox), "sync")
    except Exception:
        pass
    duration = time.perf_counter() - start
    print(f"常用字符预热完毕，耗时 {duration:.2f} 秒")
    if perf_hook.enabled:
        perf_hook.hook_time("gui.metrics_sync", duration)
    textbox.delete("1.0", "end")
    for tag in tags:
        textbox.tag_delete(tag)
