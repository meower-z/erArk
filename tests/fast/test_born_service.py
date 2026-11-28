"""
生产与破壳结算服务与 Tk 回调测试
================================
BornFlowCase 与 CrowdCase 提供共用的世界初始化、钩子打桩与辅助方法。
LiveBirthTest 验证单胎、高扩张保留、同卵双胞胎、多胎、胎教转写与女儿生育成就。
NameCheckTest 验证新生儿取名校验的重问提示与重复非法名称抛错。
HandlerCheckTest 验证缺少选择或取名处理函数时直接报错且不写入状态。
DoctorTest 验证凯尔希、医疗干员与无医生时的接生人选定规则。
KaltsitBirthTest 验证母亲为凯尔希时由其他医疗干员接生。
WardTest 验证母亲已在住院区时保持原病房且玩家前往会合。
HardEggTest 验证带壳卵单枚破壳的状态写入、乳汁上限与文本。
SoftEggTest 验证无壳卵多枚同孵与单枚孵化的状态与文本。
TkRowsTest 验证 Tk 等待按钮渲染与取名回调对接 input_name_panel。
"""

from unittest import mock

from Script.Config import normal_config
from Script.Core import constant, flow_handle, get_text
from Script.Design import game_time, handle_premise, map_handle
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, growth, identity
from Script.Modules.domains import pregnancy, relations, roster
from Script.Modules.gameplay_resolution import achievement_service, born_service
from Script.Modules.gameplay_resolution import modal_hooks, pregnancy_hooks
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.Protocol.modal_prompts import ChoiceOption, ChoicePrompt
from Script.Protocol.modal_prompts import ChoiceResult
from Script.System.Pregnancy_System import egg_handle
from Script.UI.Moudle import draw
from Script.UI.Panel import input_name_panel
from tests import chara_abilities as ca
from tests import kernel_data
from tests.fast.base import FastTestCase

_ = get_text._
""" 文本翻译函数，指向 get_text._。 """
MOTHER = 1
""" 测试使用的母亲角色编号（1）。 """
HARD_EGG_RACE = 6
""" 测试使用的带壳卵生种族编号（6）。 """
SOFT_EGG_RACE = 11
""" 测试使用的无壳卵生种族编号（11）。 """
WARDS = constant.place_data["Inpatient_Department"]
""" 医疗部住院区（Inpatient_Department）场景路径字符串列表。 """
BYSTANDERS = range(4, 10)
""" 医生选定测试使用的路人角色编号范围（4 至 9）。 """


