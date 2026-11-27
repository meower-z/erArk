"""
服装面板纯数据服务测试
======================
覆盖只读服装文本（内衣可见性、部位 8 换行、真空、全裸、精液详略、避孕套数量与等级、
H 中已脱下列表每行 8 件）、H 模式切换布局与面板渲染、脱衣选项及其按钮适配、
衣物穿脱切换、写缓冲外只读调用，以及无界面导入边界。
"""

import subprocess
import sys
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import text_handle
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, dirty, flags, modes
from Script.Modules.domains import player_ability, wardrobe
from Script.Modules.gameplay_resolution import cloth_panel_service as svc
from Script.Modules.gameplay_resolution import working
from Script.UI.Moudle import draw
from Script.UI.Panel import cloth_panel
from tests import kernel_data
from tests.chara_activity import aim
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
from Script.Modules.gameplay_resolution import cloth_panel_service as svc
print(len(svc.undress_option_labels()))
print(svc.LINE_BREAK == svc.SwitchLineBreak())
print(sorted(name for name in sys.modules if is_blocked(name)))
"""
""" 在拦截界面、窗口与 Tk 模块的子进程中导入并调用服装面板服务，并输出被加载的受限模块列表的脚本。 """


def _clothes(part: int, count: int = 1) -> list[int]:
    """返回指定部位按编号升序排列的前 count 件衣物 id。"""
    tem = game_config.config_clothing_tem
    return sorted(i for i in tem if tem[i].clothing_type == part)[:count]


def _name(cloth_id: int) -> str:
    """返回指定衣物 id 对应的配置名称。"""
    return game_config.config_clothing_tem[cloth_id].name


def _part(part: int) -> str:
    """返回指定服装部位编号对应的配置名称。"""
    return game_config.config_clothing_type[part].name


class ClothPanelServiceCase(FastTestCase):
    """服装面板服务测试基类，初始化博士（0）与干员 1、清空穿着与已脱衣物并重置观察及展示设置。"""

    def setUp(self) -> None:
        """
        创建博士与干员 1、开启写缓冲并设为交互目标，清空衣物与 cloth_see，关闭透视/调试/H/详细污浊，
        并选取四件示例衣物。
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "干员甲")
        self.enterContext(working.based_on(core.state()))
        self._orig_full_dirty = normal_config.system_setting.draw_setting[10]
        self.addCleanup(self._restore_draw_setting)
        normal_config.system_setting.draw_setting[10] = 0
        activity.set_target(0, 1)
        player_ability.set(0, visual=False)
        modes.set_debug(False)
        flags.set(0, is_h=0)
        flags.set(1, is_h=0)
        for part in wardrobe.of(1).cloth_wear:
            wardrobe.set_part(1, "cloth_wear", part, [])
        for part in wardrobe.of(1).cloth_off:
            wardrobe.set_part(1, "cloth_off", part, [])
        wardrobe.set(1, "cloth_see", {6: False, 9: False})
        [self.coat], [self.bra] = _clothes(5), _clothes(6)
        [self.skirt], [self.pan] = _clothes(8), _clothes(9)

    def _restore_draw_setting(self) -> None:
        """恢复系统设置中的详细污浊文本开关 draw_setting[10]。"""
        normal_config.system_setting.draw_setting[10] = self._orig_full_dirty

    def _wear(self, *cloth_ids: int) -> None:
        """将指定衣物按各自部位穿戴到角色 1 身上。"""
        for cloth_id in cloth_ids:
            part = game_config.config_clothing_tem[cloth_id].clothing_type
            wardrobe.append(1, "cloth_wear", part, cloth_id)

    def _semen(self, part: int, level: int) -> None:
        """设置角色 1 指定服装部位的精液污浊等级（等级为 0 时同步清空污浊量）。"""
        with dirty.editing(1) as d:
            d.cloth_semen[part][1] = 100 if level else 0
            d.cloth_semen[part][2] = level


