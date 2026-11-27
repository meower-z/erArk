"""
难度系数与角色自定义指令后端服务测试
====================================
- 难度系数服务（difficulty_service）：0 到 6 级的系数映射与越界默认值。
- 角色自定义指令服务（diy_instruct_service）：无目标、无事件、前提筛选与缓存复用，以及无意识目标放行。
- 模块边界与导入顺序：调用方源码导入边界、面板模块运行期属性检查，以及独立子进程中的双顺序导入。
"""

import ast
import inspect
import subprocess
import sys
from importlib.util import resolve_name
from types import ModuleType
from unittest import mock

from Script.Config import game_config
from Script.Core import constant, game_type
from Script.Design import handle_premise
from Script.Kernel import core
from Script.Modules.domains import activity, flags
from Script.Modules.gameplay_resolution import difficulty_service
from Script.Modules.gameplay_resolution import diy_instruct_service, working
from Script.Settle import common_default
from Script.UI.Panel import event_option_panel, see_instruct_panel
from Script.UI.Panel import system_setting
from tests.fast.base import FastTestCase
from tests.world import ROOT

TARGET = 1
""" 测试用交互目标角色编号 """
ADV = 9001
""" 测试用交互目标的剧情 npc 编号（adv） """
PASS = "diy_test_pass"
""" 测试用恒通过前提标识名 """
FAIL = "diy_test_fail"
""" 测试用恒失败前提标识名 """
SETTING_PANEL = "Script.UI.Panel.system_setting"
""" 系统设置面板的完整模块路径 """
OPTION_PANEL = "Script.UI.Panel.event_option_panel"
""" 事件选项面板的完整模块路径 """
IMPORT_IN_ORDER = """
import importlib
import sys

from Script.Config import normal_config

normal_config.init_normal_config()
for name in sys.argv[1:]:
    importlib.import_module(name)
service = sys.modules["Script.Modules.gameplay_resolution.diy_instruct_service"]
print(callable(service.get_target_chara_diy_instruct))
"""
""" 在独立子进程中按参数顺序导入模块并检查服务函数是否可调用的脚本 """


def imports_in(source: str, package: str) -> set[str]:
    """
    解析源码语法树并返回其中所有被导入的完整模块或符号路径。
    Keyword arguments:
    source -- str，待解析的 Python 源码文本
    package -- str，用于解析相对导入的所属包名
    Return arguments:
    set[str] -- 展开相对导入后的导入目标路径集合
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = resolve_name("." * node.level + (node.module or ""), package)
            found.add(base)
            found.update(f"{base}.{alias.name}" for alias in node.names)
    return found


def imported_modules(module: ModuleType) -> set[str]:
    """
    读取已加载模块源码并返回其所有导入目标路径集合。
    Keyword arguments:
    module -- ModuleType，待检查的模块对象
    Return arguments:
    set[str] -- 展开相对导入后的导入目标路径集合
    """
    return imports_in(inspect.getsource(module), module.__package__ or "")


def make_event(uid: str, premises: tuple[str, ...]) -> game_type.Event:
    """
    构造挂在测试用 adv 下的角色自定义指令事件对象。
    Keyword arguments:
    uid -- str，事件唯一编号
    premises -- tuple[str, ...]，事件所需前提标识名元组
    Return arguments:
    game_type.Event -- 填好编号、行为类型与前提字典的事件实例
    """
    event = game_type.Event()
    event.uid = uid
    event.adv_id = str(ADV)
    event.behavior_id = constant.Behavior.CHARA_DIY_INSTRUCT
    event.premise = {premise: 1 for premise in premises}
    return event


class DifficultyServiceTest(FastTestCase):
    """测试 difficulty_service.get_difficulty_coefficient 的系数映射与越界回退"""

    def test_each_level_has_its_coefficient(self) -> None:
        """验证 0 到 6 级难度依次返回系数表中的对应值"""
        expected = (0.25, 0.5, 0.75, 1.0, 1.25, 2.0, 4.0)
        for level, coefficient in enumerate(expected):
            with self.subTest(level=level):
                self.assertEqual(
                    difficulty_service.get_difficulty_coefficient(level),
                    coefficient,
                )

    def test_level_outside_table_gives_one(self) -> None:
        """验证超出 0 到 6 范围的难度等级均返回默认值 1.0"""
        for level in (-7, -1, 7, 100):
            with self.subTest(level=level):
                self.assertEqual(
                    difficulty_service.get_difficulty_coefficient(level), 1.0
                )


class DiyInstructServiceTest(FastTestCase):
    """测试 diy_instruct_service.get_target_chara_diy_instruct 的筛选与缓存行为"""

    def setUp(self) -> None:
        """准备测试角色、工作集上下文以及替身前提处理函数与自定义指令事件配置"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(TARGET, "测试干员", adv=ADV)
        self.enterContext(working.based_on(core.state()))
        self.checked: list[str] = []
        handlers = {PASS: self.passing, FAIL: self.failing}
        self.enterContext(
            mock.patch.dict(constant.handle_premise_data, handlers)
        )
        self.events = {
            "diy_a": make_event("diy_a", (PASS,)),
            "diy_b": make_event("diy_b", (PASS, FAIL)),
            "diy_c": make_event("diy_c", (PASS,)),
        }
        self.enterContext(
            mock.patch.object(game_config, "config_event", self.events)
        )
        by_adv = {
            constant.Behavior.CHARA_DIY_INSTRUCT: {
                ADV: list(self.events),
            }
        }
        self.enterContext(
            mock.patch.object(
                game_config, "config_event_status_data_by_chara_adv", by_adv
            )
        )

    def passing(self, character_id: int) -> int:
        """记录调用并返回权重 1 的替身前提处理函数"""
        self.checked.append(PASS)
        return 1

    def failing(self, character_id: int) -> int:
        """记录调用并返回权重 0 的替身前提处理函数"""
        self.checked.append(FAIL)
        return 0

    def test_without_target_lists_nothing(self) -> None:
        """验证无交互目标时返回空结果且不调用前提处理函数"""
        activity.set_target(0, 0)
        self.assertEqual(
            diy_instruct_service.get_target_chara_diy_instruct(0), (0, [])
        )
        self.assertEqual(self.checked, [])

    def test_target_without_diy_events_lists_nothing(self) -> None:
        """验证交互目标的 adv 下无自定义指令配置时返回空结果且不调用前提处理函数"""
        self.world.chara(2, "无事件干员", adv=ADV + 1)
        activity.set_target(0, 2)
        self.assertEqual(
            diy_instruct_service.get_target_chara_diy_instruct(0), (0, [])
        )
        self.assertEqual(self.checked, [])

    def test_events_whose_premises_pass_are_listed(self) -> None:
        """验证仅返回前提通过的事件且同一前提跨事件只计算一次"""
        activity.set_target(0, TARGET)
        self.assertEqual(
            diy_instruct_service.get_target_chara_diy_instruct(0),
            (2, ["diy_a", "diy_c"]),
        )
        self.assertEqual(self.checked, [PASS, FAIL])

    def test_unconscious_target_still_gets_events(self) -> None:
        """验证无意识目标仍可获取自定义指令事件且默认前提判定返回权重 0"""
        activity.set_target(0, TARGET)
        flags.set(TARGET, unconscious_h=1)
        self.assertEqual(
            diy_instruct_service.get_target_chara_diy_instruct(0),
            (2, ["diy_a", "diy_c"]),
        )
        self.assertEqual(
            handle_premise.get_weight_from_premise_dict(
                self.events["diy_a"].premise, 0, {}
            ),
            (0, {}),
        )


