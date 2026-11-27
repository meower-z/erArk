"""
隐奸结算服务测试
================
覆盖隐蔽等级与发现概率、同场景角色筛选、隐蔽值结算、被发现结算与回调、隐奸总流程、露出模式更新及模块导入边界。
"""

import ast
import contextlib
import io
import subprocess
import sys
from importlib.util import resolve_name
from pathlib import PurePosixPath
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import constant, game_type
from Script.Kernel import core
from Script.Modules.domains import activity, flags, h_state
from Script.Modules.gameplay_resolution import hidden_sex_service, working
from Script.Settle import Second_effect
from Script.System.Sex_System import exhibitionism_sex_panel
from Script.System.Sex_System import hidden_sex_panel
from Script.UI.Panel import sex_be_discovered_panel
from tests import chara_abilities
from tests.chara_activity import aim, behave
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports

PARTNER = 1
""" 测试使用的隐奸或露出对象角色编号（1）。 """
WITNESS = 2
""" 测试使用的旁观者角色编号（2）。 """
EXTRA = 3
""" 测试使用的额外同场景角色编号（3）。 """
ELSEWHERE = ["中枢", "休息室"]
""" 测试使用的另一处室内场景路径。 """
OUTDOOR = ["甲板", "甲板"]
""" 测试使用的室外场景路径。 """
SERVICE_PATH = "Script/Modules/gameplay_resolution/hidden_sex_service.py"
""" 隐奸结算服务模块的仓库相对路径。 """
CALLER_PATHS = (
    "Script/Design/character_behavior.py",
    "Script/Settle/Second_effect.py",
)
""" 需要校验导入边界的两处后端调用方相对路径元组。 """
PANELS = (
    "Script.System.Sex_System.hidden_sex_panel",
    "Script.System.Sex_System.exhibitionism_sex_panel",
)
""" 边界测试禁止后端调用方导入的两处性行为面板模块全名。 """
MOVED = """handle_hidden_sex_flow get_hidden_level get_hidden_sex_targets
get_nearby_conscious_unfallen_characters settle_hidden_value_by_action
check_hidden_sex_discovery settle_discovered update_exhibiionism_sex_mode
""".split()
""" 由 hidden_sex_service 提供的八个结算函数名列表。 """
EXPOSED_ORGASMS = (
    (Second_effect.handle_exposed_orgasm_small_in_hidden_sex, 10),
    (Second_effect.handle_exposed_orgasm_normal_in_hidden_sex, 18),
    (Second_effect.handle_exposed_orgasm_strong_in_hidden_sex, 28),
    (Second_effect.handle_exposed_orgasm_super_in_hidden_sex, 50),
)
""" Second_effect 中四项隐奸高潮暴露效果函数及预期被发现度增量。 """
BLOCKED_RUN = """
import importlib.abc, sys
PANELS = ("Script.UI.Panel", "Script.System.Sex_System.hidden_sex_panel",
    "Script.System.Sex_System.exhibitionism_sex_panel")
def blocked(name):
    return any(name == root or name.startswith(root + ".") for root in PANELS)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if blocked(fullname):
            raise ImportError(fullname)
sys.meta_path.insert(0, Block())
from tests.fast.base import FastTestCase
from tests import kernel_data
from tests.chara_activity import aim
from Script.Modules.domains import flags, h_state
from Script.Modules.gameplay_resolution import hidden_sex_service as service
case = FastTestCase()
case.setUp()
for cid in (0, 1, 2):
    case.world.chara(cid, str(cid))
aim(0, 1)
seen = []
service._on_discovered[:] = [lambda cid, flag: seen.append((cid, flag))]
with kernel_data.writing():
    flags.set(0, hidden_sex_mode=2, exhibitionism_sex_mode=1)
    flags.set(1, hidden_sex_mode=2)
    h_state.set(0, hidden_sex_discovery_dregree=50)
    service.settle_hidden_value_by_action(0, True, 10, 1)
    degree = h_state.get(0, "hidden_sex_discovery_dregree")
    service.settle_discovered(0)
    service.update_exhibiionism_sex_mode()
    mode = flags.get(0, "exhibitionism_sex_mode")
print(service.get_hidden_level(70)[0], degree, seen, mode)
print(sorted(name for name in sys.modules if blocked(name)))
"""
""" 在拦截面板导入的子进程中运行隐奸结算服务各项函数的测试脚本。 """
REGISTERED = list(hidden_sex_service._on_discovered)
""" 模块加载后已登记在 hidden_sex_service._on_discovered 的回调快照。 """