class DisplayTextTest(ClothPanelServiceCase):
    """build_cloth_display_text 只读服装展示文本行为测试。"""

    def test_covered_underwear_hidden_until_xray_or_debug(self) -> None:
        """验证被外衣与下衣遮挡的胸衣和内裤默认隐藏，开启透视（visual 且具素质 307）或调试模式后显示。"""
        self._wear(self.coat, self.bra, self.skirt, self.pan)
        coat, bra = _name(self.coat), _name(self.bra)
        skirt, pan = _name(self.skirt), _name(self.pan)
        hidden = f"  [{_part(5)}]: {coat}\n  [{_part(8)}]: {skirt}\n"
        shown = (
            f"  [{_part(5)}]: {coat}  [{_part(6)}]: {bra}\n"
            f"  [{_part(8)}]: {skirt}  [{_part(9)}]: {pan}\n"
        )
        self.assertEqual(svc.build_cloth_display_text(), hidden)
        player_ability.set(0, visual=True)
        abilities.talent(0)[307] = 1
        self.assertEqual(svc.build_cloth_display_text(), shown)
        player_ability.set(0, visual=False)
        modes.set_debug(True)
        self.assertEqual(svc.build_cloth_display_text(), shown)

    def test_empty_lower_slot_always_breaks_line(self) -> None:
        """验证仅穿内裤而下衣部位（8）为空时，内裤行前仍会插入换行。"""
        self._wear(self.pan)
        expected = f"\n  [{_part(9)}]: {_name(self.pan)}\n"
        self.assertEqual(svc.build_cloth_display_text(), expected)

    def test_vacuum_follows_stored_cloth_see_or_debug(self) -> None:
        """验证真空提示遵循已保存的 cloth_see 状态，且调试模式下胸衣与内裤真空提示同时显示。"""
        self._wear(self.coat)
        wardrobe.set(1, "cloth_see", {6: True, 9: False})
        coat = f"  [{_part(5)}]: {_name(self.coat)}"
        vac6, vac9 = f"  [{_part(6)}]: 真空", f"  [{_part(9)}]: 真空"
        self.assertEqual(svc.build_cloth_display_text(), f"{coat}{vac6}\n")
        modes.set_debug(True)
        self.assertEqual(
            svc.build_cloth_display_text(), f"{coat}{vac6}\n{vac9}\n"
        )

    def test_naked_replaces_vacuum_lines(self) -> None:
        """验证未穿任何衣物时文本仅输出“  全裸”，不包含真空提示行。"""
        wardrobe.set(1, "cloth_see", {6: True, 9: True})
        self.assertEqual(svc.build_cloth_display_text(), "  全裸\n")

    def test_semen_compact_on_each_cloth_detailed_on_last(self) -> None:
        """验证简略模式在同部位每件衣物后附简短精液文本，详细模式仅在末件后附完整文本并换行。"""
        first, second = _clothes(5, 2)
        self._wear(first, second)
        self._semen(5, 2)
        ui = game_config.ui_text_data
        compact = f"<semen>({ui['dirty'][f'{_part(5)}精液污浊2']})</semen>"
        full = f"<semen>({ui['dirty_full'][f'{_part(5)}精液污浊2']})</semen>"
        head = f"  [{_part(5)}]: {_name(first)}"
        self.assertEqual(
            svc.build_cloth_display_text(),
            f"{head}{compact} {_name(second)}{compact}\n",
        )
        normal_config.system_setting.draw_setting[10] = 1
        self.assertEqual(
            svc.build_cloth_display_text(),
            f"{head} {_name(second)}{full}\n\n",
        )

    def test_condom_decoration_count_or_level(self) -> None:
        """验证简略模式显示避孕套数量（同部位有精液时先换行），详细模式显示对应等级描述。"""
        self._wear(self.coat)
        with dirty.editing(1) as d:
            d.condom_decoration[(1, 5)] = [10, 10, 10]
        head = f"  [{_part(5)}]: {_name(self.coat)}"
        count = "<semen>(挂着3个用过的避孕套)</semen>"
        level = game_config.ui_text_data["condom_dirty"][
            f"{_part(5)}避孕套装饰3"
        ]
        self.assertEqual(svc.build_cloth_display_text(), f"{head}{count}\n")
        self._semen(5, 1)
        semen = game_config.ui_text_data["dirty"][f"{_part(5)}精液污浊1"]
        self.assertEqual(
            svc.build_cloth_display_text(),
            f"{head}<semen>({semen})</semen>\n{count}\n",
        )
        self._semen(5, 0)
        normal_config.system_setting.draw_setting[10] = 1
        self.assertEqual(
            svc.build_cloth_display_text(),
            f"{head}<semen>({level})</semen>\n",
        )

    def test_off_clothes_listed_only_in_h_eight_per_line(self) -> None:
        """验证已脱下衣物列表仅在 H 状态下显示，且按每行 8 件折行。"""
        off = _clothes(10, 9)
        wardrobe.set_part(1, "cloth_off", 10, off)
        names = [f" {_name(cloth_id)}" for cloth_id in off]
        block = (
            "  [已脱下]:"
            + "".join(names[:8])
            + "\n           "
            + names[8]
            + "\n"
        )
        self.assertEqual(svc.build_cloth_display_text(), "  全裸\n")
        flags.set(1, is_h=1)
        self.assertEqual(svc.build_cloth_display_text(), "  全裸\n" + block)


