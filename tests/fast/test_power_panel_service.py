"""
动力系统管理面板服务与适配测试
==============================
覆盖区块策略、调控员、燃料与模块、设施门控、反应炉、上限提示、面板适配及无界面导入边界。
"""

import json
import os
import subprocess
import sys
from collections.abc import Callable
from unittest import mock

from Script.Config import game_config
from Script.Core import flow_handle
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, location, power, power_supply
from Script.Modules.domains import warehouse, work
from Script.Modules.gameplay_resolution import power_panel_service as svc
from Script.Modules.gameplay_resolution import working
from Script.UI.Moudle import draw
from Script.UI.Panel import manage_power_system_panel
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

ZONE = 2
""" 策略测试使用的非动力区测试区块编号。 """
BACKEND_RUN = """
import contextlib, datetime, importlib.abc, io, json, sys
BLOCKED = ("Script.UI", "Script.Settle",
    "Script.System.Instruct_System.handle_instruct", "Script.Core.flow_handle",
    "Script.Core.io_init", "Script.Frontend", "Script.Modules.tk_ui",
    "tkinter", "_tkinter", "PIL.ImageTk")
ALLOWED = frozenset({"Script.Modules.tk_ui", "Script.Modules.tk_ui.orders"})
attempted = []
def blocked(name):
    if name in ALLOWED:
        return False
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if blocked(fullname):
            attempted.append(fullname)
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Blocker())
sys.path.insert(0, sys.argv[1])
from types import MappingProxyType
from Script.Config import game_config, normal_config
with contextlib.redirect_stdout(io.StringIO()):
    normal_config.init_normal_config()
    game_config.init()
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import facility, identity, location, power
from Script.Modules.domains import warehouse, work
from Script.Modules.gameplay_resolution import power_panel_service as svc
from Script.Modules.gameplay_resolution import working
start = game_time.minutes(datetime.datetime(2020, 5, 3))
core.reset_state(core.GameState(start, MappingProxyType({}), MappingProxyType({})))
out = {}
with working.based_on(core.state()):
    warehouse.start({})
    identity.put(identity.Identity(0, name="player"))
    identity.put(identity.Identity(7, name="op"))
    facility.set_level(1, 3)
    work.set_rosters({power.OPERATOR_WORK: (0, 7)})
    power.set_plant(aux_reactors=3, clean=(0, 0, 0), batteries=(0, 0, 0),
                    main_operators=(7, 0, 0, 0))
    warehouse.add(svc.FUEL, 1)
    out["zones"] = len(svc.zones()) > 0
    svc.step_strategy(2, 1)
    out["strategy"] = power.strategy_of(2)
    out["mains"] = [[o.chara_id, o.name, o.craft] for o in svc.main_operators()]
    out["assistants"] = [[o.chara_id, o.craft is None] for o in svc.assistants()]
    out["candidates"] = svc.candidates()
    out["low"] = svc.fuel_text().count("\\n")
    location.set_move(2, game_time.now())
    out["sailing"] = svc.fuel_text().count("\\n")
    out["usable"] = [row.usable for row in svc.clean_rows()]
    out["batteries"] = [row.usable for row in svc.battery_rows()]
    out["modules"] = svc.plant_modules_text().count("\\n")
    out["battery_modules"] = svc.battery_modules_text().count("\\n")
    out["efficiency"] = svc.main_efficiency() > 0
    out["aux_fuel"] = svc.aux_fuel() > 0
    out["aux"] = svc.aux_adjustable()
    warehouse.add(svc.CLEAN_MODULE, -warehouse.amount(svc.CLEAN_MODULE))
    power.set_plant(clean=(9, 0, 0))
    out["clean_hint"] = svc.change_clean(0, 1) is not None
    power.set_plant(batteries=(20, 0, 0))
    out["battery_hint"] = svc.change_battery(0, 1) is not None
    out["clean_ok"] = svc.change_clean(0, -1)
    out["name"] = svc.chara_name(99)
out["attempted"] = attempted
out["loaded"] = sorted(
    name for name in sys.modules
    if name.startswith(("Script.UI", "Script.Settle")) or blocked(name)
)
print(json.dumps(out))
"""
""" 在拦截界面与结算模块的独立子进程中执行服务接口并输出 ASCII JSON 的脚本。 """


