"""
身体污秽与状态计算服务测试
==========================
覆盖透视等级、服装遮挡与腔内可见性、详略污浊文本、差分文本编号、
头发避孕套装饰、体外无壳卵、腹部累计与附加状态、面板委托以及界面导入边界。
"""

import datetime
from fractions import Fraction
import subprocess
import sys
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import (
    abilities,
    activity,
    dirty,
    first_record,
    flags,
    h_state,
    needs,
    player_ability,
    player_collection,
    pregnancy,
    status,
    wardrobe,
)
from Script.Modules.gameplay_resolution import body_dirty_service as svc
from Script.Modules.gameplay_resolution import working
from Script.UI.Moudle import draw
from Script.UI.Panel import dirty_panel
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
from Script.Modules.gameplay_resolution import body_dirty_service as svc
print(svc.get_soft_egg_semen_level(0))
print(svc.get_soft_egg_semen_level(12000))
print(repr(svc.format_body_dirty_text((" a", " b"))))
print(sorted(name for name in sys.modules if is_blocked(name)))
"""
""" 在拦截界面与窗口模块的子进程中导入并调用身体污秽服务的脚本。 """


class BodyDirtyServiceCase(FastTestCase):
    """身体污秽计算服务测试基类，初始化博士与干员 1 并清空衣物。"""

    def setUp(self) -> None:
        """创建博士与干员 1、设置交互目标，并保存原始 draw_setting[10]。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "干员甲")
        self.enterContext(working.based_on(core.state()))
        self._orig_full_dirty = normal_config.system_setting.draw_setting[10]
        self.addCleanup(self._restore_draw_setting)
        normal_config.system_setting.draw_setting[10] = 0
        activity.set_position(0, ["0", "0", "0"])
        activity.set_position(1, ["0", "0", "0"])
        activity.set_target(0, 1)
        player_ability.set(0, visual=False)
        for cloth_part in wardrobe.of(1).cloth_wear:
            wardrobe.set_part(1, "cloth_wear", cloth_part, [])

    def _restore_draw_setting(self) -> None:
        """恢复系统设置中的详细污浊文本开关。"""
        normal_config.system_setting.draw_setting[10] = self._orig_full_dirty

    def _set_visual(self, level: int) -> None:
        """按 0/1/2/3 设置博士的透视开关与对应素质。"""
        player_ability.set(0, visual=level > 0)
        abilities.talent(0)[308] = 1 if level == 2 else 0
        abilities.talent(0)[309] = 1 if level >= 3 else 0


class VisualAndVisibilityTest(BodyDirtyServiceCase):
    """透视等级判定、暴露部位与腔内可见性规则测试。"""

    def test_get_visual_level_covers_all_four_modes(self) -> None:
        """验证无透视、服装透视、腔内透视与生理透视四档返回值。"""
        self._set_visual(0)
        self.assertEqual(svc.get_visual_level(0), 0)
        abilities.talent(0)[309] = 1
        self.assertEqual(svc.get_visual_level(0), 0)
        for expected in (1, 2, 3):
            self._set_visual(expected)
            self.assertEqual(svc.get_visual_level(0), expected)

    def test_exposed_parts_and_cavity_visibility(self) -> None:
        """验证衣物遮挡、特殊部位素质与腔内部位 7/9/15 的透视门槛。"""
        wardrobe.set_part(1, "cloth_wear", 0, [1])
        wardrobe.set_part(1, "cloth_wear", 9, [2])
        abilities.talent(1)[113] = 1
        abilities.talent(1)[112] = 0
        abilities.talent(1)[111] = 1
        exposed = svc.get_exposed_body_parts(1)
        self.assertNotIn(0, exposed)
        self.assertNotIn(6, exposed)
        self.assertIn(12, exposed)
        self.assertNotIn(13, exposed)
        self.assertIn(14, exposed)

        with dirty.editing(1) as d:
            d.body_semen[0][2] = 1
            d.body_semen[7][2] = 1
        self._set_visual(0)
        self.assertEqual(svc.build_body_dirty_report(1).part_lines, ())

        self._set_visual(1)
        report_v1 = svc.build_body_dirty_report(1)
        self.assertTrue(any("头发" in line for line in report_v1.part_lines))
        self.assertFalse(any("子宫" in line for line in report_v1.part_lines))

        self._set_visual(2)
        report_v2 = svc.build_body_dirty_report(1)
        self.assertTrue(any("子宫" in line for line in report_v2.part_lines))


