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
  按列表顺序绘制 draw_list 中的绘制对象。
  随后绘制一段左对齐补位文本。
  """

  def __init__(self, width: float) -> None:
    """
    创建左对齐合并绘制实例。
    参数 width (float)：左对齐的目标宽度。
    返回 (None)：无返回值。
    """
    self.width: float = width
    """
    左对齐补位所依据的目标宽度。
    """
    self.draw_list: list[SizedDrawable] = []
    """
    draw() 依次绘制的绘制对象列表。
    """
    self.column: int = 0
    """
    列数属性。
    本类的方法不读取该属性。
    """

  def __len__(self) -> int:
    """
    把目标宽度的整数值作为本对象的长度。
    返回 (int)：int(self.width) 的结果。
    """
    return int(self.width)

  def __gt__(self, other: Sized) -> int:
    """
    判断本对象的长度是否大于 other 的长度。
    参数 other (Sized)：可用 len() 取长度的对象。
    返回 (bool)：比较结果。
    """
    return int(len(self)) > int(len(other))

  def draw(self) -> None:
    """
    按列表顺序绘制 draw_list 中的绘制对象。
    随后用 NormalDraw 绘制一段补位文本。
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
