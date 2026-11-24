"""
后端成就调用方边界与通知测试
============================
- 通过语法树检查 Script 下除 Script/UI/ 与 Script/Modules/tk_ui/callbacks.py 外的源码
  不导入成就面板（achievement_panel）。
- 验证医疗部结算、干员催眠素质检查与人力发电三处调用经 achievement_service.settle_and_notify 结算并绘制金色提示。
- 在子进程中运行模式 A 单元测试模板，验证 settle_and_notify 触发的成就提示写入记录列表 wait_texts。
"""

import ast
import json
import os
import subprocess
import sys
from importlib.util import resolve_name
from pathlib import Path, PurePosixPath
from unittest import mock

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import handle_talent
from Script.Kernel import core
from Script.Modules.domains import achievement, hypnosis, power_supply
from Script.Modules.domains import warehouse
from Script.Modules.gameplay_resolution import achievement_service, working
from Script.Settle import power_settle
from Script.System.Medical_System import medical_service
from Script.UI.Moudle import draw
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.world import ROOT

PANEL = "Script.UI.Panel.achievement_panel"
""" 禁止后端调用方导入的成就面板模块全名 """
SKIPPED = ("Script/UI/", "Script/Modules/tk_ui/callbacks.py")
""" 边界检查跳过的目录与回调文件路径前缀 """
MONEY_ID = 201
""" 测试用龙门币成就编号（Achievement.csv 编号 201） """
HYPNOSIS_ID = 621
""" 测试用催眠成就编号（Achievement.csv 编号 621） """
HUMAN_POWER_ID = 827
""" 测试用能源类人力发电成就编号（Achievement.csv 编号 827） """
OPERATOR = 1
""" 测试用干员角色编号 """
TEMPLATE_ID = 821
""" 测试模式 A 模板所用的能源类成就编号（Achievement.csv 编号 821） """
TEMPLATES = (
    ("tools/verify/headless_unit_template.py", "# ==== 1. ", "wait_texts"),
)
""" 待测模式 A 模板清单，每项为 (模板路径, 截断标记, WaitDraw 记录列表名) """
TEMPLATE_PROBE = """
import json
import sys

path, marker, recorder, achievement_id = sys.argv[1:5]
with open(path, encoding="utf-8") as file:
    source = file.read()
probe = (
    "from Script.Modules.domains import warehouse as _warehouse\\n"
    "from Script.Modules.gameplay_resolution import achievement_service as _service\\n"
    "kernel_data.written(_warehouse.ensure, 1)\\n"
    f"_data = game_config.config_achievement[{achievement_id}]\\n"
    "with kernel_data.writing():\\n"
    f"    _new = _service.settle_and_notify(_data.type, {achievement_id})\\n"
    f"_drawn = [text for text in {recorder} if _data.name in text]\\n"
    "print(json.dumps({\\"new\\": _new, \\"drawn\\": len(_drawn)}))\\n"
)
prefix = source[: source.index(marker)]
exec(compile(prefix + probe, path, "exec"), {"__name__": "__main__", "json": json})
"""
""" 子进程探针脚本，截取模板初始化段并运行 settle_and_notify 后以 JSON 输出新达成编号与绘制条数 """


def panel_imports(source: str | bytes, path: str) -> list[int]:
    """
    解析源码语法树，找出导入 PANEL 或其成员的语句行号。
    Keyword arguments:
    source -- str | bytes，待检查的 Python 源码
    path -- str，文件的仓库相对路径，用于解析相对导入
    Return arguments:
    list[int] -- 升序排列的命中导入语句行号列表
    """
    package = ".".join(PurePosixPath(path).parent.parts)
    found: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = resolve_name("." * node.level + (node.module or ""), package)
            names = [base] + [f"{base}.{alias.name}" for alias in node.names]
        else:
            continue
        if any(name == PANEL or name.startswith(PANEL + ".") for name in names):
            found.append(node.lineno)
    return sorted(found)


