"""
图书馆借书面板，提供界面可借书籍列表刷新函数 settle_library_book 与借书界面类 Borrow_Book_Panel。
"""

from types import FunctionType
from Script.Core import get_text, flow_handle, constant
from Script.UI.Moudle import draw, view
from Script.Modules.tk_ui import player_pick
from Script.Config import game_config, normal_config
from Script.Modules.domains import chara_life, facility
from Script.Modules.domains import library
from Script.Modules.gameplay_resolution import library_service
from Script.Modules.domains import identity

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


def settle_library_book() -> None:
    """
    刷新图书馆的可借阅书籍
    """

    for book_type_cid in game_config.config_book_type:
        game_config.config_book_type_data.setdefault(book_type_cid, set())
        level = facility.level(10)
        now_choose_list = []
        # 遍历书籍
        for book_id in game_config.config_book_type_data[book_type_cid]:
            # 如果书籍难度大于等于3，且图书馆等级小于4，则跳过
            book_difficulty = game_config.config_book[book_id].difficulty
            if book_difficulty >= 3 and level < 4:
                continue
            # 如果书籍难度大于等于2，且图书馆等级小于3，则跳过
            if book_difficulty >= 2 and level < 2:
                continue
            # 符合条件则加入可选列表
            now_choose_list.append(book_id)
        # 如果该类型的书籍超过3本，则随机选择其中的三本
        if len(now_choose_list) > 3:
            now_choose_list = player_pick.ui_random.sample(now_choose_list, 3)
        view.now_show_book_cid_of_type[book_type_cid] = now_choose_list

    # 获取玩家的借书情况
    pl_borrow = chara_life.borrow_book_id_set(0)
    # 遍历借的书籍，也加入到展示列表里
    for book_id in pl_borrow:
        book_type = game_config.config_book[book_id].type
        if book_id not in view.now_show_book_cid_of_type[book_type]:
            view.now_show_book_cid_of_type[book_type].append(book_id)