class DirtyDiffTextCidTest(BodyDirtyServiceCase):
    """差分污浊文本编号在全部身体部位分组上的测试。"""

    def test_all_body_part_groups_and_fallback(self) -> None:
        """覆盖年龄、胸部、妊娠/受精/未孕、臀部、腿部、脚部与无差分部位。"""
        abilities.talent(1)[104] = 1
        abilities.talent(1)[121] = 1
        abilities.talent(1)[126] = 1
        abilities.talent(1)[129] = 1
        abilities.talent(1)[131] = 1
        for part_idx in (1, 2, 4, 5):
            part_name = game_config.config_body_part[part_idx].name
            self.assertEqual(
                svc.get_dirty_diff_text_cid(1, part_idx, 3),
                f"{part_name}少女精液污浊3",
            )
        self.assertEqual(
            svc.get_dirty_diff_text_cid(1, 3, 2), "胸部绝壁精液污浊2"
        )
        self.assertEqual(
            svc.get_dirty_diff_text_cid(1, 8, 4), "后穴小臀精液污浊4"
        )
        self.assertEqual(
            svc.get_dirty_diff_text_cid(1, 10, 5), "腿部细腿精液污浊5"
        )
        self.assertEqual(
            svc.get_dirty_diff_text_cid(1, 11, 6), "脚部小足精液污浊6"
        )

        abilities.talent(1)[20] = 0
        abilities.talent(1)[21] = 0
        self.assertEqual(
            svc.get_dirty_diff_text_cid(1, 6, 1), "小穴未孕精液污浊1"
        )
        self.assertEqual(
            svc.get_dirty_diff_text_cid(1, 7, 2), "子宫未孕精液污浊2"
        )

        abilities.talent(1)[20] = 1
        self.assertEqual(
            svc.get_dirty_diff_text_cid(1, 6, 1), "小穴受精精液污浊1"
        )
        abilities.talent(1)[21] = 1
        self.assertEqual(
            svc.get_dirty_diff_text_cid(1, 7, 2), "子宫妊娠精液污浊2"
        )

        for part_idx in (0, 9, 12, 15, 18):
            self.assertEqual(svc.get_dirty_diff_text_cid(1, part_idx, 1), "")


