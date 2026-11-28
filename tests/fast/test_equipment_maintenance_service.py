"""
装备维修保养服务测试
====================
- 维修：验证指定目标、按优先度自动选目标、无损坏时不操作，以及修完清记录并结算成就 321。
- 保养：验证指定目标、全体在队角色与指定名单两种范围，以及保养达标清记录并结算成就 331。
- 一次维护：验证优先维修与优先保养、在修目标处理、无可维护提示与不绘制时的状态写入。
- 结算调用：验证维护装备行为结算按铁匠是否与玩家同处一地传参，以及时长为 0 时跳过。
- 导入边界：验证屏蔽 Script.UI.Panel 的子进程可导入并运行装备服务完成维护。
"""

import random
import subprocess
import sys
from collections.abc import Callable
from typing import Any
from unittest import mock

from Script.Config import game_config
from Script.Core import game_type, get_text
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, achievement, activity, chara_life
from Script.Modules.domains import maintenance, wardrobe
from Script.Modules.gameplay_resolution import equipment_service, ui_hooks
from Script.Modules.gameplay_resolution import working
from Script.Settle import default as settle_default
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

SMITH = 1
""" 测试铁匠的角色编号（1）。 """
ALPHA = 2
""" 第一名测试干员的角色编号（2）。 """
BETA = 3
""" 第二名测试干员的角色编号（3）。 """
NAMES = {SMITH: "铁匠", ALPHA: "干员甲", BETA: "干员乙"}
""" 测试角色编号到名称的映射表。 """
BLACKSMITH = 22
""" 铁匠工作类型编号（22）。 """
SKILL = 4
""" 测试铁匠能力 48 的等级（4），修正值 1.6，对应维修量 0.8 与保养量 0.4。 """
OFFICE = ["中枢", "博士办公室"]
""" 与默认位置不同的测试场景路径，用于让铁匠离开玩家所在场景。 """

type Drawn = tuple[str, float, str, str]
""" 单次绘制记录的元组类型，依次为绘制类名、宽度、样式名与文本。 """

_ = get_text._


def repaired(target: int, name: str, value: float) -> str:
    """构造 SMITH 维修 target 后装备状态为 name 与 value 时的预期维修结果行。"""
    return _("{0}维修了{1}的装备，当前情况：{2} ({3})\n").format(
        NAMES[SMITH], NAMES[target], name, value
    )


def maintained(target: int, name: str, value: float) -> str:
    """构造 SMITH 保养 target 后装备状态为 name 与 value 时的预期保养结果行。"""
    return _("{0}保养了{1}的装备，当前情况：{2} ({3})\n").format(
        NAMES[SMITH], NAMES[target], name, value
    )


