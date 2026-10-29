"""
本模块定义 LeftMergeDraw 类。
LeftMergeDraw 按顺序绘制 draw_list 中的对象。
随后 LeftMergeDraw 绘制一段空格，用于左对齐补位。
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
  将绘制列表合并在一起并左对齐绘制
  Keyword arguments:
  width -- 最大宽度
  """

  def __init__(self, width: float) -> None:
    """初始化绘制对象"""
    self.width: float = width
    """ 最大宽度 """
    self.draw_list: list[SizedDrawable] = []
    """ 绘制列表 """
    self.column: int = 0
    """ 每行最大元素数 """

  def __len__(self) -> int:
    """获取当前绘制对象宽度"""
    return int(self.width)

  def __gt__(self, other: Sized) -> int:
    """
    按 len() 比较两个绘制对象的长度，self 更长时为真
    Keyword arguments:
    other -- 另一个绘制对象
    Return arguments:
    bool -- len(self) 是否大于 len(other)
    """
    return int(len(self)) > int(len(other))

  def draw(self) -> None:
    """绘制列表"""
    now_width = 0
    for value in self.draw_list:
      now_width += len(value)
    now_text = " " * now_width
    fix_text = text_handle.align(now_text, "left", True, 1, self.width)
    fix_draw = NormalDraw()
    fix_draw.text = fix_text
    fix_draw.width = len(fix_text)
    # fix_draw.draw()
    for value in self.draw_list:
      value.draw()
    now_width = fix_draw.width * 2 + now_width
    if now_width < self.width:
      fix_draw.text += int(self.width - now_width) * " "
    fix_draw.draw()
