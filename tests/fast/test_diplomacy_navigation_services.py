"""
势力外交与导航抵达结算服务测试
==============================
- 覆盖 diplomacy_service 的外交方针与感染率周结算及 navigation_service 的抵达判定与导航成就。
- 覆盖经快速层世界登记 Tk 回调后的 WaitDraw 绘制与每日结算的导入边界。
"""

import ast
import datetime
import inspect
import random
from importlib.util import resolve_name
from pathlib import Path
from types import ModuleType
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import get_text
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, achievement, activity, country
from Script.Modules.domains import diplomacy, location, medical, roster
from Script.Modules.domains import visitor
from Script.Modules.gameplay_resolution import achievement_service
from Script.Modules.gameplay_resolution import diplomacy_service
from Script.Modules.gameplay_resolution import navigation_service
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.Protocol.delta_events import DeltaEntry
from Script.Settle import past_day_settle
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase

DIPLOMAT = 1
""" 测试用外交官角色编号 """
ENVOY = 2
""" 测试用第二名外交官角色编号 """
AEGIR = 1
""" 阿戈尔的出生地编号（Birthplace.csv 编号 1） """
COLUMBIA = 4
""" 哥伦比亚的出生地编号（Birthplace.csv 编号 4），主势力 41 含附属势力 """
KAZDEL = 6
""" 卡兹戴尔的出生地编号（Birthplace.csv 编号 6） """
LATERAN = 7
""" 拉特兰的出生地编号（Birthplace.csv 编号 7） """
SAMI = 12
""" 萨米的出生地编号（Birthplace.csv 编号 12） """
DURIN = 19
""" 杜林的出生地编号（Birthplace.csv 编号 19，不在大地图中） """
SKILL = 3
""" 测试外交官的能力 40 等级 """
NAVIGATION_FIRST = 1101
""" 访问两个国家时达成的导航成就编号（Achievement.csv 编号 1101） """
MOVED = (
    "judge_diplomatic_policy",
    "settle_all_country_infection_rate",
    "judge_arrive",
)
""" 由外交与导航后端服务定义的三个结算函数名 """
PANELS = (
    "Script.UI.Panel.nation_diplomacy_panel",
    "Script.UI.Panel.navigation_panel",
)
""" 需校验不绑定结算函数名的外交与导航面板模块全名 """
OWNERS = {diplomacy_service: MOVED[:2], navigation_service: MOVED[2:]}
""" 后端服务模块到其所属结算函数名元组的映射 """
FORBIDDEN = {*MOVED, "*", "__getattr__"}
""" 面板模块禁止绑定的名称集合，含三个结算函数名、* 与 __getattr__ """
NAMED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
""" 通过 name 字段绑定名称的语法树节点类型（函数、异步函数与类） """


def imported_names(module: ModuleType) -> set[str]:
    """解析模块源码语法树，收集全部导入语句解析后的模块全名"""
    return names_in(inspect.getsource(module), module.__package__ or "")


def names_in(source: str, package: str) -> set[str]:
    """收集源码中全部导入语句按指定包名解析后的模块全名"""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = resolve_name("." * node.level + (node.module or ""), package)
            names.update(f"{base}.{alias.name}" for alias in node.names)
    return names


def bindings(source: str) -> set[str]:
    """遍历源码语法树，收集任意作用域中经定义、导入、赋值、属性、下标或 setattr 绑定的名称"""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        store = isinstance(getattr(node, "ctx", None), ast.Store)
        if isinstance(node, NAMED):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(a.asname or a.name.split(".")[0] for a in node.names)
        elif store and isinstance(node, ast.Name):
            names.add(node.id)
        elif store and isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif store and isinstance(node, ast.Subscript):
            names.update(texts([node.slice]))
        elif isinstance(node, ast.Call) and ast.unparse(node.func) == "setattr":
            names.update(texts(node.args[1:2]))
    return names


def texts(nodes: list[ast.expr]) -> set[str]:
    """提取表达式节点列表中的全部字符串字面量"""
    return {
        n.value
        for n in nodes
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }


