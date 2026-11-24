"""富文本绘制对象与绘制面板构造"""

from Script.Core.rich_text import get_rich_text_print, remove_rich_cache
from Script.UI.Moudle import draw, panel


def get_rich_text_draw_panel(now_text: str) -> panel.LeftDrawTextListPanel:
    """
    根据带富文本标签的字符串构造左侧富文本绘制面板。
    Keyword arguments:
    now_text -- 含有富文本标签的原始文本
    Return arguments:
    panel.LeftDrawTextListPanel -- 包含绘制列表与总宽度的面板对象
    """
    now_draw = panel.LeftDrawTextListPanel()
    rich_text_draw_list = get_rich_text_draw_list(now_text)
    if rich_text_draw_list:
        now_draw.draw_list.append(rich_text_draw_list)
        for rich_draw in rich_text_draw_list:
            now_draw.width += len(rich_draw.text)
    return now_draw


def get_rich_text_draw_list(
    now_text: str, base_style: str = "standard", wait_flag: bool = False
) -> list:
    """
    将带富文本标签的字符串切分并合并为绘制对象列表。
    Keyword arguments:
    now_text -- 带富文本标签的字符串
    base_style -- 无富文本样式时的默认样式，默认为 "standard"
    wait_flag -- 遇到换行时是否使用等待绘制对象，默认为 False
    Return arguments:
    list -- 合并连续同样式片段后的绘制对象列表
    """
    rich_text_draw_list: list[draw.NormalDraw] = []
    if not now_text:
        return rich_text_draw_list
    if now_text == "\n":
        now_rich_draw = draw.NormalDraw()
        now_rich_draw.text = "\n"
        now_rich_draw.style = base_style
        rich_text_draw_list.append(now_rich_draw)
        return rich_text_draw_list
    if now_text and now_text[-1] != "\n":
        now_text += "\n"
    now_style_list = get_rich_text_print(now_text, base_style)
    new_x_list = remove_rich_cache(now_text)
    while len(new_x_list) > 0:
        if new_x_list[0] == "\n":
            lf_draw = (
                draw.LineFeedWaitDraw() if wait_flag else draw.NormalDraw()
            )
            lf_draw.text = "\n"
            lf_draw.style = now_style_list[0]
            rich_text_draw_list.append(lf_draw)
            now_style_list = now_style_list[1:]
            new_x_list = new_x_list[1:]
            continue

        now_rich_draw = draw.NormalDraw()
        now_rich_draw.text = new_x_list[0]
        now_rich_draw.style = now_style_list[0]
        now_style_list = now_style_list[1:]
        new_x_list = new_x_list[1:]

        while (
            len(new_x_list) > 0
            and now_style_list[0] == now_rich_draw.style
            and new_x_list[0] != "\n"
        ):
            now_rich_draw.text += new_x_list[0]
            now_style_list = now_style_list[1:]
            new_x_list = new_x_list[1:]

        if wait_flag and "\n" in now_rich_draw.text:
            tmp_text = now_rich_draw.text
            tmp_style = now_rich_draw.style
            now_rich_draw = draw.LineFeedWaitDraw()
            now_rich_draw.text = tmp_text
            now_rich_draw.style = tmp_style

        rich_text_draw_list.append(now_rich_draw)
    return rich_text_draw_list
