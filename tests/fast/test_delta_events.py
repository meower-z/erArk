"""
数值变化事件协议、适配器、回调与外交周结算测试
==============================================
- 协议校验（DeltaProtocolTest）：覆盖 DeltaEntry 与 DeltaEvent 的字段校验。
- 绘制适配（DeltaAdapterTest）：验证 DeltaEvent 按摘要文本或变化项文本绘制单个对象。
- 回调转发（DeltaHookTest）：验证 emit_delta 的空登记、参数转发与 Tk 回调绘制。
- 结算对照（SettlementParityTest）：验证两个外交周结算按外交结算提示格式绘制并附带变化项。
- 导入边界（DeltaBoundaryTest）：验证 delta_events.py 只导入标准库与 narrative_events。
"""

import ast
import itertools
import math
import os
import random
import sys
from collections.abc import Callable
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import get_text, io_init
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, country, diplomacy, location
from Script.Modules.domains import medical
from Script.Modules.gameplay_resolution import diplomacy_service, ui_hooks
from Script.Modules.gameplay_resolution import working
from Script.Modules.tk_ui import callbacks
from Script.Modules.tk_ui.event_stream_adapter import STREAM
from Script.Protocol import (
    BackendEvent,
    RenderChunk,
    ScriptedUiPort,
    StyleDefOp,
    default_first_option,
)
from Script.Protocol.delta_events import DeltaEntry, DeltaEvent
from Script.Protocol.narrative_events import EventMeta
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase
from tests.world import ROOT

META = EventMeta(0, 0, "test")
""" 测试共用的默认事件元数据。 """
ENTRY = DeltaEntry("甲", "声望", 1)
""" 测试共用的默认数值变化项。 """
DIPLOMAT = 1
""" 测试用外交官角色编号。 """
COLUMBIA = 4
""" 哥伦比亚的出生地编号，其主势力 41 含附属势力。 """
KAZDEL = 6
""" 卡兹戴尔的出生地编号。 """
LATERAN = 7
""" 拉特兰的出生地编号，该国家不参与感染率结算。 """
DURIN = 19
""" 杜林的出生地编号，该地区不在大地图中。 """
SKILL = 3
""" 测试外交官的能力 40 等级。 """
JUDGE = "diplomacy_service.judge_diplomatic_policy"
""" 外交方针结算的事件来源标识。 """
SETTLE = "diplomacy_service.settle_all_country_infection_rate"
""" 感染率周结算的事件来源标识。 """

type Drawn = tuple[str, float, str, str]
""" 一次绘制的类名、宽度、样式名与文本。 """
type Delta = tuple[tuple[DeltaEntry, ...], str, str | None, bool, bool]
""" 一次 emit_delta 收到的变化项、来源、摘要文本、等待与宽度开关。 """


def build(
    make: Callable[..., object], *args: object, **kwargs: object
) -> object:
    """以任意位置与关键字参数调用 make，供测试传入非法字段类型。"""
    return make(*args, **kwargs)


def reputation_notice(total: float) -> str:
    """按声望总变化拼出外交方针结算的提示文本。"""
    return "\n" + get_text._("本周全势力声望变化：{0}\n").format(
        round(total, 2)
    )


def infection_report(average: str, now_change: float) -> str:
    """按平均总变化文本与所在国变化拼出感染率统计报告文本。"""
    return (
        "\n"
        + get_text._("○源石病感染率统计报告：")
        + get_text._("本周各国源石病感染率平均总变化：")
        + average
        + get_text._("当前罗德岛所在国家为{0}，本周感染率变化：{1}%\n").format(
            game_config.config_birthplace[location.country()].name,
            round(now_change, 2),
        )
    )


