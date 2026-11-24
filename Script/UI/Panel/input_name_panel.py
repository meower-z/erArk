"""角色取名输入框，负责询问并循环校验角色名"""

from Script.Config import normal_config
from Script.Design import character
from Script.UI.Moudle import draw, panel

line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


def input_name_func(ask_text: str) -> str:
    """
    先绘出换行与等号分隔线，再通过 panel.AskForOneMessage 展示询问文本并读取输入。
    输入框将单次输入限制在 10 个英文字符宽度以内。
    每次读取后调用 character.validate_character_name 校验输入。
    校验返回提示文本时，本函数绘出该提示并重新询问。
    校验返回 None 时，本函数返回该角色名。
    Keyword arguments:
    ask_text -- str，询问文本
    Return arguments:
    str -- 通过校验的角色名
    """
    ask_name_panel = panel.AskForOneMessage()
    ask_name_panel.set(ask_text, 10)
    line_feed.draw()
    line = draw.LineDraw("=", width=window_width)
    line.draw()
    while True:
        now_name = ask_name_panel.draw()
        error = character.validate_character_name(now_name)
        if error is None:
            return now_name
        error_draw = draw.NormalDraw()
        error_draw.text = error
        error_draw.draw()
