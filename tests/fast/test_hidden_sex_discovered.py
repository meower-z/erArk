"""
H中被发现选择结算测试
=====================
DiscoveredUiFreeTest 在无界面子进程中验证未登记报错、支开分支与界面模块隔离。
DiscoveredFlowTest 验证情境文本、目标重选、打断反应与五类选项分支的进程内结算。
DiscoveredTkTest 验证 Tk 选项渲染顺序与模式邀请面板打开回调。
"""

from unittest import mock

from Script.Config import normal_config
from Script.Core import constant, flow_handle
from Script.Design import instuct_judege
from Script.Modules.domains import action_info, activity, flags, h_state
from Script.Modules.domains import modes
from Script.Modules.gameplay_resolution import achievement_service
from Script.Modules.gameplay_resolution import hidden_sex_discovered
from Script.Modules.gameplay_resolution import modal_hooks, plan_queue
from Script.Modules.gameplay_resolution import ui_hooks
from Script.Modules.tk_ui import callbacks
from Script.Protocol.modal_prompts import ChoiceOption, ChoicePrompt
from Script.Protocol.modal_prompts import ChoiceResult
from Script.UI.Moudle import draw, view
from Script.UI.Panel import exhibitionism_sex_panel, hidden_sex_panel
from tests import chara_abilities as ca, kernel_data
from tests.chara_activity import aim
from tests.fast.base import FastTestCase

PARTNER = 1
""" 与博士处于H状态的交互对象角色编号（1）。 """
FINDER = 2
""" 发现博士H的角色编号（2）。 """
BYSTANDER = 3
""" 同场景旁观者角色编号（3）。 """
B = constant.Behavior
""" constant.Behavior 的简短别名。 """
ENDED = {
    0: [B.H_INTERRUPT],
    PARTNER: [B.WAIT],
    FINDER: [B.SEE_H_AND_INTERRUPT],
}
""" 非群交状态下结束H时主角、对象与发现者的预期计划行为映射。 """
CHILD_RUN = """
from Script.Config import map_config
from Script.Kernel import core
from Script.Modules.domains import flags, identity
from Script.Modules.gameplay_resolution import hidden_sex_discovered as found
from Script.Modules.gameplay_resolution import modal_hooks, plan_queue
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.Protocol.modal_prompts import ChoiceResult
from tests import chara_abilities, chara_data, kernel_data
from tests.chara_activity import aim, place
from tests.world import DEFAULT_SCENE, STANDARD_OUTFIT, start_time

map_config.init_map_data()
kernel_data.reset_clock(start_time(), {})
for cid in (0, 1, 2):
    kernel_data.put(identity.put, identity.Identity(cid, name=f"c{cid}", sex=1))
    chara_abilities.zero_tables(cid)
    chara_data.seed(cid, STANDARD_OUTFIT)
    place(cid, DEFAULT_SCENE)
aim(0, 1)
core.reset_state(kernel_data.reprojected(core.state()))
notices, asked, answers = [], [], ["1", "2"]


@ui_hooks.on_notice
def keep(text, **kwargs):
    notices.append(text)


def answer(prompt):
    asked.append([prompt.title, [o.option_id for o in prompt.options]])
    return ChoiceResult(prompt.prompt_id, answers.pop(0))


chara_abilities.talent(2)[222] = 1
with working.based_on(core.state()):
    flags.set(1, is_h=True)
    try:
        found.resolve(2, False)
    except RuntimeError as error:
        payload["unasked"] = str(error)
    modal_hooks.on_choice(answer)
    found.resolve(2, False)
    payload["planned"] = [i["behavior_id"] for i in plan_queue.planned(2)]
    try:
        found.resolve(2, False)
    except RuntimeError as error:
        payload["uninvited"] = str(error)
    payload["seen"] = flags.get(2, "see_pl_h")
payload["notices"] = notices
payload["asked"] = asked
"""
""" 在无界面子进程中验证未登记报错、222 号素质支开与模块隔离的测试脚本。 """


def planned() -> dict[int, list[str]]:
    """
    收集主角、对象、发现者与旁观者计划队列中的行为编号，并过滤空队列。
    Return arguments:
    dict[int, list[str]] -- 存在已排入行为的角色编号到行为编号列表的映射
    """
    found = {
        cid: [item["behavior_id"] for item in plan_queue.planned(cid)]
        for cid in (0, PARTNER, FINDER, BYSTANDER)
    }
    return {cid: ids for cid, ids in found.items() if ids}


