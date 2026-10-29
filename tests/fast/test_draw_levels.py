"""
本模块测试 ExpLevelDraw 的等级绘制。
本模块测试 StatusLevelDraw 的等级绘制。
测试输入包含等级边界值。
"""

from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase


class LevelDrawTest(FastTestCase):
  """
  本测试类检查 ExpLevelDraw 与 StatusLevelDraw 在不同输入值下的绘制结果。
  """

  def test_experience_grades(self) -> None:
    """
    检查 ExpLevelDraw 在各经验值下的等级文本。
    检查 grade_draw 的样式名称按等级取值。
    检查 grade_draw 宽度与对象长度都等于等级文本的字符数。
    """
    for experience, grade in (
        (-1, "G"),
        (0, "G"),
        (1, "F"),
        (2, "E"),
        (3, "D"),
        (4, "C"),
        (5, "B"),
        (6, "A"),
        (7, "S"),
        (8, "EX"),
        (20, "EX"),
    ):
      with self.subTest(experience=experience):
        item = draw.ExpLevelDraw(experience)
        self.assertEqual(item.grade_draw.text, grade)
        self.assertEqual(item.grade_draw.style, "level" + grade.lower())
        self.assertEqual(item.grade_draw.width, len(grade))
        self.assertEqual(len(item), len(grade))

  def test_status_grades_preserve_label(self) -> None:
    """
    检查 StatusLevelDraw 的 grade_draw 文本保持传入的标签。
    检查 grade_draw 的样式名称与宽度按状态值所属等级取值。
    检查对象长度受等级宽度限制。
    """
    for value, grade in (
        (0, "G"),
        (99, "G"),
        (100, "F"),
        (499, "F"),
        (500, "E"),
        (1000, "D"),
        (2500, "C"),
        (6000, "B"),
        (12000, "A"),
        (30000, "S"),
        (50000, "S"),
        (75000, "S"),
        (99999, "EX"),
        (100000, "EX"),
    ):
      with self.subTest(value=value):
        item = draw.StatusLevelDraw(value, "lv ")
        self.assertEqual(item.grade_draw.text, "lv ")
        self.assertEqual(item.grade_draw.style, "level" + grade.lower())
        self.assertEqual(item.grade_draw.width, len(grade))
        self.assertEqual(len(item), len(grade))
