"""
带 uid 属性的列表条目 ListItem
"""

from PySide6.QtWidgets import QListWidgetItem


class ListItem(QListWidgetItem):
    """表单对象"""

    def __init__(self, any: str) -> None:
        """初始化表单对象"""
        super().__init__(any)
        self.uid = ""
        """ id """


def list_item(item: QListWidgetItem) -> ListItem:
    """
    以 ListItem 类型原样返回 DataList 列表里的一个条目
    Keyword arguments:
    item -- DataList 列表里的一个条目
    Return arguments:
    ListItem -- 传入的同一个条目
    """
    assert isinstance(item, ListItem)
    return item
