"""角色身体污秽状况展示面板 SeeCharacterBodyPanel"""

from types import FunctionType

from Script.Core import get_text
from Script.Modules.gameplay_resolution import body_dirty_service
from Script.UI.Moudle import draw, rich_text_draw

_: FunctionType = get_text._
""" 翻译接口。 """
line_feed = draw.NormalDraw()
""" 换行绘制对象。 """
line_feed.text = "\n"
line_feed.width = 1


class SeeCharacterBodyPanel:
    """
    显示角色身体面板对象。
    Keyword arguments:
    character_id -- 角色编号
    width -- 绘制宽度
    column -- 每行状态最大个数
    type_number -- 显示的状态类型
    """

    def __init__(
        self,
        character_id: int,
        width: int,
        column: int,
        type_number: int,
        center_status: bool = True,
    ) -> None:
        """初始化绘制对象并委托身体污秽计算服务生成绘制列表。"""
        self.character_id = character_id
        """ 要绘制的角色编号。 """
        self.width = width
        """ 面板最大宽度。 """
        self.column = column
        """ 每行状态最大个数。 """
        self.draw_list: list = []
        """ 绘制的文本列表。 """
        self.return_list: list[str] = []
        """ 当前面板监听的按钮列表。 """
        self.center_status: bool = center_status
        """ 居中绘制状态文本。 """
        self.type_number = type_number
        """ 显示的状态类型。 """

        report = body_dirty_service.build_body_dirty_report(character_id)
        if report.has_content:
            self.draw_list.append(
                draw.LittleTitleLineDraw(_("身体"), width, ":")
            )
        self.draw_list.extend(
            rich_text_draw.get_rich_text_draw_list(report.rendered_text)
        )

    def get_dirty_diff_text_cid(
        self, body_part_index: int, semen_level: int
    ) -> str:
        """
        获取污浊差分文本编号，无对应差分规则时返回空字符串。
        Keyword arguments:
        body_part_index -- 部位索引
        semen_level -- 精液污浊等级
        Return arguments:
        str -- 污浊差分文本编号，如果没有则返回空字符串
        """
        return body_dirty_service.get_dirty_diff_text_cid(
            self.character_id, body_part_index, semen_level
        )

    def draw(self) -> None:
        """绘制面板。"""
        for label in self.draw_list:
            if isinstance(label, list):
                for value in label:
                    value.draw()
                line_feed.draw()
            else:
                label.draw()