class PowerPanelCase(FastTestCase):
    """动力面板测试基类，初始化博士与角色甲、乙并开启临时状态写缓冲。"""

    def setUp(self) -> None:
        """创建角色 0（博士）、1（甲）、2（乙）并进入当前内核状态的临时写缓冲。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "甲")
        self.world.chara(2, "乙")
        self.enterContext(working.based_on(core.state()))

    def level(self, value: int) -> None:
        """将动力区（设施 1）设为指定等级 value。"""
        kernel_data.set_facility_level(1, value)

    def roster(self, *ids: int) -> None:
        """将供能调控员岗位（工作类型 11）名单设为角色编号 ids。"""
        work.set_rosters({power.OPERATOR_WORK: ids})


class ZoneTest(PowerPanelCase):
    """区块列表过滤、策略耗电展示与策略循环步进测试。"""

    def test_zones_list_blocks_except_power_zone(self) -> None:
        """验证 zones 按配置顺序列出所有 type 为 -1 且非动力区的区块。"""
        expected = [
            cid
            for cid, data in game_config.config_facility.items()
            if data.type == -1 and cid != 1
        ]
        self.assertEqual([zone.cid for zone in svc.zones()], expected)

    def test_row_shows_strategy_and_consumption(self) -> None:
        """验证区块条目包含正确的名称、策略百分比标签与区域耗电量。"""
        power.set_strategy(ZONE, 2)
        row = next(zone for zone in svc.zones() if zone.cid == ZONE)
        now = game_config.config_supply_strategy[2]
        self.assertEqual(row.name, game_config.config_facility[ZONE].name)
        self.assertEqual(row.strategy, f"{now.name}({int(now.adjust * 100)}%)")
        self.assertEqual(row.consumption, power_supply.zone_consumption(ZONE))

    def test_step_wraps_around_five_strategies(self) -> None:
        """验证 step_strategy 在 5 项策略间正反向循环回绕。"""
        power.set_strategy(ZONE, 4)
        svc.step_strategy(ZONE, 1)
        self.assertEqual(power.strategy_of(ZONE), 0)
        svc.step_strategy(ZONE, -1)
        self.assertEqual(power.strategy_of(ZONE), 4)
        svc.step_strategy(ZONE, -1)
        self.assertEqual(power.strategy_of(ZONE), 3)


class OperatorTest(PowerPanelCase):
    """主调控员、辅助调控员、任命候选与角色名回退测试。"""

    def test_main_operators_hide_vacant_level(self) -> None:
        """验证 main_operators 对空缺槽位返回空名与 None 等级，对干员返回名称与等级。"""
        self.roster(1, 2)
        abilities.ability(1)[48] = 3
        power.set_plant(main_operators=(0, 1, 0, 0))
        self.assertEqual(
            svc.main_operators(),
            [
                svc.Operator(0, "", None),
                svc.Operator(1, "甲", 3),
                svc.Operator(0, "", None),
                svc.Operator(0, "", None),
            ],
        )

    def test_assistants_skip_main_operators(self) -> None:
        """验证 assistants 排除主调控员并在四槽全满时将玩家显示为 (未知)。"""
        self.roster(2, 0, 1)
        abilities.ability(0)[48] = 1
        abilities.ability(2)[48] = 5
        for mains, expected in (
            ((1, 0, 0, 0), [svc.Operator(2, "乙", 5)]),
            (
                (1, 1, 1, 1),
                [svc.Operator(2, "乙", 5), svc.Operator(0, "(未知)", 1)],
            ),
        ):
            with self.subTest(mains=mains):
                power.set_plant(main_operators=mains)
                self.assertEqual(svc.assistants(), expected)

    def test_candidates_leave_out_player(self) -> None:
        """验证 candidates 按名册顺序返回候选干员并排除玩家编号 0。"""
        self.roster(2, 0, 1)
        self.assertEqual(svc.candidates(), [2, 1])

    def test_name_falls_back_to_id(self) -> None:
        """验证 chara_name 对玩家返回空串、已知角色返回姓名、缺失角色回退干员编号。"""
        self.assertEqual(svc.chara_name(0), "")
        self.assertEqual(svc.chara_name(2), "乙")
        self.assertEqual(svc.chara_name(77), "干员77")


class FuelTest(PowerPanelCase):
    """燃料可支撑天数计算与低燃料、行驶中预警测试。"""

    def daily(self, aux: int) -> float:
        """将副源石反应炉设为 aux 台并返回火力发电日计划燃料消耗（float）。"""
        power.set_plant(aux_reactors=aux)
        return power_supply.fire_detail()["fuel_daily_plan"]

    def test_days_floor_stock_by_daily_plan(self) -> None:
        """验证燃料可用天数按库存除以日计划消耗向下取整，充足时无预警。"""
        daily = self.daily(3)
        warehouse.add(svc.FUEL, int(daily * 5) + 1)
        text = svc.fuel_text()
        self.assertIn("约可支持 5 天\n", text)
        self.assertNotIn("！", text)

    def test_short_stock_warns(self) -> None:
        """验证燃料可支撑天数低于 3 天时追加燃料不足警告行。"""
        daily = self.daily(3)
        warehouse.add(svc.FUEL, int(daily * 2))
        text = svc.fuel_text().split("\n")
        self.assertIn("约可支持 2 天", text[0])
        self.assertTrue(text[1].startswith("！燃料库存不足3天"))

    def test_no_reactor_never_runs_out(self) -> None:
        """验证副炉为 0 且日耗为 0 时显示可支撑 9999 天。"""
        self.daily(0)
        self.assertIn("约可支持 9999 天\n", svc.fuel_text())

    def test_sailing_warns(self) -> None:
        """验证罗德岛行驶中时追加水力与风力设施无法工作的警告行。"""
        self.daily(0)
        location.set_move(2, game_time.now())
        self.assertTrue(
            svc.fuel_text().endswith(
                "！当前罗德岛处于行驶中，水力与风力发电设施无法工作！\n"
            )
        )


class ModuleTest(PowerPanelCase):
    """发电设施与蓄电池扩展模块统计文案测试。"""

    def test_totals_add_level_base_to_stock(self) -> None:
        """验证扩展模块总上限等于仓库库存加对应动力区等级基础额。"""
        self.level(2)
        warehouse.add(svc.AUX_MODULE, 4)
        warehouse.add(svc.CLEAN_MODULE, 1)
        warehouse.add(svc.BATTERY_MODULE, 2)
        power.set_plant(aux_reactors=5, clean=(1, 2, 0), batteries=(1, 1, 1))
        self.assertEqual(
            svc.plant_modules_text(),
            "  副源石反应炉扩展模块 ：已用 5 / 总 11 （含区块等级提供的7）\n"
            "  清洁能源通用扩展模块 ：已用 3 / 总 8 （含区块等级提供的7）\n",
        )
        self.assertEqual(
            svc.battery_modules_text(),
            "  蓄电池通用扩展模块 ：已用 3 / 总 14 （含区块等级提供的12）\n",
        )


class GateTest(PowerPanelCase):
    """清洁能源、蓄电池与副源石反应炉的等级和行驶门控测试。"""

    def test_clean_rows_follow_level_and_sailing(self) -> None:
        """验证清洁能源各行按等级与行驶状态判定可用性，不可用行产出归零。"""
        power.set_plant(clean=(1, 2, 3))
        index = game_config.config_power_generation_level_index
        base = [
            float(game_config.config_power_generation[index[kind][3]].value)
            for kind in ("水力", "风力", "光伏", "人力")
        ]
        cases = (
            (3, False, [True, False, False, True]),
            (4, False, [True, True, False, True]),
            (5, False, [True, True, True, True]),
            (5, True, [False, False, True, True]),
        )
        for level, sailing, usable in cases:
            with self.subTest(level=level, sailing=sailing):
                self.level(level)
                if sailing:
                    location.set_move(2, game_time.now())
                rows = svc.clean_rows()
                self.assertEqual([row.usable for row in rows], usable)
                self.assertEqual([row.count for row in rows], [1, 2, 3, 0])
                self.assertEqual(
                    [row.output for row in rows],
                    [base[k] if usable[k] else 0.0 for k in range(4)],
                )

    def test_battery_rows_unlock_by_level(self) -> None:
        """验证 L2 与 L3 蓄电池分别在动力区 3 级与 4 级解锁并携带数量与容量。"""
        power.set_plant(batteries=(2, 1, 0))
        caps = power.storage_levels("电池容量", int, 0)
        for level, usable in (
            (2, [True, False, False]),
            (3, [True, True, False]),
            (4, [True, True, True]),
        ):
            with self.subTest(level=level):
                self.level(level)
                rows = svc.battery_rows()
                self.assertEqual([row.usable for row in rows], usable)
                self.assertEqual([row.count for row in rows], [2, 1, 0])
                self.assertEqual([row.capacity for row in rows], caps)

    def test_aux_reactors_adjust_from_level_two(self) -> None:
        """验证副源石反应炉自动力区 2 级起允许调整。"""
        self.level(1)
        self.assertFalse(svc.aux_adjustable())
        self.level(2)
        self.assertTrue(svc.aux_adjustable())


class ReactorTest(PowerPanelCase):
    """主副源石反应炉配置查询测试。"""

    def test_reactor_rows_match_fire_generation(self) -> None:
        """验证主炉效率与副炉单台日耗与 power_supply.fire_detail 一致。"""
        for level in (1, 3, 5):
            with self.subTest(level=level):
                self.level(level)
                power.set_plant(aux_reactors=4)
                detail = power_supply.fire_detail()
                self.assertEqual(svc.main_efficiency(), detail["eff_per_fuel"])
                self.assertEqual(svc.aux_fuel() * 4, detail["fuel_daily_plan"])


class ChangeTest(PowerPanelCase):
    """清洁能源与蓄电池增减上限提示测试。"""

    def test_clean_limit_returns_hint(self) -> None:
        """验证清洁能源达上限返回提示且不改数量，减少返回 None 并扣减数量。"""
        self.level(1)
        power.set_plant(clean=(2, 2, 1))
        self.assertEqual(
            svc.change_clean(1, 1),
            "三种清洁能源设施总数已达上限(5)，可通过生产清洁能源模块扩展上限",
        )
        self.assertEqual(power.plant()["clean"], (2, 2, 1))
        self.assertIsNone(svc.change_clean(1, -1))
        self.assertEqual(power.plant()["clean"], (2, 1, 1))

    def test_battery_limit_returns_hint(self) -> None:
        """验证蓄电池达上限返回提示且不改数量，减少返回 None 并扣减数量。"""
        self.level(1)
        power.set_plant(batteries=(10, 0, 0))
        self.assertEqual(
            svc.change_battery(0, 1),
            "蓄电池总数已达上限(10)，可通过生产蓄电池扩展上限",
        )
        self.assertIsNone(svc.change_battery(0, -1))
        self.assertEqual(power.plant()["batteries"], (9, 0, 0))


class PanelAdapterTest(PowerPanelCase):
    """Manage_Power_System_Panel 与服务层及按钮回调的适配测试。"""

    def offered(
        self, view: str
    ) -> tuple[list[str], dict[str, Callable[..., object]]]:
        """拦截输入直接返回，运行面板方法 view 并返回返回键列表与居中按钮回调映射。"""
        seen: list[str] = []
        buttons: dict[str, Callable[..., object]] = {}

        def back(return_list: list[str], *args: object) -> str:
            seen.extend(return_list)
            return "返回"

        def record(button: draw.CenterButton) -> None:
            if button.cmd_func is not None:
                buttons[button.return_text] = button.cmd_func

        panel = manage_power_system_panel.Manage_Power_System_Panel(100)
        with (
            mock.patch.object(flow_handle, "askfor_all", back),
            mock.patch.object(draw.CenterButton, "draw", record),
        ):
            getattr(panel, view)()
        return seen, buttons

    def test_facilities_offer_buttons_for_usable_rows(self) -> None:
        """验证发电设施子界面仅为当前可用的设施行提供增减按钮。"""
        self.level(3)
        seen, _buttons = self.offered("_panel_facilities")
        self.assertEqual(
            seen,
            [
                "增加副源石反应炉",
                "减少副源石反应炉",
                "增加水力发电轮组",
                "减少水力发电轮组",
                "返回",
            ],
        )

    def test_battery_button_draws_limit_hint(self) -> None:
        """验证蓄电池达上限时绘制等待提示，减少按钮正常扣减数量。"""
        self.level(4)
        power.set_plant(batteries=(16, 0, 0))
        seen, buttons = self.offered("_panel_battery")
        self.assertEqual(
            seen,
            [
                "增加L1",
                "减少L1",
                "增加L2",
                "减少L2",
                "增加L3",
                "减少L3",
                "返回",
            ],
        )
        buttons["增加L3"]()
        self.assertEqual(
            self.world.wait_texts,
            ["\n蓄电池总数已达上限(16)，可通过生产蓄电池扩展上限\n"],
        )
        buttons["减少L1"]()
        self.assertEqual(power.plant()["batteries"], (15, 0, 0))

    def test_strategy_buttons_step_their_zone(self) -> None:
        """验证供电策略子界面的提升按钮回调按 5 项循环步进对应区块策略。"""
        name = game_config.config_facility[ZONE].name
        seen, buttons = self.offered("_panel_supply_strategy")
        self.assertIn("降低" + name, seen)
        before = power.strategy_of(ZONE)
        buttons["提升" + name]()
        self.assertEqual(power.strategy_of(ZONE), (before + 1) % 5)


class BackendIsolationTest(FastTestCase):
    """power_panel_service 无界面与无结算导入边界的独立子进程测试。"""

    def test_fresh_backend_process_loads_no_ui_or_settle(self) -> None:
        """在 cp1252 下运行拦截界面与结算模块的独立子进程，验证结果正确且无受限导入。"""
        result = subprocess.run(
            [sys.executable, "-c", BACKEND_RUN, str(ROOT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
            env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        line = result.stdout.splitlines()[-1]
        self.assertTrue(line.isascii())
        out = json.loads(line)
        self.assertEqual(out["attempted"], [])
        self.assertEqual(out["loaded"], [])
        self.assertTrue(out["zones"])
        self.assertEqual(out["strategy"], 1)
        self.assertEqual(
            out["mains"],
            [[7, "op", 0], [0, "", None], [0, "", None], [0, "", None]],
        )
        self.assertEqual(out["assistants"], [])
        self.assertEqual(out["candidates"], [7])
        self.assertEqual((out["low"], out["sailing"]), (2, 3))
        self.assertEqual(out["usable"], [False, False, False, True])
        self.assertEqual(out["batteries"], [True, True, False])
        self.assertEqual((out["modules"], out["battery_modules"]), (2, 1))
        self.assertTrue(out["efficiency"] and out["aux_fuel"] and out["aux"])
        self.assertTrue(out["clean_hint"] and out["battery_hint"])
        self.assertIsNone(out["clean_ok"])
        self.assertEqual(out["name"], "干员99")