class BodyPartAndDetailTextTest(BodyDirtyServiceCase):
    """身体各部位污浊、附加状态、避孕套装饰与详略格式测试。"""

    def test_love_juice_virgin_blood_and_urine_thresholds(self) -> None:
        """验证爱液、当日破处血与尿液五档在详略两种模式下的输出。"""
        self._set_visual(2)
        status.set(1, 8, 1000)
        abilities.talent(1)[0] = 0
        with first_record.editing(1) as fr:
            fr.first_part_sex_dict[6] = {"time": game_time.now(), "partner": 0}

        urine_cases = (
            (20, "尿液0"),
            (100, "尿液1"),
            (180, "尿液2"),
            (300, "尿液3"),
            (360, "尿液4"),
        )
        for urine_val, expected_key in urine_cases:
            needs.set(1, urine=urine_val)
            compact = svc.build_body_dirty_report(1)
            self.assertIn(
                f" {game_config.ui_text_data['dirty'][expected_key]}",
                compact.part_lines,
            )
            self.assertIn(
                f" <{game_config.ui_text_data['dirty']['破处血1']}>",
                compact.part_lines,
            )
            self.assertTrue(
                any(
                    game_config.ui_text_data["dirty"][f"爱液{n}"] in line
                    for n in (1, 2, 3, 4)
                    for line in compact.part_lines
                )
            )

        normal_config.system_setting.draw_setting[10] = 1
        needs.set(1, urine=360)
        detailed = svc.build_body_dirty_report(1)
        self.assertTrue(
            any("[爱液]:<lavender>" in line for line in detailed.part_lines)
        )
        self.assertTrue(
            any("  [破处]:" in line for line in detailed.part_lines)
        )
        self.assertTrue(
            any("[尿液]:<khaki>" in line for line in detailed.part_lines)
        )

    def test_semen_diff_fallback_and_hair_condom_decoration(self) -> None:
        """验证精液差分优先与通用回退、以及头发避孕套装饰的换行与详略文案。"""
        abilities.talent(1)[104] = 1
        with dirty.editing(1) as d:
            d.body_semen[0][2] = 1
            d.body_semen[1][2] = 1
            d.condom_decoration[(0, 0)] = [15, 20]

        compact = svc.build_body_dirty_report(1)
        self.assertIn(
            f" 头发{game_config.ui_text_data['dirty']['头发精液污浊1']}",
            compact.part_lines,
        )
        self.assertIn("\n 头发上挂着2个用过的避孕套", compact.part_lines)

        normal_config.system_setting.draw_setting[10] = 1
        detailed = svc.build_body_dirty_report(1)
        diff_text = game_config.ui_text_data["dirty_full_diff"][
            "脸部少女精液污浊1"
        ]
        self.assertIn(
            f"  [脸部]:<semen>{diff_text}</semen>\n", detailed.part_lines
        )
        condom_text = game_config.ui_text_data["condom_dirty"][
            "头发避孕套装饰2"
        ]
        self.assertIn(
            f"  [头发]:<semen>{condom_text}</semen>\n", detailed.part_lines
        )

        abilities.talent(1)[104] = 0
        abilities.talent(1)[101] = 1
        fallback = svc.build_body_dirty_report(1)
        common_text = game_config.ui_text_data["dirty_full"]["脸部精液污浊1"]
        self.assertIn(
            f"  [脸部]:<semen>{common_text}</semen>\n", fallback.part_lines
        )

    def test_abdomen_enema_physiology_h_state_and_wrapping(self) -> None:
        """验证腹部累计、灌肠、乳汁与生理透视、插入体位、捆绑、道具、套池、香薰及每 6 项换行。"""
        wardrobe.set_part(1, "cloth_wear", 9, [2])
        with dirty.editing(1) as d:
            d.body_semen[6][1] = 600
            d.body_semen[15][1] = 200
            d.a_clean = 1
            d.enema_capacity = 1
        self._set_visual(3)
        needs.set(1, milk=Fraction(31, 3), desire=45)
        pregnancy.update(1, reproduction_period=5, fertilization_rate=30)
        h_state.set(1, insert_position=6, bondage=1)
        h_state.set(0, current_sex_position=1)
        with h_state.editing(1) as hs:
            hs.body_item[0][1] = 1
            hs.body_item[4][1] = 1
        flags.set(1, sex_toy_level=2, aromatherapy=1)
        player_collection.put("used_condoms", [12, 30])

        report = svc.build_body_dirty_report(1)
        joined = report.rendered_text
        self.assertIn(
            game_config.ui_text_data["dirty"]["腹部整体精液污浊2"], joined
        )
        self.assertIn(f"<{game_config.ui_text_data['dirty']['灌肠1']}>", joined)
        self.assertIn(
            f"<{game_config.ui_text_data['dirty']['灌肠液量1']}>", joined
        )
        self.assertIn(" 乳汁量为10ml", joined)
        self.assertIn("受精概率30%", joined)
        self.assertIn("欲望值45%", joined)
        self.assertIn(
            f"以{game_config.ui_text_data['h_state']['体位1']}"
            f"{game_config.ui_text_data['h_state']['阴茎位置6']}",
            joined,
        )
        self.assertIn(
            f" 被绳子捆成了{game_config.config_bondage[1].name}", joined
        )
        self.assertIn(f" {game_config.config_body_item[0].name}(中)", joined)
        self.assertIn(f" {game_config.config_body_item[4].name}", joined)
        self.assertIn(" 现留有2个用过的避孕套（12ml、30ml）", joined)
        self.assertIn(
            f" <{game_config.config_aromatherapy_recipes[1].name}>", joined
        )
        self.assertTrue(joined.endswith("\n"))

        normal_config.system_setting.draw_setting[10] = 1
        full_report = svc.build_body_dirty_report(1)
        self.assertTrue(
            any("[腹部]:<semen>" in line for line in full_report.part_lines)
        )
        self.assertTrue(
            any("[肠道]:<semen>" in line for line in full_report.part_lines)
        )
        self.assertTrue(
            any("[灌肠]:<semen>" in line for line in full_report.part_lines)
        )

        wrapped = svc.format_body_dirty_text(tuple(f" p{i}" for i in range(8)))
        self.assertEqual(wrapped, " p0 p1 p2 p3 p4 p5 p6\n p7\n")
        self.assertEqual(svc.format_body_dirty_text(()), "")