class DrawCase(FastTestCase):
    """打桩绘制方法、收集样式定义并提供数值变化记录回调的测试基类。"""

    def setUp(self) -> None:
        """
        打桩 NormalDraw、WaitDraw 与 LineDraw 的 draw 方法。
        配置收集样式定义的测试端口并初始化绘制与变化记录列表。
        """
        super().setUp()
        self.drawn: list[Drawn] = []
        self.styles: dict[str, StyleDefOp] = {}
        for cls in (draw.NormalDraw, draw.WaitDraw, draw.LineDraw):
            self.enterContext(
                mock.patch.object(
                    cls, "draw", autospec=True, side_effect=self.keep
                )
            )
        io_init.configure(
            ScriptedUiPort(default_first_option(), listener=self.listen)
        )
        self.width = normal_config.config_normal.text_width
        self.deltas: list[Delta] = []

    def record(
        self,
        entries: tuple[DeltaEntry, ...],
        *,
        source: str,
        summary_text: str | None,
        wait: bool,
        use_text_width: bool,
    ) -> None:
        """记录一次数值变化回调收到的全部参数。"""
        self.deltas.append(
            (entries, source, summary_text, wait, use_text_width)
        )

    def keep(self, now: draw.NormalDraw | draw.LineDraw) -> None:
        """记录一次绘制调用的类名、宽度、样式名与文本内容。"""
        self.drawn.append((type(now).__name__, now.width, now.style, now.text))

    def listen(self, event: BackendEvent) -> None:
        """从测试端口收到的 RenderChunk 事件中收集 StyleDefOp 样式定义。"""
        if isinstance(event, RenderChunk):
            self.styles.update(
                (op.name, op) for op in event.ops if isinstance(op, StyleDefOp)
            )


class DeltaProtocolTest(FastTestCase):
    """DeltaEntry 与 DeltaEvent 的字段校验测试。"""

    def test_entry_accepts_delta_values(self) -> None:
        """验证 DeltaEntry 的三个数值字段接受整数、浮点数、字符串与 None。"""
        for good in (0, -3, 1.5, "上升", None):
            with self.subTest(good=good):
                entry = DeltaEntry("甲", "声望", good, good, good, "%")
                self.assertEqual(
                    (entry.delta, entry.before, entry.after),
                    (good, good, good),
                )

    def test_entry_rejects_bad_values(self) -> None:
        """验证 DeltaEntry 的三个数值字段拒绝布尔、NaN、正负无穷与其他类型。"""
        bads = (True, False, math.nan, math.inf, -math.inf, [1], b"1")
        for name, bad in itertools.product(("delta", "before", "after"), bads):
            fields: dict[str, object] = {"delta": 1, name: bad}
            with (
                self.subTest(name=name, bad=bad),
                self.assertRaises(ValueError),
            ):
                build(DeltaEntry, "甲", "声望", **fields)

    def test_entry_rejects_blank_labels_and_bad_unit(self) -> None:
        """验证 DeltaEntry 拒绝空串、全空白或非字符串标签与非字符串单位。"""
        for bad in ("", " ", "\n", None, 1):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    build(DeltaEntry, bad, "声望", 1)
                with self.assertRaises(ValueError):
                    build(DeltaEntry, "甲", bad, 1)
        for bad in (None, 1):
            with self.subTest(unit=bad), self.assertRaises(ValueError):
                build(DeltaEntry, "甲", "声望", 1, unit=bad)

    def test_event_shapes(self) -> None:
        """验证 DeltaEvent 的元数据、变化项元组、布尔开关与摘要文本校验。"""
        self.assertEqual(
            DeltaEvent(META, (ENTRY,), summary_text="\n").summary_text, "\n"
        )
        cases: list[tuple[tuple[object, ...], dict[str, object]]] = [
            ((None, (ENTRY,)), {}),
            ((META, ()), {}),
            ((META, [ENTRY]), {}),
            ((META, (ENTRY, "甲")), {}),
            ((META, (ENTRY,)), {"summary_text": ""}),
            ((META, (ENTRY,)), {"summary_text": 1}),
            ((META, (ENTRY,)), {"pause": 1}),
            ((META, (ENTRY,)), {"use_text_width": 1}),
        ]
        for args, kwargs in cases:
            with (
                self.subTest(args=args, kwargs=kwargs),
                self.assertRaises(ValueError),
            ):
                build(DeltaEvent, *args, **kwargs)


