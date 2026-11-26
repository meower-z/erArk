"""事件描述文本的绘制面板"""

from Script.Design import event
from Script.UI.Moudle import draw
from Script.Config import normal_config

window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1


class DrawEventTextPanel(draw.LineFeedWaitDraw):
    """
    用于绘制事件描述文本的面板对象
    Keyword arguments:
    event_id -- 事件id
    character_id -- 触发事件的角色id
    """

    def __init__(
        self, event_id: str, character_id: int, event_type: int
    ) -> None:
        """初始化绘制对象"""
        event_text = event.build_event_text(event_id, character_id, event_type)
        self.width: int = window_width
        """ 绘制的最大宽度 """
        self.event_id: str = event_text.event_id
        """ 事件id """
        self.character_id: int = character_id
        """ 触发事件的角色id """
        self.event_type: int = event_type
        """ 事件的类型 """
        self.text: str = event_text.text
        """ 当前绘制的文本 """
        self.style: str = event_text.style
        """ 绘制文本的样式 """
        self.tooltip: str = ""
        """ 绘制文本的悬停提示 """

    def draw(self) -> None:
        """
        绘制事件文本
        """
        # 如果没有文本则不绘制
        if not self.text:
            return

        super().draw()
