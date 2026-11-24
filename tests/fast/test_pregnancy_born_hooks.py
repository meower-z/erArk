"""
生产与破壳事件回调测试
======================
- HookContractTest：回调登记与派发约定，以及 Tk 回调打开生育事件面板。
- CheckBornTest：check_born 的胎生生产判定与回调派发。
- CheckHardEggBornTest：带壳卵生 check_egg_born 的到期卵判定与回调派发。
- CheckSoftEggBornTest：无壳卵生 check_egg_born 的到期卵判定与回调派发。
- ImportBoundaryTest：妊娠后端模块的导入边界与屏蔽妊娠面板后的独立运行。
"""

import datetime
import json
import subprocess
import sys
from unittest import mock

from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import pregnancy
from Script.Modules.gameplay_resolution import pregnancy_hooks, working
from Script.Modules.tk_ui import callbacks
from Script.System.Pregnancy_System import born_event_panel, egg_handle
from Script.System.Pregnancy_System import pregnancy_constant, pregnancy_handle
from Script.UI.Moudle import draw
from tests import chara_abilities as ca
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports
from tests.fast.test_ejaculation_services import imports_in

MOTHER = 1
""" 测试使用的母亲角色编号（1）。 """
HARD_EGG_RACE = 6
""" 带壳卵生种族编号（6）。 """
SOFT_EGG_RACE = 11
""" 无壳卵生种族编号（11）。 """
PANELS = (
    "Script.System.Pregnancy_System.born_event_panel",
    "Script.System.Pregnancy_System.pregnancy_panel",
)
""" 导入边界检查禁止直接导入的两个妊娠面板模块全名元组。 """
SOURCES = (
    "Script/System/Pregnancy_System/__init__.py",
    "Script/System/Pregnancy_System/egg_handle.py",
    "Script/System/Pregnancy_System/family_tree_draw.py",
    "Script/System/Pregnancy_System/pregnancy_constant.py",
    "Script/System/Pregnancy_System/pregnancy_handle.py",
    "Script/System/Pregnancy_System/soft_egg_handle.py",
    "Script/Modules/gameplay_resolution/pregnancy_hooks.py",
)
""" 接受导入边界检查的七个模块仓库相对路径元组。 """
BLOCKED_RUN = """
import datetime, importlib.abc, json, sys
BLOCKED = (
    "Script.System.Pregnancy_System.born_event_panel",
    "Script.System.Pregnancy_System.pregnancy_panel",
)
def blocked(name):
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if blocked(fullname):
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Block())
from tests import chara_abilities as ca
from tests.fast import WORLD
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import pregnancy
from Script.Modules.gameplay_resolution import pregnancy_hooks, working
from Script.System.Pregnancy_System import egg_handle, pregnancy_constant, pregnancy_handle
WORLD.reset()
WORLD.chara(0, "0")
WORLD.chara(1, "1")
WORLD.chara(2, "2", race=11)
born = []
pregnancy_hooks._on_born[:] = [lambda cid, **options: born.append([cid, options])]
days = datetime.timedelta(days=pregnancy_constant.PARTURIENT_DAY + 5)
hatch = datetime.timedelta(days=pregnancy_constant.HATCH_TOTAL_DAY)
with working.based_on(core.state()):
    ca.talent(1)[22] = 1
    pregnancy.update(1, fertilization_time=game_time.now() - days)
    pregnancy_handle.check_born(1)
    for _ in range(2):
        egg_id = egg_handle.add_egg(2, True, soft=True)
        with pregnancy.editing(2) as preg:
            preg.eggs[egg_id]["identified"] = True
            preg.eggs[egg_id]["lay_time"] -= hatch
    egg_handle.check_egg_born(2)
loaded = sorted(name for name in sys.modules if blocked(name))
print(json.dumps({"born": born, "loaded": loaded}))
"""
"""
子进程脚本源码：屏蔽两个妊娠面板后运行一次生产与一次无壳卵破壳，并以 JSON 输出回调参数与受屏蔽模块的加载列表。
"""