class DeltaAdapterTest(DrawCase):
    """EventStreamAdapter 绘制 DeltaEvent 的测试。"""

    def assert_one_draw(
        self,
        entries: tuple[DeltaEntry, ...],
        summary: str | None,
        text: str,
    ) -> None:
        """遍历 pause 与 use_text_width 组合绘制 DeltaEvent，断言每次单条记录相符且无样式定义。"""
        for pause, use_text_width in itertools.product((False, True), repeat=2):
            with self.subTest(pause=pause, use_text_width=use_text_width):
                self.drawn.clear()
                event = DeltaEvent(
                    META,
                    entries,
                    pause=pause,
                    use_text_width=use_text_width,
                    summary_text=summary,
                )
                STREAM.render(event)
                kind = "WaitDraw" if pause else "NormalDraw"
                width = self.width if use_text_width else 0
                self.assertEqual(self.drawn, [(kind, width, "standard", text)])
        self.assertEqual(self.styles, {})

    def test_summary_text_draws_one_object(self) -> None:
        """验证带摘要文本的 DeltaEvent 绘制单个对象且不发送样式定义。"""
        summary = "\n摘要：1\n"
        self.assert_one_draw((ENTRY,), summary, summary)

    def test_entries_text_without_summary(self) -> None:
        """验证无摘要文本时按变化项逐行生成文本并绘制单个对象。"""
        entries = (
            DeltaEntry("甲", "声望", 3),
            DeltaEntry("乙", "感染率", -1.5, before=10.0, after=8.5, unit="%"),
            DeltaEntry("丙", "库存", None),
            DeltaEntry("丁", "状态", "高", unit="档"),
            DeltaEntry("戊", "人数", 0, before=5),
        )
        text = (
            "甲 声望：+3\n"
            "乙 感染率：-1.5%（10.0% → 8.5%）\n"
            "丙 库存：—\n"
            "丁 状态：高档\n"
            "戊 人数：0\n"
        )
        self.assert_one_draw(entries, None, text)


class DeltaHookTest(DrawCase):
    """ui_hooks.emit_delta 的登记、转发与 Tk 回调绘制测试。"""

    def test_hook_reaches_only_registered_callbacks(self) -> None:
        """验证未登记回调时 emit_delta 不绘制，登记后转发显式与默认参数。验证 on_delta 返回原回调。"""
        self.enterContext(mock.patch.object(ui_hooks, "_deltas", []))
        entries = (ENTRY, DeltaEntry("乙", "感染率", 0.5, unit="%"))
        ui_hooks.emit_delta(entries, source="t", summary_text="x", wait=True)
        self.assertEqual(self.drawn, [])
        record = self.record
        self.assertIs(ui_hooks.on_delta(record), record)
        ui_hooks.emit_delta(
            entries,
            source="s",
            summary_text="t",
            wait=True,
            use_text_width=True,
        )
        ui_hooks.emit_delta(entries, source="d")
        self.assertEqual(
            self.deltas,
            [
                (entries, "s", "t", True, True),
                (entries, "d", None, False, False),
            ],
        )
        self.assertEqual(self.drawn, [])

    def test_tk_callback_draws_like_notice(self) -> None:
        """验证经已登记的 Tk 回调，emit_delta 与 emit_notice 对相同文本绘制相同对象。"""
        self.assertIn(callbacks.draw_delta, ui_hooks._deltas)
        text = "\n本周变化：1\n"
        for wait, use_text_width in itertools.product((False, True), repeat=2):
            with self.subTest(wait=wait, use_text_width=use_text_width):
                self.drawn.clear()
                ui_hooks.emit_notice(
                    text, wait=wait, use_text_width=use_text_width
                )
                notice = list(self.drawn)
                self.drawn.clear()
                ui_hooks.emit_delta(
                    (ENTRY,),
                    source="t",
                    summary_text=text,
                    wait=wait,
                    use_text_width=use_text_width,
                )
                self.assertEqual(len(notice), 1)
                self.assertEqual(self.drawn, notice)
        self.assertEqual(self.styles, {})


