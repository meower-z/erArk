"""
素质升级资格查询服务测试
========================
覆盖共通前提判定、陷落等级与路线可见性、多类型获取需求解析、
动作模式分支、面板委托绘制以及后端界面导入边界。
"""

import subprocess
import sys
from unittest import mock

from Script.Config import config_def, game_config
from Script.Kernel import core
from Script.Modules.domains import abilities, relations
from Script.Modules.gameplay_resolution import talent_up_service as svc
from Script.Modules.gameplay_resolution import working
from Script.UI.Moudle import draw
from Script.UI.Panel import talent_up_panel
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

BLOCKED_IMPORT_RUN = """
import importlib.abc, sys
BLOCKED = ("Script.UI", "Script.Core.flow_handle", "Script.Core.image_cache",
    "Script.Core.io_init", "Script.Core.key_listion_event",
    "Script.Core.main_frame", "Script.Core.py_cmd", "Script.Frontend",
    "Script.Modules.tk_ui", "tkinter", "_tkinter", "PIL.ImageTk")
def is_blocked(name):
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if is_blocked(fullname):
            raise ImportError(fullname)
sys.meta_path.insert(0, Blocker())
from Script.Modules.gameplay_resolution import talent_up_service as svc
print(svc.next_route_talent_id("love", 0))
print(svc.resolve_action_mode(203, False))
print(sorted(name for name in sys.modules if is_blocked(name)))
"""
""" 在拦截界面与窗口模块的子进程中导入并调用素质升级服务的脚本。 """


