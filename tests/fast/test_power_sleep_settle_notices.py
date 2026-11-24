"""
动力与睡眠结算提示经 ui_hooks 发出的测试
========================================
- 提示发出（PowerSleepNoticeTest）：验证 power_settle 与 sleep_settle 经 ui_hooks 发出各结算提示参数。
- Tk 回调绘制（TkPowerSleepNoticeTest）：验证已登记的 Tk 提示回调以预期绘制类、文本、宽度与样式绘制上述提示。
- 导入边界（PowerSleepImportBoundaryTest）：经语法树检查两模块源码，验证任意作用域不含各自禁用的模块导入。
"""

import functools
import os
from collections.abc import Callable
from typing import NamedTuple
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import save_handle
from Script.Kernel import core
from Script.Modules.domains import activity, h_meters, needs, player_ability
from Script.Modules.domains import power_supply
from Script.Modules.gameplay_resolution import achievement_service, ui_hooks
from Script.Modules.gameplay_resolution import working
from Script.Settle import power_settle, sleep_settle
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase
from tests.fast.test_ejaculation_services import imports_in
from tests.world import ROOT

OPERATOR = 1
"""测试使用的干员角色编号（1）。"""
POWER = 12.34
"""人力发电测试中由模拟函数返回的电量值（12.34）。"""
GUARDS = (
    (power_settle, ("Script.UI", "tkinter", "Script.Core.io_init")),
    (sleep_settle, ("Script.UI", "tkinter")),
)
"""各结算模块与其禁止导入前缀的配对元组。sleep_settle 保留 Script.Core.io_init 以在耗时结算前刷出入睡提示。"""


class Notice(NamedTuple):
    """一条预期提示的参数记录，依次对应 ui_hooks.emit_notice 的 text、wait、style 与 use_text_width。"""

    text: str
    wait: bool
    style: str | None
    use_text_width: bool


def power_day(**changes: object) -> dict[str, object]:
    """
    构造默认有余电的动力日结算数据字典，并用 changes 覆盖指定字段。
    Keyword arguments:
    changes -- object，按字段名覆盖默认日结算数据的关键字参数
    Return arguments:
    dict[str, object] -- 合并后的动力日结算数据字典
    """
    day: dict[str, object] = {
        "fuel_use": 10.0,
        "fuel_plan": 10.0,
        "fire_power": 100.0,
        "clean": (1, 2, 3),
        "clean_power": 50.5,
        "generated": 150.5,
        "consumed": 120.0,
        "short": False,
        "gap": 0.0,
        "drawn": 0.0,
        "storage": 80.0,
        "storage_max": 200,
        "remain_gap": 0.0,
        "shortage_ratio": 0.0,
        "discharged": 1.2,
        "discharge_rate": 0.01,
        "after_discharge": 78.8,
        "surplus": 30.5,
        "charged": 20.0,
        "overflow": 10.5,
    }
    day.update(changes)
    return day


POWER_REPORTS = (
    (
        power_day(),
        "\n○动力区结算\n"
        " - 火力发电：消耗燃料 10.0 单位，产出 100.0 单位电量\n"
        " - 清洁能源：水 1 风 2 太阳能 3 台，总产出 50.5 单位电量\n"
        " - 汇总：总发电 150.5 单位电量，总耗电 120.0 单位电量\n"
        " - 自放电：损失 1.2 单位电量 (1.00%)，储能剩余 78.8\n"
        " - 结余：过剩 30.5 单位电量，充入 20.0 单位电量，当前储能 80.0/200，溢出 10.5 单位电量\n",
    ),
    (
        power_day(
            fuel_use=4.0,
            fire_power=40.0,
            generated=90.0,
            consumed=150.0,
            short=True,
            gap=60.0,
            drawn=50.0,
            storage=0.0,
            remain_gap=10.0,
            shortage_ratio=0.25,
        ),
        "\n○动力区结算\n"
        " - 火力发电：燃料不足（计划 10.0，实际 4.0），按比例产出 40.0 单位电量\n"
        " - 清洁能源：水 1 风 2 太阳能 3 台，总产出 50.5 单位电量\n"
        " - 汇总：总发电 90.0 单位电量，总耗电 150.0 单位电量\n"
        " - 亏电：缺口 60.0 单位电量，已从蓄电池补充 50.0 单位电量，剩余储能 0.0/200\n"
        " - 警告：仍缺 10.0 单位电量，占需求 25.0%\n",
    ),
    (
        power_day(
            generated=90.0,
            consumed=120.0,
            short=True,
            gap=30.0,
            drawn=30.0,
            storage=50.0,
        ),
        "\n○动力区结算\n"
        " - 火力发电：消耗燃料 10.0 单位，产出 100.0 单位电量\n"
        " - 清洁能源：水 1 风 2 太阳能 3 台，总产出 50.5 单位电量\n"
        " - 汇总：总发电 90.0 单位电量，总耗电 120.0 单位电量\n"
        " - 亏电：缺口 30.0 单位电量，已从蓄电池补充 30.0 单位电量，剩余储能 50.0/200\n"
        " - 已完全由蓄电池弥补当日缺口\n",
    ),
)
"""三组 (日结算数据, 预期报告文本) 用例元组，分别对应有结余、燃料不足且仍缺电与蓄电池补足缺口。"""