class ModuleBoundaryTest(FastTestCase):
    """测试服务调用方与界面面板之间的模块导入边界及双顺序导入"""

    def test_settle_uses_difficulty_service(self) -> None:
        """验证 common_default 导入 difficulty_service"""
        imports = imported_modules(common_default)
        self.assertIn(difficulty_service.__name__, imports)

    def test_diy_callers_use_diy_instruct_service(self) -> None:
        """验证 handle_premise 与 see_instruct_panel 导入 diy_instruct_service 且不导入 event_option_panel"""
        for module in (handle_premise, see_instruct_panel):
            with self.subTest(module=module.__name__):
                imports = imported_modules(module)
                self.assertIn(diy_instruct_service.__name__, imports)
                self.assertNotIn(OPTION_PANEL, imports)

    def test_relative_import_of_panel_is_caught(self) -> None:
        """验证 imports_in 能识别针对两处面板模块的相对导入写法"""
        source = "def f():\n    from ..UI.Panel import system_setting\n"
        package = common_default.__package__ or ""
        self.assertIn(SETTING_PANEL, imports_in(source, package))
        source = "from ...UI.Panel import event_option_panel\n"
        package = see_instruct_panel.__package__ or ""
        self.assertIn(OPTION_PANEL, imports_in(source, package))

    def test_panels_bind_no_service_function(self) -> None:
        """验证两处界面面板模块在运行期属性中均不存在这两个服务函数名"""
        cases = (
            (system_setting, "get_difficulty_coefficient"),
            (event_option_panel, "get_target_chara_diy_instruct"),
        )
        for panel, name in cases:
            with self.subTest(panel=panel.__name__):
                self.assertFalse(hasattr(panel, name))

    def test_premise_and_service_import_in_either_order(self) -> None:
        """验证 handle_premise 与 diy_instruct_service 在独立子进程中按任意先后顺序导入均可成功"""
        premise = handle_premise.__name__
        service = diy_instruct_service.__name__
        for order in ((premise, service), (service, premise)):
            with self.subTest(order=order):
                result = subprocess.run(
                    [sys.executable, "-c", IMPORT_IN_ORDER, *order],
                    cwd=ROOT,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                self.assertEqual(result.returncode, 0, result.stderr[-2000:])
                self.assertEqual(result.stdout.splitlines()[-1], "True")