class BornFlowCase(FastTestCase):
    """born_service.resolve_born 进程内流程测试的共用基类。"""

    race = 0
    mother_name = "测试母亲"

    def setUp(self) -> None:
        """初始化玩家与母亲角色、工作集，并打桩选项、取名、提示、分隔线与成就钩子。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(MOTHER, self.mother_name, race=self.race)
        self.events: list[tuple[object, ...]] = []
        self.notices: list[str] = []
        self.asks: list[str] = []
        self.prompts: list[ChoicePrompt] = []
        self.settle = mock.Mock()
        for owner, name, value in (
            (modal_hooks, "_ask", self.answer),
            (pregnancy_hooks, "_name_input", self.name),
            (ui_hooks, "_notices", [self.notice]),
            (ui_hooks, "_dividers", [lambda char: self.events.append(("-",))]),
            (achievement_service, "settle_and_notify", self.settle),
        ):
            self.enterContext(mock.patch.object(owner, name, value))
        self.settle.side_effect = lambda *args: self.events.append(args)
        self.enterContext(working.based_on(core.state()))

    def answer(self, prompt: ChoicePrompt) -> ChoiceResult:
        """记录等待提示对象与事件，并返回首项对应的 ChoiceResult。"""
        self.prompts.append(prompt)
        self.events.append(("ask", prompt.prompt_id))
        return ChoiceResult(prompt.prompt_id, prompt.options[0].option_id)

    def name(self, ask_text: str) -> str:
        """记录取名事件与询问文本，按调用顺序返回「宝0」「宝1」等测试名称。"""
        self.events.append(("name",))
        self.asks.append(ask_text)
        return f"宝{len(self.asks) - 1}"

    def notice(self, text: str, **options: object) -> None:
        """记录提示正文与 wait、use_text_width 选项标记。"""
        self.notices.append(text)
        self.events.append(
            ("notice", options["wait"], options["use_text_width"])
        )

    def doctor(self, cid: int, name: str) -> None:
        """在测试世界中创建指定编号与名称且职业为 3（医疗）的角色。"""
        self.world.chara(cid, name)
        kernel_data.put(identity.update, cid, profession=3)

    def pregnant(self, fetus: int, *, identical: bool = False) -> None:
        """为母亲设置临盆（22）、孕肚（26）、胎数、同卵标记与妊娠加速天数。"""
        talent = ca.talent(MOTHER)
        talent[22] = 1
        talent[26] = 1
        pregnancy.update(
            MOTHER,
            fetus_count=fetus,
            identical_twins=identical,
            acceleration_days=2.0,
        )

    def children(self) -> list[str]:
        """返回母亲名下当前全部子女的角色名称列表。"""
        return [
            identity.of(cid).name for cid in relations.child_id_list(MOTHER)
        ]

    def joined(self, text: str) -> list[str]:
        """筛选并返回 self.notices 中包含指定子串的提示文本列表。"""
        return [notice for notice in self.notices if text in notice]

    def arrival(self) -> str:
        """执行一次单胎生产并返回含「推开产房的门」的首条诞生提示。"""
        self.pregnant(1)
        born_service.resolve_born(MOTHER)
        return self.joined("推开产房的门")[0]


class LiveBirthTest(BornFlowCase):
    """胎生生产流程的事件顺序、状态写入、多胎、胎教转写与成就测试。"""

    def test_single_birth(self) -> None:
        """验证单胎生产的事件顺序、等待选项、取名询问、住院区移动与产后状态写入。"""
        self.pregnant(1)
        born_service.resolve_born(MOTHER)
        paragraph = ("notice", True, True)
        feed = ("notice", False, False)
        pause = ("notice", True, False)
        self.assertEqual(
            self.events,
            [("-",), paragraph, feed, ("ask", born_service.WAIT_PROMPT_ID)]
            + [paragraph, feed, ("name",), paragraph, feed]
            + [paragraph, pause, pause, (_("生育"),)],
        )
        self.assertEqual(
            [(o.option_id, o.label) for o in self.prompts[0].options],
            [("wait", _("[焦急等待]"))],
        )
        self.assertEqual(self.asks, [_(" 你决定给女儿取名为——")])
        self.assertEqual(self.children(), ["宝0"])
        child = relations.child_id_list(MOTHER)[0]
        self.assertEqual(pregnancy.of(child).born_time, game_time.now())
        talent = abilities.talent(MOTHER)
        self.assertEqual((talent[22], talent[23], talent[26]), (0, 1, 0))
        experience = abilities.experience(MOTHER)
        self.assertEqual(
            (experience[65], experience[68], experience[86]), (10, 10, 1)
        )
        ability = abilities.ability(MOTHER)
        self.assertEqual((ability[9], ability[12]), (5, 5))
        state = pregnancy.of(MOTHER)
        self.assertEqual(
            (state.fetus_count, state.identical_twins, state.acceleration_days),
            (0, False, 0.0),
        )
        self.assertEqual(len(self.joined("上升至5级")), 1)
        ward = map_handle.get_map_system_path_str_for_list(
            activity.position(MOTHER)
        )
        self.assertIn(ward, WARDS)
        self.assertEqual(activity.position(0), activity.position(MOTHER))

    def test_high_dilation_is_kept(self) -> None:
        """验证母亲扩张能力（9、12）已高于 5 级时生产结算保留原值且不提示升级。"""
        self.pregnant(1)
        ability = ca.ability(MOTHER)
        ability[9] = 6
        ability[12] = 7
        born_service.resolve_born(MOTHER)
        ability = abilities.ability(MOTHER)
        self.assertEqual((ability[9], ability[12]), (6, 7))
        self.assertEqual(self.joined("上升至5级"), [])

    def test_identical_twins(self) -> None:
        """验证同卵双胞胎按姐姐与妹妹顺序询问取名、输出汇总并清除同卵标记。"""
        self.pregnant(2, identical=True)
        born_service.resolve_born(MOTHER)
        self.assertEqual(
            self.asks,
            [
                _(" 你决定给双胞胎中的姐姐取名为——"),
                _(" 你决定给双胞胎中的妹妹取名为——"),
            ],
        )
        self.assertEqual(self.children(), ["宝0", "宝1"])
        self.assertEqual(len(self.joined("宝0与宝1")), 1)
        self.assertFalse(pregnancy.of(MOTHER).identical_twins)

    def test_triplets(self) -> None:
        """验证三胞胎按序号询问取名、忽略同卵标记、输出多人汇总并清零胎数。"""
        self.pregnant(3, identical=True)
        born_service.resolve_born(MOTHER)
        self.assertEqual(
            self.asks,
            [_(" 你决定给第{0}个女儿取名为——").format(i) for i in (1, 2, 3)],
        )
        self.assertEqual(len(self.joined("宝0、宝1、宝2")), 1)
        self.assertEqual(pregnancy.of(MOTHER).fetus_count, 0)

    def test_prenatal_points_go_to_every_child(self) -> None:
        """验证母亲胎教值全额转写给每名新生儿、逐个提示并在结束后清零母亲侧。"""
        self.pregnant(2)
        pregnancy.update(MOTHER, prenatal_point=30.0)
        born_service.resolve_born(MOTHER)
        grown = [growth.of(cid) for cid in relations.child_id_list(MOTHER)]
        self.assertEqual(
            [None if g is None else g.prenatal_point for g in grown],
            [30.0, 30.0],
        )
        self.assertEqual(len(self.joined("胎教")), 2)
        self.assertEqual(pregnancy.of(MOTHER).prenatal_point, 0.0)

    def test_player_daughter_unlocks_daughter_birth(self) -> None:
        """验证母亲为玩家女儿时追加调用 707 号生育成就结算。"""
        self.pregnant(1)
        self.enterContext(
            mock.patch.object(
                handle_premise,
                "handle_self_is_player_daughter",
                return_value=1,
            )
        )
        born_service.resolve_born(MOTHER)
        self.assertEqual(
            self.settle.call_args_list,
            [mock.call(_("生育")), mock.call(_("生育"), 707)],
        )


class NameCheckTest(BornFlowCase):
    """新生儿取名校验的重问提示与重复非法名称抛错测试。"""

    def test_rejected_names_are_asked_again(self) -> None:
        """验证重名与纯数字名称输出提示并重问，且次胎校验包含前胎已用名。"""
        roster.add_name("旧名")
        replies = iter(["旧名", "123", "宝0", "宝0", "宝1"])
        self.enterContext(
            mock.patch.object(
                pregnancy_hooks,
                "_name_input",
                lambda text: self.asks.append(text) or next(replies),
            )
        )
        self.pregnant(2, identical=True)
        born_service.resolve_born(MOTHER)
        elder = _(" 你决定给双胞胎中的姐姐取名为——")
        younger = _(" 你决定给双胞胎中的妹妹取名为——")
        self.assertEqual(self.asks, [elder] * 3 + [younger] * 2)
        self.assertEqual(self.children(), ["宝0", "宝1"])
        taken = _("已有角色使用该姓名，请重新输入\n")
        digits = _("角色名不能为纯数字，请重新输入\n")
        errors = [n for n in self.notices if n in (taken, digits)]
        self.assertEqual(errors, [taken, digits, taken])

    def test_repeated_rejected_name_raises(self) -> None:
        """验证取名回调重复返回已被拒绝的名称时抛出 ValueError 且不创建新生儿。"""
        self.enterContext(
            mock.patch.object(pregnancy_hooks, "_name_input", lambda t: "7")
        )
        self.pregnant(1)
        with self.assertRaises(ValueError):
            born_service.resolve_born(MOTHER)
        self.assertEqual(self.children(), [])


class HandlerCheckTest(BornFlowCase):
    """缺少选择或取名处理函数时的前置校验测试。"""

    def test_missing_handler_changes_nothing(self) -> None:
        """验证缺少选择或取名处理函数时抛出 RuntimeError 且工作集与事件均无写入。"""
        for owner, name in (
            (modal_hooks, "_ask"),
            (pregnancy_hooks, "_name_input"),
        ):
            with (
                self.subTest(name),
                mock.patch.object(owner, name, None),
                working.based_on(core.state()) as buffer,
            ):
                with self.assertRaises(RuntimeError):
                    born_service.resolve_born(MOTHER)
                self.assertEqual(buffer.effects(), ())
            self.assertEqual(self.events, [])


class CrowdCase(BornFlowCase):
    """在 BornFlowCase 基础上向测试世界加入六名路人角色的基类。"""

    def setUp(self) -> None:
        """调用父类初始化并为 BYSTANDERS 中的每个编号创建路人角色。"""
        super().setUp()
        for cid in BYSTANDERS:
            self.world.chara(cid, f"路人{cid}")


class DoctorTest(CrowdCase):
    """不同在册医生配置下的接生人选定测试。"""

    def test_kaltsit_delivers(self) -> None:
        """验证在册角色同时有医疗干员与凯尔希时优先由凯尔希接生。"""
        self.doctor(2, "医生")
        self.world.chara(3, _("凯尔希"))
        self.assertIn(_("凯尔希") + "推开产房的门", self.arrival())

    def test_doctor_delivers_without_kaltsit(self) -> None:
        """验证没有凯尔希时由职业为 3 的医疗干员接生。"""
        self.doctor(2, "医生")
        self.assertIn("医生推开产房的门", self.arrival())

    def test_anyone_delivers_without_doctor(self) -> None:
        """验证既无凯尔希也无医疗干员时从在册角色中随机选一人接生。"""
        names = [f"路人{cid}推开产房的门" for cid in BYSTANDERS]
        names.append(f"{self.mother_name}推开产房的门")
        arrival = self.arrival()
        self.assertEqual(sum(name in arrival for name in names), 1)


class KaltsitBirthTest(CrowdCase):
    """母亲本人为凯尔希时的接生人选定测试。"""

    mother_name = _("凯尔希")

    def test_kaltsit_mother_gets_doctor(self) -> None:
        """验证母亲名为凯尔希时不由自己接生，而是选定在册医疗干员。"""
        self.doctor(2, "医生")
        self.assertIn("医生推开产房的门", self.arrival())


class WardTest(BornFlowCase):
    """母亲已在住院区时的场景移动行为测试。"""

    def test_mother_in_ward_stays(self) -> None:
        """验证母亲已在住院区场景时留在原病房，且玩家移动至同一场景。"""
        ward = map_handle.get_map_system_path_for_str(WARDS[-1])
        self.world.move(MOTHER, ward)
        self.pregnant(1)
        born_service.resolve_born(MOTHER)
        self.assertEqual(list(activity.position(MOTHER)), ward)
        self.assertEqual(list(activity.position(0)), ward)


class HardEggTest(BornFlowCase):
    """带壳卵生破壳流程的状态与文本测试。"""

    race = HARD_EGG_RACE

    def test_hatch_one_egg(self) -> None:
        """验证单枚带壳卵破壳仅移除该卵、授予育儿与泌乳、按罩杯设乳汁上限并加妊娠经验。"""
        talent = ca.talent(MOTHER)
        talent[121] = 0
        talent[123] = 1
        hatched = egg_handle.add_egg(MOTHER, True)
        kept = egg_handle.add_egg(MOTHER, True)
        born_service.resolve_born(MOTHER, (hatched,))
        self.assertEqual(list(pregnancy.of(MOTHER).eggs), [kept])
        self.assertEqual(self.asks, [_(" 你决定给女儿取名为——")])
        self.assertEqual(self.children(), ["宝0"])
        talent = abilities.talent(MOTHER)
        self.assertEqual(
            [talent[k] for k in (22, 23, 24, 26, 27)], [0, 0, 1, 0, 1]
        )
        self.assertEqual(pregnancy.milk_max(MOTHER), 230)
        experience = abilities.experience(MOTHER)
        self.assertEqual((experience[65], experience[86]), (0, 1))
        self.assertEqual(len(self.joined("破壳")), 2)
        self.assertEqual(len(self.joined("照顾宝0为主")), 1)


class SoftEggTest(BornFlowCase):
    """无壳卵生破壳流程的多卵与单卵测试。"""

    race = SOFT_EGG_RACE

    def test_hatch_together(self) -> None:
        """验证三枚无壳卵同批孵化时清空全部卵、按序取名并输出同批孵化汇总文本。"""
        eggs = tuple(
            egg_handle.add_egg(MOTHER, True, soft=True) for _i in "abc"
        )
        born_service.resolve_born(MOTHER, eggs)
        self.assertEqual(pregnancy.of(MOTHER).eggs, {})
        self.assertEqual(
            self.asks,
            [_(" 你决定给第{0}个女儿取名为——").format(i) for i in (1, 2, 3)],
        )
        self.assertEqual(len(self.joined("3颗受精卵粒")), 2)
        self.assertEqual(len(self.joined("一同孵化了：宝0、宝1、宝2")), 1)
        self.assertEqual(len(self.joined("照顾宝0、宝1、宝2为主")), 1)

    def test_hatch_single(self) -> None:
        """验证单枚无壳卵孵化时按单人询问取名、输出凝胶文本且不输出同批汇总。"""
        egg = egg_handle.add_egg(MOTHER, True, soft=True)
        born_service.resolve_born(MOTHER, (egg,))
        self.assertEqual(self.asks, [_(" 你决定给女儿取名为——")])
        self.assertEqual(len(self.joined("凝胶")), 2)
        self.assertEqual(self.joined("一同孵化了"), [])


class TkRowsTest(FastTestCase):
    """born_callbacks 中 Tk 等待按钮与取名回调的测试。"""

    def test_wait_button(self) -> None:
        """验证 WAIT_PROMPT_ID 经 LeftButton 按文本宽度绘制按钮并以 "\n" 完成等待应答。"""
        buttons: list[tuple[str, str, float]] = []
        offers: list[list[str]] = []

        def keep(button: draw.LeftButton) -> None:
            """记录传入 LeftButton.draw 的按钮文本、响应文本与宽度。"""
            buttons.append((button.text, button.return_text, button.width))

        def pick(return_list: list[str], *args: object) -> str:
            """记录传入 flow_handle.askfor_all 的应答列表并返回首项。"""
            offers.append(list(return_list))
            return return_list[0]

        self.enterContext(
            mock.patch.object(
                draw.LeftButton, "draw", autospec=True, side_effect=keep
            )
        )
        self.enterContext(mock.patch.object(flow_handle, "askfor_all", pick))
        prompt = ChoicePrompt(
            born_service.WAIT_PROMPT_ID, (ChoiceOption("wait", "[等]"),)
        )
        self.assertEqual(modal_hooks.ask(prompt).selected_option_id, "wait")
        width = normal_config.config_normal.text_width
        self.assertEqual(buttons, [("[等]", "\n", width)])
        self.assertEqual(offers, [["\n"]])

    def test_name_goes_to_input_panel(self) -> None:
        """验证 pregnancy_hooks.ask_name 将询问文本转发至 input_name_panel.input_name_func。"""
        panel = self.enterContext(
            mock.patch.object(
                input_name_panel, "input_name_func", return_value="阿宝"
            )
        )
        self.assertEqual(pregnancy_hooks.ask_name("问"), "阿宝")
        panel.assert_called_once_with("问")