class DiscoveredUiFreeTest(FastTestCase):
    """无界面子进程中 hidden_sex_discovered.resolve 的报错、支开结算与模块隔离测试。"""

    def test_resolve_without_ui(self) -> None:
        """
        在启动基础配置的无界面子进程中运行 CHILD_RUN。
        验证未登记选择处理器与未登记邀请处理器时分别抛出预期 RuntimeError。
        验证登记返回 "1" 与 "2" 的处理器后，两次提示标题均为 "H中被发现" 且选项为 "1" 至 "5"，
        支开分支排入 SEE_H_BUT_DECEIVED、写入 see_pl_h 并发出 222 号素质提示文本，
        且子进程未尝试导入也未载入受拦截模块。
        """
        from tests.ui_free_subprocess import run_ui_free

        child = run_ui_free(CHILD_RUN, boot=True)
        self.assertEqual(
            child.payload["unasked"], "no choice handler for sex_be_discovered"
        )
        self.assertEqual(child.payload["planned"], [B.SEE_H_BUT_DECEIVED])
        self.assertEqual(
            child.payload["uninvited"], "no invite handler for hidden"
        )
        self.assertEqual(
            child.payload["notices"],
            ["c2还不懂这是什么意义，被你随口糊弄走了\n"],
        )
        self.assertEqual(
            child.payload["asked"],
            [["H中被发现", ["1", "2", "3", "4", "5"]]] * 2,
        )
        self.assertTrue(child.payload["seen"])
        self.assertEqual((child.attempted, child.loaded), ([], []))