class SwitchLayoutTest(ClothPanelServiceCase):
    """build_switch_cloth_layout 切换布局及面板渲染测试。"""

    def test_rows_hide_covered_underwear_and_carry_semen(self) -> None:
        """验证被遮挡胸衣不生成按钮，精液片段按简略每件或详细末件附着，且在下衣（部位 8）前换行。"""
        first, second = _clothes(5, 2)
        self._wear(first, second, self.bra, self.skirt)
        self._semen(5, 2)
        ui = game_config.ui_text_data
        compact = f"<semen>({ui['dirty'][f'{_part(5)}精液污浊2']})</semen>"
        full = f"<semen>({ui['dirty_full'][f'{_part(5)}精液污浊2']})</semen>"
        coat_label = svc.SwitchLabel(f"  [{_part(5)}]:")
        skirt_row = (
            svc.SwitchLabel(f"  [{_part(8)}]:"),
            svc.SwitchClothItem(self.skirt, 8, True),
            svc.LINE_BREAK,
        )
        self.assertEqual(
            svc.build_switch_cloth_layout(),
            (
                coat_label,
                svc.SwitchClothItem(first, 5, True),
                svc.SwitchMarkup(compact),
                svc.SwitchClothItem(second, 5, True),
                svc.SwitchMarkup(compact),
                svc.LINE_BREAK,
                *skirt_row,
            ),
        )
        normal_config.system_setting.draw_setting[10] = 1
        self.assertEqual(
            svc.build_switch_cloth_layout(),
            (
                coat_label,
                svc.SwitchClothItem(first, 5, True),
                svc.SwitchClothItem(second, 5, True),
                svc.SwitchMarkup(full),
                svc.LINE_BREAK,
                *skirt_row,
            ),
        )

    def test_naked_keeps_vacuum_and_lists_off_rows(self) -> None:
        """验证全裸布局保留两处真空提示并追加全裸行，且非 H 状态下也将 9 件已脱衣物分为 8+1 两行置于同一标题下。"""
        wardrobe.set(1, "cloth_see", {6: True, 9: True})
        off = _clothes(10, 9)
        wardrobe.set_part(1, "cloth_off", 10, off)
        items = [svc.SwitchClothItem(cloth_id, 10, False) for cloth_id in off]
        self.assertEqual(
            svc.build_switch_cloth_layout(),
            (
                svc.SwitchLabel(f"  [{_part(6)}]: 真空"),
                svc.LINE_BREAK,
                svc.SwitchLabel(f"  [{_part(9)}]: 真空"),
                svc.LINE_BREAK,
                svc.SwitchLabel("  全裸\n"),
                svc.SwitchLabel("  [已脱下]:"),
                *items[:8],
                svc.LINE_BREAK,
                items[8],
                svc.LINE_BREAK,
            ),
        )

    def test_panel_renders_layout_tokens(self) -> None:
        """验证 SwitchCharacterClothPanel 依据单次布局结果生成衣物按钮列表、返回值列表与绘制对象列表。"""
        self._wear(self.coat)
        wardrobe.set_part(1, "cloth_off", 8, [self.skirt])
        with mock.patch.object(
            svc,
            "build_switch_cloth_layout",
            wraps=svc.build_switch_cloth_layout,
        ) as build_fn:
            panel = cloth_panel.SwitchCharacterClothPanel(0, 90, 20, 0, False)
        build_fn.assert_called_once_with()
        self.assertEqual(
            [(b.cloth_id, b.is_wear) for b in panel.button_list],
            [(self.coat, True), (self.skirt, False)],
        )
        self.assertEqual(panel.return_list, [str(self.coat), str(self.skirt)])
        self.assertIsInstance(panel.draw_list[0], draw.LittleTitleLineDraw)
        self.assertIs(panel.draw_list[3], cloth_panel.line_feed)
        off_title = panel.draw_list[4]
        assert isinstance(off_title, draw.NormalDraw)
        self.assertEqual((off_title.text, off_title.width), ("  [已脱下]:", 90))


