"""教程（PRTS）界面面板与干员口上信息面板"""

from types import FunctionType
from Script.Core import (
    get_text,
    flow_handle,
    constant,
)
from Script.Design import character, attr_calculation
from Script.UI.Moudle import draw, panel, view
from Script.Config import game_config, normal_config
from Script.Modules.domains import identity
from Script.Modules.gameplay_resolution import prts_service

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


def chara_talk_info() -> None:
    """
    干员口上信息
    """

    handle_panel_normal = panel.PageHandlePanel(
        [], ShowCharaNameDraw, 20, 1, window_width, True, False, 0
    )

    while 1:
        line = draw.LineDraw("-", window_width)
        line.draw()
        return_list = []

        handle_panel_normal.text_list = list(
            game_config.config_tip_chara_data_by_adv
        )
        handle_panel_normal.update()
        handle_panel_normal.draw()
        return_list.extend(handle_panel_normal.return_list)

        line_feed.draw()
        back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
        back_draw.draw()
        return_list.append(back_draw.return_text)
        line_feed.draw()
        yrn = flow_handle.askfor_all(return_list)
        if yrn == back_draw.return_text:
            break


class Prts_Panel:
    """
    用于显示教程界面面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.draw_list: list[draw.Drawable] = []
        """ 绘制的文本列表 """

    def draw(self) -> None:
        """绘制对象"""

        title_text = _("普瑞赛斯")

        title_draw = draw.TitleLineDraw(title_text, self.width)

        while 1:
            title_draw.draw()

            info_draw = draw.NormalDraw()
            info_draw.width = self.width
            return_list = []
            now_draw_list: list[draw.Drawable] = []

            pl_name = identity.of(0).name
            info_text = _("身份验证通过，最高权限账户——管理员账户\n\n")
            info_text += _(
                "Dr.{0}，欢迎访问普瑞赛斯终端，请问我可以为您做什么？\n\n"
            ).format(pl_name)
            info_text += _(
                "○请注意，本终端内的资料查询功能会直接涉及游戏流程和实际内容的介绍和剧透，如果更倾向于自己体验和摸索的话，请仅在必要时刻再使用本功能。\n\n"
            )
            info_draw.text = info_text
            info_draw.draw()

            draw_text_list = []
            draw_text_list.append(_("[000]查询系统本身的相关资料"))
            draw_text_list.append(_("[001]获得日常生活的建议"))
            draw_text_list.append(_("[002]询问如何与干员相处"))
            draw_text_list.append(_("[003]与干员发生肉体关系时的注意事项"))
            draw_text_list.append(_("[004]怎么样才能更好的经营罗德岛"))
            draw_text_list.append(_("[010]干员的口上信息"))
            draw_text_list.append(_("[011]与普瑞赛斯闲聊（未实装）"))

            for i in range(len(draw_text_list)):
                button_draw = draw.LeftButton(
                    draw_text_list[i],
                    f"\n{i}",
                    self.width,
                    cmd_func=self.select_question,
                    args=i,
                )
                now_draw_list.append(button_draw)
                now_draw_list.append(line_feed)
                return_list.append(button_draw.return_text)

            self.draw_list = []
            """ 绘制的文本列表 """
            self.draw_list.extend(now_draw_list)

            for label in self.draw_list:
                if isinstance(label, list):
                    for value in label:
                        value.draw()
                    line_feed.draw()
                else:
                    label.draw()

            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def select_question(self, key_index: int) -> None:
        """
        选择问题
        """

        while 1:
            self.fater_type = key_index
            if self.fater_type >= 5:
                break

            line = draw.LineDraw("-", self.width)
            line.draw()
            return_list = []

            for question in prts_service.questions(self.fater_type):
                button_draw = draw.LeftButton(
                    _(question.text),
                    _(question.text),
                    self.width,
                    cmd_func=self.show_answer,
                    args=(question.son_type,),
                )
                return_list.append(button_draw.return_text)
                button_draw.draw()
                line_feed.draw()

            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                break

        if self.fater_type == 5:
            chara_talk_info()

    def show_answer(self, key_index: int) -> None:
        """
        显示答案
        """

        line = draw.LineDraw("-", self.width)
        line.draw()

        answer_draw = draw.WaitDraw()
        answer_draw.text = prts_service.answer_text(self.fater_type, key_index)
        answer_draw.width = self.width
        answer_draw.draw()

        line_feed.draw()


class ShowCharaNameDraw:
    """
    点击后可查看角色名字列表的按钮对象
    Keyword arguments:
    text -- 食物名字
    width -- 最大宽度
    is_button -- 绘制按钮
    num_button -- 绘制数字按钮
    button_id -- 数字按钮id
    """

    def __init__(
        self,
        chara_adv_id: int,
        width: int,
        is_button: bool,
        num_button: bool,
        button_id: int,
    ) -> None:
        """初始化绘制对象"""
        self.chara_adv_id: int = chara_adv_id
        """ 角色adv_id """
        self.draw_text: str = ""
        """ 食物名字绘制文本 """
        self.width: int = width
        """ 最大宽度 """
        self.num_button: bool = num_button
        """ 绘制数字按钮 """
        self.button_id: int = button_id
        """ 数字按钮的id """
        self.button_return: str = str(button_id)
        """ 按钮返回值 """
        self.text_color: str = "standard"
        """ 文本颜色 """

        if self.chara_adv_id == 0:
            name_draw = draw.NormalDraw()
            name_draw.text = ""
            name_draw.width = self.width
            tip_chara_data = game_config.config_tip_chara_data[0]
            now_text = _("[0000]通用文本  by {0}").format(
                tip_chara_data.writer_name
            )
            button_draw: draw.LeftButton | draw.CenterButton = draw.LeftButton(
                _(now_text),
                _(now_text),
                self.width,
                normal_style=self.text_color,
                cmd_func=self.show_chara_info,
                args=(now_text, tip_chara_data.text),
            )
        else:
            character_id = character.get_character_id_from_adv(
                self.chara_adv_id
            )
            character_data = identity.of(character_id)
            name_text = character_data.name.ljust(12, "　")
            version_text = attr_calculation.pad_display_width(
                prts_service.version_label(self.chara_adv_id), 36
            )
            for char in name_text:
                if char.isascii():
                    name_text += " "
            now_text = f"[{str(self.chara_adv_id).rjust(4,'0')}]{name_text}  "
            now_text += _("当前选择版本：{0}             ").format(version_text)
            name_draw = draw.NormalDraw()
            name_draw.text = now_text
            name_draw.width = self.width
            if character_data.text_color:
                self.text_color = character_data.name
            name_draw.style = self.text_color
            now_text = _(" [版本切换] ")
            button_draw = draw.CenterButton(
                now_text,
                character_data.name,
                len(now_text) * 2,
                normal_style=self.text_color,
                cmd_func=self.show_character_text_version,
            )
        self.info_draw = name_draw
        self.now_draw = button_draw
        self.button_return = button_draw.return_text
        """ 绘制的对象 """

    def draw(self) -> None:
        """绘制对象"""
        self.info_draw.draw()
        self.now_draw.draw()

    def show_character_text_version(self) -> None:
        """
        切换角色文本版本
        """

        character_id = character.get_character_id_from_adv(self.chara_adv_id)
        character_data = identity.of(character_id)

        while 1:
            return_list = []
            line = draw.LineDraw("-", self.width)
            line.draw()
            line_feed.draw()

            info_text = _(
                "○一个角色可能会有多个版本的文本，只能选择其中一个版本，或者不选择任何版本。\n"
            )
            info_text += _("  选择一个版本后，将仅显示该版本的口上与事件。\n")
            info_text += _(
                "  选择不使用版本时，该角色将回到只有地文的通用角色状态，不再使用任何口上。\n\n"
            )
            info_draw = draw.NormalDraw()
            info_draw.text = info_text
            info_draw.width = self.width
            info_draw.draw()

            chara_text = f"[{str(self.chara_adv_id).rjust(4,'0')}]{character_data.name}\n\n"
            chara_draw = draw.NormalDraw()
            chara_draw.text = chara_text
            chara_draw.width = self.width
            chara_draw.style = self.text_color
            chara_draw.draw()

            for option in prts_service.version_options(self.chara_adv_id):
                self.show_chara_info(option.title, option.text)
                now_text = _(" [选择该版本] ")
                button_draw = draw.CenterButton(
                    now_text,
                    str(option.tip_cid),
                    len(now_text) * 2,
                    normal_style=self.text_color,
                    cmd_func=prts_service.choose_version,
                    args=(self.chara_adv_id, option.version_id),
                )
                button_draw.draw()
                return_list.append(button_draw.return_text)
                line_feed.draw()

            line_feed.draw()
            now_text = _(" [不使用任何版本] ")
            button_draw = draw.CenterButton(
                now_text,
                now_text,
                len(now_text) * 2,
                normal_style=self.text_color,
                cmd_func=prts_service.choose_version,
                args=(self.chara_adv_id, 0),
            )
            button_draw.draw()
            return_list.append(button_draw.return_text)
            line_feed.draw()

            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                break

    def show_chara_info(self, name_text: str, info_text: str) -> None:
        """
        显示角色信息
        """

        info_text = info_text.replace("\\n", "\n")

        line_feed.draw()
        line = draw.LineDraw("-", self.width)
        line.draw()
        line_feed.draw()

        name_draw = draw.NormalDraw()
        name_draw.text = name_text + "\n\n" + info_text + "\n\n"
        name_draw.width = self.width
        name_draw.style = self.text_color
        name_draw.draw()