class DiscoveredFlowTest(FastTestCase):
    """hidden_sex_discovered.resolve 的情境文本、重选目标、打断标记与五类分支进程内测试。"""

    def setUp(self) -> None:
        """
        初始化含博士、对象、发现者与旁人的测试世界，设置对象处于H状态与发现者初始标记。
        注册计划队列清理并初始化记录字段，将选择提示、模式邀请、成就判定、指令判定与通知回调
        替换为测试桩。
        """
        super().setUp()
        self.addCleanup(plan_queue.forget)
        self.world.chara(0, "博士")
        self.world.chara(PARTNER, "对方")
        self.world.chara(FINDER, "发现者")
        self.world.chara(BYSTANDER, "旁人")
        aim(0, PARTNER)
        aim(FINDER, BYSTANDER)
        kernel_data.put(flags.set, PARTNER, is_h=True)
        kernel_data.put(flags.set, FINDER, npc_masturebate_for_player=True)
        self.prompts: list[ChoicePrompt] = []
        """ 测试桩按顺序记录的 ChoicePrompt 列表。 """
        self.answer = "5"
        """ 打桩选择处理器返回给 resolve 的选项标识，默认 "5"。 """
        self.invites: list[str] = []
        """ 测试桩按顺序记录的模式邀请类型列表。 """
        self.invite_failed = False
        """ 打桩模式邀请回调返回的失败标志，默认 False。 """
        self.invite_mode = 0
        """ 邀请成功时由测试桩写入主角 hidden_sex_mode 的模式值，默认 0。 """
        self.unlocked: list[int] = []
        """ 测试桩按顺序记录的已触发成就编号列表。 """
        self.notices: list[str] = []
        """ 测试桩按顺序记录的通知文本列表。 """
        self.passed: set[str] = set()
        """ 打桩指令判定中视作通过的判定名称集合。 """
        unlock = "get_achievement_judge_by_value"
        for owner, name, value in (
            (modal_hooks, "_ask", self.ask),
            (hidden_sex_discovered, "_invite", self.invite),
            (
                achievement_service,
                unlock,
                lambda key, _: self.unlocked.append(key),
            ),
            (instuct_judege, "calculation_instuct_judege", self.judge),
            (
                ui_hooks,
                "_notices",
                [lambda text, **_: self.notices.append(text)],
            ),
        ):
            self.enterContext(mock.patch.object(owner, name, value))

    def ask(self, prompt: ChoicePrompt) -> ChoiceResult:
        """
        记录收到的 ChoicePrompt，断言提问前四项状态写入均已完成，并返回指向 self.answer 的 ChoiceResult。
        Keyword arguments:
        prompt -- ChoicePrompt，resolve 发起的选项提示
        Return arguments:
        ChoiceResult -- 选中 self.answer 的选择结果
        """
        self.prompts.append(prompt)
        self.assertTrue(flags.get(FINDER, "see_pl_h"))
        self.assertFalse(flags.get(FINDER, "npc_masturebate_for_player"))
        self.assertEqual(activity.target(FINDER), 0)
        self.assertEqual(activity.behavior(0).h_interrupt_chara_name, "发现者")
        return ChoiceResult(prompt.prompt_id, self.answer)

    def invite(self, mode: hidden_sex_discovered.InviteMode) -> bool:
        """
        记录邀请模式，在未失败且 self.invite_mode 非零时写入主角 hidden_sex_mode，再返回失败标志。
        Keyword arguments:
        mode -- hidden_sex_discovered.InviteMode，请求的模式邀请类型
        Return arguments:
        bool -- self.invite_failed 的当前取值
        """
        self.invites.append(mode)
        if not self.invite_failed and self.invite_mode:
            flags.set(0, hidden_sex_mode=self.invite_mode)
        return self.invite_failed

    def judge(
        self, cid: int, target: int, name: str, **kwargs: bool
    ) -> list[float]:
        """
        按判定名是否位于 self.passed 返回通过或失败的判定结果列表。
        Keyword arguments:
        cid -- int，发起判定的角色编号，此桩实现不使用
        target -- int，判定对象角色编号，此桩实现不使用
        name -- str，指令判定名称
        kwargs -- bool，其余关键字参数，此桩实现不使用
        Return arguments:
        list[float] -- 首项为 1 或 0 的三元素判定结果列表
        """
        return [1 if name in self.passed else 0, 0, 0.0]

    def run_flow(
        self, answer: str, from_hidden_sex_flag: bool = False
    ) -> dict[int, list[str]]:
        """
        设定预设回答并将面板置为 SEE_MAP，在写入事务内执行 resolve，断言返回后切回 IN_SCENE。
        计算并返回本次调用新排入计划队列的各角色行为编号映射。
        Keyword arguments:
        answer -- str，本次模拟玩家选择的选项标识
        from_hidden_sex_flag -- bool，是否由隐奸被发现触发，默认 False
        Return arguments:
        dict[int, list[str]] -- 本次调用新增计划行为的角色编号到行为编号列表映射
        """
        before = planned()
        self.answer = answer
        view.now_panel_id = constant.Panel.SEE_MAP
        kernel_data.written(
            hidden_sex_discovered.resolve, FINDER, from_hidden_sex_flag
        )
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
        added = {
            cid: ids[len(before.get(cid, [])) :]
            for cid, ids in planned().items()
        }
        return {cid: ids for cid, ids in added.items() if ids}

    def test_situation_text(self) -> None:
        """验证七种状态与标记组合下，提示标题均为 "H中被发现" 且正文包含对应的情境描述文本。"""
        cases = (
            ("", False, "你正在和对方单独H"),
            ("group", False, "你正在和对方等多人群交"),
            ("npc_active_h", False, "对方正在逆推你"),
            ("unconscious_h", False, "你正在无意识奸对方"),
            ("exhibitionism_sex_mode", False, "你和对方的露出"),
            ("", True, "你和对方的隐奸"),
            ("hidden_sex_mode", False, "你和对方的隐奸"),
        )
        for mark, from_hidden, situation in cases:
            with self.subTest(mark=mark, from_hidden=from_hidden):
                if mark == "group":
                    kernel_data.put(modes.set_group_sex, True)
                elif mark == "npc_active_h":
                    kernel_data.put(h_state.set, PARTNER, npc_active_h=True)
                elif mark:
                    kernel_data.put(flags.set, 0, **{mark: 1})
                self.run_flow("5", from_hidden)
                prompt = self.prompts[-1]
                self.assertEqual(
                    (prompt.title, prompt.text),
                    ("H中被发现", f"\n发现者发现了{situation}，要怎么做？\n"),
                )

    def test_partner_out_of_h_retargets(self) -> None:
        """验证原交互对象未处于H状态时，resolve 将主角目标重设为同场景处于H状态的旁人并仅对其写入 h_interrupt。"""
        kernel_data.put(flags.set, PARTNER, is_h=False)
        kernel_data.put(flags.set, BYSTANDER, is_h=True)
        self.run_flow("5")
        self.assertEqual(activity.target(0), BYSTANDER)
        self.assertIn("旁人", self.prompts[0].text)
        self.assertEqual(action_info.get(BYSTANDER, "h_interrupt"), 1)
        self.assertEqual(action_info.get(PARTNER, "h_interrupt"), 0)

    def test_reaction_interrupts_finder(self) -> None:
        """验证在写入事务内执行支开通过分支时，经 plan_queue 仅向内核登记发现者的打断请求。"""
        self.passed = {"目击H后被话术支开"}
        self.answer = "1"
        with kernel_data.writing():
            position = plan_queue.mark()
            hidden_sex_discovered.resolve(FINDER, False)
            interrupted = plan_queue.take_since(position)
        self.assertEqual(interrupted, [str(FINDER)])

    def test_talk_away(self) -> None:
        """验证支开分支在判定通过、判定失败与发现者拥有 222 号素质三种情形下的计划行为与通知文本。"""
        self.passed = {"目击H后被话术支开"}
        self.assertEqual(self.run_flow("1"), {FINDER: [B.SEE_H_BUT_DECEIVED]})
        self.assertEqual(self.notices, [""])
        self.passed = set()
        self.assertEqual(self.run_flow("1"), ENDED)
        ca.talent(FINDER)[222] = 1
        self.assertEqual(self.run_flow("1"), {FINDER: [B.SEE_H_BUT_DECEIVED]})
        self.assertEqual(
            self.notices[-1], "发现者还不懂这是什么意义，被你随口糊弄走了\n"
        )

    def test_hidden_switch(self) -> None:
        """验证转为隐奸分支在模式 1 触发 914 号成就、模式 2 不触发成就及邀请失败时结束H的表现。"""
        self.invite_mode = 1
        self.assertEqual(self.run_flow("2"), {})
        self.assertEqual((self.invites, self.unlocked), (["hidden"], [914]))
        kernel_data.put(flags.set, 0, hidden_sex_mode=0)
        self.invite_mode = 2
        self.assertEqual((self.run_flow("2"), self.unlocked), ({}, [914]))
        kernel_data.put(flags.set, 0, hidden_sex_mode=0)
        self.invite_failed = True
        self.assertEqual((self.run_flow("2"), self.unlocked), (ENDED, [914]))

    def test_exhibitionism_switch(self) -> None:
        """验证非露出模式下选 "3" 触发露出邀请，成功时解锁 934 号成就，失败时结束H。"""
        self.assertEqual(self.run_flow("3"), {})
        self.assertEqual(
            (self.invites, self.unlocked), (["exhibitionism"], [934])
        )
        self.invite_failed = True
        self.assertEqual((self.run_flow("3"), self.unlocked), (ENDED, [934]))

    def test_exhibitionism_keeps_going(self) -> None:
        """验证已处于露出模式时选 "3" 不调用邀请回调，并按露出与 H模式判定结果分别排入无视、离开或结束H。"""
        kernel_data.put(flags.set, 0, exhibitionism_sex_mode=1)
        for passed, reaction in (
            ({"露出", "H模式"}, {FINDER: [B.SEE_H_BUT_IGNORE]}),
            ({"H模式"}, {FINDER: [B.SEE_H_AND_LEAVE]}),
            (set(), ENDED),
        ):
            with self.subTest(passed=passed):
                self.passed = passed
                self.assertEqual(self.run_flow("3"), reaction)
                self.assertEqual(self.invites, [])

    def test_group_invite(self) -> None:
        """验证非群交状态下选 "4" 通过判定时排入转群交行动并触发 905 号成就，发现者疲惫时结束H。"""
        self.passed = {"群交"}
        self.assertEqual(
            self.run_flow("4"),
            {
                0: [B.OTHER_SEX_BE_FOUND_TO_GROUP_SEX],
                FINDER: [B.DISCOVER_OTHER_SEX_AND_JOIN],
            },
        )
        self.assertEqual(self.unlocked, [905])
        kernel_data.put(flags.set, FINDER, tired=True)
        self.assertEqual(self.run_flow("4"), ENDED)

    def test_group_sex_join_or_refuse(self) -> None:
        """验证群交状态下选 "4" 按判定排入加入或拒绝且不触发成就，选 "5" 排入 GROUP_SEX_END。"""
        kernel_data.put(modes.set_group_sex, True)
        for passed, reaction in (
            ({"群交"}, B.JOIN_GROUP_SEX),
            (set(), B.REFUSE_JOIN_GROUP_SEX),
        ):
            with self.subTest(passed=passed):
                self.passed = passed
                self.assertEqual(self.run_flow("4"), {FINDER: [reaction]})
        self.assertEqual(self.run_flow("5"), {**ENDED, 0: [B.GROUP_SEX_END]})
        self.assertEqual(self.unlocked, [])


