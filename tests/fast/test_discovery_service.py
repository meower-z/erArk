"""
旁人目睹H的发现行动测试
=======================
验证发现行动的排队、开始时的通知派发、Tk 回调打开被发现面板，以及拦截面板导入时的运行。
同时检查 Script/Modules/gameplay_resolution 目录不导入面板模块。
"""

import ast
import subprocess
import sys
from collections.abc import Callable, Mapping
from importlib.util import resolve_name
from pathlib import PurePosixPath
from unittest import mock

from Script.Config import normal_config
from Script.Core import constant
from Script.Kernel import core
from Script.Modules.gameplay_resolution import hidden_sex_service, intent
from Script.Modules.gameplay_resolution import npc_starters, plan_queue
from Script.UI.Panel import sex_be_discovered_panel
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

FINDER = 2
""" 发现者的测试角色编号。 """
PACKAGE = "Script/Modules/gameplay_resolution"
""" 禁止导入面板模块的后端目录相对路径。 """
SEEN = intent.Intent(behavior_id=constant.Behavior.SHARE_BLANKLY, minutes=1)
""" 传给开始函数的占位行动意图，被测函数不读取其字段。 """
REGISTERED = list(hidden_sex_service._on_discovered)
""" 模块导入完成后，hidden_sex_service._on_discovered 中已登记的被发现通知回调副本。 """
BLOCKED_RUN = """
import importlib.abc, sys
PANELS = ("Script.UI.Panel",)
def blocked(name):
    return any(name == root or name.startswith(root + ".") for root in PANELS)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if blocked(fullname):
            raise ImportError(fullname)
sys.meta_path.insert(0, Block())
from tests.fast.base import FastTestCase
from tests import kernel_data
from Script.Kernel import core
from Script.Modules.gameplay_resolution import hidden_sex_service as service
from Script.Modules.gameplay_resolution import intent, npc_starters, plan_queue
case = FastTestCase()
case.setUp()
for cid in (0, 2):
    case.world.chara(cid, str(cid))
seen = []
service._on_discovered[:] = [lambda cid, flag: seen.append((cid, flag))]
kernel_data.written(npc_starters.see_h, 2, intent.Intent(behavior_id="wait", minutes=1))
act = plan_queue.queue_head("2").value
service.start_discovery(2, intent.Intent(**act.action_data))
print(act.action_id, act.action_id in core._actions, seen)
print(sorted(name for name in sys.modules if blocked(name)))
"""
""" 在拦截面板模块导入的子进程中运行目睹H排队与发现行动开始的测试脚本。 """


def panel_imports(source: str | bytes, path: str) -> list[str]:
    """
    解析源码中的导入语句，找出名称中含有以 _panel 结尾的段的模块或成员。
    Keyword arguments:
    source -- str | bytes，待解析的 Python 源码
    path -- str，文件相对仓库根目录的 POSIX 路径，用于展开相对导入
    Return arguments:
    list[str] -- 名称中含有以 _panel 结尾的段的导入模块或成员完整名称列表
    """
    package = ".".join(PurePosixPath(path).parent.parts)
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = resolve_name("." * node.level + (node.module or ""), package)
            names = [base, *(f"{base}.{alias.name}" for alias in node.names)]
        else:
            continue
        found.extend(
            name
            for name in names
            if any(part.endswith("_panel") for part in name.split("."))
        )
    return found