class PowerSleepNoticeTest(FastTestCase):
    """验证 power_settle 与 sleep_settle 经 ui_hooks 发出提示参数的单元测试。"""

    def setUp(self) -> None:
        """创建玩家与测试干员、打开工作集，并模拟成就结算函数与存档函数 save_handle.establish_save。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(OPERATOR, "测试干员")
        self.enterContext(working.based_on(core.state()))
        for name in ("get_achievement_judge_by_value", "settle_and_notify"):
            self.enterContext(mock.patch.object(achievement_service, name))
        self.save = self.enterContext(
            mock.patch.object(save_handle, "establish_save")
        )

    def expect(self, run: Callable[[], object], notices: list[Notice]) -> None:
        """
        将 ui_hooks._notices 临时替换为单个模拟回调并执行 run，断言回调按顺序收到 notices 中的参数。
        Keyword arguments:
        run -- Callable[[], object]，触发结算提示的无参可调用对象
        notices -- list[Notice]，预期按顺序收到的提示参数列表
        Return arguments:
        None -- 无返回值
        """
        handler = mock.Mock()
        with mock.patch.object(ui_hooks, "_notices", [handler]):
            run()
        self.assertEqual(
            handler.call_args_list,
            [
                mock.call(
                    n.text,
                    wait=n.wait,
                    style=n.style,
                    use_text_width=n.use_text_width,
                )
                for n in notices
            ],
        )

    def test_power_report_waits_with_settled_text(self) -> None:
        """验证三组日结算数据下 settle_power_system 发出等待型动力结算报告并返回缺口比例与文本。"""
        returned: list[object] = []
        for day, text in POWER_REPORTS:
            with (
                self.subTest(text=text.splitlines()[-1]),
                mock.patch.object(power_supply, "settle_day", return_value=day),
            ):
                self.expect(
                    lambda: returned.append(power_settle.settle_power_system()),
                    [Notice(text, True, None, True)],
                )
                self.assertEqual(returned.pop(), (day["shortage_ratio"], text))

    def test_power_report_silent_without_draw_flag(self) -> None:
        """验证 draw_flag 为 False 时 settle_power_system 不发出提示且返回缺口比例与文本。"""
        day, text = POWER_REPORTS[0]
        returned: list[object] = []
        with mock.patch.object(power_supply, "settle_day", return_value=day):
            self.expect(
                lambda: returned.append(
                    power_settle.settle_power_system(draw_flag=False)
                ),
                [],
            )
        self.assertEqual(returned, [(0.0, text)])

    def test_human_power_notice_by_climax(self) -> None:
        """验证 store_power_by_human_power 按绝顶分支发出等待提示，并在 draw_flag 为 False 时静默。"""
        tail = "性爱发电装置产生了 12.3 单位电量\n"
        self.enterContext(
            mock.patch.object(power_supply, "human_power", return_value=POWER)
        )
        for degree, cid, head in (
            (1, 0, "\n在博士射精的同时，"),
            (4, OPERATOR, "\n在测试干员绝顶的同时，"),
            (5, OPERATOR, "\n在测试干员2重绝顶的同时，"),
            (7, 0, "\n在博士4重绝顶的同时，"),
        ):
            with self.subTest(degree=degree, cid=cid):
                self.expect(
                    functools.partial(
                        power_settle.store_power_by_human_power, degree, cid
                    ),
                    [Notice(head + tail, True, None, True)],
                )
        with self.subTest(draw_flag=False):
            self.expect(
                lambda: power_settle.store_power_by_human_power(
                    1, 0, draw_flag=False
                ),
                [],
            )

    def test_sleep_start_and_player_line_feed(self) -> None:
        """验证 update_sleep 依次发出两条不等待的提示：按文本宽度的入睡提示与默认宽度的单换行提示。"""
        self.expect(
            sleep_settle.update_sleep,
            [
                Notice("\n博士入睡，开始结算各种数据\n", False, None, True),
                Notice("\n", False, None, False),
            ],
        )

    def test_autosave_tip_waits_before_saving(self) -> None:
        """验证 update_save 发出含最小编号小贴士的等待型自动存档提示，并以 "auto" 调用一次存档函数。"""
        tip_id = min(game_config.config_tip_data)
        tip = game_config.config_tip_data[tip_id].info
        self.enterContext(
            mock.patch.object(
                sleep_settle.random, "choice", return_value=tip_id
            )
        )
        self.expect(
            sleep_settle.update_save,
            [
                Notice(
                    "\n全部结算完毕，开始自动保存\n"
                    f"\n请博士在保存时阅读今日的小贴士：\n\n  {tip}\n\n\n",
                    True,
                    None,
                    True,
                )
            ],
        )
        self.save.assert_called_once_with("auto")

    def test_sanity_growth_notice(self) -> None:
        """验证 sanity_point_grow 在理智消耗为 49 时静默，在消耗为 520 时上限增 10 并发出等待提示。"""
        for cost, notices, sanity_max in (
            (49, [], 1000),
            (
                520,
                [
                    Notice(
                        "\n在刻苦的锻炼下，博士理智最大值成长了10点\n",
                        True,
                        None,
                        True,
                    )
                ],
                1010,
            ),
        ):
            with self.subTest(cost=cost):
                player_ability.set(0, today_sanity_point_cost=cost)
                needs.set(0, sanity_max=1000)
                self.expect(sleep_settle.sanity_point_grow, notices)
                self.assertEqual(needs.of(0)["sanity_max"], sanity_max)

    def test_semen_conversion_notice(self) -> None:
        """验证 refresh_temp_semen_max 在睡眠 300 分钟时静默，在 480 分钟时按是否达上限发出精液转化提示。"""
        line = "\n在充足的睡眠下，今日未消耗的 100ml 精液转化为了 50ml 次日额外精液"
        for extra, duration, notices in (
            (0, 300, []),
            (0, 480, [Notice(line + "\n", False, None, True)]),
            (
                380,
                480,
                [
                    Notice(
                        line
                        + "，额外精液量已达上限，并获得了为期一天的[浓厚精液]\n",
                        False,
                        None,
                        True,
                    )
                ],
            ),
        ):
            with self.subTest(extra=extra, duration=duration):
                h_meters.set(0, semen=100, semen_max=100, extra_semen=extra)
                activity.update_behavior(0, duration=duration)
                self.expect(sleep_settle.refresh_temp_semen_max, notices)


class TkPowerSleepNoticeTest(PowerSleepNoticeTest):
    """沿用已登记的 Tk 提示回调重跑 PowerSleepNoticeTest 用例，验证各提示的绘制类、文本、宽度与样式。"""

    def expect(self, run: Callable[[], object], notices: list[Notice]) -> None:
        """
        保留已登记的 Tk 提示回调并拦截 NormalDraw.draw 与 WaitDraw.draw，断言记录的绘制参数与 notices 一致。
        Keyword arguments:
        run -- Callable[[], object]，触发结算提示的无参可调用对象
        notices -- list[Notice]，预期按顺序绘制的提示参数列表
        Return arguments:
        None -- 无返回值
        """
        drawn: list[tuple[str, str, float, str]] = []

        def keep(now: draw.NormalDraw) -> None:
            """
            记录被拦截绘制对象的类名、文本、宽度与样式。
            Keyword arguments:
            now -- draw.NormalDraw，被调用 draw 的绘制对象
            Return arguments:
            None -- 无返回值
            """
            drawn.append((type(now).__name__, now.text, now.width, now.style))

        with (
            mock.patch.object(
                draw.NormalDraw, "draw", autospec=True, side_effect=keep
            ),
            mock.patch.object(
                draw.WaitDraw, "draw", autospec=True, side_effect=keep
            ),
        ):
            run()
        width = normal_config.config_normal.text_width
        self.assertEqual(
            drawn,
            [
                (
                    "WaitDraw" if n.wait else "NormalDraw",
                    n.text,
                    width if n.use_text_width else 0,
                    n.style or draw.NormalDraw.style,
                )
                for n in notices
            ],
        )


class PowerSleepImportBoundaryTest(FastTestCase):
    """power_settle 与 sleep_settle 导入边界的语法树测试。"""

    def test_settle_modules_skip_ui_imports(self) -> None:
        """验证 GUARDS 中两结算模块源码的任意作用域均不导入各自禁用的模块或其子模块。"""
        for module, banned in GUARDS:
            path = module.__name__.replace(".", "/") + ".py"
            with open(os.path.join(ROOT, path), encoding="utf-8") as file:
                imports = imports_in(file.read(), module.__package__ or "")
            with self.subTest(path=path):
                self.assertEqual(
                    sorted(
                        name
                        for name in imports
                        for root in banned
                        if name == root or name.startswith(root + ".")
                    ),
                    [],
                )
