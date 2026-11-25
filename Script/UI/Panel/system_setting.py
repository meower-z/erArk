"""
系统设置面板与游戏基础设置面板
"""

from types import FunctionType
from collections.abc import Callable

from Script.Core import constant, flow_handle, get_text
from Script.UI.Moudle import draw, panel, view
from Script.Config import normal_config
from Script.Modules.save_load import settings
from Script.Modules.domains import identity
from Script.Modules.gameplay_resolution import system_setting_service as svc

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


def _left_button(
    text: str,
    return_text: str,
    min_width: int,
    func: Callable[..., None],
    return_list: list[str],
    args: object = (),
) -> None:
    """按最小宽度绘制左对齐按钮，并将按钮返回值追加到 return_list。"""
    width = max(len(text) * 2, min_width)
    button = draw.LeftButton(text, return_text, width, cmd_func=func, args=args)
    button.draw()
    return_list.append(button.return_text)


def _notice(text: str, width: int = 0) -> None:
    """以金色样式绘制一条等待确认的提示文本。"""
    now_draw = draw.WaitDraw()
    now_draw.text = text
    now_draw.style = "gold_enrod"
    now_draw.width = width
    now_draw.draw()


def _back_chosen(return_list: list[str]) -> bool:
    """绘制返回按钮并读取输入，选中返回时返回 True。"""
    line_feed.draw()
    line_feed.draw()
    back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
    back_draw.draw()
    line_feed.draw()
    return_list.append(back_draw.return_text)
    return flow_handle.askfor_all(return_list) == back_draw.return_text


