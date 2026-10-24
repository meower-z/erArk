"""
带 uid 属性的列表条目 ListItem
"""

from PySide6.QtWidgets import QListWidgetItem


class ListItem(QListWidgetItem):
  """表单对象"""

  def __init__(self, any: str) -> None:
    """初始化表单对象"""
    super(ListItem, self).__init__(any)
    self.uid = ""
    """ id """