class SoftEggDirtyLinesTest(BodyDirtyServiceCase):
    """体外无壳卵精液等级换算与同场景筛选输出测试。"""

    def test_soft_egg_semen_level_and_scene_filtering(self) -> None:
        """覆盖精液等级 0/中段/上限、同场景筛选、未知母亲回退与详略模式。"""
        self.assertEqual(svc.get_soft_egg_semen_level(0), 0)
        self.assertEqual(svc.get_soft_egg_semen_level(-5), 0)
        self.assertEqual(svc.get_soft_egg_semen_level(500), 3)
        self.assertEqual(svc.get_soft_egg_semen_level(5000), 10)
        self.assertEqual(svc.get_soft_egg_semen_level(7000), 12)
        self.assertEqual(svc.get_soft_egg_semen_level(20000), 15)

        now = datetime.datetime(1097, 1, 1, 12, 0)
        player_collection.add_soft_egg(1, now, ["0", "0", "0"], 500)
        player_collection.add_soft_egg(999, now, ["0", "0", "0"], 0)
        player_collection.add_soft_egg(1, now, ["9", "9", "9"], 800)

        compact = svc.build_body_dirty_report(1)
        self.assertEqual(len(compact.part_lines), 2)
        self.assertIn("干员甲排出的卵块", compact.part_lines[0])
        self.assertIn("500", compact.part_lines[0])
        self.assertIn("某人排出的卵块", compact.part_lines[1])

        normal_config.system_setting.draw_setting[10] = 1
        detailed = svc.build_body_dirty_report(1)
        self.assertIn(
            f"  [卵块]:<semen>干员甲排出的卵块(500ml精液)："
            f"{game_config.ui_text_data['soft_egg_dirty_full']['体外卵精液污浊3']}</semen>\n",
            detailed.part_lines,
        )
        self.assertIn(
            f"  [卵块]:<semen>某人排出的卵块(0ml精液)："
            f"{game_config.ui_text_data['soft_egg_dirty_full']['体外卵精液污浊0']}</semen>\n",
            detailed.part_lines,
        )


class DirtyPanelDelegationTest(BodyDirtyServiceCase):
    """身体污秽面板向服务委托与绘制行为契约测试。"""

    def test_panel_attributes_delegation_and_draw(self) -> None:
        """验证空/非空报告下标题行、实例属性、差分接口与 draw 渲染兼容。"""
        empty_panel = dirty_panel.SeeCharacterBodyPanel(1, 80, 9, 0, False)
        self.assertEqual(empty_panel.character_id, 1)
        self.assertEqual(empty_panel.width, 80)
        self.assertEqual(empty_panel.column, 9)
        self.assertEqual(empty_panel.type_number, 0)
        self.assertFalse(empty_panel.center_status)
        self.assertEqual(empty_panel.return_list, [])
        self.assertEqual(empty_panel.draw_list, [])

        abilities.talent(1)[104] = 1
        self.assertEqual(
            empty_panel.get_dirty_diff_text_cid(1, 2), "脸部少女精液污浊2"
        )

        with dirty.editing(1) as d:
            d.body_semen[1][2] = 1
        with mock.patch.object(
            svc,
            "build_body_dirty_report",
            wraps=svc.build_body_dirty_report,
        ) as build_fn:
            panel = dirty_panel.SeeCharacterBodyPanel(1, 80, 9, 0)

        build_fn.assert_called_once_with(1)
        self.assertIsInstance(panel.draw_list[0], draw.LittleTitleLineDraw)
        self.assertGreater(len(panel.draw_list), 1)

        drawn: list[str] = []
        with (
            mock.patch.object(
                draw.LittleTitleLineDraw,
                "draw",
                lambda inst: drawn.append(f"TITLE:{inst.title}"),
            ),
            mock.patch.object(
                draw.NormalDraw,
                "draw",
                lambda inst: drawn.append(inst.text),
            ),
        ):
            panel.draw()
        self.assertTrue(drawn and drawn[0].startswith("TITLE:"))
        self.assertIn("脸部", "".join(drawn[1:]))


class ImportBoundaryTest(FastTestCase):
    """身体污秽计算服务模块的界面导入边界测试。"""

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
            result.stdout.splitlines()[-4:],
            ["0", "15", "' a b\\n'", "[]"],
        )