def bound_names(name: str) -> set[str]:
    """按模块全名定位仓库内对应 .py 文件，不导入模块而收集任意作用域绑定的名称"""
    path = Path(__file__).resolve().parents[2].joinpath(*name.split("."))
    return bindings(path.with_suffix(".py").read_text(encoding="utf-8"))


class NoticeCase(FastTestCase):
    """创建测试角色并记录提示、数值变化与成就解锁回调的测试基类"""

    def setUp(self) -> None:
        """创建角色 0 与两名外交官，并接管提示回调、数值变化回调与成就解锁回调列表"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(DIPLOMAT, "外交官")
        self.world.chara(ENVOY, "驻外干员")
        self.notices: list[tuple[str, bool, str | None, bool]] = []
        self.enterContext(mock.patch.object(ui_hooks, "_notices", [self.note]))
        self.deltas: list[tuple[str | None, bool, bool]] = []
        self.enterContext(mock.patch.object(ui_hooks, "_deltas", [self.delta]))
        self.unlocked: list[list[int]] = []
        self.enterContext(
            mock.patch.object(
                achievement_service, "_unlocked", [self.unlocked.append]
            )
        )

    def note(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """将提示回调收到的四元组参数追加到 self.notices"""
        self.notices.append((text, wait, style, use_text_width))

    def delta(
        self,
        entries: tuple[DeltaEntry, ...],
        *,
        source: str,
        summary_text: str | None,
        wait: bool,
        use_text_width: bool,
    ) -> None:
        """将数值变化回调收到的摘要文本、等待与宽度开关追加到 self.deltas"""
        self.deltas.append((summary_text, wait, use_text_width))


def reputation_notice(total: float) -> str:
    """按声望总变化拼出外交方针结算的总结提示文本"""
    return "\n" + get_text._("本周全势力声望变化：{0}\n").format(
        round(total, 2)
    )


class JudgeDiplomaticPolicyTest(NoticeCase):
    """外交方针结算（judge_diplomatic_policy）的单元测试"""

    def test_each_policy_moves_reputation_or_infection(self) -> None:
        """验证五种外交方针分别正确更新感染率或主附势力声望、外交官经验 80 与 82 及声望总结提示"""
        nation = COLUMBIA * 10 + 1
        subs = game_config.config_nation_data_of_country_subordinate[nation]
        self.assertTrue(subs)
        adjust = game_config.config_ability_lv_adjust[SKILL].adjust_value
        just = 0.7
        cases = {
            1: (0.01, None),
            2: (0.1, 0.5),
            3: (0.1, 3),
            4: (0.05, None),
            5: (0.3, 1),
        }
        for policy, (scale, share) in cases.items():
            with (
                self.subTest(policy=policy),
                working.based_on(core.state()),
                mock.patch.object(
                    random, "uniform", return_value=just * 10
                ) as uniform,
            ):
                self.deltas.clear()
                country.fill()
                abilities.ability(DIPLOMAT)[40] = SKILL
                diplomacy.set_post(COLUMBIA, diplomat=DIPLOMAT, policy=policy)
                rate = country.infection_rate(COLUMBIA)
                exp = dict(abilities.experience(DIPLOMAT))
                diplomacy_service.judge_diplomatic_policy()
                uniform.assert_called_once_with(-6 + SKILL, 6 + SKILL)
                delta = scale * adjust * just
                if share is None:
                    self.assertAlmostEqual(
                        country.infection_rate(COLUMBIA), rate - delta
                    )
                    self.assertEqual(country.reputation(nation), 0)
                    total = 0
                else:
                    self.assertEqual(country.infection_rate(COLUMBIA), rate)
                    self.assertAlmostEqual(country.reputation(nation), delta)
                    for sub in subs:
                        self.assertAlmostEqual(
                            country.reputation(sub), delta * share
                        )
                    total = delta + delta * share * len(subs)
                difficulty = game_config.config_diplomatic_policy[
                    policy
                ].difficulty
                for exp_id in (80, 82):
                    self.assertEqual(
                        abilities.experience(DIPLOMAT)[exp_id]
                        - exp.get(exp_id, 0),
                        difficulty,
                    )
                self.assertEqual(
                    self.deltas, [(reputation_notice(total), True, True)]
                )

    def test_vacant_post_or_unset_policy_is_skipped(self) -> None:
        """验证外交官或方针为 0 时跳过结算且不抽随机数，仍发出声望变化为 0 的总结提示"""
        with (
            working.based_on(core.state()),
            mock.patch.object(random, "uniform") as uniform,
        ):
            country.fill()
            diplomacy.set_post(COLUMBIA, diplomat=0, policy=2)
            diplomacy.set_post(AEGIR, diplomat=DIPLOMAT, policy=0)
            before = (
                country.table(country.REPUTATION),
                country.table(country.INFECTION),
                dict(abilities.experience(DIPLOMAT)),
            )
            diplomacy_service.judge_diplomatic_policy()
            after = (
                country.table(country.REPUTATION),
                country.table(country.INFECTION),
                dict(abilities.experience(DIPLOMAT)),
            )
        self.assertEqual(after, before)
        uniform.assert_not_called()
        self.assertEqual(self.deltas, [(reputation_notice(0), True, True)])


class SettleInfectionRateTest(NoticeCase):
    """感染率周结算（settle_all_country_infection_rate）的单元测试"""

    def setUp(self) -> None:
        """在父类基础上打开工作集上下文并补齐各国感染率表"""
        super().setUp()
        self.enterContext(working.based_on(core.state()))
        country.fill()

    def counted(self) -> list[int]:
        """返回大地图中除拉特兰外的出生地编号列表"""
        return [
            cid
            for cid, data in game_config.config_birthplace.items()
            if data.inmap and cid != LATERAN
        ]

    def report(self, average: str, now_change: float) -> tuple[str, bool, bool]:
        """按平均总变化与所在国变化拼出感染率统计报告的摘要文本、等待与宽度开关三元组"""
        text = (
            "\n"
            + get_text._("○源石病感染率统计报告：")
            + get_text._("本周各国源石病感染率平均总变化：")
            + average
            + get_text._(
                "当前罗德岛所在国家为{0}，本周感染率变化：{1}%\n"
            ).format(
                game_config.config_birthplace[location.country()].name,
                round(now_change, 2),
            )
        )
        return (text, True, True)

    def test_first_week_updates_rates_and_reports_no_data(self) -> None:
        """验证首周结算更新大地图各国感染率与病人系数、跳过杜林与拉特兰感染率、清零治疗量并报暂无数据"""
        country.set_infection_rate(COLUMBIA, 25.0)
        country.set_infection_rate(KAZDEL, 95.0)
        country.set_infection_rate(SAMI, 10.0)
        country.set_infection_rate(LATERAN, 3.0)
        country.set_patient_ratio(LATERAN, 0.5)
        durin = (country.infection_rate(DURIN), country.patient_ratio(DURIN))
        start = country.infection_rate(location.START)
        with medical.editing() as m:
            m.weekly_weighted_treatment = 100
        diplomacy_service.settle_all_country_infection_rate()
        self.assertAlmostEqual(country.infection_rate(COLUMBIA), 26.2)
        self.assertAlmostEqual(country.patient_ratio(COLUMBIA), 26.2 / 30)
        self.assertAlmostEqual(country.infection_rate(KAZDEL), 99.0)
        self.assertEqual(country.patient_ratio(KAZDEL), 3.0)
        self.assertAlmostEqual(country.infection_rate(SAMI), 10.8)
        self.assertAlmostEqual(country.patient_ratio(SAMI), 10.8 / 30)
        self.assertEqual(
            (country.infection_rate(DURIN), country.patient_ratio(DURIN)), durin
        )
        self.assertEqual(country.infection_rate(LATERAN), 3.0)
        self.assertEqual(country.patient_ratio(LATERAN), 0.1)
        self.assertEqual(medical.state().weekly_weighted_treatment, 0)
        self.assertAlmostEqual(
            country.last_week_rate(),
            sum(country.infection_rate(cid) for cid in self.counted()),
        )
        now_change = (start // 10 + 1) * 0.4
        no_data = self.report(get_text._("暂无数据\n"), now_change)
        self.assertEqual(self.deltas, [no_data])

    def test_later_week_reports_average_change(self) -> None:
        """验证已有上周总和时，统计报告写出参与结算各国感染率的平均变化"""
        diplomacy_service.settle_all_country_infection_rate()
        last = country.last_week_rate()
        start = country.infection_rate(location.START)
        self.deltas.clear()
        diplomacy_service.settle_all_country_infection_rate()
        average = (country.last_week_rate() - last) / len(self.counted())
        self.assertGreater(average, 0)
        now_change = (start // 10 + 1) * 0.5
        report = self.report(f"{round(average, 2)}%\n", now_change)
        self.assertEqual(self.deltas, [report])


class JudgeArriveTest(NoticeCase):
    """抵达判断（judge_arrive）的单元测试"""

    def setUp(self) -> None:
        """在父类基础上打开工作集上下文"""
        super().setUp()
        self.enterContext(working.based_on(core.state()))

    def test_no_move_or_not_yet_due_returns_false(self) -> None:
        """验证未移动或未到抵达时刻时返回 False，状态不变且不发提示"""
        self.assertFalse(navigation_service.judge_arrive())
        later = game_time.now() + datetime.timedelta(days=1)
        location.set_move(AEGIR, later)
        self.assertFalse(navigation_service.judge_arrive())
        self.assertEqual(location.country(), location.START)
        self.assertEqual(location.move(), (AEGIR, later))
        self.assertFalse(visitor.moved())
        self.assertEqual(self.notices, [])
        self.assertEqual(achievement.get("visited_nation_list"), [])

    def test_arrival_swaps_diplomats_and_records_visit(self) -> None:
        """验证到时抵达更新位置与外交官上下线、补记已访问国家、发出金色提示并触发导航成就 1101"""
        diplomacy.set_post(location.START, diplomat=DIPLOMAT, policy=1)
        diplomacy.set_post(AEGIR, diplomat=ENVOY, policy=1)
        roster.remove(ENVOY)
        location.set_move(AEGIR, game_time.now())
        settle = self.enterContext(
            mock.patch.object(
                achievement_service,
                "settle_and_notify",
                wraps=achievement_service.settle_and_notify,
            )
        )
        self.assertTrue(navigation_service.judge_arrive())
        self.assertEqual(location.country(), AEGIR)
        self.assertIsNone(location.move())
        self.assertTrue(visitor.moved())
        self.assertFalse(roster.has(DIPLOMAT))
        self.assertEqual(activity.position(DIPLOMAT), ["0", "0"])
        self.assertTrue(roster.has(ENVOY))
        self.assertEqual(achievement.get("visited_nation_list"), [17, AEGIR])
        arrived = get_text._("\n罗德岛已抵达目的地：{0}\n").format(
            game_config.config_birthplace[AEGIR].name
        )
        self.assertEqual(self.notices, [(arrived, True, "gold_enrod", True)])
        settle.assert_called_once_with(get_text._("导航"))
        self.assertEqual(self.unlocked, [[NAVIGATION_FIRST]])

    def test_arrival_home_records_it_once(self) -> None:
        """验证已访问列表为空且抵达国家 17 时只记录一次 17，不达成导航成就"""
        location.set_move(location.START, game_time.now())
        self.assertTrue(navigation_service.judge_arrive())
        self.assertEqual(achievement.get("visited_nation_list"), [17])
        self.assertEqual(self.unlocked, [])


class TkNoticeTest(FastTestCase):
    """经快速层世界登记的 Tk 回调绘制三个结算函数提示的测试"""

    def setUp(self) -> None:
        """创建玩家角色、打开工作集上下文、补齐国家数据并记录 WaitDraw 绘制"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))
        country.fill()
        self.drawn: list[tuple[float, str, str]] = []
        self.enterContext(
            mock.patch.object(
                draw.WaitDraw, "draw", autospec=True, side_effect=self.keep
            )
        )

    def keep(self, now: draw.WaitDraw) -> None:
        """将 WaitDraw 绘制对象的宽度、样式与文本追加到 self.drawn"""
        self.drawn.append((now.width, now.style, now.text))

    def test_notices_draw_as_wait_draws_at_text_width(self) -> None:
        """验证三个结算提示均以配置文本宽度绘制为 WaitDraw，抵达用 gold_enrod，其余用 standard"""
        width = normal_config.config_normal.text_width
        diplomacy_service.judge_diplomatic_policy()
        diplomacy_service.settle_all_country_infection_rate()
        location.set_move(AEGIR, game_time.now())
        navigation_service.judge_arrive()
        arrived = get_text._("\n罗德岛已抵达目的地：{0}\n").format(
            game_config.config_birthplace[AEGIR].name
        )
        self.assertEqual(
            [(w, style) for w, style, _text in self.drawn[:3]],
            [(width, "standard"), (width, "standard"), (width, "gold_enrod")],
        )
        self.assertEqual(self.drawn[0][2], reputation_notice(0))
        self.assertIn(get_text._("暂无数据\n"), self.drawn[1][2])
        self.assertEqual(self.drawn[2][2], arrived)