class EquipmentCase(FastTestCase):
    """装备维护测试基类，准备玩家、铁匠与两名测试干员，并记录提示回调与绘制调用。"""

    def setUp(self) -> None:
        """创建测试角色、打开工作集并固定随机倍率为 1.0，接管提示回调并拦截全部绘制类。"""
        super().setUp()
        self.world.chara(0, "博士")
        for cid, name in NAMES.items():
            self.world.chara(cid, name)
        self.enterContext(working.based_on(core.state()))
        chara_life.work_type.set(SMITH, BLACKSMITH)
        abilities.ability(SMITH).merge({48: SKILL})
        self.enterContext(
            mock.patch.object(random, "uniform", return_value=1.0)
        )
        self.notices: list[tuple[str, bool, str | None, bool]] = []
        self.drawn: list[Drawn] = []
        self.direct: list[Drawn] = []
        self.inside = False
        notice_hooks = list(ui_hooks._notices)
        self.enterContext(
            mock.patch.object(
                ui_hooks, "_notices", [self.relay(notice_hooks, self.note)]
            )
        )
        for cls in vars(draw).values():
            if isinstance(cls, type) and hasattr(cls, "draw"):
                self.enterContext(
                    mock.patch.object(
                        cls, "draw", autospec=True, side_effect=self.keep
                    )
                )

    def note(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """记录一条提示文本及 wait、style、use_text_width 三个选项。"""
        self.notices.append((text, wait, style, use_text_width))

    def relay(
        self, hooks: list[Callable[..., None]], record: Callable[..., None]
    ) -> Callable[..., None]:
        """返回先记录参数、再置位回调标记并依次调用原有回调的转发函数。"""

        def forward(*args: Any, **kwargs: Any) -> None:
            record(*args, **kwargs)
            self.inside = True
            try:
                for fn in hooks:
                    fn(*args, **kwargs)
            finally:
                self.inside = False

        return forward

    def keep(self, now: object) -> None:
        """按是否处于回调内，将绘制对象的类名、宽度、样式名与文本记入对应列表。"""
        drawn = (
            type(now).__name__,
            getattr(now, "width", 0),
            getattr(now, "style", ""),
            getattr(now, "text", ""),
        )
        (self.drawn if self.inside else self.direct).append(drawn)

    def condition(self, cid: int, value: float) -> None:
        """将角色 cid 的装备状态数值设为 value。"""
        wardrobe.set(cid, "equipment_condition", value)

    def conditions(self) -> dict[int, float]:
        """返回 ALPHA 与 BETA 当前装备状态数值的字典。"""
        return {
            cid: round(wardrobe.of(cid).equipment_condition, 6)
            for cid in (ALPHA, BETA)
        }

    def assert_notice(self, text: str) -> None:
        """核对发出单条默认选项提示、回调绘出零宽默认样式 NormalDraw 且无直接绘制。"""
        self.assertEqual(self.notices, [(text, False, None, False)])
        self.assertEqual(
            self.drawn, [("NormalDraw", 0, draw.NormalDraw.style, text)]
        )
        self.assertEqual(self.direct, [])

    def assert_badge(self, achievement_id: int) -> None:
        """核对提示回调收到指定成就的金色等待提示、回调绘出同文本的零宽 gold_enrod 样式 WaitDraw 且无直接绘制。"""
        data = game_config.config_achievement[achievement_id]
        text = _("\n\n   ○ 获得蚀刻章：{name} ○\n").format(name=data.name)
        text += _("      （{description}）\n\n\n").format(
            description=data.description
        )
        self.assertEqual(self.notices, [(text, True, "gold_enrod", False)])
        self.assertEqual(self.drawn, [("WaitDraw", 0, "gold_enrod", text)])
        self.assertEqual(self.direct, [])


class RepairTest(EquipmentCase):
    """repair_equipment 的目标选择、数值封顶、维修记录与成就结算测试。"""

    def test_named_target_is_repaired(self) -> None:
        """验证指定目标 ALPHA 维修量为 0.8，写入维修记录且不触发成就结算。"""
        self.condition(ALPHA, -2)
        result = equipment_service.repair_equipment(SMITH, ALPHA)
        self.assertEqual(result, (True, repaired(ALPHA, "中度损坏", -1.2)))
        self.assertEqual(self.conditions(), {ALPHA: -1.2, BETA: 0})
        self.assertEqual(maintenance.repairs(), {SMITH: ALPHA})
        self.assertEqual(achievement.get("equipment_repair_count"), 0)
        self.assertEqual(self.notices, [])

    def test_auto_target_follows_priority(self) -> None:
        """验证维修优先度为 0 时自动选状态最低的 BETA，为 1 时选最高的 ALPHA。"""
        for priority, target, text in (
            (0, BETA, repaired(BETA, "严重损坏", -2.2)),
            (1, ALPHA, repaired(ALPHA, "轻微损坏", -0.2)),
        ):
            with self.subTest(priority=priority):
                self.condition(ALPHA, -1)
                self.condition(BETA, -3)
                maintenance.set_setting(0, priority)
                self.assertEqual(
                    equipment_service.repair_equipment(SMITH), (True, text)
                )
                self.assertEqual(maintenance.repairs(), {SMITH: target})

    def test_nothing_damaged_does_nothing(self) -> None:
        """验证无损坏装备时返回 (False, "") 且不写入维修记录。"""
        self.condition(ALPHA, 1)
        self.assertEqual(equipment_service.repair_equipment(SMITH), (False, ""))
        self.assertEqual(maintenance.repairs(), {})

    def test_finished_repair_settles_achievement(self) -> None:
        """验证修至 0 时清除维修记录、维修计数加 1 并通知绘出成就 321。"""
        self.condition(ALPHA, -0.5)
        maintenance.set_repair(SMITH, ALPHA)
        result = equipment_service.repair_equipment(SMITH)
        self.assertEqual(result, (True, repaired(ALPHA, "正常状态", 0)))
        self.assertEqual(self.conditions(), {ALPHA: 0, BETA: 0})
        self.assertEqual(maintenance.repairs(), {})
        self.assertEqual(achievement.get("equipment_repair_count"), 1)
        self.assert_badge(321)


class MaintainTest(EquipmentCase):
    """maintain_equipment 的目标选择、保养上限、维修记录与成就结算测试。"""

    def test_named_target_is_maintained(self) -> None:
        """验证保养上限设为 2 时指定目标 ALPHA 保养量为 0.4，写入记录且不结算成就。"""
        maintenance.set_setting(1, 2)
        result = equipment_service.maintain_equipment(SMITH, ALPHA)
        self.assertEqual(result, (True, maintained(ALPHA, "正常状态", 0.4)))
        self.assertEqual(self.conditions(), {ALPHA: 0.4, BETA: 0})
        self.assertEqual(maintenance.repairs(), {SMITH: ALPHA})
        self.assertEqual(self.notices, [])

    def test_auto_target_follows_scope(self) -> None:
        """验证保养范围为 0 时选在队最低者 BETA，为 1 时只在指定名单内选 ALPHA。"""
        maintenance.set_setting(1, 2)
        for scope, target, text in (
            (0, BETA, maintained(BETA, "正常状态", 0.4)),
            (1, ALPHA, maintained(ALPHA, "正常状态", 0.9)),
        ):
            with self.subTest(scope=scope):
                self.condition(ALPHA, 0.5)
                self.condition(BETA, 0)
                maintenance.set_setting(2, scope)
                if scope == 1:
                    maintenance.toggle_operator(ALPHA)
                self.assertEqual(
                    equipment_service.maintain_equipment(SMITH), (True, text)
                )
                self.assertEqual(maintenance.repairs(), {SMITH: target})

    def test_finished_maintenance_settles_achievement(self) -> None:
        """验证保养上限设为 1 时状态封顶于 1、清除记录、保养计数加 1 并通知绘出成就 331。"""
        maintenance.set_setting(1, 1)
        self.condition(ALPHA, 0.7)
        maintenance.set_repair(SMITH, ALPHA)
        result = equipment_service.maintain_equipment(SMITH, ALPHA)
        self.assertEqual(result, (True, maintained(ALPHA, "良好保养", 1)))
        self.assertEqual(self.conditions(), {ALPHA: 1, BETA: 0})
        self.assertEqual(maintenance.repairs(), {})
        self.assertEqual(achievement.get("equipment_maintenance_count"), 1)
        self.assert_badge(331)


class MaintainOnceTest(EquipmentCase):
    """smith_maintain_equipment_once 的优先顺序、在修目标与结果提示测试。"""

    def setUp(self) -> None:
        """执行基类准备并将保养上限设为 1、ALPHA 装备状态设为 -1、BETA 设为 0。"""
        super().setUp()
        maintenance.set_setting(1, 1)
        self.condition(ALPHA, -1)
        self.condition(BETA, 0)

    def once(self, draw_flag: bool = True) -> bool:
        """以 SMITH 调用一次 smith_maintain_equipment_once 并返回其布尔结果。"""
        return equipment_service.smith_maintain_equipment_once(SMITH, draw_flag)

    def test_repair_first_skips_maintenance(self) -> None:
        """验证默认优先维修时只维修 ALPHA 并绘出维修结果行。"""
        self.assertTrue(self.once())
        self.assertEqual(self.conditions(), {ALPHA: -0.2, BETA: 0})
        self.assert_notice(repaired(ALPHA, "轻微损坏", -0.2) + "\n")

    def test_maintain_first_skips_repair(self) -> None:
        """验证优先保养且仅保养名单内 BETA 时只保养 BETA，不维修 ALPHA。"""
        maintenance.set_setting(3, 1)
        maintenance.set_setting(2, 1)
        maintenance.toggle_operator(BETA)
        self.assertTrue(self.once())
        self.assertEqual(self.conditions(), {ALPHA: -1, BETA: 0.4})
        self.assert_notice(maintained(BETA, "正常状态", 0.4) + "\n")

    def test_recorded_target_is_maintained_then_repair_runs(self) -> None:
        """验证记录目标 BETA 未损坏时先保养它，优先维修再修 ALPHA，提示先维修行后保养行。"""
        maintenance.set_repair(SMITH, BETA)
        self.assertTrue(self.once())
        self.assertEqual(self.conditions(), {ALPHA: -0.2, BETA: 0.4})
        self.assertEqual(maintenance.repairs(), {SMITH: ALPHA})
        self.assert_notice(
            repaired(ALPHA, "轻微损坏", -0.2)
            + "\n"
            + maintained(BETA, "正常状态", 0.4)
            + "\n"
        )

    def test_recorded_damaged_target_is_repaired(self) -> None:
        """验证记录目标 BETA 处于损坏状态时只维修 BETA 并绘出其维修结果行。"""
        self.condition(BETA, -2)
        maintenance.set_repair(SMITH, BETA)
        self.assertTrue(self.once())
        self.assertEqual(self.conditions(), {ALPHA: -1, BETA: -1.2})
        self.assert_notice(repaired(BETA, "中度损坏", -1.2) + "\n")

    def test_nothing_to_do_notices(self) -> None:
        """验证无可维修或保养的装备时返回 False 并发出无可维护提示。"""
        self.condition(ALPHA, 1)
        self.condition(BETA, 1)
        self.assertFalse(self.once())
        self.assert_notice(_("没有可维修或可保养的装备。"))

    def test_no_draw_flag_still_repairs(self) -> None:
        """验证 draw_flag 为 False 时照常维修 ALPHA，不发提示也不触发绘制。"""
        self.assertTrue(self.once(draw_flag=False))
        self.assertEqual(self.conditions(), {ALPHA: -0.2, BETA: 0})
        self.assertEqual((self.notices, self.drawn, self.direct), ([], [], []))


class SettlementCallerTest(EquipmentCase):
    """维护装备行为结算 handle_maintain_equipment_add_adjust 的调用测试。"""

    def setUp(self) -> None:
        """执行基类准备并将 ALPHA 的装备状态设为 -1。"""
        super().setUp()
        self.condition(ALPHA, -1)

    def settle(self, add_time: int) -> mock.MagicMock:
        """包装 smith_maintain_equipment_once 运行一次行为结算并返回该包装对象。"""
        with mock.patch.object(
            equipment_service,
            "smith_maintain_equipment_once",
            wraps=equipment_service.smith_maintain_equipment_once,
        ) as once:
            settle_default.handle_maintain_equipment_add_adjust(
                SMITH,
                add_time,
                game_type.CharacterStatusChange(),
                game_time.now(),
            )
        return once

    def test_smith_with_player_draws(self) -> None:
        """验证铁匠与玩家同处一地时以 draw_flag=True 调用一次维护并绘出维修结果行。"""
        self.settle(10).assert_called_once_with(SMITH, True)
        self.assert_notice(repaired(ALPHA, "轻微损坏", -0.2) + "\n")

    def test_smith_elsewhere_stays_silent(self) -> None:
        """验证铁匠位于 OFFICE 时以 draw_flag=False 调用一次维护，照常维修且不绘制。"""
        activity.set_position(SMITH, OFFICE)
        self.settle(10).assert_called_once_with(SMITH, False)
        self.assertEqual(self.conditions(), {ALPHA: -0.2, BETA: 0})
        self.assertEqual((self.notices, self.drawn, self.direct), ([], [], []))

    def test_zero_time_skips(self) -> None:
        """验证结算时长 add_time 为 0 时直接返回且不调用维护服务。"""
        self.settle(0).assert_not_called()


BLOCKED_RUN = """
import importlib.abc, json, sys

class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "Script.UI.Panel" or fullname.startswith("Script.UI.Panel."):
            raise ImportError(fullname)
        return None

sys.meta_path.insert(0, Block())
from tests import kernel_data
from tests.fast import WORLD
from Script.Kernel import core
from Script.Modules.domains import abilities, chara_life, maintenance, wardrobe, warehouse
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.Modules.gameplay_resolution import equipment_service

WORLD.reset()
kernel_data.written(warehouse.start, {})
for cid in range(3):
    WORLD.chara(cid, str(cid))
notices = []
ui_hooks._notices[:] = [lambda text, *, style, **_: notices.append(style)]
with working.based_on(core.state()):
    chara_life.work_type.set(1, 22)
    abilities.ability(1).merge({48: 4})
    wardrobe.set(2, "equipment_condition", -0.5)
    maintenance.set_repair(1, 2)
    done = equipment_service.smith_maintain_equipment_once(1, True)
panels = sorted(m for m in sys.modules if m.startswith("Script.UI.Panel"))
print(json.dumps([done, notices, panels]))
"""
""" 子进程脚本：屏蔽 Script.UI.Panel 后导入装备服务，执行一次完成维修收尾的维护并输出结果。 """


class ImportBoundaryTest(FastTestCase):
    """屏蔽 Script.UI.Panel 的子进程中运行装备服务的测试。"""

    def test_service_runs_with_panels_blocked(self) -> None:
        """验证屏蔽 Script.UI.Panel 的子进程可导入并运行服务完成维修收尾，发提示且通知成就 321。"""
        result = subprocess.run(
            [sys.executable, "-c", BLOCKED_RUN],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertEqual(
            result.stdout.splitlines()[-1], '[true, ["gold_enrod", null], []]'
        )
