"""
文本生成AI的设置面板
"""

from types import FunctionType
from Script.Core import get_text, flow_handle
from Script.UI.Moudle import draw, panel
from Script.Config import game_config, normal_config
from Script.Modules.gameplay_resolution import chat_ai_setting_service as svc
from Script.Modules.save_load import settings

_: FunctionType = get_text._
""" 翻译api """
line_feed = draw.NormalDraw()
""" 换行绘制对象 """
line_feed.text = "\n"
line_feed.width = 1
window_width: int = normal_config.config_normal.text_width
""" 窗体宽度 """


class Chat_Ai_Setting_Panel:
    """
    用于文本生成AI设置的面板对象
    Keyword arguments:
    width -- 绘制宽度
    """

    def __init__(self, width: int) -> None:
        """初始化绘制对象"""
        self.width: int = width
        """ 绘制的最大宽度 """
        self.draw_list: list[draw.NormalDraw] = []
        """ 绘制的文本列表 """
        self.test_flag = 0
        """ 测试标志，0为未测试，1为测试通过，2为测试不通过 """
        self.error_message = ""
        """ 错误信息 """

    def say(self, text: str) -> None:
        """按面板宽度绘制普通文本。"""
        now_draw = draw.NormalDraw()
        now_draw.text = text
        now_draw.width = self.width
        now_draw.draw()

    def rule(self) -> None:
        """绘制上下带换行的横向分隔线。"""
        line_feed.draw()
        line_draw = draw.LineDraw("-", self.width)
        line_draw.draw()
        line_feed.draw()

    def ask(self, text: str, input_max: int) -> str:
        """弹出单条输入面板并返回玩家输入文本。"""
        ask_panel = panel.AskForOneMessage()
        ask_panel.set(text, input_max)
        return ask_panel.draw()

    def confirm_disclaimer(self, title_draw: draw.TitleLineDraw) -> bool:
        """绘制免责声明并循环等待玩家选择返回或下一步。"""
        while 1:
            return_list = []
            title_draw.draw()
            self.say(
                _(
                    " \n ○文本生成AI是一个试验性的功能，存在相当多的风险，所以需要您确认以下所有免责事项才可以使用\n\n"
                    "\n 1.该功能需要您自行准备好OpenAI/Gemini的API密钥，并保证电脑的网络环境可以正常访问该API，"
                    "本游戏不会为您提供相关的获取方法，请自行准备\n\n\n   2.文本生成AI以及网络环境的使用会产生一定的费"
                    "用，该费用需自己承担，与开发者没有任何关系\n\n\n 3.文本生成AI的使用可能会产生一定的风险，"
                    "包括但不限于：聊天内容不当、聊天内容不符合社会规范等，开发者不对生成的内容负责，"
                    "也不代表开发者同意或反对其中的任何观点\n\n\n 4.不恰当的使用过程或生成内容有可能会导致模型提供商对"
                    "您的api和相关账号提出警告或进一步的停止服务等举措，请牢记该风险，"
                    "相关的直接或间接损失均需您自己承担，与开发者无关\n\n\n 5.本声明的解释权归开发者所有，"
                    "且在版本更新中声明内容可能有所变更，请以最新版本为准。\n\n\n 6.基于以上又叠了这么多层buff，"
                    "明确知道自己在做什么，并且愿意承担费用和风险的人再来点击下一步吧\n\n\n"
                )
            )
            no_draw = draw.LeftButton(
                _("[0]我不太确定，再考虑一下"), _("返回"), self.width
            )
            no_draw.draw()
            return_list.append(no_draw.return_text)
            line_feed.draw()
            line_feed.draw()
            yes_draw = draw.LeftButton(
                _(
                    "[1]我已阅读并同意以上所有免责事项，理解并愿意承担对应的费用和风险"
                ),
                _("下一步"),
                self.width,
            )
            yes_draw.draw()
            return_list.append(yes_draw.return_text)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn == no_draw.return_text:
                return False
            elif yrn == yes_draw.return_text:
                return True

    def draw(self) -> None:
        """绘制对象"""
        title_text = _("文本生成AI设置")
        title_draw = draw.TitleLineDraw(title_text, self.width)
        if svc.setting_of(1) == 0 and not self.confirm_disclaimer(title_draw):
            return
        while 1:
            return_list = []
            line_feed.draw()
            title_draw.draw()
            info_text = _(
                " \n ○点击[选项标题]显示[选项介绍]，点击[选项本身]即可[改变该选项]\n"
            )
            info_text += _(
                "   开启本功能后，受网络连接速度和模型的文本生成速度影响，在生成文本时会有明显的延迟\n"
            )
            info_text += _(
                "   系统提示词文件路径为 data/ui_text/text_ai_system_promote.csv ，可以根据自己的需要进行调整，"
                "调整后需重启游戏\n"
            )
            info_text += _(
                "   如需对模型进行破甲/破限/越狱，同样也是将相关内容添加到上述系统提示词文件中\n"
            )
            info_text += _(
                "   相关源码文件路径如下。"
                "Script/UI/Panel/chat_ai_setting.py 负责设置界面绘制与输入。"
                "Script/Modules/gameplay_resolution/chat_ai_setting_service.py"
                " 负责设置规则、发送数据选项、API密钥存取（ai_chat_api_key.csv）、客户端构造与模型测试。"
                "Script/Design/handle_chat_ai.py 负责游玩时按所选发送数据构造提示词并调用模型。"
                "可以根据自己的需要进行调整，调整后需自行打包\n"
            )
            self.say(info_text)
            for row in svc.setting_rows():
                line_feed.draw()
                button_text = f"  [{row.name}]： "
                button_draw = draw.LeftButton(
                    button_text,
                    button_text,
                    max(len(button_text) * 2, 60),
                    cmd_func=self.draw_info,
                    args=(row.cid),
                )
                button_draw.draw()
                return_list.append(button_draw.return_text)
                button_draw = draw.LeftButton(
                    row.value,
                    str(row.cid) + row.value,
                    max(len(row.value) * 2, 20),
                    cmd_func=self.change_setting,
                    args=(row.cid, row.option_len),
                )
                button_draw.draw()
                return_list.append(button_draw.return_text)
            if normal_config.config_normal.language != "zh_CN":
                self.draw_translator(return_list)
            if svc.setting_of(1) == 1:
                line_feed.draw()
                line_feed.draw()
                svc.load_api_keys()
                self.draw_keys(return_list)
                self.draw_test(return_list)
            line_feed.draw()
            line_feed.draw()
            back_draw = draw.CenterButton(_("[返回]"), _("返回"), window_width)
            back_draw.draw()
            line_feed.draw()
            return_list.append(back_draw.return_text)
            yrn = flow_handle.askfor_all(return_list)
            if yrn == back_draw.return_text:
                settings.save()
                break

    def draw_translator(self, return_list: list[str]) -> None:
        """绘制语言翻译说明与状态切换按钮并登记返回值。"""
        line_feed.draw()
        button_text = _("  [语言翻译]： ")
        button_len = max(len(button_text) * 2, 60)
        button_draw = draw.LeftButton(
            button_text,
            button_text,
            button_len,
            cmd_func=self.draw_info,
            args=(31),
        )
        button_draw.draw()
        return_list.append(button_draw.return_text)
        label = svc.translator_label()
        if label is not None:
            button_text = label
        button_draw = draw.LeftButton(
            button_text,
            "translator" + button_text,
            button_len,
            cmd_func=svc.next_translator,
        )
        button_draw.draw()
        return_list.append(button_draw.return_text)

    def draw_keys(self, return_list: list[str]) -> None:
        """绘制三类API密钥设置状态及对应更改按钮。"""
        key_info_text = ""
        for key_type, line_text in (
            ("OPENAI_API_KEY", _("  OpenAI API密钥： {0}\n")),
            ("GEMINI_API_KEY", _("  Gemini API密钥： {0}\n")),
            ("DEEPSEEK_API_KEY", _("  DeepSeek API密钥： {0}\n")),
        ):
            state = _("已设置") if svc.key_filled(key_type) else _("未设置")
            key_info_text += line_text.format(state)
        self.say(key_info_text)
        for key_type, button_text, return_text in (
            (
                "OPENAI_API_KEY",
                _("  [更改OpenAI API密钥] "),
                _("更改OpenAI API密钥"),
            ),
            (
                "GEMINI_API_KEY",
                _("  [更改Gemini API密钥] "),
                _("更改Gemini API密钥"),
            ),
            (
                "DEEPSEEK_API_KEY",
                _("  [更改DeepSeek API密钥] "),
                _("更改DeepSeek API密钥"),
            ),
        ):
            button_draw = draw.CenterButton(
                button_text,
                return_text,
                max(len(button_text) * 2, 20),
                cmd_func=self.change_api_key,
                args=(key_type),
            )
            button_draw.draw()
            return_list.append(button_draw.return_text)

    def draw_test(self, return_list: list[str]) -> None:
        """绘制模型测试按钮及最近一次测试结果文本。"""
        line_feed.draw()
        line_feed.draw()
        button_text = _("  [测试](最大延迟上限10秒) ")
        button_draw = draw.CenterButton(
            button_text,
            _("测试"),
            max(len(button_text) * 2, 20),
            cmd_func=self.test_ai,
        )
        button_draw.draw()
        return_list.append(button_draw.return_text)
        if self.test_flag == 1:
            self.say(
                _(" \n  测试通过，当前调用的模型为：")
                + svc.setting_of(5)
                + "\n"
            )
        elif self.test_flag == 2:
            self.say(
                _(" \n  测试不通过，错误信息为：\n  ")
                + self.error_message
                + "\n"
            )

    def draw_info(self, cid: int) -> None:
        """绘制选项介绍信息"""
        line = draw.LineDraw("-", self.width)
        line.draw()
        now_draw = draw.WaitDraw()
        if cid <= 30:
            info_text = f"\n {game_config.config_ai_chat_setting[cid].info}\n"
        else:
            info_text = _(" \n  本选项用于设置是否开启语言翻译功能\n")
            info_text += _(
                "  开启后，游戏中的文本将会被翻译成您设置的语言-[{0}]\n"
            ).format(normal_config.config_normal.language)
        now_draw.text = info_text
        now_draw.width = self.width
        now_draw.draw()
        line = draw.LineDraw("-", self.width)
        line.draw()

    def change_setting(self, cid: int, option_len: int) -> None:
        """修改设置"""
        svc.fill_defaults()
        if cid == 5:
            self.rule()
            ask_text = _("请输入您要使用的模型名（不含引号、逗号或空格）：\n")
            ask_text += _(
                "  *此处使用的模型会默认使用官方api地址，如果是第三方或本地部署，请更改[base_url]\n"
            )
            ask_text += _(
                "  *更多模型名请在官方文档中查阅，非该三类的模型将自动使用OpenAI格式来处理\n"
            )
            ask_text += _(
                "  gpt模型示例：gpt-3.5-turbo, gpt-4, gpt-4-turbo, gpt-4o, gpt-4o-mini, gpt-4.1, o4-mini\n"
            )
            ask_text += _(
                "  deepseek模型示例：deepseek-chat,deepseek-reasoner\n"
            )
            ask_text += _(
                "  gemini模型示例：gemini-1.5-pro, gemini-1.5-flash，gemini-2.0-flash-exp, gemini-2.5-flash, "
                "gemini-2.5-pro\n"
            )
            svc.set_model(self.ask(ask_text, 99))
            self.test_flag = 0
        elif cid == 6:
            self.select_send_data()
        elif cid == 9:
            self.rule()
            svc.set_talk_count(self.ask(_("请输入1~10的数字\n"), 99))
        elif cid == 10:
            if svc.setting_of(cid) == 0:
                self.rule()
                ask_text = _(
                    "请输入您要使用的api的base_url（不含引号、逗号或空格）：\n"
                )
                ask_text += _(
                    "  调用gpt、deepseek、gemini的官方api时url会自动填充，非官方api调用或本地api调用可在此手动输入\n"
                )
                ask_text += _(
                    "  在线调用示例：http://my.test.server.example.com:8083/v1\n"
                )
                ask_text += _("  本地调用示例：http://localhost:1234/v1\n")
                svc.set_base_url(self.ask(ask_text, 999))
            else:
                svc.switch_off(cid)
        elif cid == 11:
            if svc.setting_of(cid) == 0:
                self.rule()
                ask_text = _(
                    "请输入您要使用的代理服务器配置（不含引号、逗号或空格）：\n"
                )
                ask_text += _(
                    "  示例：\nhttp://username:password@proxy_ip:proxy_port\nhttps://proxy_ip:proxy_port\n"
                )
                svc.set_proxy_url(self.ask(ask_text, 999))
                line_feed.draw()
                ask_text = _(
                    "请输入您要使用的本地绑定的 IP 地址，不使用本地ip则随便输入数字后回车即可：\n"
                )
                ask_text += _("  示例：0.0.0.0\n")
                svc.set_local_ip(self.ask(ask_text, 999))
            else:
                svc.switch_off(cid)
        else:
            svc.cycle(cid, option_len)

    def select_send_data(self) -> None:
        """选择发送的数据"""
        while True:
            return_list = []
            title_draw = draw.TitleLineDraw(_("选择发送给AI的数据"), self.width)
            title_draw.draw()
            info_text = _(
                " \n ○发送的数据越多，AI可以利用的信息就越多，理论效果会越好\n"
            )
            info_text += _(
                "  但同时消耗的tokens和响应时间也越多，也可能因为信息太多而抓不住重点或超出上下文长度\n"
            )
            info_text += _("  每项的数据量有小、中、大三级区分\n")
            info_text += _(
                "  发送数据的文件路径为：data\\csv\\Ai_Chat_Send_Data.csv，可根据需要自行修改提示词\n"
            )
            self.say(info_text)
            for row in svc.send_data_rows():
                if row.cid % 10 == 1:
                    line_feed.draw()
                line_text = f"  {row.name}({row.size})  "
                name_draw = draw.LeftButton(
                    line_text,
                    row.name + "_prompt",
                    max(len(line_text) * 2, 40),
                    cmd_func=self.print_send_data_prompt,
                    args=(row.cid,),
                )
                name_draw.draw()
                return_list.append(name_draw.return_text)
                if row.required:
                    required_draw = draw.LeftDraw()
                    required_draw.text = _("【必选】")
                    required_draw.draw()
                else:
                    button_draw = draw.CenterButton(
                        _("[√]") if row.chosen else _("[×]"),
                        row.name,
                        10,
                        cmd_func=svc.toggle_send_data,
                        args=(row.cid),
                    )
                    button_draw.draw()
                    return_list.append(button_draw.return_text)
                line_feed.draw()
            line_feed.draw()
            save_draw = draw.CenterButton(
                _("[返回]"), _("返回"), window_width // 2
            )
            save_draw.draw()
            return_list.append(save_draw.return_text)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn == save_draw.return_text:
                break

    def print_send_data_prompt(self, send_data_cid: int) -> None:
        """打印数据的提示信息"""
        line_draw = draw.LineDraw("-", self.width)
        line_draw.draw()
        line_feed.draw()
        ai_chat_send_data = game_config.config_ai_chat_send_data[send_data_cid]
        now_draw = draw.WaitDraw()
        now_draw.text = ai_chat_send_data.prompt
        now_draw.width = self.width
        now_draw.draw()
        line_feed.draw()
        line_feed.draw()

    def change_api_key(self, key_type: str) -> None:
        """修改api密钥"""
        while 1:
            return_list = []
            title_draw = draw.TitleLineDraw(_("更改API密钥"), self.width)
            title_draw.draw()
            self.say(
                _(
                    " \n ○请在下方输入您的{0}，输入完成后点击[确定]即可保存，保存后会在当前目录下创建一个文件，"
                    "请注意保管密钥文件，谨防泄露\n\n\n"
                ).format(key_type)
            )
            ask_text = {
                "OPENAI_API_KEY": _(
                    "请输入您的OpenAI API密钥，应当是以 sk- 开头的一长段字符串（第三方或本地部署没有格式需求）\n"
                ),
                "DEEPSEEK_API_KEY": _(
                    "请输入您的DeepSeek API密钥，应当是以 sk- 开头的一长段字符串（第三方或本地部署没有格式需求）\n"
                ),
                "GEMINI_API_KEY": _(
                    "请输入您的Gemini API密钥，应当是一个长段字符串\n"
                ),
            }[key_type]
            api_key = self.ask(ask_text, 999)
            line_feed.draw()
            line_feed.draw()
            if not svc.key_format_ok(key_type, api_key):
                self.say(
                    _(
                        " \n  输入的API密钥不符合规范，请确认是否输入正确（第三方或本地部署没有格式需求）\n\n"
                    )
                )
            yes_draw = draw.CenterButton(
                _("[确定]"), _("确定"), int(self.width / 2)
            )
            yes_draw.draw()
            return_list.append(yes_draw.return_text)
            back_draw = draw.CenterButton(
                _("[返回]"), _("返回"), int(self.width / 2)
            )
            back_draw.draw()
            return_list.append(back_draw.return_text)
            line_feed.draw()
            yrn = flow_handle.askfor_all(return_list)
            if yrn == yes_draw.return_text:
                self.test_flag = 0
                svc.save_api_key(key_type, api_key)
                break
            elif yrn == back_draw.return_text:
                break

    def test_ai(self) -> None:
        """测试AI"""
        found = svc.model_key()
        if found is None:
            info_draw = draw.WaitDraw()
            info_draw.style = "warning"
            info_draw.text = _(" \n  未设置模型，请先选择模型\n")
            info_draw.width = self.width
            info_draw.draw()
            return
        key_type, known = found
        if not known:
            self.say(
                _(" \n  未识别到gpt或gemini字符，将默认为openAI格式的模型\n")
            )
        client = svc.make_client(key_type)
        if client is None:
            self.say(_(" \n  请先设置该模型的API密钥\n"))
            return
        error = svc.ping(client, key_type, self.say)
        if error is None:
            self.test_flag = 1
        else:
            self.test_flag = 2
            self.error_message = error
