# -*- coding: UTF-8 -*-
"""
绘制捕获与回放

install() 时给 NormalDraw / WaitDraw / LineFeedWaitDraw 的 draw 各套一层常驻薄包装（只套一次）：
- 有捕获窗口时，把 (绘制类, text, style, width, tooltip) 记进最内层窗口的列表，不绘制
- 没有捕获窗口时，调用保存下来的原 draw
窗口用 capture_into() 开关，可以嵌套，内层的绘制只进内层列表。
draw_live() 直接调用保存的原 draw，不论此刻有没有窗口都会真正画出来。

只接管这三个类：口上、刻印、素质、成就提示都只产生这三种绘制对象。
事件面板 DrawEventTextPanel 自己覆写了 draw，不经过这里，事件照常原地显示、原地交互——这是有意的。
交互面板（射精面板、发现群交面板等）的按钮也不是这三个类，不会被捕获，否则会卡在等待输入。
记录只存值不存对象：绘制系统里 line_feed 等模块级单例会被反复复用，存对象会被后来的改动串改。
"""
import functools
from contextlib import contextmanager
from typing import Dict, Iterable, List, Tuple

DrawItem = Tuple[type, str, str, int, str]
""" 一条被捕获的绘制：(绘制类, text, style, width, tooltip) """

_stack: List[List[DrawItem]] = []
""" 捕获窗口栈，栈顶是最内层窗口的目标列表 """
_originals: Dict[type, object] = {}
""" 绘制类 -> 套包装之前的 draw """


def _wrap(draw_class: type):
    """
    生成某个绘制类的常驻包装
    Keyword arguments:
    draw_class -- 绘制类
    Return arguments:
    function -- 新的 draw
    """
    original = draw_class.draw

    @functools.wraps(original)
    def draw(self):
        if _stack:
            _stack[-1].append((type(self), self.text, self.style, self.width, self.tooltip))
            return None
        return original(self)

    _originals[draw_class] = original
    return draw


def install_draw_wrappers(draw_classes: Iterable[type]) -> None:
    """
    给绘制类套上常驻包装；已经套过的类跳过
    Keyword arguments:
    draw_classes -- 要接管的绘制类
    Return arguments:
    None
    """
    for draw_class in draw_classes:
        if draw_class in _originals:
            continue
        draw_class.draw = _wrap(draw_class)


@contextmanager
def capture_into(target: list):
    """
    开一个捕获窗口：窗口内三个绘制类的 draw 只记录进 target
    Keyword arguments:
    target -- 记录写入的列表
    Return arguments:
    上下文管理器
    """
    _stack.append(target)
    try:
        yield target
    finally:
        _stack.pop()


def _rebuild(item: DrawItem):
    """
    按记录新建一个绘制对象
    Keyword arguments:
    item -- 捕获记录
    Return arguments:
    绘制对象
    """
    draw_class, text, style, width, tooltip = item
    obj = draw_class()
    obj.text = text
    obj.style = style
    obj.width = width
    obj.tooltip = tooltip
    return obj


def draw_live(items: Iterable[DrawItem]) -> None:
    """
    把捕获的内容原样画出来，绕过所有捕获窗口
    用在"先捕获、拿到结算结果后再决定显示"的地方：决定显示的那一刻可能还处在外层窗口里，不能被外层再捕获一次
    Keyword arguments:
    items -- 捕获记录
    Return arguments:
    None
    """
    for item in items:
        _originals[item[0]](_rebuild(item))


def replay(items: List[DrawItem]) -> None:
    """
    按顺序回放缓冲的保留信息（走正常 draw，调用时不应处在捕获窗口内）
    Keyword arguments:
    items -- 捕获记录
    Return arguments:
    None
    """
    for item in items:
        _rebuild(item).draw()