class SettleImportBoundaryTest(FastTestCase):
    """每日结算导入边界与结算函数模块归属的测试"""

    def test_new_day_imports_services(self) -> None:
        """验证每日结算模块导入外交与导航两个后端服务"""
        names = imported_names(past_day_settle)
        self.assertIn(diplomacy_service.__name__, names)
        self.assertIn(navigation_service.__name__, names)

    def test_relative_imports_resolve_against_the_package(self) -> None:
        """验证相对导入按所在包解析为模块全名，相对形式的面板导入同样会被检出"""
        source = (
            "from ..UI.Panel import navigation_panel\nfrom . import default"
        )
        self.assertEqual(
            names_in(source, past_day_settle.__package__ or ""),
            {"Script.UI.Panel.navigation_panel", "Script.Settle.default"},
        )

    def test_each_service_owns_only_its_functions(self) -> None:
        """验证每个后端服务只定义并绑定自身所属的结算函数，不含其余结算函数"""
        for service, owned in OWNERS.items():
            bound = bound_names(service.__name__)
            for name in MOVED:
                with self.subTest(service=service.__name__, name=name):
                    if name in owned:
                        fn = getattr(service, name)
                        self.assertEqual(fn.__module__, service.__name__)
                        self.assertIn(name, bound)
                    else:
                        self.assertFalse(hasattr(service, name))
                        self.assertNotIn(name, bound)

    def test_panels_bind_no_settle_function(self) -> None:
        """验证外交与导航面板源码任意作用域均不绑定 FORBIDDEN 中的名称"""
        for panel in PANELS:
            with self.subTest(panel=panel):
                self.assertEqual(bound_names(panel) & FORBIDDEN, set())

    def test_binding_scan_sees_each_form(self) -> None:
        """验证 bindings 对十六种绑定写法均能检出 FORBIDDEN 中的名称"""
        for line in (
            "def judge_arrive(): pass",
            "async def judge_arrive(): pass",
            "class judge_arrive: pass",
            "from a.navigation_service import judge_arrive",
            "from a import b as judge_arrive",
            "import judge_arrive",
            "from a import *",
            "judge_arrive = 1",
            "a, (b, judge_arrive) = 1, (2, 3)",
            "[a, judge_arrive] = 1, 2",
            "judge_arrive: int = 1",
            "judge_arrive += 1",
            "(judge_arrive := 1)",
            "globals()['judge_arrive'] = 1",
            "setattr(a, 'judge_arrive', 1)",
            "a.judge_arrive = 1",
        ):
            with self.subTest(line=line):
                self.assertTrue(bindings(line) & FORBIDDEN)