class DiscoveredTkTest(FastTestCase):
    """callbacks 中「H中被发现」选项渲染器与模式邀请打开回调的测试。"""

    def test_choice_draws(self) -> None:
        """验证经 modal_hooks.ask 调用 Tk 渲染器时的绘制顺序、提供给 askfor_all 的返回键列表与返回值。"""
        drawn: list[tuple[object, ...]] = []
        offers: list[list[str]] = []

        def record(shown: draw.NormalDraw) -> None:
            """
            将一次绘制调用按按钮、标题或普通文本分类记录到外层 drawn 列表。
            Keyword arguments:
            shown -- draw.NormalDraw，被调用 draw 方法的绘制对象
            Return arguments:
            None -- 无返回值
            """
            if isinstance(shown, draw.CenterButton):
                drawn.append(("button", shown.text, shown.return_text))
            elif isinstance(shown, draw.TitleLineDraw):
                drawn.append(("title", shown.title))
            else:
                drawn.append(("text", shown.text))

        def answer(return_list: list[str], *args: object) -> str:
            """
            记录本次提供的返回键列表副本并返回列表末项作为模拟选择。
            Keyword arguments:
            return_list -- list[str]，渲染器传给 askfor_all 的可选返回键列表
            args -- object，其余位置参数，此桩实现不使用
            Return arguments:
            str -- return_list 的最后一个返回键
            """
            offers.append(list(return_list))
            return return_list[-1]

        for shown in (draw.NormalDraw, draw.TitleLineDraw, draw.LeftButton):
            self.enterContext(
                mock.patch.object(
                    shown, "draw", autospec=True, side_effect=record
                )
            )
        self.enterContext(mock.patch.object(flow_handle, "askfor_all", answer))
        prompt = ChoicePrompt(
            hidden_sex_discovered.DISCOVERED_PROMPT_ID,
            (ChoiceOption("1", "[1]甲"), ChoiceOption("5", "[5]乙")),
            text="正文",
            title="标题",
        )
        self.assertEqual(modal_hooks.ask(prompt).selected_option_id, "5")
        self.assertEqual(
            drawn,
            [
                ("title", "标题"),
                ("text", "正文"),
                ("text", "\n"),
                ("button", "[1]甲", "1"),
                ("text", "\n"),
                ("button", "[5]乙", "5"),
                ("text", "\n"),
            ],
        )
        self.assertEqual(offers, [["1", "5"]])

    def test_invite_opens_mode_panel(self) -> None:
        """
        验证 draw_discovered_invite 按模式以配置文本宽度和被发现标志打开对应模式面板，
        并返回其 invite_failed。
        """
        opened: list[tuple[str, int, bool]] = []

        def show(panel: hidden_sex_panel.Select_Hidden_Sex_Mode_Panel) -> None:
            """
            记录模式选择面板的类名、宽度与被发现标志，并仅对隐奸模式面板将 invite_failed 设为 True。
            Keyword arguments:
            panel -- hidden_sex_panel.Select_Hidden_Sex_Mode_Panel，被调用 draw 的模式选择面板实例
            Return arguments:
            None -- 无返回值
            """
            opened.append(
                (
                    type(panel).__name__,
                    panel.width,
                    panel.sex_be_discovered_flag,
                )
            )
            panel.invite_failed = isinstance(
                panel, hidden_sex_panel.Select_Hidden_Sex_Mode_Panel
            )

        for panel in (
            hidden_sex_panel.Select_Hidden_Sex_Mode_Panel,
            exhibitionism_sex_panel.Select_Exhibitionism_Sex_Mode_Panel,
        ):
            self.enterContext(
                mock.patch.object(
                    panel, "draw", autospec=True, side_effect=show
                )
            )
        width = normal_config.config_normal.text_width
        self.assertEqual(
            [
                callbacks.draw_discovered_invite("hidden"),
                callbacks.draw_discovered_invite("exhibitionism"),
            ],
            [True, False],
        )
        self.assertEqual(
            opened,
            [
                ("Select_Hidden_Sex_Mode_Panel", width, True),
                ("Select_Exhibitionism_Sex_Mode_Panel", width, True),
            ],
        )