class TalentUpServiceCase(FastTestCase):
    """素质升级服务测试基类，初始化玩家与干员 1 并打开工作集。"""

    def setUp(self) -> None:
        """重置测试世界，创建玩家与干员 1 并进入工作集上下文。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "干员甲")
        self.enterContext(working.based_on(core.state()))
        relations.favorability.set(1, {0: 0})
        relations.trust.set(1, 0)

    def _set_common_ready(self, cid: int = 1) -> None:
        """将指定角色的共通前提设为全部满足。"""
        relations.favorability.set(cid, {0: 500})
        relations.trust.set(cid, 50)
        abilities.ability(cid)[18] = 0

    def _set_love_ready(self, cid: int = 1) -> None:
        """将指定角色的爱情路线前提设为全部满足。"""
        abilities.ability(cid)[15] = 0
        abilities.ability(cid)[17] = 0
        abilities.ability(cid)[32] = 2

    def _set_obey_ready(self, cid: int = 1) -> None:
        """将指定角色的隶属路线前提设为全部满足。"""
        abilities.ability(cid)[13] = 1
        abilities.ability(cid)[14] = 1
        abilities.ability(cid)[31] = 2


class CommonPrerequisitesTest(TalentUpServiceCase):
    """陷落系素质共通基础前提的判定测试。"""

    def test_common_prerequisites_pass_and_individual_failures(self) -> None:
        """验证好感度、信任度与反发刻印三项共通前提的通过与单项失败。"""
        self._set_common_ready(1)
        self.assertEqual(
            svc.evaluate_common_prerequisites(1),
            (
                svc.PrerequisiteCheck("favorability", 500, 500, True),
                svc.PrerequisiteCheck("trust", 50, 50, True),
                svc.PrerequisiteCheck("hate_mark", 0, 0, True),
            ),
        )
        relations.favorability.set(1, {0: 499})
        self.assertEqual(
            [c.met for c in svc.evaluate_common_prerequisites(1)],
            [False, True, True],
        )
        self._set_common_ready(1)
        relations.trust.set(1, 49)
        self.assertEqual(
            [c.met for c in svc.evaluate_common_prerequisites(1)],
            [True, False, True],
        )
        self._set_common_ready(1)
        abilities.ability(1)[18] = 1
        self.assertEqual(
            [c.met for c in svc.evaluate_common_prerequisites(1)],
            [True, True, False],
        )


class FallLevelAndRoutesTest(TalentUpServiceCase):
    """陷落等级、路线可见性、路线前提与下一级素质编号的测试。"""

    def test_get_fall_level_player_unfallen_love_and_obey(self) -> None:
        """覆盖玩家恒为 0、未陷落、爱情 1-4、隶属 1-4 及混合优先级。"""
        abilities.talent(0)[201] = 1
        self.assertEqual((svc.get_fall_level(0), svc.get_fall_level(1)), (0, 0))
        for level, tid in ((1, 201), (2, 202), (3, 203), (4, 204)):
            abilities.talent(1)[tid] = 1
            self.assertEqual(svc.get_fall_level(1), level)
            abilities.talent(1)[tid] = 0
        for level, tid in ((1, 211), (2, 212), (3, 213), (4, 214)):
            abilities.talent(1)[tid] = 1
            self.assertEqual(svc.get_fall_level(1), -level)
            abilities.talent(1)[tid] = 0
        abilities.talent(1)[201] = 1
        abilities.talent(1)[212] = 1
        self.assertEqual(svc.get_fall_level(1), -1)

    def test_next_route_talent_id_and_invalid_route(self) -> None:
        """验证两条路线各阶段对应的下一级素质编号与非法路线报错。"""
        self.assertEqual(
            [svc.next_route_talent_id("love", lv) for lv in range(5)],
            [201, 202, 203, 204, None],
        )
        self.assertEqual(
            [svc.next_route_talent_id("obey", lv) for lv in range(5)],
            [211, 212, 213, 214, None],
        )
        with self.assertRaises(ValueError):
            svc.next_route_talent_id("other", 0)
        with self.assertRaises(ValueError):
            svc.evaluate_route_prerequisites(1, "other")

    def test_route_prerequisites_and_visibility(self) -> None:
        """验证未陷落双路线展示、单项路线前提失败、共通前提传导与满级状态。"""
        self._set_common_ready(1)
        self._set_love_ready(1)
        self._set_obey_ready(1)
        overview = svc.build_talent_upgrade_overview(1)
        self.assertTrue(overview.common_ok)
        self.assertEqual((overview.love_level, overview.obey_level), (0, 0))
        assert overview.love_route is not None
        assert overview.obey_route is not None
        self.assertTrue(
            overview.love_route.route_ok and overview.obey_route.route_ok
        )
        self.assertEqual(
            (
                overview.love_route.next_talent_id,
                overview.obey_route.next_talent_id,
            ),
            (201, 211),
        )

        for aid, bad_val, expected in (
            (15, 1, [False, True, True]),
            (17, 1, [True, False, True]),
            (32, 1, [True, True, False]),
        ):
            self._set_love_ready(1)
            abilities.ability(1)[aid] = bad_val
            self.assertEqual(
                [c.met for c in svc.evaluate_route_prerequisites(1, "love")],
                expected,
            )
        self._set_love_ready(1)

        for aid, bad_val, expected in (
            (13, 0, [False, True, True]),
            (14, 0, [True, False, True]),
            (31, 1, [True, True, False]),
        ):
            self._set_obey_ready(1)
            abilities.ability(1)[aid] = bad_val
            self.assertEqual(
                [c.met for c in svc.evaluate_route_prerequisites(1, "obey")],
                expected,
            )
        self._set_obey_ready(1)

        relations.trust.set(1, 10)
        blocked = svc.build_talent_upgrade_overview(1)
        assert blocked.love_route is not None and blocked.obey_route is not None
        self.assertFalse(
            blocked.common_ok
            or blocked.love_route.route_ok
            or blocked.obey_route.route_ok
        )
        assert blocked.love_route.next_gain is not None
        self.assertEqual(
            blocked.love_route.next_gain.action_mode, "route_blocked"
        )

        self._set_common_ready(1)
        abilities.talent(1)[202] = 1
        love_mid = svc.build_talent_upgrade_overview(1)
        self.assertEqual((love_mid.love_level, love_mid.obey_level), (2, 0))
        self.assertIsNone(love_mid.obey_route)
        assert love_mid.love_route is not None
        assert love_mid.love_route.next_gain is not None
        self.assertEqual(love_mid.love_route.next_talent_id, 203)
        self.assertEqual(
            love_mid.love_route.next_gain.action_mode, "ring_confession"
        )

        abilities.talent(1)[202] = 0
        abilities.talent(1)[204] = 1
        love_max = svc.build_talent_upgrade_overview(1)
        assert love_max.love_route is not None
        self.assertTrue(love_max.love_route.is_max_level)
        self.assertIsNone(love_max.love_route.next_talent_id)
        self.assertIsNone(love_max.obey_route)

        abilities.talent(1)[204] = 0
        abilities.talent(1)[214] = 1
        obey_max = svc.build_talent_upgrade_overview(1)
        self.assertIsNone(obey_max.love_route)
        assert obey_max.obey_route is not None
        self.assertTrue(obey_max.obey_route.is_max_level)
        self.assertIsNone(obey_max.obey_route.next_gain)


class TalentGainEvaluationTest(TalentUpServiceCase):
    """素质获取条件解析与动作模式评估的测试。"""

    def test_evaluate_all_requirement_types(self) -> None:
        """覆盖 A/T/J/E/F/X 全部六类需求解析及未满足与全满足状态。"""
        fake_entry = config_def.TalentGain()
        fake_entry.cid = 999
        fake_entry.talent_id = 999
        fake_entry.second_behavior_id = ""
        fake_entry.gain_type = 3
        fake_entry.gain_need = "A32|3&T|201&J5|100&E10|20&F|600&X|80"
        fake_entry.replace_talent_id = 0
        with mock.patch.dict(
            game_config.config_talent_gain_data, {999: fake_entry}
        ):
            unmet = svc.evaluate_talent_gain(1, 999, route_ok=True)
            self.assertFalse(unmet.all_met)
            self.assertEqual(unmet.action_mode, "upgrade_blocked")
            self.assertEqual(
                [r.kind for r in unmet.requirements],
                ["A", "T", "J", "E", "F", "X"],
            )
            self.assertEqual([r.met for r in unmet.requirements], [False] * 6)

            abilities.ability(1)[32] = 3
            abilities.talent(1)[201] = 1
            abilities.juel(1)[5] = 100
            abilities.experience(1)[10] = 20
            relations.favorability.set(1, {0: 600})
            relations.trust.set(1, 80)
            met = svc.evaluate_talent_gain(1, 999, route_ok=True)
            self.assertTrue(met.all_met)
            self.assertEqual(met.action_mode, "upgrade_confirm")
            self.assertEqual(
                met.requirements,
                (
                    svc.TalentRequirementCheck("A", 32, 3, 3, True),
                    svc.TalentRequirementCheck("T", 201, 1, 1, True),
                    svc.TalentRequirementCheck("J", 5, 100, 100, True),
                    svc.TalentRequirementCheck("E", 10, 20, 20, True),
                    svc.TalentRequirementCheck("F", 0, 600, 600, True),
                    svc.TalentRequirementCheck("X", 0, 80, 80, True),
                ),
            )

    def test_action_modes_for_route_special_and_upgrade_talents(self) -> None:
        """覆盖路线选择 201/211、戒指告白 203、项圈 213 与普通升级 202/212 的动作模式。"""
        abilities.ability(1)[32] = 4
        abilities.talent(1)[201] = 1
        relations.trust.set(1, 100)
        self.assertEqual(
            svc.evaluate_talent_gain(1, 201, route_ok=True).action_mode,
            "route_confirm",
        )
        self.assertEqual(
            svc.evaluate_talent_gain(1, 201, route_ok=False).action_mode,
            "route_blocked",
        )
        self.assertEqual(
            svc.evaluate_talent_gain(1, 202, route_ok=True).action_mode,
            "upgrade_confirm",
        )
        self.assertEqual(
            svc.evaluate_talent_gain(1, 202, route_ok=False).action_mode,
            "upgrade_blocked",
        )
        self.assertEqual(
            svc.evaluate_talent_gain(1, 203, route_ok=False).action_mode,
            "ring_confession",
        )
        self.assertEqual(
            svc.evaluate_talent_gain(1, 213, route_ok=True).action_mode,
            "collar_equip",
        )


class TalentUpPanelDelegationTest(TalentUpServiceCase):
    """素质升级面板向服务委托查询并保持渲染与按钮契约一致的测试。"""

    def test_draw_delegates_to_service_and_renders_routes_and_buttons(
        self,
    ) -> None:
        """验证面板 draw 委托总览服务，按满足状态输出文案、样式与确认按钮。"""
        self._set_common_ready(1)
        self._set_love_ready(1)
        panel = talent_up_panel.Character_talent_show_Text(1, 80)
        drawn: list[tuple[str, str]] = []
        buttons: list[tuple[str, str, int]] = []
        with (
            mock.patch.object(
                svc,
                "build_talent_upgrade_overview",
                wraps=svc.build_talent_upgrade_overview,
            ) as build_ov,
            mock.patch.object(
                draw.NormalDraw,
                "draw",
                lambda inst: drawn.append((inst.text, inst.style)),
            ),
            mock.patch.object(draw.LittleTitleLineDraw, "draw"),
            mock.patch.object(draw.LineDraw, "draw"),
            mock.patch.object(
                draw.CenterButton,
                "draw",
                lambda inst: buttons.append(
                    (inst.text, inst.return_text, inst.args)
                ),
            ),
        ):
            panel.draw()

        build_ov.assert_called_once_with(1)
        self.assertEqual(panel.return_list, ["确定_201"])
        self.assertEqual(buttons, [("[确定]", "确定_201", 201)])
        self.assertIn((" 好感度500以上(√)", "green"), drawn)
        self.assertIn((" 快乐刻印>=1(X)", "warning"), drawn)
        self.assertIn(("不满足条件，无法选择\n", "standard"), drawn)

        abilities.talent(1)[204] = 1
        drawn.clear()
        with (
            mock.patch.object(
                draw.NormalDraw,
                "draw",
                lambda inst: drawn.append((inst.text, inst.style)),
            ),
            mock.patch.object(draw.LittleTitleLineDraw, "draw"),
            mock.patch.object(draw.LineDraw, "draw"),
            mock.patch.object(draw.CenterButton, "draw"),
        ):
            panel.draw()
        self.assertEqual(panel.return_list, [])
        self.assertIn(("已达到最高级-爱侣\n", "standard"), drawn)

    def test_show_gain_need_delegates_special_and_upgrade_modes(self) -> None:
        """验证 show_gain_need 委托条件评估服务并正确输出特殊提示与手动升级按钮。"""
        abilities.ability(1)[32] = 4
        abilities.talent(1)[201] = 1
        relations.trust.set(1, 100)
        panel = talent_up_panel.Character_talent_show_Text(1, 80)
        texts: list[str] = []
        with (
            mock.patch.object(
                svc, "evaluate_talent_gain", wraps=svc.evaluate_talent_gain
            ) as eval_fn,
            mock.patch.object(
                draw.NormalDraw, "draw", lambda inst: texts.append(inst.text)
            ),
            mock.patch.object(draw.CenterButton, "draw"),
        ):
            panel.show_gain_need(203, 1)
            panel.show_gain_need(213, 0)
            panel.show_gain_need(202, 1)
            panel.show_gain_need(202, 0)

        self.assertEqual(
            eval_fn.call_args_list,
            [
                mock.call(1, 203, route_ok=True),
                mock.call(1, 213, route_ok=False),
                mock.call(1, 202, route_ok=True),
                mock.call(1, 202, route_ok=False),
            ],
        )
        self.assertIn(
            "满足条件后需要准备【戒指】，然后进行【告白】，成功后即可获得\n",
            texts,
        )
        self.assertIn(
            "满足条件后需要准备【项圈】，然后进行【戴上项圈】，成功后即可获得\n",
            texts,
        )
        self.assertIn(
            "\n满足条件，确定要现在获得该素质吗（也可以在过夜时自动获得）\n",
            texts,
        )
        self.assertEqual(panel.return_list, ["确定_202"])


class ImportBoundaryTest(FastTestCase):
    """素质升级资格查询服务模块的界面导入边界测试。"""

    def test_fresh_subprocess_import_loads_no_ui(self) -> None:
        """独立子进程拦截界面与窗口模块时可导入并执行服务，且未加载被拦截模块。"""
        result = subprocess.run(
            [sys.executable, "-c", BLOCKED_IMPORT_RUN],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertEqual(
            result.stdout.splitlines()[-3:],
            ["201", "ring_confession", "[]"],
        )