class UndressOptionTest(ClothPanelServiceCase):
    """脱衣选项构建与按钮适配测试。"""

    def test_options_list_affected_clothes_in_slot_order(self) -> None:
        """验证各脱衣选项按各自部位顺序（先下后上或配置顺序）列出受影响衣物及对应动作文案。"""
        self._wear(self.coat, self.bra, self.skirt, self.pan)
        coat, bra = _name(self.coat), _name(self.bra)
        skirt, pan = _name(self.skirt), _name(self.pan)
        labels = svc.undress_option_labels()
        expected = {
            0: f" ：会脱掉 {skirt} {coat}",
            1: f" ：会脱掉 {skirt} {pan} {coat} {bra}",
            2: f" ：会脱掉 {coat} {bra} {skirt} {pan}",
            3: f" ：会收走 {pan}",
        }
        for choice, suffix in expected.items():
            option = svc.build_undress_option(choice, labels[choice])
            prefix = f"{text_handle.id_index(choice)}{labels[choice]}"
            self.assertEqual(option, svc.UndressOption(prefix + suffix, True))

    def test_options_without_clothes_are_not_selectable(self) -> None:
        """验证没有受影响衣物的脱衣选项显示空提示文案且标记为不可选。"""
        self._wear(self.bra)
        labels = svc.undress_option_labels()
        empty = {0: " ：无可脱的衣服", 2: None, 3: " ：无可收的内裤"}
        for choice, suffix in empty.items():
            option = svc.build_undress_option(choice, labels[choice])
            self.assertEqual(option.selectable, suffix is None)
            if suffix is not None:
                self.assertTrue(option.text.endswith(suffix))

    def test_button_list_adapts_option(self) -> None:
        """
        验证 SeeUndressButtonList 将可选选项渲染为返回序号的按钮、空选项渲染为普通文本，并将标签存于 button_return。
        """
        self._wear(self.pan)
        labels = svc.undress_option_labels()
        take = cloth_panel.SeeUndressButtonList(labels[3], 70, True, True, 3)
        strip = cloth_panel.SeeUndressButtonList(labels[0], 70, True, True, 0)
        self.assertIsInstance(take.now_draw, draw.LeftButton)
        self.assertEqual(take.now_draw.return_text, "3")
        self.assertEqual(take.button_return, labels[3])
        self.assertTrue(take.draw_text.endswith(f" ：会收走 {_name(self.pan)}"))
        self.assertIsInstance(strip.now_draw, draw.LeftDraw)
        self.assertEqual(strip.now_draw.text, strip.draw_text)
        self.assertEqual(strip.now_draw.width, 70)


class ToggleTest(ClothPanelServiceCase):
    """toggle_target_cloth 衣物穿脱切换测试。"""

    def test_toggle_moves_between_wear_and_off(self) -> None:
        """验证同一衣物可在已穿列表与已脱下列表之间来回切换。"""
        self._wear(self.coat)
        svc.toggle_target_cloth(self.coat, 5, True)
        self.assertEqual(wardrobe.of(1).cloth_wear[5], ())
        self.assertEqual(wardrobe.of(1).cloth_off[5], (self.coat,))
        svc.toggle_target_cloth(self.coat, 5, False)
        self.assertEqual(wardrobe.of(1).cloth_wear[5], (self.coat,))
        self.assertEqual(wardrobe.of(1).cloth_off[5], ())

    def test_toggle_missing_cloth_changes_nothing(self) -> None:
        """验证目标衣物不在源列表时切换操作不改变角色衣柜状态。"""
        self._wear(self.coat)
        before = wardrobe.of(1)
        svc.toggle_target_cloth(self.coat, 5, False)
        svc.toggle_target_cloth(self.skirt, 8, True)
        self.assertEqual(wardrobe.of(1), before)


class ReadOnlyTest(FastTestCase):
    """写缓冲外只读构建行为测试。"""

    def test_builders_read_outside_write_buffer(self) -> None:
        """
        验证在无写缓冲环境下构建服装文本、切换布局与只读面板均不写入状态（遮挡胸衣保持隐藏、
        外衣生成按钮且衣柜不变）。
        """
        self.world.chara(0, "博士")
        self.world.chara(1, "干员甲")
        [coat], [bra] = _clothes(5), _clothes(6)
        kernel_data.put(wardrobe.set_part, 1, "cloth_wear", 5, [coat])
        kernel_data.put(wardrobe.set_part, 1, "cloth_wear", 6, [bra])
        kernel_data.put(wardrobe.set, 1, "cloth_see", {6: True, 9: True})
        kernel_data.put(flags.set, 0, is_h=1)
        aim(0, 1)
        before = wardrobe.of(1)
        text = svc.build_cloth_display_text()
        layout = svc.build_switch_cloth_layout()
        cloth_panel.SeeCharacterClothPanel(0, 100, 20, 0, False)
        self.assertNotIn(_name(bra), text)
        self.assertIn(svc.SwitchClothItem(coat, 5, True), layout)
        self.assertEqual(wardrobe.of(1), before)


class ImportBoundaryTest(FastTestCase):
    """服务模块的无界面导入边界测试。"""

    def test_fresh_subprocess_import_loads_no_ui(self) -> None:
        """验证在拦截界面、窗口与 Tk 模块的全新子进程中导入并调用服务可成功执行且不加载任何受限模块。"""
        result = subprocess.run(
            [sys.executable, "-c", BLOCKED_IMPORT_RUN],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertEqual(result.stdout.splitlines()[-3:], ["4", "True", "[]"])