class SettlementParityTest(DrawCase):
    """两个外交周结算经真实回调链绘制提示文本并发出变化项的测试。"""

    def setUp(self) -> None:
        """创建玩家与外交官、打开工作集、补齐国家数据，并在已登记的数值变化回调旁追加记录回调。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(DIPLOMAT, "外交官")
        self.enterContext(working.based_on(core.state()))
        country.fill()
        self.enterContext(
            mock.patch.object(
                ui_hooks, "_deltas", [*ui_hooks._deltas, self.record]
            )
        )

    def assert_emitted(
        self, text: str, entries: tuple[DeltaEntry, ...], source: str
    ) -> None:
        """
        断言恰好绘制一条文本宽度的 standard WaitDraw，且回调收到相同文本与变化项。
        断言通过后清空绘制与变化记录。
        """
        self.assertEqual(
            self.drawn, [("WaitDraw", self.width, "standard", text)]
        )
        self.assertEqual(self.deltas, [(entries, source, text, True, True)])
        self.drawn.clear()
        self.deltas.clear()

    def judge(self, uniform: float) -> float:
        """
        以方针 2 派遣外交官并固定随机数后执行外交方针结算。
        按方针 2 的公式计算并返回声望总变化。
        """
        nation = COLUMBIA * 10 + 1
        subs = game_config.config_nation_data_of_country_subordinate[nation]
        adjust = game_config.config_ability_lv_adjust[SKILL].adjust_value
        abilities.ability(DIPLOMAT)[40] = SKILL
        diplomacy.set_post(COLUMBIA, diplomat=DIPLOMAT, policy=2)
        with mock.patch.object(random, "uniform", return_value=uniform):
            diplomacy_service.judge_diplomatic_policy()
        delta = 0.1 * adjust * (uniform / 10)
        return delta + delta * 0.5 * len(subs)

    def reputation(self, total: float) -> tuple[DeltaEntry, ...]:
        """返回外交方针结算应发出的声望变化项元组。"""
        label, field = get_text._("全势力"), get_text._("声望")
        return (DeltaEntry(label, field, round(total, 2)),)

    def infection(
        self,
        average: float | None,
        before: float | None,
        after: float | None,
    ) -> tuple[DeltaEntry, ...]:
        """按平均变化与所在国前后值构造感染率周结算的两条变化项元组。"""
        field = get_text._("源石病感染率")
        name = game_config.config_birthplace[location.country()].name
        moved = None if before is None or after is None else after - before
        return (
            DeltaEntry(get_text._("各国平均"), field, average, unit="%"),
            DeltaEntry(
                name,
                field,
                0.0 if moved is None else round(moved, 2) + 0.0,
                before=before,
                after=after,
                unit="%",
            ),
        )

    def settle(self, treatment: int) -> tuple[float, float]:
        """设定每周治疗加权量后执行感染率周结算，返回所在国结算前后的感染率。"""
        with medical.editing() as m:
            m.weekly_weighted_treatment = treatment
        before = country.infection_rate(location.country())
        diplomacy_service.settle_all_country_infection_rate()
        return before, country.infection_rate(location.country())

    def next_week(self, treatment: int) -> tuple[float, float, float]:
        """先以治疗量 0 结算并清空记录，再以 treatment 结算，返回所在国前后感染率与平均变化。"""
        self.settle(0)
        self.drawn.clear()
        self.deltas.clear()
        last = country.last_week_rate()
        before, after = self.settle(treatment)
        counted = [
            cid
            for cid, data in game_config.config_birthplace.items()
            if data.inmap and cid != LATERAN
        ]
        average = (country.last_week_rate() - last) / len(counted)
        return before, after, average

    def move_to(self, cid: int) -> None:
        """将罗德岛立即移动到指定国家。"""
        location.set_move(cid, game_time.now())
        location.arrive()
        self.assertEqual(location.country(), cid)

    def test_judge_without_posts_reports_int_zero(self) -> None:
        """验证无外交官时绘制声望变化为 0 的提示文本，且变化项数值为整数 0。"""
        diplomacy_service.judge_diplomatic_policy()
        self.assertIs(type(self.deltas[0][0][0].delta), int)
        self.assert_emitted(reputation_notice(0), self.reputation(0), JUDGE)

    def test_judge_factor_sign_sets_delta_sign(self) -> None:
        """验证随机因子为正或负时按外交方针结算格式绘制提示文本，并发出与随机因子同号的声望变化项。"""
        for uniform in (7, -3):
            with self.subTest(uniform=uniform):
                total = self.judge(uniform)
                self.assertGreater(round(total, 2) * uniform, 0)
                self.assert_emitted(
                    reputation_notice(total), self.reputation(total), JUDGE
                )

    def test_settle_first_week_reports_no_data(self) -> None:
        """验证首周无上周总和时绘制暂无数据报告，平均变化量为 None 且所在国带前后值。"""
        self.assertEqual(country.last_week_rate(), -1.0)
        before = country.infection_rate(location.START)
        change = (before // 10 + 1) * 0.4
        rates = self.settle(100)
        text = infection_report(get_text._("暂无数据\n"), change)
        self.assert_emitted(text, self.infection(None, *rates), SETTLE)

    def test_settle_later_week_signed_average(self) -> None:
        """验证存在上周总和时，治疗量 0 与 1000 下结算分别发出正负平均变化报告与变化项。"""
        for treatment, rate in ((0, 0.5), (1000, -0.5)):
            with self.subTest(treatment=treatment):
                before, after, average = self.next_week(treatment)
                change = (before // 10 + 1) * rate
                self.assertGreater(average * rate, 0)
                text = infection_report(f"{round(average, 2)}%\n", change)
                entries = self.infection(round(average, 2), before, after)
                self.assert_emitted(text, entries, SETTLE)

    def test_settle_zero_average_reports_no_data(self) -> None:
        """验证存在上周总和且平均变化为 0 时，报告绘制暂无数据而平均变化量为 0.0。"""
        before, after, average = self.next_week(500)
        self.assertEqual(average, 0.0)
        self.assertEqual(before, after)
        text = infection_report(get_text._("暂无数据\n"), 0.0)
        entries = self.infection(0.0, before, after)
        self.assert_emitted(text, entries, SETTLE)

    def test_clamped_rate_delta_matches_stored_rates(self) -> None:
        """验证卡兹戴尔感染率被截断至 99.99 时，报告记未截断变化而所在国变化项取存盘差值。"""
        self.move_to(KAZDEL)
        country.set_infection_rate(KAZDEL, 99.5)
        self.assertEqual(self.settle(0), (99.5, 99.99))
        text = infection_report(get_text._("暂无数据\n"), 5.0)
        self.assert_emitted(text, self.infection(None, 99.5, 99.99), SETTLE)

    def test_unsettled_country_has_no_before_after(self) -> None:
        """验证罗德岛位于拉特兰或大地图外杜林时，所在国变化项数值为 0.0 且 before 与 after 为 None。"""
        for cid in (LATERAN, DURIN):
            with self.subTest(cid=cid):
                self.move_to(cid)
                country.set_last_week_rate(-1.0)
                self.settle(0)
                text = infection_report(get_text._("暂无数据\n"), 0.0)
                entries = self.infection(None, None, None)
                self.assert_emitted(text, entries, SETTLE)


class DeltaBoundaryTest(FastTestCase):
    """数值变化事件协议模块的导入边界测试。"""

    def test_imports_only_stdlib_and_narrative_events(self) -> None:
        """验证 delta_events.py 只导入标准库与 Script.Protocol.narrative_events。"""
        path = os.path.join(ROOT, "Script", "Protocol", "delta_events.py")
        with open(path, encoding="utf-8") as source:
            tree = ast.parse(source.read())
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.add("." * node.level + (node.module or ""))
        self.assertEqual(
            {
                name
                for name in names
                if name.split(".")[0] not in sys.stdlib_module_names
            },
            {"Script.Protocol.narrative_events"},
        )
