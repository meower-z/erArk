"""
角色取名的测试
==============
- 名字校验（NameRuleTest）：验证 character.validate_character_name 对纯数字、
  系统保留字、重名与合规名字的返回结果及规则先后。
- 取名输入框（NamePromptTest）：验证 input_name_panel.input_name_func 的绘制内容、
  不合规时的提示重问及返回值。
- 调用方（NameCallerTest）：验证角色称呼设置与改名卡将输入的名字写入对应字段。
"""

from unittest import mock

from Script.Config import normal_config
from Script.Core import flow_handle, get_text
from Script.Design import character
from Script.Kernel import core
from Script.Modules.domains import chara_profile, identity, inventory, roster
from Script.Modules.gameplay_resolution import working
from Script.UI.Moudle import draw
from Script.UI.Panel import character_setting, input_name_panel
from Script.UI.Panel import see_item_info_panel
from tests.fast.base import FastTestCase

DIGITS = "角色名不能为纯数字，请重新输入\n"
"""名字全是数字时的提示。"""
RESERVED = "角色名不能为系统保留字，请重新输入\n"
"""名字是系统保留字时的提示。"""
TAKEN = "已有角色使用该姓名，请重新输入\n"
"""名字已被其他角色使用时的提示。"""
ASK = "给她取个名字"
"""取名输入框的询问文本。"""


class NameCase(FastTestCase):
    """打开工作集，设定系统保留字与已用名字的测试基类。"""

    def setUp(self) -> None:
        """打开工作集，把系统保留字设为「系统」「42」「保留字」，把已用名字设为「阿米娅」「7」「保留字」。"""
        super().setUp()
        self.enterContext(working.based_on(core.state()))
        self.enterContext(
            mock.patch.object(
                get_text, "translation_values", {"系统", "42", "保留字"}
            )
        )
        roster.set_names(["阿米娅", "7", "保留字"])


class NameRuleTest(NameCase):
    """character.validate_character_name 的校验规则测试。"""

    def test_each_rule(self) -> None:
        """仅违反单条规则的名字返回对应提示文本。合规名字返回 None。"""
        for name, error in (
            ("2024", DIGITS),
            ("系统", RESERVED),
            ("阿米娅", TAKEN),
            ("凯尔希", None),
            ("W2", None),
        ):
            with self.subTest(name=name):
                self.assertEqual(character.validate_character_name(name), error)

    def test_rule_order(self) -> None:
        """多条规则同时命中时，按纯数字、系统保留字、已有角色重名的先后返回首条提示。"""
        for name, error in (
            ("42", DIGITS),
            ("7", DIGITS),
            ("保留字", RESERVED),
        ):
            with self.subTest(name=name):
                self.assertEqual(character.validate_character_name(name), error)


class NamePromptTest(NameCase):
    """input_name_panel.input_name_func 的绘制、重问与返回值测试。"""

    def setUp(self) -> None:
        """在基类设定之外拦截 NormalDraw 与 LineDraw 的 draw 方法，记录每次绘制。"""
        super().setUp()
        self.drawn: list[tuple[str, str, float]] = []
        for cls in (draw.NormalDraw, draw.LineDraw):
            self.enterContext(
                mock.patch.object(
                    cls, "draw", autospec=True, side_effect=self.keep
                )
            )

    def keep(self, now: draw.NormalDraw | draw.LineDraw) -> None:
        """
        记录被拦截绘制对象的类名、文本与宽度。
        Keyword arguments:
        now -- draw.NormalDraw | draw.LineDraw，调用 draw 方法的绘制对象
        Return arguments:
        None -- 无返回值
        """
        self.drawn.append((type(now).__name__, now.text, now.width))

    def ask(self, *typed: str) -> str:
        """
        用 typed 作为模拟输入调用 input_name_func，断言调用次数与输入个数一致并返回最终名字。
        Keyword arguments:
        typed -- str，依次提供给输入框的名字
        Return arguments:
        str -- input_name_func 返回的名字
        """
        with mock.patch.object(
            flow_handle, "askfor_str", side_effect=typed
        ) as askfor:
            name = input_name_panel.input_name_func(ASK)
        self.assertEqual(askfor.call_count, len(typed))
        return name

    def test_valid_name_returned(self) -> None:
        """首个输入合规时，输入框先绘出换行与整行等号，再绘出询问文本，然后返回该名字。"""
        width = normal_config.config_normal.text_width
        self.assertEqual(self.ask("凯尔希"), "凯尔希")
        self.assertEqual(
            self.drawn,
            [
                ("NormalDraw", "\n", 1),
                ("LineDraw", "=", width),
                ("NormalDraw", ASK, width),
            ],
        )

    def test_rejected_names_ask_again(self) -> None:
        """每个不合规的名字之后，输入框绘出对应提示并重新询问，直到得到合规名字。"""
        prompt = ("NormalDraw", ASK, normal_config.config_normal.text_width)
        self.assertEqual(self.ask("2024", "系统", "阿米娅", "凯尔希"), "凯尔希")
        self.assertEqual(
            self.drawn[2:],
            [
                prompt,
                ("NormalDraw", DIGITS, 0),
                prompt,
                ("NormalDraw", RESERVED, 0),
                prompt,
                ("NormalDraw", TAKEN, 0),
                prompt,
            ],
        )


class NameCallerTest(FastTestCase):
    """角色称呼设置与改名卡经 input_name_panel.input_name_func 取名的测试。"""

    def setUp(self) -> None:
        """创建玩家与一名干员，打开工作集，把取名输入框换成按序返回名字并记下询问文本的替身。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "阿米娅")
        self.enterContext(working.based_on(core.state()))
        self.asked: list[str] = []
        self.names = iter(["凯尔希", "临光"])
        self.enterContext(
            mock.patch.object(
                input_name_panel, "input_name_func", side_effect=self.typed
            )
        )

    def typed(self, ask_text: str) -> str:
        """
        记下询问文本，按序返回下一个名字。
        Keyword arguments:
        ask_text -- str，询问文本
        Return arguments:
        str -- 下一个名字
        """
        self.asked.append(ask_text)
        return next(self.names)

    def test_custom_titles(self) -> None:
        """打开角色设置第 3、4 项时，输入的名字依次成为该角色对玩家的称呼和玩家对该角色的称呼。"""
        panel = character_setting.CharacterSetting(1, 120, 1)
        panel.change_setting(3, 2)
        panel.change_setting(4, 2)
        self.assertEqual(
            self.asked,
            ["请输入该角色对玩家的专属称呼", "请输入玩家对该角色的专属称呼"],
        )
        self.assertEqual(chara_profile.nick_name_to_pl(1), "凯尔希")
        self.assertEqual(chara_profile.nick_name(1), "临光")

    def test_rename_card(self) -> None:
        """使用改名卡（道具 161）会消耗 1 张该道具，并将输入的名字写入玩家姓名。"""
        self.enterContext(mock.patch.object(draw.WaitDraw, "draw"))
        inventory.set_item(0, 161, 1)
        item = see_item_info_panel.ItemNameDraw("161", 120, False, False, 0)
        item.use_consumables()
        self.assertEqual(inventory.items(0)[161], 0)
        self.assertEqual(
            self.asked,
            ["你能回忆起自己的名字吗？（默认称呼为博士，此处仅输入姓名即可）"],
        )
        self.assertEqual(identity.of(0).name, "凯尔希")
