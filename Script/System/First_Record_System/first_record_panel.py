"""
性行为履历面板（first_record_panel）
====================================
绘制角色信息页中的性行为履历分页、周目切换与分组折叠按钮。
"""

from types import FunctionType
from Script.UI.Moudle import draw
from Script.Core import get_text
from Script.UI.Panel import character_info_head
from Script.Modules.gameplay_resolution import first_record_service

_: FunctionType = get_text._
""" 文本翻译函数。 """

line_feed = draw.NormalDraw()
""" 换行绘制项。 """
line_feed.text = "\n"
line_feed.width = 1

_state = first_record_service.PanelState()
""" 当前会话的周目选择与分组折叠状态。 """


class FirstRecordText:
    """绘制指定角色的性行为履历正文、周目切换与分组折叠按钮。"""

    def __init__(self, character_id: int, width: int) -> None:
        """按角色编号与绘制宽度构建履历绘制项和按钮列表。"""
        self.character_id = character_id
        """ 当前展示的角色编号。 """
        self.width = width
        """ 面板绘制宽度。 """
        self.draw_list: list = []
        """ 待绘制的界面元素列表。 """
        self.return_list: list[str] = []
        """ 当前监听的按钮返回值列表。 """

        type_line = draw.LittleTitleLineDraw(_("性行为履历"), width, ":")
        self.draw_list.append(type_line)
        view = first_record_service.round_view(
            character_id, _state.selected_round
        )
        if len(view.rounds) > 1:
            self._draw_round_switch(view)
        round_title_draw = draw.NormalDraw()
        if view.is_current:
            round_title_draw.text = _("\n◆ 第{0}周目（当前）\n").format(
                view.shown
            )
        else:
            round_title_draw.text = _("\n◆ 第{0}周目\n").format(view.shown)
        round_title_draw.width = width
        self.draw_list.append(round_title_draw)
        for entry in first_record_service.group_entries(view):
            self._draw_group(view, entry)

    def _draw_round_switch(self, view: first_record_service.RoundView) -> None:
        """向绘制列表追加多周目切换提示与各周目按钮。"""
        switch_tip_draw = draw.NormalDraw()
        switch_tip_draw.text = _("\n周目切换：")
        switch_tip_draw.width = self.width
        self.draw_list.append(switch_tip_draw)
        for round_num in view.rounds:
            if round_num == view.current:
                button_label = _("第{0}周目(当前)").format(round_num)
            else:
                button_label = _("第{0}周目").format(round_num)
            if round_num == view.shown:
                button_text = f"▶{button_label}"
            else:
                button_text = f"[{button_label}]"
            round_button_draw = draw.LeftButton(
                button_text,
                f"first_record_round_{round_num}",
                int(self.width / 6),
                cmd_func=_state.select_round,
                args=(round_num,),
            )
            self.draw_list.append(round_button_draw)
            self.return_list.append(round_button_draw.return_text)
        self.draw_list.append(line_feed)

    def _draw_group(
        self,
        view: first_record_service.RoundView,
        entry: first_record_service.GroupEntry,
    ) -> None:
        """追加单个履历分组的折叠按钮及展开时的正文。"""
        now_expand = _state.expanded(entry)
        if now_expand:
            button_text = f"▼{entry.name}"
        else:
            button_text = f"▶{entry.name}"
        button_draw = draw.LeftButton(
            button_text,
            f"first_record_fold_{entry.fold_key}",
            int(self.width / 3),
            cmd_func=_state.toggle_fold,
            args=(entry.fold_key, entry.default_expand),
        )
        self.draw_list.append(button_draw)
        self.return_list.append(button_draw.return_text)
        self.draw_list.append(line_feed)
        if now_expand:
            group_draw = draw.NormalDraw()
            group_draw.text = first_record_service.group_text(
                self.character_id, view, entry.group
            )
            group_draw.width = self.width
            self.draw_list.append(group_draw)
        self.draw_list.append(line_feed)

    def draw(self) -> None:
        """先输出换行再依次绘制各界面元素。"""
        line_feed.draw()
        for label in self.draw_list:
            label.draw()


class See_Character_First_Record_Panel:
    """
    显示角色属性面板中的性行为履历分页对象
    Keyword arguments:
    character_id -- 角色id
    width -- 绘制宽度
    """

    def __init__(self, character_id: int, width: int) -> None:
        """初始化绘制对象"""
        head_draw = character_info_head.CharacterInfoHead(character_id, width)
        record_draw = FirstRecordText(character_id, width)
        self.draw_list: list = [
            head_draw,
            record_draw,
        ]
        """ 绘制的面板列表 """
        self.return_list: list[str] = []
        """ 当前面板监听的按钮列表 """

    def draw(self) -> None:
        """清空按钮列表，依次绘制子组件并汇总监听按钮。"""
        self.return_list = []
        for label in self.draw_list:
            label.draw()
            if hasattr(label, "return_list"):
                self.return_list.extend(label.return_list)
