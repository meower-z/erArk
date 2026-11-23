"""课程表面板模块：只定义缓存、翻译函数与换行绘制对象，课程表面板类整段写在注释里"""

from types import FunctionType
from Script.Core import get_text
from Script.UI.Moudle import draw

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