type Born = tuple[int, bool, list[int] | None]
""" 一次生产或破壳回调派发的记录元组类型，依次为母亲角色编号、是否卵生破壳与卵编号列表。 """


class BornCase(FastTestCase):
    """生产与破壳测试基类，接管回调列表、Born_Panel 与 draw 中的绘制类以记录派发和绘制行为。"""

    race = 0
    """ 测试母亲角色的种族编号。 """

    def setUp(self) -> None:
        """
        初始化玩家与测试母亲并打开工作集，
        接管回调列表、Born_Panel 与 Script.UI.Moudle.draw 中所有带 draw 方法的类。
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(MOTHER, "测试母亲", race=self.race)
        self.enterContext(working.based_on(core.state()))
        self.emitted: list[Born] = []
        self.enterContext(
            mock.patch.object(pregnancy_hooks, "_on_born", [self.record])
        )
        self.panel = self.enterContext(
            mock.patch.object(born_event_panel, "Born_Panel")
        )
        self.drawn: list[str] = []
        for cls in vars(draw).values():
            if isinstance(cls, type) and hasattr(cls, "draw"):
                self.enterContext(
                    mock.patch.object(
                        cls, "draw", autospec=True, side_effect=self.keep
                    )
                )

    def record(
        self,
        character_id: int,
        *,
        egg_mode: bool = False,
        egg_id_list: list[int] | None = None,
    ) -> None:
        """
        记录一次回调派发收到的参数。
        Keyword arguments:
        character_id -- int，母亲角色编号
        egg_mode -- bool，为 True 时表示卵生破壳模式，默认为 False
        egg_id_list -- list[int] | None，本次破壳的卵编号列表，默认为 None
        """
        self.emitted.append((character_id, egg_mode, egg_id_list))

    def keep(self, now: object) -> None:
        """
        记录被调用 draw 方法的绘制对象类名。
        Keyword arguments:
        now -- object，被调用 draw 方法的绘制对象实例
        """
        self.drawn.append(type(now).__name__)

    def with_tk(self) -> None:
        """在当前测试回调之后追加登记 Tk 回调 callbacks.draw_born_event。"""
        pregnancy_hooks._on_born.append(callbacks.draw_born_event)

    def unregister(self) -> None:
        """清空回调列表，模拟未登记回调的无界面运行环境。"""
        pregnancy_hooks._on_born.clear()

    def assert_panel(self, *calls: Born) -> None:
        """
        断言 Born_Panel 按 calls 顺序以对应参数构造，且每次构造后调用 draw 一次。
        Keyword arguments:
        calls -- tuple[Born, ...]，预期依次发生的 Born_Panel 构造参数记录
        """
        self.assertEqual(
            self.panel.call_args_list,
            [mock.call(c, egg_mode=m, egg_id_list=e) for c, m, e in calls],
        )
        self.assertEqual(
            self.panel.return_value.draw.call_args_list,
            [mock.call()] * len(calls),
        )

    def assert_silent(self) -> None:
        """断言未派发回调、未构造 Born_Panel 且未触发任何 draw 调用。"""
        self.assertEqual(self.emitted, [])
        self.panel.assert_not_called()
        self.assertEqual(self.drawn, [])


class HookContractTest(FastTestCase):
    """回调登记、派发顺序与 Tk 回调行为的单元测试。"""

    def test_emit_calls_in_registration_order(self) -> None:
        """验证未登记回调时 emit_born 不执行操作。同时验证 on_born 原样返回回调，以及多个回调按登记顺序收到相同参数。"""
        calls = mock.Mock()
        first, second = calls.first, calls.second
        self.enterContext(mock.patch.object(pregnancy_hooks, "_on_born", []))
        pregnancy_hooks.emit_born(MOTHER)
        self.assertIs(pregnancy_hooks.on_born(first), first)
        self.assertIs(pregnancy_hooks.on_born(second), second)
        self.assertEqual(calls.mock_calls, [])
        pregnancy_hooks.emit_born(5, egg_mode=True, egg_id_list=[3, 4])
        pregnancy_hooks.emit_born(6)
        self.assertEqual(
            calls.mock_calls,
            [
                mock.call.first(5, egg_mode=True, egg_id_list=[3, 4]),
                mock.call.second(5, egg_mode=True, egg_id_list=[3, 4]),
                mock.call.first(6, egg_mode=False, egg_id_list=None),
                mock.call.second(6, egg_mode=False, egg_id_list=None),
            ],
        )

    def test_tk_callback_registered(self) -> None:
        """验证测试小世界载入后 callbacks.draw_born_event 已登记到 pregnancy_hooks._on_born。"""
        self.assertIn(callbacks.draw_born_event, pregnancy_hooks._on_born)

    def test_tk_callback_opens_panel(self) -> None:
        """验证 Tk 回调在收到胎生与破壳派发时均按对应参数构造 Born_Panel 并各绘制一次。"""
        self.enterContext(
            mock.patch.object(
                pregnancy_hooks, "_on_born", [callbacks.draw_born_event]
            )
        )
        panel = self.enterContext(
            mock.patch.object(born_event_panel, "Born_Panel")
        )
        pregnancy_hooks.emit_born(MOTHER)
        pregnancy_hooks.emit_born(MOTHER, egg_mode=True, egg_id_list=[2, 3])
        self.assertEqual(
            panel.call_args_list,
            [
                mock.call(MOTHER, egg_mode=False, egg_id_list=None),
                mock.call(MOTHER, egg_mode=True, egg_id_list=[2, 3]),
            ],
        )
        self.assertEqual(
            panel.return_value.draw.call_args_list, [mock.call()] * 2
        )


class CheckBornTest(BornCase):
    """pregnancy_handle.check_born 胎生生产判定的单元测试。"""

    def pregnant(self, parturient: bool, extra_days: int) -> None:
        """
        设置测试母亲的临盆素质，并将受精时间设为当前游戏时间之前 PARTURIENT_DAY + extra_days 天。
        Keyword arguments:
        parturient -- bool，是否赋予临盆素质（22）
        extra_days -- int，超出 PARTURIENT_DAY 的天数，每日增加 20% 生产几率
        """
        ca.talent(MOTHER)[22] = int(parturient)
        past = pregnancy_constant.PARTURIENT_DAY + extra_days
        when = game_time.now() - datetime.timedelta(days=past)
        pregnancy.update(MOTHER, fertilization_time=when)

    def test_no_birth_is_silent(self) -> None:
        """验证未临盆，或临盆但掷骰结果大于当日几率时，不派发回调也不触发绘制。"""
        for parturient, extra_days, roll in (
            (False, 5, 1),
            (True, 0, 1),
            (True, 2, 41),
        ):
            with self.subTest(parturient=parturient, extra_days=extra_days):
                self.pregnant(parturient, extra_days)
                with mock.patch.object(
                    pregnancy_handle.random, "randint", return_value=roll
                ):
                    pregnancy_handle.check_born(MOTHER)
                self.assert_silent()

    def test_birth_emits_live_birth(self) -> None:
        """验证临盆且掷骰结果不大于当日几率时，派发一次胎生回调且不直接构造或绘制面板。"""
        for extra_days, roll in ((2, 40), (5, 100)):
            with self.subTest(extra_days=extra_days, roll=roll):
                self.emitted.clear()
                self.pregnant(True, extra_days)
                with mock.patch.object(
                    pregnancy_handle.random, "randint", return_value=roll
                ):
                    pregnancy_handle.check_born(MOTHER)
                self.assertEqual(self.emitted, [(MOTHER, False, None)])
        self.panel.assert_not_called()
        self.assertEqual(self.drawn, [])

    def test_tk_callback_opens_live_birth_panel(self) -> None:
        """验证登记 Tk 回调后，生产判定成立时以胎生参数构造 Born_Panel 并绘制一次。"""
        self.with_tk()
        self.pregnant(True, 5)
        pregnancy_handle.check_born(MOTHER)
        self.assertEqual(self.emitted, [(MOTHER, False, None)])
        self.assert_panel((MOTHER, False, None))

    def test_unregistered_birth_is_silent(self) -> None:
        """验证未登记任何回调时，生产判定成立也不构造 Born_Panel 且不触发绘制。"""
        self.unregister()
        self.pregnant(True, 5)
        pregnancy_handle.check_born(MOTHER)
        self.assert_silent()


class EggCase(BornCase):
    """卵生破壳测试基类，提供造卵、读取孵化阶段与无到期卵静默断言的辅助方法。"""

    def lay(
        self, days_ago: int, identified: bool = True, fertilized: bool = True
    ) -> int:
        """
        为测试母亲新增一枚卵，设置鉴定状态并将排出时间前移 days_ago 天。
        Keyword arguments:
        days_ago -- int，排出时间早于当前游戏时间的天数
        identified -- bool，是否已鉴定，默认为 True
        fertilized -- bool，是否受精，默认为 True
        Return arguments:
        int -- 新增卵的编号
        """
        egg_id = egg_handle.add_egg(
            MOTHER, fertilized, soft=self.race == SOFT_EGG_RACE
        )
        with pregnancy.editing(MOTHER) as preg:
            egg = preg.eggs[egg_id]
            egg["identified"] = identified
            egg["lay_time"] -= datetime.timedelta(days=days_ago)
        return egg_id

    def stages(self) -> dict[int, int]:
        """
        返回测试母亲每枚卵当前的 hatch_stage 映射。
        Return arguments:
        dict[int, int] -- 以卵编号为键、hatch_stage 为值的字典
        """
        return {
            egg_id: egg["hatch_stage"]
            for egg_id, egg in pregnancy.of(MOTHER).eggs.items()
        }

    def assert_no_due_egg_is_silent(self) -> None:
        """
        断言仅有未鉴定、未受精或未满孵化总天数的卵时不派发回调也不绘制。
        同时断言受精且已鉴定的未到期卵写入对应 hatch_stage。
        """
        total = pregnancy_constant.HATCH_TOTAL_DAY
        unidentified = self.lay(total, identified=False)
        unfertilized = self.lay(total, fertilized=False)
        young = self.lay(total - 1)
        egg_handle.check_egg_born(MOTHER)
        self.assert_silent()
        self.assertEqual(
            self.stages(),
            {unidentified: 0, unfertilized: 0, young: total - 1},
        )


class CheckHardEggBornTest(EggCase):
    """带壳卵生 egg_handle.check_egg_born 的单元测试。"""

    race = HARD_EGG_RACE

    def test_no_due_egg_is_silent(self) -> None:
        """验证带壳卵生没有到期卵时不派发回调也不触发绘制。"""
        self.assert_no_due_egg_is_silent()

    def test_emits_first_due_egg_only(self) -> None:
        """验证带壳卵生有多枚到期卵时仅派发首枚到期卵。排在其后的卵保持孵化阶段 0。"""
        total = pregnancy_constant.HATCH_TOTAL_DAY
        young = self.lay(total - 1)
        first = self.lay(total + 1)
        second = self.lay(total)
        egg_handle.check_egg_born(MOTHER)
        self.assertEqual(self.emitted, [(MOTHER, True, [first])])
        self.assertEqual(
            self.stages(), {young: total - 1, first: total + 1, second: 0}
        )
        self.panel.assert_not_called()
        self.assertEqual(self.drawn, [])

    def test_tk_callback_opens_egg_panel(self) -> None:
        """验证登记 Tk 回调后，带壳卵生破壳以破壳参数与首枚到期卵构造 Born_Panel 并绘制一次。"""
        self.with_tk()
        total = pregnancy_constant.HATCH_TOTAL_DAY
        first = self.lay(total)
        self.lay(total)
        egg_handle.check_egg_born(MOTHER)
        self.assert_panel((MOTHER, True, [first]))

    def test_unregistered_egg_is_silent(self) -> None:
        """验证未登记任何回调时，带壳卵生存在到期卵也不构造 Born_Panel 且不触发绘制。"""
        self.unregister()
        self.lay(pregnancy_constant.HATCH_TOTAL_DAY)
        egg_handle.check_egg_born(MOTHER)
        self.assert_silent()


class CheckSoftEggBornTest(EggCase):
    """无壳卵生 egg_handle.check_egg_born 的单元测试。"""

    race = SOFT_EGG_RACE

    def test_no_due_egg_is_silent(self) -> None:
        """验证无壳卵生没有到期卵时不派发回调也不触发绘制。"""
        self.assert_no_due_egg_is_silent()

    def test_emits_all_due_eggs(self) -> None:
        """验证无壳卵生有多枚到期卵时一次派发全部到期卵，并更新每枚受精已鉴定卵的孵化阶段。"""
        total = pregnancy_constant.HATCH_TOTAL_DAY
        first = self.lay(total + 1)
        young = self.lay(total - 1)
        second = self.lay(total)
        egg_handle.check_egg_born(MOTHER)
        self.assertEqual(self.emitted, [(MOTHER, True, [first, second])])
        self.assertEqual(
            self.stages(),
            {first: total + 1, young: total - 1, second: total},
        )
        self.panel.assert_not_called()
        self.assertEqual(self.drawn, [])

    def test_tk_callback_opens_egg_panel(self) -> None:
        """验证登记 Tk 回调后，无壳卵生破壳以破壳参数与全部到期卵构造 Born_Panel 并绘制一次。"""
        self.with_tk()
        total = pregnancy_constant.HATCH_TOTAL_DAY
        first = self.lay(total)
        second = self.lay(total)
        egg_handle.check_egg_born(MOTHER)
        self.assert_panel((MOTHER, True, [first, second]))


class ImportBoundaryTest(FastTestCase):
    """妊娠后端模块导入边界与屏蔽妊娠面板后独立运行的单元测试。"""

    def test_sources_import_no_ui_or_pregnancy_panels(self) -> None:
        """验证 SOURCES 中每个模块均通过 banned_imports 检查，且不直接导入 PANELS 中的妊娠面板。"""
        for path in SOURCES:
            with self.subTest(path=path):
                source = (ROOT / path).read_bytes()
                self.assertEqual(banned_imports(source, path), [])
                self.assertEqual(panel_imports(source, path), [])

    def test_checkers_report_relative_and_multi_name_imports(self) -> None:
        """验证 banned_imports 与 panel_imports 均能检出相对导入以及单条导入语句中的后续目标名。"""
        path = "Script/System/Pregnancy_System/sample.py"
        source = (
            "from . import pregnancy_constant, born_event_panel\n"
            "from ...UI.Moudle import draw\n"
            "from Script import Core, UI\n"
            "def f():\n"
            "    from .pregnancy_panel import get_date_text\n"
        )
        self.assertEqual(
            banned_imports(source, path),
            [(2, "Script.UI.Moudle.draw"), (3, "Script.UI")],
        )
        self.assertEqual(
            panel_imports(source, path),
            [
                "Script.System.Pregnancy_System.born_event_panel",
                "Script.System.Pregnancy_System.pregnancy_panel",
                "Script.System.Pregnancy_System.pregnancy_panel.get_date_text",
            ],
        )

    def test_birth_and_hatch_run_without_panels(self) -> None:
        """
        验证在屏蔽两个妊娠面板的子进程中，一次胎生生产与一次无壳卵破壳均可向回调派发预期参数且不加载受屏蔽面板。
        """
        result = subprocess.run(
            [sys.executable, "-c", BLOCKED_RUN],
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
                "born": [
                    [1, {"egg_mode": False, "egg_id_list": None}],
                    [2, {"egg_mode": True, "egg_id_list": [0, 1]}],
                ],
                "loaded": [],
            },
        )


def panel_imports(source: str | bytes, path: str) -> list[str]:
    """
    列出源码中导入 PANELS 模块或其成员的解析后完整路径。
    Keyword arguments:
    source -- str | bytes，待检查的 Python 源码
    path -- str，文件的仓库相对路径，用于解析相对导入
    Return arguments:
    list[str] -- 排序后的命中完整路径列表
    """
    package = path.rsplit("/", 1)[0].replace("/", ".")
    text = source.decode() if isinstance(source, bytes) else source
    return sorted(
        name
        for name in imports_in(text, package)
        if any(name == root or name.startswith(root + ".") for root in PANELS)
    )
