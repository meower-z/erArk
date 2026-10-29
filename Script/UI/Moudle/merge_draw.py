"""
定义左对齐合并绘制类 LeftMergeDraw。
"""

from __future__ import annotations

from collections.abc import Sized
from typing import TYPE_CHECKING

from Script.Core import text_handle
from Script.UI.Moudle.draw import NormalDraw

if TYPE_CHECKING:
  from Script.UI.Moudle.draw import SizedDrawable


class LeftMergeDraw:
  """
  按左对齐方式顺序绘制 draw_list 中的绘制对象。
  参数 width (float)：左对齐的目标宽度。
  """

  def __init__(self, width: float) -> None:
    """
    初始化左对齐合并绘制实例。
    参数 width (float)：左对齐的目标宽度。
    返回 (None)：无返回值。
    """
    self.width: float = width
    """
    左对齐的目标宽度。
    绘制对象的总宽度可以超过该值。
    """
    self.draw_list: list[SizedDrawable] = []
    """
    待绘制的绘制对象列表。
    列表元素需支持 draw() 和 len()。
    """
    self.column: int = 0
    """
    当前绘制逻辑未使用的列数属性。
    """

  def __len__(self) -> int:
    """
    以目标宽度作为本对象的长度。
    返回 (int)：int(self.width)。
    """
    return int(self.width)

  def __gt__(self, other: Sized) -> int:
    """
    判断本对象的长度是否大于 other 的长度。
    参数 other (Sized)：支持 len() 的对象。
    返回 (bool)：比较结果。
    """
    return int(len(self)) > int(len(other))

  def draw(self) -> None:
    """
    按列表顺序绘制 draw_list 中的绘制对象。
    随后绘制一段左对齐补位空格。
    返回 (None)：无返回值。
    """
    now_width = 0
    for value in self.draw_list:
      now_width += len(value)
    now_text = " " * now_width
    fix_text = text_handle.align(now_text, "left", True, 1, self.width)
    fix_draw = NormalDraw()
    fix_draw.text = fix_text
    fix_draw.width = len(fix_text)
    for value in self.draw_list:
      value.draw()
    now_width = fix_draw.width * 2 + now_width
    if now_width < self.width:
      fix_draw.text += int(self.width - now_width) * " "
    fix_draw.draw()
