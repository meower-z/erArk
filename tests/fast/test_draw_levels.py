"""
测试 ExpLevelDraw 和 StatusLevelDraw 生成的等级标签属性。
"""

from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase


class LevelDrawTest(FastTestCase):
  """
  等级绘制类的快速测试类。
  """

  def test_experience_grades(self) -> None:
    """
    按 11 个经验值检查 ExpLevelDraw 生成的 grade_draw 属性。
    实例长度应等于等级字符串长度。
    返回 (None)：无返回值。
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
    按 14 个数值检查 StatusLevelDraw 生成的 grade_draw 属性。
    传入的标签 'lv ' 应保留为 grade_draw.text。
    实例长度应等于等级字符串长度。
    返回 (None)：无返回值。
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
