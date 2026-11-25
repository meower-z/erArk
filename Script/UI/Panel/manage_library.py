"""图书馆管理面板与推荐书籍类别的选择按钮"""

from types import FunctionType
from Script.Core import get_text, flow_handle, constant
from Script.UI.Moudle import draw, panel, view
from Script.UI.Panel import common_select_NPC
from Script.Config import game_config, normal_config
from Script.Modules.gameplay_resolution import library_panel_service

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


class Manage_Library_Panel:
    """
    用于管理图书馆的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("管理图书馆")
        """ 当前绘制的页面 """

    def draw(self) -> None:
        """绘制对象"""

        title_text = _("管理图书馆")
        title_draw = draw.TitleLineDraw(title_text, self.width)
        while 1:
            return_list = []
            title_draw.draw()
            cinfo_draw = draw.NormalDraw()
            info_text = _("\n要进行哪方面的管理呢？\n")
            cinfo_draw.text = info_text
            cinfo_draw.draw()

            button0_text = _("[001]催还书")
            button0_draw = draw.LeftButton(
                _(button0_text),
                _("1"),
                window_width,
                cmd_func=self.urge_return_book_list,
                args=(),
            )
            line_feed.draw()
            button0_draw.draw()
            return_list.append(button0_draw.return_text)

            button1_text = _("[002]图书进货(未实装)")
            button1_draw = draw.LeftButton(
                _(button1_text),
                _("2"),
                window_width,
                cmd_func=self.get_new_book,
                args=(),
            )
            line_feed.draw()
            button1_draw.draw()
            return_list.append(button1_draw.return_text)

            button2_text = _("[003]阅读推荐")
            button2_draw = draw.LeftButton(
                _(button2_text),
                _("3"),
                window_width,
                cmd_func=self.read_recommend,
                args=(),
            )
            line_feed.draw()
            button2_draw.draw()
            return_list.append(button2_draw.return_text)

            button3_text = _("[004]读书会")
            button3_draw = draw.LeftButton(
                _(button3_text),
                _("4"),
                window_width,
                cmd_func=self.reading_party,
                args=(),
            )
            line_feed.draw()
            button3_draw.draw()
            return_list.append(button3_draw.return_text)

            button4_text = _("[005]借阅历史记录")
            button4_draw = draw.LeftButton(
                _(button4_text),
                _("5"),
                window_width,
                cmd_func=self.borrowing_history,
                args=(),
            )
            line_feed.draw()
            button4_draw.draw()
            return_list.append(button4_draw.return_text)

            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def urge_return_book_list(self) -> None:
        """催还书的大列表"""

        while 1:
            return_list = []
            line_feed.draw()
            line = draw.LineDraw("-", window_width)
            line.draw()
            lent = library_panel_service.lent_books()
            for book_count, row in enumerate(lent, 1):
                button_draw = draw.LeftButton(
                    _(row.text),
                    _(str(book_count)),
                    self.width,
                    cmd_func=self.return_book,
                    args=(row.holder_id,),
                )
                line_feed.draw()
                button_draw.draw()
                return_list.append(button_draw.return_text)

            if not lent:
                now_draw = draw.NormalDraw()
                now_draw.width = window_width
                now_draw.text = _("\n  目前无人借书，不需要催还\n")
                now_draw.draw()

            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                break

    def return_book(self, chara_id: int) -> None:
        """角色还书"""

        now_draw = draw.WaitDraw()
        now_draw.width = window_width
        now_draw.text = library_panel_service.urge_return(chara_id)
        now_draw.draw()

    def get_new_book(self) -> None:
        """图书进货"""

        now_draw = draw.WaitDraw()
        now_draw.width = window_width
        now_draw.text = _("\n暂未实装\n")
        now_draw.draw()

    def read_recommend(self) -> None:
        """阅读推荐"""

        self.handle_panel = panel.PageHandlePanel(
            [], SelectRecommendBookButton, 999, 6, self.width, True, True, 0
        )

        while 1:
            line = draw.LineDraw("-", self.width)
            line.draw()
            info_draw = draw.NormalDraw()
            info_draw.text = _("\n 当前剩余可选推荐 {0}\n").format(
                library_panel_service.recommend_left()
            )
            info_draw.draw()
            line_feed.draw()
            self.handle_panel.text_list = list(game_config.config_book_type)
            self.handle_panel.update()
            self.handle_panel.draw()
            return_list = []
            return_list.extend(self.handle_panel.return_list)
            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), self.width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                break

    def reading_party(self) -> None:
        """读书会"""

        while 1:
            return_list = []
            line_feed.draw()
            line = draw.LineDraw("-", window_width)
            line.draw()
            now_draw = draw.NormalDraw()
            now_draw.width = window_width
            now_draw.text = _("\n  要把哪一天定为读书会呢？\n")
            now_draw.draw()

            for i, button_text in enumerate(library_panel_service.party_rows()):
                button_draw = draw.LeftButton(
                    _(button_text),
                    _(str(i)),
                    self.width,
                    cmd_func=self.choice_read_party,
                    args=(i,),
                )
                line_feed.draw()
                button_draw.draw()
                return_list.append(button_draw.return_text)

            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                break

    def choice_read_party(self, week_day: int) -> None:
        """选择读书会之日"""

        refusal = library_panel_service.pick_party_day(week_day)
        if refusal is not None:
            now_draw = draw.WaitDraw()
            now_draw.width = window_width
            now_draw.text = refusal
            now_draw.draw()

    def borrowing_history(self) -> None:
        """借阅历史记录查看"""

        character_list = [
            [character_id, self.show_character_history, []]
            for character_id in library_panel_service.history_holders()
        ]
        if not character_list:
            while 1:
                line_feed.draw()
                line = draw.LineDraw("-", window_width)
                line.draw()

                no_history_draw = draw.NormalDraw()
                no_history_draw.width = window_width
                no_history_draw.text = _("\n  暂无任何角色的借阅历史记录\n")
                no_history_draw.draw()

                line_feed.draw()
                back_draw = draw.CenterButton(
                    _("[返回]"), _("返回"), window_width
                )
                back_draw.draw()
                yrn = flow_handle.askfor_all([back_draw.return_text])

                if yrn == back_draw.return_text:
                    break
        else:
            original_character_list = character_list.copy()
            self.character_handle_panel = panel.PageHandlePanel(
                [],
                common_select_NPC.CommonSelectNPCButtonList,
                10,
                5,
                window_width,
                True,
                False,
                0,
            )
            select_state: dict[str, int | str] = {}

            while 1:
                info_text = _("以下角色拥有借阅历史记录：\n\n")
                self.character_handle_panel.text_list = (
                    original_character_list.copy()
                )
                return_list, _other_return_list, select_state = (
                    common_select_NPC.common_select_npc_button_list_func(
                        self.character_handle_panel,
                        _("借阅历史记录"),
                        info_text,
                        select_state,
                    )
                )

                yrn = flow_handle.askfor_all(return_list)
                if yrn == _("返回"):
                    break

    def show_character_history(self, character_id: int) -> None:
        """显示指定角色的借阅历史"""

        while 1:
            return_list = []
            card = library_panel_service.history_card(character_id)
            title_text = _("[{0}]的借书卡记录").format(card.name)
            title_draw = draw.TitleLineDraw(title_text, window_width)
            title_draw.draw()
            line_feed.draw()

            if not card.records:
                no_history_draw = draw.NormalDraw()
                no_history_draw.width = window_width
                no_history_draw.text = _("\n  该角色暂无借阅历史记录\n")
                no_history_draw.draw()
            else:
                stats_draw = draw.NormalDraw()
                stats_draw.width = window_width
                stats_draw.text = _(
                    "\n  借阅历史统计：共借阅过{0}本书，累计阅读{1}次\n"
                ).format(card.total_books, card.total_reads)
                stats_draw.draw()
                line_feed.draw()
                for record_text in card.records:
                    record_draw = draw.NormalDraw()
                    record_draw.width = window_width
                    record_draw.text = record_text
                    record_draw.draw()
                    line_feed.draw()

            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)

            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                break


class SelectRecommendBookButton:
    """
    点击后可选择作为推荐书籍类别的按钮对象
    Keyword arguments:
    text -- 选项名字
    width -- 最大宽度
    is_button -- 绘制按钮
    num_button -- 绘制数字按钮
    button_id -- 数字按钮id
    """

    def __init__(
        self,
        book_type_id: int,
        width: int,
        is_button: bool,
        num_button: bool,
        button_id: int,
    ) -> None:
        """初始化绘制对象"""

        self.book_type_id: int = book_type_id
        """ 书籍类型编号 """
        self.draw_text: str = ""
        """ 绘制文本 """
        self.width: int = width
        """ 最大宽度 """
        self.num_button: bool = num_button
        """ 绘制数字按钮 """
        self.button_id: int = button_id
        """ 数字按钮的id """
        self.button_return: str = str(button_id)
        """ 按钮返回值 """
        option = library_panel_service.recommend_option(self.book_type_id)
        self.now_draw = draw.LeftButton(
            option.text,
            self.button_return,
            self.width,
            normal_style="gold_enrod" if option.picked else "standard",
            cmd_func=self.button_0,
        )
        """ 绘制的对象 """

    def button_0(self) -> None:
        """选项1"""
        library_panel_service.toggle_recommend(self.book_type_id)

    def draw(self) -> None:
        """绘制对象"""
        self.now_draw.draw()