def violations() -> list[str]:
    """
    扫描 Script 下除 SKIPPED 外的 .py 文件，收集命中 PANEL 的导入位置。
    Keyword arguments:
    无
    Return arguments:
    list[str] -- 形如 "相对路径:行号" 的违规导入列表
    """
    found: list[str] = []
    for path in sorted((Path(ROOT) / "Script").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith(SKIPPED):
            continue
        found.extend(
            f"{relative}:{line}"
            for line in panel_imports(path.read_bytes(), relative)
        )
    return found


class PanelImportBoundaryTest(FastTestCase):
    """验证 Script 下界面目录与 Tk 回调以外的代码不导入成就面板"""

    def test_game_code_outside_ui_imports_no_panel(self) -> None:
        """断言 Script 下除 SKIPPED 外的源码不含导入 PANEL 的语句"""
        self.assertEqual(violations(), [])

    def test_checker_resolves_absolute_and_relative_imports(self) -> None:
        """验证 panel_imports 能检出绝对导入、相对导入与函数内导入，且不误报其他模块或相近前缀"""
        settle = "Script/Settle/sample.py"
        medical = "Script/System/Medical_System/sample.py"
        cases = (
            ("from Script.UI.Panel import achievement_panel", settle, True),
            ("import Script.UI.Panel.achievement_panel", settle, True),
            ("from Script.UI.Panel.achievement_panel import x", settle, True),
            ("from ..UI.Panel import achievement_panel", settle, True),
            ("from ..UI.Panel.achievement_panel import x", settle, True),
            ("from ...UI.Panel import draw, achievement_panel", medical, True),
            (
                "def f():\n    from ..UI.Panel import achievement_panel",
                settle,
                True,
            ),
            ("from . import achievement_panel", "Script/UI/Panel/a.py", True),
            ("from ..UI.Panel import achievement_panel", medical, False),
            (
                "from Script.UI.Panel import achievement_panel_extra",
                settle,
                False,
            ),
            ("from ..UI.Panel import ejaculation_panel", settle, False),
            ("from Script.Modules.gameplay_resolution import x", settle, False),
        )
        self.assertEqual(
            [bool(panel_imports(source, path)) for source, path, _hit in cases],
            [hit for _source, _path, hit in cases],
        )


class CallerNotifiesTest(FastTestCase):
    """验证三处后端调用经 achievement_service.settle_and_notify 结算并绘制金色提示"""

    def setUp(self) -> None:
        """创建玩家角色，包装 achievement_service.settle_and_notify 并打桩 WaitDraw.draw"""
        super().setUp()
        self.world.chara(0, "博士")
        self.settle = self.enterContext(
            mock.patch.object(
                achievement_service,
                "settle_and_notify",
                wraps=achievement_service.settle_and_notify,
            )
        )
        self.waited = self.enterContext(
            mock.patch.object(draw.WaitDraw, "draw", autospec=True)
        )

    def notices(self) -> list[str]:
        """返回 WaitDraw.draw 收到的 gold_enrod 样式提示文本列表"""
        return [
            now.text
            for (now,), _kwargs in self.waited.call_args_list
            if now.style == "gold_enrod"
        ]

    def assert_notice(self, achievement_id: int) -> None:
        """断言指定成就已达成且仅绘制了一条包含该成就名称的金色提示"""
        name = game_config.config_achievement[achievement_id].name
        self.assertTrue(achievement.done(achievement_id))
        self.assertEqual(len(self.notices()), 1)
        self.assertIn(name, self.notices()[0])

    def test_medical_day_settles_money_type(self) -> None:
        """验证医疗部结算按龙门币类型调用 settle_and_notify，达成成就 201 并绘制金色提示"""
        need = game_config.config_achievement[MONEY_ID].value
        with kernel_data.writing():
            medical_service.init_medical_department_data()
            warehouse.set(1, need)
            medical_service.settle_medical_department(draw_flag=False)
        self.assertEqual(
            self.settle.call_args_list, [mock.call(get_text._("龙门币"))]
        )
        self.assert_notice(MONEY_ID)

    def test_hypnosis_talent_check_settles_hypnosis_type(self) -> None:
        """验证干员催眠素质检查按催眠类型调用 settle_and_notify，达成成就 621 并绘制金色提示"""
        self.world.chara(OPERATOR)
        with kernel_data.writing():
            hypnosis.set(OPERATOR, hypnosis_degree=1)
            handle_talent.npc_gain_hypnosis_talent(OPERATOR)
        self.assertEqual(
            self.settle.call_args_list, [mock.call(get_text._("催眠"))]
        )
        self.assert_notice(HYPNOSIS_ID)

    def test_human_power_forces_its_achievement_at_threshold(self) -> None:
        """验证人力发电在阈值减 1 时不调用 settle_and_notify，达到阈值时强制结算成就 827 并绘制金色提示"""
        data = game_config.config_achievement[HUMAN_POWER_ID]
        self.enterContext(working.based_on(core.state()))
        with mock.patch.object(
            power_supply, "human_power", return_value=data.value - 1
        ):
            power_settle.store_power_by_human_power(1, 0, draw_flag=False)
        self.settle.assert_not_called()
        self.assertEqual(self.notices(), [])
        with mock.patch.object(
            power_supply, "human_power", return_value=data.value
        ):
            power_settle.store_power_by_human_power(1, 0, draw_flag=False)
        self.assertEqual(
            self.settle.call_args_list,
            [mock.call(data.type, HUMAN_POWER_ID)],
        )
        self.assert_notice(HUMAN_POWER_ID)


def template_notice(
    path: str, marker: str, recorder: str
) -> dict[str, int | list[int]]:
    """
    在子进程中运行模板初始化段与探针，返回成就结算与提示绘制统计。
    Keyword arguments:
    path -- str，模式 A 模板文件的仓库相对路径
    marker -- str，截取模板源码时用于定位截断点的标记文本
    recorder -- str，模板中记录 WaitDraw 文本的列表变量名
    Return arguments:
    dict[str, int | list[int]] -- 含新达成编号列表 new 与命中提示条数 drawn 的字典
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            TEMPLATE_PROBE,
            path,
            marker,
            recorder,
            str(TEMPLATE_ID),
        ],
        cwd=ROOT,
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        check=True,
        capture_output=True,
        encoding="utf-8",
        timeout=300,
    )
    found: dict[str, int | list[int]] = json.loads(
        result.stdout.splitlines()[-1]
    )
    return found


class UnitTemplateNoticeTest(FastTestCase):
    """验证模式 A 单元测试模板会记录 settle_and_notify 触发的成就提示"""

    def test_unit_templates_record_achievement_notice(self) -> None:
        """断言 TEMPLATES 中的模板执行 settle_and_notify 后达成成就 821 且记录一条提示"""
        for path, marker, recorder in TEMPLATES:
            with self.subTest(path=path):
                self.assertEqual(
                    template_notice(path, marker, recorder),
                    {"new": [TEMPLATE_ID], "drawn": 1},
                )
