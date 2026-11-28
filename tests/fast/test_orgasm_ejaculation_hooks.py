"""
高潮与射精结算界面回调测试
==========================
- TkRendererTest：验证启动加载顺序登记忍耐、对象与部位三个选项渲染函数。
- OrgasmJudgeTest：验证玩家射精时 orgasm_judge 对忍耐判定与射精结算的调用。
- EdgeNoticeTest：验证寸止判定结果经提示回调派发。
- ClimaxPanelTest：验证玩家 P 部位绝顶时 base_chara_climix_common_settle 调用射精结算。
- ImportBoundaryTest：验证独立子进程加载两个结算模块时不加载界面与 Tk 模块。
"""

import json
import subprocess
import sys
from unittest import mock

from Script.Core import game_type, get_text
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, h_meters, h_state
from Script.Modules.gameplay_resolution import ejaculation_service, ui_hooks
from Script.Modules.gameplay_resolution import working
from Script.Modules.tk_ui import callbacks
from Script.Settle import common_default, orgasm_settle
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

TARGET = 1
""" 测试使用的目标角色编号（1）。 """
NAME = "测试干员"
""" 测试使用的目标角色名称。 """
STARTUP_CHECK = """
import json, sys
from Script.Config import normal_config
normal_config.init_normal_config()
from Script.Modules.gameplay_resolution import ejaculation_service
before = "Script.Modules.tk_ui.callbacks" in sys.modules
from Script.Kernel import core
from Script.Modules import load_order
core.load(load_order.LOAD_ORDER)
from Script.Modules.tk_ui import choice_prompts
ids = [
    ejaculation_service.ENDURE_PROMPT_ID,
    ejaculation_service.TARGET_PROMPT_ID,
    ejaculation_service.PART_PROMPT_ID,
]
found = [choice_prompts.RENDERERS.get(i) for i in ids]
print(json.dumps({
    "before": before,
    "renderers": [None if f is None else [f.__module__, f.__name__] for f in found],
}))
"""
""" 子进程脚本源码：装载内核并输出 callbacks 加载前状态及三个射精选项渲染函数的登记结果。 """
CLEAN_RUN = """
import json, sys
from Script.Config import normal_config
normal_config.init_normal_config()
from Script.Modules.gameplay_resolution import ejaculation_service
from Script.Settle import common_default, orgasm_settle
loaded = sorted(
    name
    for name in sys.modules
    if name.split(".")[0] in ("tkinter", "_tkinter")
    or name.startswith(("Script.UI", "Script.Modules.tk_ui"))
)
print(json.dumps({"loaded": loaded}))
"""
""" 子进程脚本源码：导入射精服务与两个结算模块，以 JSON 输出已加载的界面与 Tk 模块列表。 """

type Drawn = tuple[str, object, object, object]
""" 一次绘制的记录元组类型，依次为绘制类名、文本、宽度与样式名。 """

_ = get_text._