class PlanDiscoveryTest(FastTestCase):
    """验证发现行动能排入发现者的计划队列并打断其当前行动。"""

    def setUp(self) -> None:
        """初始化测试环境，创建角色 0 与发现者角色。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(FINDER, "发现者")

    def assert_discovery_planned(self, plan: Callable[[], None]) -> None:
        """
        断言调用 plan 后，发现者被打断，且其计划队列队首为 1 分钟的 DISCOVERY 等待行动。
        Keyword arguments:
        plan -- Callable[[], None]，用于排入发现行动的无参函数
        Return arguments:
        None -- 无返回值
        """
        with kernel_data.writing():
            position = plan_queue.mark()
            plan()
            interrupted = plan_queue.take_since(position)
        self.assertEqual(interrupted, [str(FINDER)])
        head = plan_queue.queue_head(str(FINDER))
        assert isinstance(head, core.Intercept)
        act = head.value
        self.assertEqual(
            act.action_id, intent.KIND_PREFIX + hidden_sex_service.DISCOVERY
        )
        self.assertEqual(act.duration, 1)
        data = act.action_data
        assert isinstance(data, Mapping)
        self.assertEqual(data["behavior_id"], constant.Behavior.WAIT)
        self.assertEqual(data["state"], constant.CharacterStatus.STATUS_WAIT)

    def test_plan_discovery(self) -> None:
        """验证 hidden_sex_service.plan_discovery 会按预期排入发现行动。"""
        self.assert_discovery_planned(
            lambda: hidden_sex_service.plan_discovery(FINDER)
        )

    def test_see_h_plans_discovery(self) -> None:
        """验证 npc_starters.see_h 会排入相同的发现行动。"""
        self.assert_discovery_planned(lambda: npc_starters.see_h(FINDER, SEEN))


class StartDiscoveryTest(FastTestCase):
    """验证发现行动登记、开始时的通知派发以及拦截面板导入时的运行。"""

    def test_kind_is_registered(self) -> None:
        """验证发现行动种类已在内核中登记开始函数与结束函数。"""
        action_id = intent.KIND_PREFIX + hidden_sex_service.DISCOVERY
        self.assertIn(action_id, core._actions)
        self.assertTrue(
            core.has_end(core.Action(str(FINDER), action_id, None, 0, 1))
        )

    def test_notifies_callbacks(self) -> None:
        """验证 start_discovery 会以 (FINDER, False) 调用已登记的通知回调。"""
        seen: list[tuple[int, bool]] = []
        with mock.patch.object(
            hidden_sex_service,
            "_on_discovered",
            [lambda cid, flag: seen.append((cid, flag))],
        ):
            hidden_sex_service.start_discovery(FINDER, SEEN)
        self.assertEqual(seen, [(FINDER, False)])

    def test_tk_callback_opens_panel(self) -> None:
        """验证保留已登记的 Tk 回调时，start_discovery 会按配置文本宽度构造并绘制被发现面板一次。"""
        with (
            mock.patch.object(hidden_sex_service, "_on_discovered", REGISTERED),
            mock.patch.object(
                sex_be_discovered_panel, "Sex_Be_Discovered_Panel"
            ) as panel,
        ):
            hidden_sex_service.start_discovery(FINDER, SEEN)
        panel.assert_called_once_with(
            normal_config.config_normal.text_width,
            FINDER,
            from_hidden_sex_flag=False,
        )
        panel.return_value.draw.assert_called_once_with()

    def test_no_callback_draws_nothing(self) -> None:
        """验证未登记通知回调时，start_discovery 不调用被发现面板构造方法。"""
        with (
            mock.patch.object(hidden_sex_service, "_on_discovered", []),
            mock.patch.object(
                sex_be_discovered_panel, "Sex_Be_Discovered_Panel"
            ) as panel,
        ):
            hidden_sex_service.start_discovery(FINDER, SEEN)
        panel.assert_not_called()

    def test_runs_with_panels_blocked(self) -> None:
        """验证在拦截面板模块导入的子进程中，目睹H能排入并开始发现行动、触发回调，且不载入被拦截的面板模块。"""
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
            result.stdout.splitlines()[-2:],
            ["gameplay_resolution.Discovery True [(2, False)]", "[]"],
        )


class PanelImportBoundaryTest(FastTestCase):
    """验证 Script/Modules/gameplay_resolution 目录不导入面板模块。"""

    def test_no_panel_imports(self) -> None:
        """验证 Script/Modules/gameplay_resolution 下的每个 Python 文件都不导入含 _panel 结尾段的模块或成员。"""
        for path in sorted((ROOT / PACKAGE).rglob("*.py")):
            relative = path.relative_to(ROOT).as_posix()
            with self.subTest(path=relative):
                self.assertEqual(panel_imports(path.read_bytes(), relative), [])

    def test_checker_finds_panel_imports(self) -> None:
        """验证 panel_imports 能识别绝对导入、相对导入、函数内导入与同句多名称导入，并忽略非 _panel 结尾的名称。"""
        path = f"{PACKAGE}/npc_starters.py"
        source = "\n".join(
            (
                "import Script.UI.Panel.hidden_sex_panel",
                "from ...UI.Panel import sex_be_discovered_panel",
                "from Script.UI.Panel import handle, exhibitionism_sex_panel",
                "def f():",
                "    from Script.UI.Panel.see_panel import x",
                "from . import panel_starters",
            )
        )
        self.assertEqual(
            panel_imports(source, path),
            [
                "Script.UI.Panel.hidden_sex_panel",
                "Script.UI.Panel.sex_be_discovered_panel",
                "Script.UI.Panel.exhibitionism_sex_panel",
                "Script.UI.Panel.see_panel",
                "Script.UI.Panel.see_panel.x",
            ],
        )