class System_Setting_Panel:
    """
    用于系统设置的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.draw_list: list[draw.NormalDraw] = []
        """ 绘制的文本列表 """
        self.pl_character_data = identity.of(0)
        """ 玩家的属性 """
        self.kinds = {
            _("基础"): svc.Kind.BASE,
            _("难度"): svc.Kind.DIFFICULTY,
            _("绘制"): svc.Kind.DRAW,
        }
        """ 本地化分类标签到设置分类枚举 Kind 的映射表 """
        self.type_show = {
            name: kind is svc.Kind.BASE for name, kind in self.kinds.items()
        }
        """ 当前显示的设置类型 """

    def draw(self) -> None:
        """绘制对象"""

        title_text = _("系统设置")
        title_draw = draw.TitleLineDraw(title_text, self.width)
        while 1:
            return_list: list[str] = []
            title_draw.draw()
            now_draw = draw.NormalDraw()
            info_text = _(
                " \n ○点击[选项标题]显示[选项介绍]，点击[选项本身]即可[改变该选项]\n\n"
            )
            now_draw.text = info_text
            now_draw.width = self.width
            now_draw.draw()
            for key in self.type_show:
                return_list = self.draw_option(key, return_list)
            for button_text, func in (
                (_(" [文本生成AI设置] "), self.chat_ai_setting_panel_draw),
                (_(" [指令过滤] "), self.chat_filter_panel_draw),
            ):
                button = draw.CenterButton(
                    button_text,
                    button_text,
                    len(button_text) * 2,
                    cmd_func=func,
                )
                button.draw()
                return_list.append(button.return_text)
            if _back_chosen(return_list):
                settings.save()
                view.now_panel_id = constant.Panel.IN_SCENE
                break

    def change_type_show(self, type_name: str) -> None:
        """改变当前显示的设置类型"""
        self.type_show[type_name] = not self.type_show[type_name]

    def chat_ai_setting_panel_draw(self) -> None:
        """绘制文本生成AI设置面板"""
        from Script.UI.Panel import chat_ai_setting

        now_panel = chat_ai_setting.Chat_Ai_Setting_Panel(self.width)
        now_panel.draw()

    def chat_filter_panel_draw(self) -> None:
        """绘制指令过滤面板"""
        from Script.UI.Panel import instruct_filter_panel

        now_panel = instruct_filter_panel.Instruct_filter_Panel(self.width)
        now_panel.draw()

    def draw_option(self, type_name: str, return_list: list[str]) -> list[str]:
        """绘制选项"""
        if self.type_show[type_name]:
            type_text = _(" ▼[{0}设置]").format(type_name)
        else:
            type_text = _(" ▶[{0}设置]").format(type_name)
        change = self.change_type_show
        _left_button(type_text, type_text, 0, change, return_list, type_name)
        line_feed.draw()
        if self.type_show[type_name]:
            for row in svc.option_rows(self.kinds[type_name]):
                self.draw_option_row(type_name, row, return_list)
        line_feed.draw()
        return return_list

    def draw_option_row(
        self, type_name: str, row: svc.OptionRow, return_list: list[str]
    ) -> None:
        """绘制单条设置项的名称按钮、值或入口按钮以及按需附加的禁止干员入口。"""
        name_text = f"  [{row.name}]： "
        args: object = (type_name, row.cid)
        _left_button(
            name_text, name_text, 60, self.option_name_info, return_list, args
        )
        links = {
            svc.Control.BIRTH_TYPE: self.birth_type_setting_panel_draw,
            svc.Control.FONT_SIZE: self.change_font_size,
            svc.Control.DPI: self.change_dpi_size,
        }
        if row.control is svc.Control.BIRTH_TYPE:
            text = _(" [修改生殖方式开关] ")
        elif row.control in links:
            text = _(" [{0}] ").format(row.value)
        else:
            text = f" [{row.value}] "
        if row.control in links:
            return_text, min_width = str(row.cid) + text, 30
            func, args = links[row.control], ()
        else:
            return_text = type_name + str(row.cid) + text
            min_width = 30 if row.control is svc.Control.NUMBER else 20
            func = self.change_setting_value
            args = (type_name, row.cid, row.option_len)
        _left_button(text, return_text, min_width, func, return_list, args)
        line_feed.draw()
        if row.ban_list:
            text = _(" [修改已禁止干员列表] ")
            _left_button(
                text, "11" + text, 30, self.change_ban_list, return_list
            )
            line_feed.draw()

    def option_name_info(self, type_name: str, cid: int) -> None:
        """绘制选项介绍信息"""
        kind = self.kinds[type_name]
        self.show_info(svc.setting_info(kind, cid))

    def show_info(self, info_text: str) -> None:
        """在两条分隔线之间绘制等待确认的选项说明文本。"""
        line = draw.LineDraw("-", self.width)
        line.draw()
        now_draw = draw.WaitDraw()
        now_draw.text = f"\n {info_text}\n"
        now_draw.width = self.width
        now_draw.draw()
        line = draw.LineDraw("-", self.width)
        line.draw()

    def rule(self) -> None:
        """绘制带上下换行的横线分隔符。"""
        line_feed.draw()
        line_draw = draw.LineDraw("-", self.width)
        line_draw.draw()
        line_feed.draw()

    def ask_number(self, ask_text: str) -> int:
        """绘制分隔线并弹出单行输入框，将用户输入转为整数返回。"""
        self.rule()
        ask_panel = panel.AskForOneMessage()
        ask_panel.set(ask_text, 99)
        return int(ask_panel.draw())

    def change_setting_value(
        self, type_name: str, cid: int, option_len: int
    ) -> None:
        """修改选项设置"""
        step = svc.cycle(self.kinds[type_name], cid, option_len)
        if step is svc.Step.LOCKED:
            self.rule()
            _notice(
                _("\n\n该选项需要在诊疗病人面板中修改，无法在此处修改\n\n"),
                self.width,
            )
        elif step is svc.Step.ASK_COUNT:
            new_num = self.ask_number(_("请输入1~10的数字\n"))
            svc.set_draw_number(cid, new_num)
        elif step is svc.Step.ASK_RATE:
            new_num = self.ask_number(_("请输入1~99的数字\n"))
            svc.set_draw_number(cid, new_num)

    def change_font_size(self) -> None:
        """修改字体大小"""
        new_size = self.ask_number(
            _(
                "请输入新的字体大小（1~50），数字越大字体就越大，默认为21，改变字体大小可能会导致绘制提前截断、错行、对不齐等排版问题，对游戏性没有影响\n"
            )
        )
        new_size = svc.apply_font_size(new_size)
        _notice(
            _("\n\n字体大小已修改为{0}，重启游戏后生效\n\n").format(new_size)
        )

    def change_dpi_size(self) -> None:
        """修改DPI缩放大小"""
        new_dpi = self.ask_number(
            _(
                "请输入新的DPI缩放值（50~300），默认为150。数值越大界面越大，数值越小界面越小。\n该设置仅影响TK绘制模式，不影响Web绘制模式，Web绘制模式下的dpi缩放见页面最下方\n常用值：100=100%缩放，125=125%缩放，150=150%缩放，200=200%缩放\n"
            )
        )
        new_dpi = svc.apply_dpi(new_dpi)
        _notice(_("\n\nDPI缩放已修改为{0}，重启游戏后生效\n\n").format(new_dpi))

    def birth_type_setting_panel_draw(self) -> None:
        """绘制生殖方式开关子面板，逐个开关多胎胎生、带壳卵生、无壳卵生三种生殖方式"""
        while 1:
            return_list: list[str] = []
            title_text = _("生殖方式开关")
            title_draw = draw.TitleLineDraw(title_text, self.width)
            title_draw.draw()
            info_draw = draw.NormalDraw()
            info_text = _(
                " \n ○点击[生殖方式名]显示[详细说明]，点击[当前状态]即可[切换开关]\n"
            )
            info_text += _(
                " ○被关闭的生殖方式，其所属种族的干员将全部改为单胎胎生\n"
            )
            info_text += _(
                " ○关闭时会立即清除该生殖方式的存量数据，该操作不可撤销\n\n"
            )
            info_draw.text = info_text
            info_draw.width = self.width
            info_draw.draw()
            for row in svc.birth_type_rows():
                birth_type = row.birth_type
                button_text = f"  [{row.name}]： "
                _left_button(
                    button_text,
                    button_text,
                    40,
                    self.birth_type_name_info,
                    return_list,
                    (birth_type,),
                )
                state_text = f" [{row.state}] "
                state_draw = draw.LeftButton(
                    state_text,
                    str(birth_type) + state_text,
                    max(len(state_text) * 2, 30),
                    normal_style="standard" if row.enabled else "deep_gray",
                    cmd_func=self.change_birth_type_setting,
                    args=(birth_type,),
                )
                state_draw.draw()
                return_list.append(state_draw.return_text)
                line_feed.draw()
            if _back_chosen(return_list):
                break

    def birth_type_name_info(self, birth_type: int) -> None:
        """
        绘制某个生殖方式的详细说明
        Keyword arguments:
        birth_type -- 生育方式编号
        """
        self.show_info(svc.birth_type_text(birth_type)[1])

    def change_birth_type_setting(self, birth_type: int) -> None:
        """
        切换某个生殖方式的开关，由开启改为关闭时进行二次确认并立即清除该生殖方式的存量数据
        Keyword arguments:
        birth_type -- 生育方式编号
        """
        if not svc.birth_type_on(birth_type):
            svc.open_birth_type(birth_type)
            return
        name, info = svc.birth_type_text(birth_type)
        if not self.confirm_close_birth_type(name, info):
            return
        clear_text = svc.close_birth_type(birth_type)
        line_feed.draw()
        _notice(
            _("\n 已关闭[{0}]，{1}\n\n").format(name, clear_text), self.width
        )

    def confirm_close_birth_type(self, name: str, info: str) -> bool:
        """
        关闭生殖方式开关前的二次确认
        Keyword arguments:
        name -- 生殖方式名
        info -- 该生殖方式的详细说明
        Return arguments:
        bool -- 是否确认关闭
        """
        while 1:
            line_feed.draw()
            line = draw.LineDraw("-", self.width)
            line.draw()
            now_draw = draw.NormalDraw()
            now_draw.text = _("\n 即将关闭[{0}]\n\n {1}\n\n").format(name, info)
            now_draw.width = self.width
            now_draw.draw()
            warning_draw = draw.NormalDraw()
            warning_draw.text = _(
                " ※该操作会立即清除对应的存量数据，且无法撤销\n\n"
            )
            warning_draw.style = "warning"
            warning_draw.width = self.width
            warning_draw.draw()
            yes_draw = draw.CenterButton(
                _("[确认关闭]"), _("确认关闭"), window_width / 2
            )
            yes_draw.draw()
            no_draw = draw.CenterButton(
                _("[取消]"), _("取消"), window_width / 2
            )
            no_draw.draw()
            line_feed.draw()
            yrn = flow_handle.askfor_all(
                [yes_draw.return_text, no_draw.return_text]
            )
            if yrn == yes_draw.return_text:
                return True
            elif yrn == no_draw.return_text:
                return False

    def change_ban_list(self) -> None:
        """修改已禁止干员列表"""
        while 1:
            return_list: list[str] = []
            title_text = _("已禁止干员列表")
            title_draw = draw.TitleLineDraw(title_text, self.width)
            title_draw.draw()
            line_feed.draw()
            for npc_count, row in enumerate(svc.ban_rows(), 1):
                button_draw = draw.LeftButton(
                    row.text,
                    str(row.npc_id),
                    int(self.width / 6),
                    normal_style="deep_gray" if row.banned else "standard",
                    cmd_func=self.change_ban_list_cmd,
                    args=row.npc_id,
                )
                button_draw.draw()
                return_list.append(button_draw.return_text)
                if npc_count % 6 == 0:
                    line_feed.draw()
            if _back_chosen(return_list):
                break

    def change_ban_list_cmd(self, npc_id: int) -> None:
        """修改已禁止干员列表"""
        if svc.toggle_ban(npc_id):
            now_draw = draw.NormalDraw()
            info_text = _("\n\n{0}干员已离岛\n\n").format(
                identity.of(npc_id).name
            )
            now_draw.text = info_text
            now_draw.width = self.width
            now_draw.draw()


class Game_Basic_Settings_Panel:
    """
    游戏基础设置面板
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 最大绘制宽度 """
        self.return_list: list[str] = []
        """ 当前面板监听的按钮列表 """

    def draw(self) -> None:
        """绘制对象"""
        title_text = _("游戏基础设置")
        title_draw = draw.TitleLineDraw(title_text, window_width)

        while True:
            title_draw.draw()
            return_list = []
            line_feed.draw()
            language_title = draw.NormalDraw()
            language_title.text = _("━━━━━ 语言设置 ━━━━━\n")
            language_title.width = window_width
            language_title.draw()
            language_options = {
                "zh_CN": _("简体中文"),
                "en_US": _("English"),
                "ko_KR": _("한국어"),
            }
            current_language = normal_config.config_normal.language
            current_language_text = ""
            current_language_text += _(
                "○各语言的存档不共通，如果需要切换语言，请重新建档\n"
            )
            current_language_text += _("当前语言：{0}\n").format(
                language_options.get(current_language, _(_("未知语言")))
            )
            current_language_text += _("可选语言：\n")
            current_language_draw = draw.NormalDraw()
            current_language_draw.text = current_language_text
            current_language_draw.width = window_width
            current_language_draw.draw()
            line_feed.draw()
            for lang_code, lang_name in language_options.items():
                button_text = f"[{lang_name}]"
                button_draw = draw.CenterButton(
                    button_text,
                    lang_code,
                    max(len(button_text) * 2, 30),
                    cmd_func=self.change_language_cmd,
                    args=(lang_code,),
                )
                button_draw.draw()
                return_list.append(button_draw.return_text)
            line_feed.draw()
            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                break

    def change_language_cmd(self, lang_code: str) -> None:
        """修改语言设置"""
        svc.apply_language(lang_code)
        _notice(
            _("语言已修改为{0}，重启游戏后生效").format(
                normal_config.config_normal.language
            )
        )