def imported_modules(source: str | bytes, path: str) -> set[str]:
    """
    解析源码中的导入语句并返回模块名与成员名集合。
    Keyword arguments:
    source -- str | bytes，待解析的 Python 源码
    path -- str，文件的仓库相对路径，用于展开相对导入
    Return arguments:
    set[str] -- 导入的模块名与成员名集合
    """
    package = ".".join(PurePosixPath(path).parent.parts)
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = resolve_name("." * node.level + (node.module or ""), package)
            found.add(base)
            found.update(f"{base}.{alias.name}" for alias in node.names)
    return found


class HiddenSexCase(FastTestCase):
    """隐奸结算测试基类，初始化角色、工作集与被发现回调记录器。"""

    def setUp(self) -> None:
        """创建主角、对象与旁观者，打开工作集并将被发现回调替换为记录函数。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(PARTNER, "对象")
        self.world.chara(WITNESS, "旁人")
        aim(0, PARTNER)
        self.enterContext(working.based_on(core.state()))
        self.seen: list[tuple[int, bool]] = []
        self.enterContext(
            mock.patch.object(
                hidden_sex_service, "_on_discovered", [self.record]
            )
        )

    def record(self, discoverer_id: int, from_hidden_sex_flag: bool) -> None:
        """
        记录一次被发现通知回调收到的参数。
        Keyword arguments:
        discoverer_id -- int，发现者角色编号
        from_hidden_sex_flag -- bool，是否由隐奸被发现触发
        Return arguments:
        None -- 无返回值
        """
        self.seen.append((discoverer_id, from_hidden_sex_flag))

    def degree(self) -> int:
        """返回主角当前的隐奸被发现度（int）。"""
        return h_state.get(0, "hidden_sex_discovery_dregree")

    def start(self, value: int) -> None:
        """将主角的隐奸被发现度设为 value（int），无返回值。"""
        h_state.set(0, hidden_sex_discovery_dregree=value)


class HiddenLevelTest(FastTestCase):
    """验证隐蔽等级划分与被发现概率判定。"""

    def test_level_by_degree(self) -> None:
        """验证各阈值边界及超过 95 时的隐蔽等级编号与配置名称。"""
        cases = {0: 0, 30: 0, 31: 1, 60: 1, 61: 2, 80: 2, 81: 3, 95: 3}
        cases.update({96: 3, 100: 3})
        for value, level in cases.items():
            with self.subTest(value=value):
                self.assertEqual(
                    hidden_sex_service.get_hidden_level(value),
                    (level, game_config.config_hidden_level[level].name),
                )

    def test_low_levels_never_draw(self) -> None:
        """验证被发现度不高于 60 时不调用随机数且返回未发现。"""
        with mock.patch("random.randint", side_effect=AssertionError):
            for value in (0, 30, 31, 60):
                with self.subTest(value=value):
                    self.assertFalse(
                        hidden_sex_service.check_hidden_sex_discovery(value)
                    )

    def test_draw_against_rate(self) -> None:
        """验证被发现度高于 60 时按 (值-60)*3 与单次 0 至 100 随机数比较。"""
        cases = ((61, 3, True), (61, 4, False), (80, 60, True))
        cases += ((80, 61, False), (100, 100, True))
        for value, roll, found in cases:
            with (
                self.subTest(value=value, roll=roll),
                mock.patch("random.randint", return_value=roll) as draw,
            ):
                self.assertIs(
                    hidden_sex_service.check_hidden_sex_discovery(value), found
                )
                draw.assert_called_once_with(0, 100)


class SceneListTest(HiddenSexCase):
    """验证同场景隐奸对象与可打断旁观者的筛选逻辑。"""

    def test_targets_and_witnesses(self) -> None:
        """验证筛选结果排除自身、异地、无意识、睡眠与隐奸中的角色。"""
        for cid in (EXTRA, 4, 5):
            self.world.chara(cid, f"角色{cid}")
        self.world.chara(6, "别处", ELSEWHERE)
        flags.set(0, hidden_sex_mode=2)
        flags.set(PARTNER, hidden_sex_mode=2)
        flags.set(5, hidden_sex_mode=4)
        flags.set(6, hidden_sex_mode=2)
        flags.set(EXTRA, unconscious_h=1)
        behave(4, constant.Behavior.SLEEP)
        self.assertEqual(hidden_sex_service.get_hidden_sex_targets(0), [1, 5])
        self.assertEqual(
            hidden_sex_service.get_nearby_conscious_unfallen_characters(0),
            [WITNESS],
        )
        self.assertEqual(
            hidden_sex_service.get_hidden_sex_targets(PARTNER), [0, 5]
        )


class HiddenValueTest(HiddenSexCase):
    """验证按行为结算隐蔽值的各项系数与上下界裁剪。"""

    def settle(
        self,
        begin: int,
        add: bool | None = None,
        duration: int = 0,
        intensity: int = 0,
    ) -> int:
        """
        以指定初值运行隐蔽值结算并返回被发现度变化量。
        Keyword arguments:
        begin -- int，结算前写入的初始被发现度
        add -- bool | None，增减方向，None 时由当前行为判定
        duration -- int，持续时间，0 时取当前行为持续时间
        intensity -- int，行为强度，0 时按行为标签推导
        Return arguments:
        int -- 结算后主角被发现度的变化量
        """
        self.start(begin)
        hidden_sex_service.settle_hidden_value_by_action(
            0, add, duration, intensity
        )
        return self.degree() - begin

    def test_direction_from_behavior(self) -> None:
        """验证 add_flag 为 None 时按猥亵标签、等待、携带移动与日常行为判定增减。"""
        cases = (
            ("hand_in_hand", 10),
            (constant.Behavior.WAIT, -20),
            (constant.Behavior.CARRY_MOVE, 10),
            ("share_blankly", -20),
        )
        for behavior_id, delta in cases:
            with self.subTest(behavior_id=behavior_id):
                behave(0, behavior_id, duration=10)
                self.assertEqual(self.settle(50), delta)

    def test_intensity_from_tags(self) -> None:
        """验证未传强度时按道具、插入与侍奉标签分别采用强度 4、3、2。"""
        cases = (("put_condom", 20), ("normal_sex", 15), ("handjob", 10))
        for behavior_id, delta in cases:
            with self.subTest(behavior_id=behavior_id):
                behave(0, behavior_id, duration=5)
                self.assertEqual(self.settle(50), delta)

    def test_mode_adjust(self) -> None:
        """验证隐奸模式 1 至 4 对增减系数的倍率调整。"""
        cases = ((1, 20, -10), (2, 10, -20), (3, 10, -20), (4, 5, -40))
        for mode, up, down in cases:
            with self.subTest(mode=mode):
                flags.set(0, hidden_sex_mode=mode)
                self.assertEqual(self.settle(50, True, 10, 1), up)
                self.assertEqual(self.settle(50, False, 10), down)

    def test_ability_crowd_and_truncation(self) -> None:
        """验证 90 号能力修正、向零截断取整以及同场景人数倍率。"""
        chara_abilities.ability(0)[90] = 2
        self.assertEqual(self.settle(50, True, 10, 5), 40)
        self.assertEqual(self.settle(50, False, 10), -25)
        chara_abilities.ability(0)[90] = 1
        self.assertEqual(self.settle(50, False, 3), -6)
        chara_abilities.ability(0)[90] = 0
        for cid in (EXTRA, 4, 5):
            self.world.chara(cid, f"角色{cid}")
        self.assertEqual(self.settle(50, True, 10, 1), 40)

    def test_explicit_direction_and_clamp(self) -> None:
        """验证显式指定增减方向及结果裁剪在 0 到 100 区间。"""
        self.assertEqual(self.settle(50, True, 10, 2), 20)
        self.assertEqual(self.settle(50, False, 10), -20)
        self.assertEqual(self.settle(95, True, 10, 2), 5)
        self.assertEqual(self.settle(5, False, 10), -5)


class SettleDiscoveredTest(HiddenSexCase):
    """验证隐奸被发现结算的状态清零、目标设置与回调触发。"""

    def setUp(self) -> None:
        """将主角与对象置入隐奸模式 2 并将主角目标设为旁观者。"""
        super().setUp()
        flags.set(0, hidden_sex_mode=2)
        flags.set(PARTNER, hidden_sex_mode=2)
        aim(0, WITNESS)

    def test_clears_both_and_reports_witness(self) -> None:
        """验证被发现结算清零双方隐奸模式、切回对象并向回调报告旁观者。"""
        hidden_sex_service.settle_discovered(0)
        self.assertEqual(flags.get(0, "hidden_sex_mode"), 0)
        self.assertEqual(flags.get(PARTNER, "hidden_sex_mode"), 0)
        self.assertEqual(activity.target(0), PARTNER)
        self.assertEqual(self.seen, [(WITNESS, True)])

    def test_flag_false_when_player_not_hidden(self) -> None:
        """验证主角隐奸模式为 0 时回调收到的标志为 False。"""
        flags.set(0, hidden_sex_mode=0)
        hidden_sex_service.settle_discovered(0)
        self.assertEqual(self.seen, [(WITNESS, False)])

    def test_skips_witness_who_already_saw(self) -> None:
        """验证已设 see_pl_h 标记的旁观者被跳过并报告下一位旁观者。"""
        self.world.chara(EXTRA, "后来者")
        flags.set(WITNESS, see_pl_h=1)
        hidden_sex_service.settle_discovered(0)
        self.assertEqual(self.seen, [(EXTRA, True)])

    def test_no_witness_or_no_hook(self) -> None:
        """验证无可用旁观者或未登记回调时不调用回调但仍清零标记。"""
        flags.set(WITNESS, see_pl_h=1)
        hidden_sex_service.settle_discovered(0)
        self.assertEqual(self.seen, [])
        self.assertEqual(activity.target(0), PARTNER)
        flags.set(0, hidden_sex_mode=2)
        flags.set(PARTNER, hidden_sex_mode=2)
        flags.set(WITNESS, see_pl_h=0)
        with mock.patch.object(hidden_sex_service, "_on_discovered", []):
            hidden_sex_service.settle_discovered(0)
        self.assertEqual(flags.get(PARTNER, "hidden_sex_mode"), 0)
        self.assertEqual(self.seen, [])

    def test_no_partner_stops_after_clearing(self) -> None:
        """验证无隐奸对象时清零主角模式、输出调试信息、维持交互目标且不触发回调。"""
        flags.set(PARTNER, hidden_sex_mode=0)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            hidden_sex_service.settle_discovered(0)
        self.assertIn("角色id:0", out.getvalue())
        self.assertEqual(flags.get(0, "hidden_sex_mode"), 0)
        self.assertEqual(activity.target(0), WITNESS)
        self.assertEqual(self.seen, [])

    def test_tk_callback_opens_discovered_panel(self) -> None:
        """验证加载时登记的 Tk 回调按配置文本宽度构造并绘制被发现面板。"""
        with (
            mock.patch.object(hidden_sex_service, "_on_discovered", REGISTERED),
            mock.patch.object(
                sex_be_discovered_panel, "Sex_Be_Discovered_Panel"
            ) as panel,
        ):
            hidden_sex_service.settle_discovered(0)
        panel.assert_called_once_with(
            normal_config.config_normal.text_width,
            WITNESS,
            from_hidden_sex_flag=True,
        )
        panel.return_value.draw.assert_called_once_with()


class FlowTest(HiddenSexCase):
    """验证隐奸总流程与高潮暴露效果的串联行为。"""

    def setUp(self) -> None:
        """将主角与对象置入隐奸模式 2。"""
        super().setUp()
        flags.set(0, hidden_sex_mode=2)
        flags.set(PARTNER, hidden_sex_mode=2)

    def test_no_conscious_onlooker(self) -> None:
        """验证场内无清醒非隐奸旁观者时不改被发现度也不抽随机数。"""
        flags.set(WITNESS, unconscious_h=1)
        self.start(90)
        with mock.patch("random.randint", side_effect=AssertionError):
            hidden_sex_service.handle_hidden_sex_flow(0, True, 10, 1)
        self.assertEqual(self.degree(), 90)
        self.assertEqual(flags.get(0, "hidden_sex_mode"), 2)

    def test_settle_then_draw(self) -> None:
        """验证总流程先结算被发现度再按随机判定保持状态或触发被发现结算。"""
        self.start(70)
        with mock.patch("random.randint", return_value=100):
            hidden_sex_service.handle_hidden_sex_flow(0, True, 5, 1)
        self.assertEqual((self.degree(), self.seen), (75, []))
        self.assertEqual(flags.get(0, "hidden_sex_mode"), 2)
        with mock.patch("random.randint", return_value=0):
            hidden_sex_service.handle_hidden_sex_flow(0, True, 5, 1)
        self.assertEqual((self.degree(), self.seen), (80, [(WITNESS, True)]))
        self.assertEqual(flags.get(0, "hidden_sex_mode"), 0)

    def test_exposed_orgasm_effects(self) -> None:
        """验证四项高潮暴露效果按档位增加被发现度且非隐奸状态不生效。"""
        for effect, delta in EXPOSED_ORGASMS:
            with (
                self.subTest(effect=effect.__name__),
                mock.patch("random.randint", return_value=100),
            ):
                self.start(0)
                effect(0, game_type.CharacterStatusChange())
                self.assertEqual(self.degree(), delta)
        flags.set(0, hidden_sex_mode=0)
        self.start(0)
        EXPOSED_ORGASMS[0][0](0, game_type.CharacterStatusChange())
        self.assertEqual(self.degree(), 0)


class ExhibitionismTest(HiddenSexCase):
    """验证露出模式随场景人数、旁观者状态与室内外条件的更新。"""

    def modes(self) -> tuple[int, int]:
        """调用 update_exhibiionism_sex_mode 并返回主角与对象的露出模式元组。"""
        hidden_sex_service.update_exhibiionism_sex_mode()
        return (
            flags.get(0, "exhibitionism_sex_mode"),
            flags.get(PARTNER, "exhibitionism_sex_mode"),
        )

    def test_off_is_untouched(self) -> None:
        """验证主角露出模式为 0 时不改动主角与对象的模式。"""
        flags.set(PARTNER, exhibitionism_sex_mode=3)
        self.assertEqual(self.modes(), (0, 3))

    def test_mode_by_scene(self) -> None:
        """验证场景变化依次将主角与对象同步更新为露出模式 3、4、1、2。"""
        flags.set(0, exhibitionism_sex_mode=4)
        flags.set(PARTNER, exhibitionism_sex_mode=4)
        self.assertEqual(self.modes(), (3, 3))
        flags.set(WITNESS, unconscious_h=1)
        self.assertEqual(self.modes(), (4, 4))
        self.world.move(WITNESS, ELSEWHERE)
        self.assertEqual(self.modes(), (1, 1))
        self.world.move(0, OUTDOOR)
        self.world.move(PARTNER, OUTDOOR)
        self.assertEqual(self.modes(), (2, 2))


class BoundaryTest(FastTestCase):
    """验证隐奸结算服务与调用方的导入边界、函数归属与无面板运行能力。"""

    def test_service_passes_ui_guard(self) -> None:
        """验证隐奸结算服务通过后端界面边界守卫检查。"""
        source = (ROOT / SERVICE_PATH).read_bytes()
        self.assertEqual(banned_imports(source, SERVICE_PATH), [])

    def test_callers_use_service_not_panels(self) -> None:
        """验证两处后端调用方导入隐奸结算服务且不导入两处性行为面板。"""
        for path in CALLER_PATHS:
            with self.subTest(path=path):
                found = imported_modules((ROOT / path).read_bytes(), path)
                self.assertIn(hidden_sex_service.__name__, found)
                for panel in PANELS:
                    self.assertFalse(
                        {name for name in found if name.startswith(panel)}
                    )

    def test_checker_self_test(self) -> None:
        """验证导入检查函数能解析相对导入，并在一条语句导入多个名称时识别其中的违规导入。"""
        source = "from ..System.Sex_System import hidden_sex_panel\n"
        self.assertIn(PANELS[0], imported_modules(source, CALLER_PATHS[1]))
        source = "from Script import Core, UI\n"
        self.assertEqual(
            banned_imports(source, SERVICE_PATH), [(1, "Script.UI")]
        )

    def test_each_function_has_one_home(self) -> None:
        """验证八个结算函数位于隐奸结算服务且不存在于两处面板模块。"""
        for name in MOVED:
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(hidden_sex_service, name)))
                self.assertFalse(hasattr(hidden_sex_panel, name))
                self.assertFalse(hasattr(exhibitionism_sex_panel, name))

    def test_runs_with_panels_blocked(self) -> None:
        """验证拦截面板模块导入的子进程中隐奸结算服务可正常执行并产出预期结果。"""
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
            result.stdout.splitlines()[-2:], ["2 60 [(2, True)] 3", "[]"]
        )