class DrawCase(FastTestCase):
    """初始化玩家与目标角色，并接管 draw 模块中各绘制类 draw 方法的测试基类。"""

    def setUp(self) -> None:
        """初始化玩家与目标角色，打开工作集，并将各绘制类的 draw 调用记录到 self.drawn。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(TARGET, NAME)
        self.enterContext(working.based_on(core.state()))
        self.drawn: list[Drawn] = []
        classes = [
            cls
            for cls in vars(draw).values()
            if isinstance(cls, type) and hasattr(cls, "draw")
        ]
        for cls in classes:
            self.enterContext(
                mock.patch.object(
                    cls, "draw", autospec=True, side_effect=self.keep
                )
            )

    def keep(self, now: object) -> None:
        """
        记录一次被调用 draw 方法的绘制对象信息到 self.drawn。
        Keyword arguments:
        now -- object，被调用 draw 方法的绘制对象实例
        """
        self.drawn.append(
            (
                type(now).__name__,
                getattr(now, "text", None),
                getattr(now, "width", None),
                getattr(now, "style", None),
            )
        )


class TkRendererTest(DrawCase):
    """正常启动加载顺序登记三个射精选项 Tk 渲染函数的测试。"""

    def test_startup_registers_tk_callbacks(self) -> None:
        """
        验证独立子进程按启动加载顺序装载内核后，
        会登记 draw_endure_choice、draw_target_choice 与 draw_part_choice。
        """
        result = subprocess.run(
            [sys.executable, "-c", STARTUP_CHECK],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        report = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(
            report,
            {
                "before": False,
                "renderers": [
                    ["Script.Modules.tk_ui.callbacks", "draw_endure_choice"],
                    [
                        "Script.Modules.tk_ui.ejaculation_callbacks",
                        "draw_target_choice",
                    ],
                    [
                        "Script.Modules.tk_ui.ejaculation_callbacks",
                        "draw_part_choice",
                    ],
                ],
            },
        )


class OrgasmJudgeTest(DrawCase):
    """玩家射精槽满时 orgasm_judge 对忍耐判定与射精结算入口的调用测试。"""

    def setUp(self) -> None:
        """
        将玩家射精槽设为已满、精液量设为 100，
        并将 emit_endure_panel 与 resolve_ejaculation 替换为 self.endure 与 self.resolve。
        """
        super().setUp()
        h_meters.set(0, eja=1000, eja_max=1000, semen=100, extra_semen=0)
        self.endure = mock.Mock(return_value=False)
        self.resolve = mock.Mock()
        self.enterContext(
            mock.patch.object(
                ejaculation_service, "emit_endure_panel", self.endure
            )
        )
        self.enterContext(
            mock.patch.object(
                ejaculation_service, "resolve_ejaculation", self.resolve
            )
        )
        self.change = game_type.CharacterStatusChange()

    def test_endured_skips_panel(self) -> None:
        """
        验证 emit_endure_panel 返回 True 时直接返回，
        不登记射精二段行为也不调用 resolve_ejaculation。
        """
        self.endure.return_value = True
        orgasm_settle.orgasm_judge(0, self.change)
        self.endure.assert_called_once_with()
        self.resolve.assert_not_called()
        self.assertEqual(activity.second_behavior(0, "p_orgasm_small"), 0)
        self.assertEqual(self.drawn, [])

    def test_not_endured_shows_panel(self) -> None:
        """
        验证 emit_endure_panel 返回 False 时登记 p_orgasm_small、清空射精槽，
        并调用一次 resolve_ejaculation。
        """
        orgasm_settle.orgasm_judge(0, self.change)
        self.endure.assert_called_once_with()
        self.resolve.assert_called_once_with()
        self.assertEqual(activity.second_behavior(0, "p_orgasm_small"), 1)
        self.assertEqual(h_meters.of(0)["eja"], 0)
        self.assertEqual(self.drawn, [])

    def test_skip_endure_shows_panel(self) -> None:
        """
        验证 skip_undure 为真时不调用 emit_endure_panel，
        按忍住次数登记 p_orgasm_strong 并调用一次 resolve_ejaculation。
        """
        h_state.set(0, endure_not_shot_count=4)
        orgasm_settle.orgasm_judge(0, self.change, skip_undure=True)
        self.endure.assert_not_called()
        self.resolve.assert_called_once_with()
        self.assertEqual(activity.second_behavior(0, "p_orgasm_strong"), 1)

    def test_no_semen_skips_both_hooks(self) -> None:
        """
        验证玩家精液合计不超过 2ml 时登记 p_no_semen_climax，
        且不调用忍耐判定与射精结算入口。
        """
        h_meters.set(0, semen=2, extra_semen=0)
        orgasm_settle.orgasm_judge(0, self.change)
        self.endure.assert_not_called()
        self.resolve.assert_not_called()
        self.assertEqual(activity.second_behavior(0, "p_no_semen_climax"), 1)


class EdgeNoticeTest(DrawCase):
    """judge_orgasm_edge_success 的寸止结果提示派发测试。"""

    def setUp(self) -> None:
        """将 ui_hooks._notices 暂时替换为只含 self.record 的列表。"""
        super().setUp()
        self.notices: list[tuple[str, bool, str | None, bool]] = []
        self.enterContext(
            mock.patch.object(ui_hooks, "_notices", [self.record])
        )

    def record(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """
        将一次经 ui_hooks.emit_notice 派发的提示参数元组追加到 self.notices。
        Keyword arguments:
        text -- str，提示文本
        wait -- bool，是否等待玩家确认
        style -- str | None，文本样式名
        use_text_width -- bool，是否按配置文本宽度排版
        """
        self.notices.append((text, wait, style, use_text_width))

    def judge(self, level: int, roll: float = 0.5) -> bool:
        """
        以玩家寸止技巧等级 level 与随机数 roll 对一个部位的一次寸止计数进行判定。
        Keyword arguments:
        level -- int，玩家能力 30 的等级
        roll -- float，random.uniform 的返回值
        Return arguments:
        bool -- judge_orgasm_edge_success 的结果
        """
        abilities.ability(0)[30] = level
        with mock.patch.object(orgasm_settle.random, "uniform") as uniform:
            uniform.return_value = roll
            return orgasm_settle.judge_orgasm_edge_success(TARGET, {4: 1})

    def test_success_notice(self) -> None:
        """验证技巧余量大于 2 时判定成功，并派发一条不等待、默认样式与宽度的成功提示。"""
        self.assertIs(self.judge(2), True)
        text = "\n" + _("成功寸止了{0}的绝顶\n").format(NAME)
        self.assertEqual(self.notices, [(text, False, None, False)])
        self.assertEqual(self.drawn, [])

    def test_near_limit_notice(self) -> None:
        """验证技巧余量在 0 到 2 之间时判定成功，并派发接近极限的提示。"""
        self.assertIs(self.judge(1), True)
        text = "\n" + _(
            "成功寸止了{0}的绝顶，但差不多也到了能控制住的极限了，还是尽快释放出来比较好\n"
        ).format(NAME)
        self.assertEqual(self.notices, [(text, False, None, False)])

    def test_fail_and_over_limit_notices(self) -> None:
        """验证技巧不足时随机数低于失败率则判定失败，否则判定成功，两种结果各派发对应提示。"""
        self.assertIs(self.judge(0, roll=0.0), False)
        self.assertIs(self.judge(0, roll=0.99), True)
        self.assertEqual(
            [text for text, *_rest in self.notices],
            [
                "\n" + _("尝试寸止{0}的绝顶，但失败了\n").format(NAME),
                "\n"
                + _(
                    "成功寸止了{0}的绝顶，但已经超过了能控制住的极限，随时都可能释放出来\n"
                ).format(NAME),
            ],
        )

    def test_tk_notice_draws_normal_text(self) -> None:
        """验证经 callbacks.draw_notice 派发时，成功提示绘制为一个宽度为 0、样式为 standard 的 NormalDraw。"""
        ui_hooks._notices[:] = [callbacks.draw_notice]
        self.judge(2)
        text = "\n" + _("成功寸止了{0}的绝顶\n").format(NAME)
        self.assertEqual(self.drawn, [("NormalDraw", text, 0, "standard")])


class ClimaxPanelTest(DrawCase):
    """base_chara_climix_common_settle 在玩家 P 部位绝顶时的射精结算调用测试。"""

    def setUp(self) -> None:
        """将玩家射精槽设为 500，并将 resolve_ejaculation 替换为模拟函数 self.resolve。"""
        super().setUp()
        h_meters.set(0, eja=500)
        self.resolve = mock.Mock()
        self.enterContext(
            mock.patch.object(
                ejaculation_service, "resolve_ejaculation", self.resolve
            )
        )

    def test_penis_climax_shows_panel(self) -> None:
        """验证玩家 P 部位（part_id 为 3）绝顶时清空射精槽并调用一次 resolve_ejaculation。"""
        common_default.base_chara_climix_common_settle(0, part_id=3)
        self.resolve.assert_called_once_with()
        self.assertEqual(h_meters.of(0)["eja"], 0)
        self.assertEqual(self.drawn, [])

    def test_npc_penis_part_is_ignored(self) -> None:
        """验证非玩家角色的 P 部位绝顶直接返回，不调用 resolve_ejaculation。"""
        common_default.base_chara_climix_common_settle(TARGET, part_id=3)
        self.resolve.assert_not_called()


class ImportBoundaryTest(FastTestCase):
    """独立子进程导入射精服务与两个结算模块时不加载界面与 Tk 模块的测试。"""

    def test_settles_load_without_panel(self) -> None:
        """验证独立子进程导入射精服务与两个结算模块后，不加载界面模块与 Tk 模块。"""
        result = subprocess.run(
            [sys.executable, "-c", CLEAN_RUN],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        report = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(report, {"loaded": []})