class Borrow_Book_Panel:
    """
    用于显示借书界面面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.now_panel = _("技能类书籍")
        """ 当前绘制的页面 """
        self.draw_list: list[draw.Drawable] = []
        """ 绘制的文本列表 """

    def draw(self) -> None:
        """绘制对象"""

        title_text = _("借阅书籍")
        book_father_type_list = [
            _("技能类书籍"),
            _("娱乐类书籍"),
            _("色情类书籍"),
        ]

        # 每次初始化可借阅字典
        settle_library_book()

        title_draw = draw.TitleLineDraw(title_text, self.width)
        while 1:
            return_list = []
            title_draw.draw()

            # 绘制主面板
            for book_fater_type in book_father_type_list:
                if book_fater_type == self.now_panel:
                    now_draw: draw.CenterDraw | draw.CenterButton
                    now_draw = draw.CenterDraw()
                    now_draw.text = f"[{book_fater_type}]"
                    now_draw.style = "onbutton"
                    now_draw.width = int(
                        self.width / len(book_father_type_list)
                    )
                    now_draw.draw()
                else:
                    now_draw = draw.CenterButton(
                        f"[{book_fater_type}]",
                        f"\n{book_fater_type}",
                        int(self.width / len(book_father_type_list)),
                        cmd_func=self.change_panel,
                        args=(book_fater_type,),
                    )
                    now_draw.draw()
                    return_list.append(now_draw.return_text)
            line_feed.draw()
            line = draw.LineDraw("+", self.width)
            line.draw()

            # 当前借书数量限制信息
            holders = library.holders()
            borrow_count = list(holders.values()).count(0)
            borrow_limit_draw = draw.NormalDraw()
            borrow_limit_text = _("\n已借书量/最大借书量：{0}/3\n").format(
                borrow_count
            )
            borrow_limit_draw.text = borrow_limit_text
            borrow_limit_draw.width = self.width
            borrow_limit_draw.draw()

            # 书籍总览信息
            book_draw_list: list[draw.Drawable] = []

            book_draw_list.append(line_feed)

            # 初始化变量
            book_count = 0
            book_can_borrow_count = 0

            # 遍历书籍类型列表，寻找符合当前书籍父类别的书籍类型cid
            for book_type_cid in game_config.config_book_type:
                book_type_data = game_config.config_book_type[book_type_cid]
                if book_type_data.father_type_name in self.now_panel:
                    now_choose_list = view.now_show_book_cid_of_type[
                        book_type_cid
                    ]
                    # 遍历该类型下的书籍
                    for book_cid in now_choose_list:
                        book_data = game_config.config_book[book_cid]
                        book_count += 1
                        book_text = (
                            f"  [{str(book_count).rjust(3,'0')}]("
                            f"{book_type_data.son_type_name}){book_data.name}"
                        )
                        # 书籍难度说明
                        if book_data.difficulty == 1:
                            book_text += _("(简单)")
                        elif book_data.difficulty == 2:
                            book_text += _("(普通)")
                        elif book_data.difficulty == 3:
                            book_text += _("(困难)")
                        else:
                            book_text += _("(未知)")
                        # 书籍阅读进度说明
                        if book_cid in chara_life.read_book_progress(0):
                            book_progress = chara_life.read_book_progress(0)[
                                book_cid
                            ]
                            book_text += _("(已阅读{0}%)").format(book_progress)
                        # 是否可借阅说明
                        button_flag = True
                        if holders[book_cid] == library.FREE:
                            book_text += _("(可借阅)")
                            book_style = "standard"
                            book_can_borrow_count += 1
                        elif holders[book_cid] == 0:
                            book_text += _("(已被博士借走)")
                            book_style = "gold_enrod"
                        else:
                            borrow_npc_id = holders[book_cid]
                            borrow_npc_name = identity.of(borrow_npc_id).name
                            book_text += _("(已被{0}借走)").format(
                                borrow_npc_name
                            )
                            book_style = "nullcmd"
                            button_flag = False

                        if button_flag:
                            button_draw: draw.LeftButton | draw.NormalDraw
                            button_draw = draw.LeftButton(
                                _(book_text),
                                _(str(book_count)),
                                self.width,
                                normal_style=book_style,
                                cmd_func=self.show_book,
                                args=(book_cid,),
                            )
                            return_list.append(button_draw.return_text)
                        else:
                            button_draw = draw.NormalDraw()
                            button_draw.text = book_text
                            button_draw.width = self.width
                            button_draw.style = book_style

                        book_draw_list.append(button_draw)
                        book_draw_list.append(line_feed)

            resouce_draw = draw.NormalDraw()
            resouce_text = _("\n当前藏书情况：")
            resouce_text += _("\n  {0}在馆量/总藏书量：{1}/{2}\n").format(
                self.now_panel, book_can_borrow_count, book_count
            )
            resouce_draw.text = resouce_text
            resouce_draw.width = self.width
            resouce_draw.draw()

            self.draw_list = []
            """ 绘制的文本列表 """
            self.draw_list.extend(book_draw_list)

            for label in self.draw_list:
                if isinstance(label, list):
                    for value in label:
                        value.draw()
                    line_feed.draw()
                else:
                    label.draw()

            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def change_panel(self, building_type: str) -> None:
        """
        切换当前面板显示
        Keyword arguments:
        building_type -- 要切换的面板类型
        """

        self.now_panel = building_type

    def show_book(self, book_cid: int) -> None:
        """
        显示书籍信息
        Keyword arguments:
        book_cid -- 书籍编号
        """
        book_data = game_config.config_book[book_cid]
        book_name = book_data.name
        book_info = book_data.info
        book_difficulty = book_data.difficulty
        bood_difficulty_text = ""
        if book_difficulty == 1:
            bood_difficulty_text = _("（难度：简单）")
        elif book_difficulty == 2:
            bood_difficulty_text = _("（难度：普通，需要对应能力大于等于3级）")
        elif book_difficulty == 3:
            bood_difficulty_text = _("（难度：困难，需要对应能力大于等于6级）")
        else:
            bood_difficulty_text = _("（难度：未知）")
        if book_cid in chara_life.read_book_progress(0):
            book_progress = chara_life.read_book_progress(0)[book_cid]
            book_info += f"\n\n{_('阅读进度：')}{book_progress}%"
        # 判断是否能力足够阅读
        ability_pass = library_service.can_read_book(0, book_cid)

        # 处理换行符
        if "\\n" in book_info:
            book_info = book_info.replace("\\n", "\n")
        book_text = f"\n{book_name}\n{bood_difficulty_text}\n\n{book_info}\n"
        while 1:
            line = draw.LineDraw("-", self.width)
            line.draw()
            return_list = []
            book_info_draw = draw.CenterDraw()
            book_info_draw.text = book_text
            book_info_draw.width = self.width
            book_info_draw.draw()
            line_feed.draw()

            # 如果已借该书，则显示还书按钮
            button_draw_flag = True
            if library.holders()[book_cid] == 0:
                borrow_buttin_text = _("[归还]")
            # 未借该书，则显示借书按钮
            else:
                borrow_buttin_text = _("[借阅]")
                # 如果能力不足，则不能借阅
                if not ability_pass:
                    borrow_buttin_text = _(
                        "[无法借阅]（对应能力不足，这本书对你来说太难了，需要提升对应能力）"
                    )
                    button_draw_flag = False

            if button_draw_flag:
                borrow_button: draw.CenterButton | draw.NormalDraw
                borrow_button = draw.CenterButton(
                    borrow_buttin_text,
                    borrow_buttin_text,
                    int(window_width / 2),
                    cmd_func=self.borrow,
                    args=(book_cid,),
                )
                borrow_button.draw()
                return_list.append(borrow_button.return_text)
            else:
                borrow_button = draw.NormalDraw()
                borrow_button.text = borrow_buttin_text
                borrow_button.draw()
                line_feed.draw()
                line_feed.draw()

            back_draw = draw.CenterButton(
                _("[返回]"), _("返回"), int(window_width / 2)
            )
            back_draw.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn in return_list:
                break

    def borrow(self, book_cid: int) -> None:
        """
        借阅书籍
        Keyword arguments:
        book_cid -- 书籍编号
        """

        # 当前借书数量限制信息
        borrow_count = len(chara_life.borrow_book_id_set(0))

        # 如果已借该书，则还书
        if library.holders()[book_cid] == 0:
            library.set_holder(book_cid, library.FREE)
            with chara_life.borrow_book_id_set.editing(0) as borrow_book_id_set:
                borrow_book_id_set.discard(book_cid)
            # 更新还书历史记录
            library_service.update_return_history_record(0, book_cid)
        # 未借该书，且借书数量不到上限，则借书
        elif borrow_count < 3:
            library.set_holder(book_cid, 0)
            with chara_life.borrow_book_id_set.editing(0) as borrow_book_id_set:
                borrow_book_id_set.add(book_cid)
            # 添加借书历史记录
            library_service.add_borrow_history_record(0, book_cid)
        # 未借该书，且借书数量已达上限，则输出错误信息
        else:
            borrow_limit_draw = draw.WaitDraw()
            borrow_limit_text = _("\n已达到最大借书上限，无法继续借阅\n")
            borrow_limit_draw.text = borrow_limit_text
            borrow_limit_draw.width = self.width
            borrow_limit_draw.draw()
