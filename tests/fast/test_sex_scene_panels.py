"""
群交、隐奸与露出面板交互测试
============================
SexSystemUiFreeTest 在无界面子进程中验证 Script.System.Sex_System 各模块无需界面即可导入。
GroupSexTemplatePanelTest 依托 PanelCase 验证 group_sex_panel 模板编辑面板的开关、返回清理与重置按钮。
HiddenSexModePanelTest 验证 hidden_sex_panel 模式选择面板的选项过滤、发起行为与邀请失败状态。
ExhibitionismSexModePanelTest 验证 exhibitionism_sex_panel 模式选择面板的发起行为与邀请失败状态。
"""

from collections.abc import Callable, Mapping
from pathlib import Path
from unittest import mock

from Script.Core import constant
from Script.Design import instuct_judege
from Script.Modules.domains import flags, h_state, modes
from Script.Modules.gameplay_resolution import (
    group_sex_editor_service as editor,
)
from Script.Modules.tk_ui import player_pick
from Script.UI.Panel import (
    exhibitionism_sex_panel,
    group_sex_panel,
    hidden_sex_panel,
)
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.fast.test_bondage_and_discovered_panels import (
    PARTNER,
    WIDTH,
    PanelCase,
)
from tests.ui_free_subprocess import ChildRun, run_ui_free

PACKAGE = "Script.System.Sex_System"
""" 待测 Sex_System 目录对应的点分包名。 """
MODULES = tuple(
    sorted(
        path.stem
        for path in Path(__file__)
        .resolve()
        .parents[2]
        .joinpath(*PACKAGE.split("."))
        .glob("*.py")
    )
)
""" 直接位于 PACKAGE 对应目录的已排序 .py 模块名元组。 """
LOAD_ALL = """
import importlib
for name in MODULES:
    module = PACKAGE if name == "__init__" else PACKAGE + "." + name
    try:
        importlib.import_module(module)
    except ImportError as error:
        payload[name] = repr(error)
    else:
        payload[name] = None
"""
""" 子进程脚本，导入 MODULES 各模块（__init__ 导入 PACKAGE），在 payload 中记 None 或 ImportError 文本。 """
FILLED = constant.Behavior.GROUP_SEX_END
""" 群交模板部位槽位测试所用的已有行为编号 constant.Behavior.GROUP_SEX_END。 """
JUDGE_FAILS = [0, 0, 0.0]
""" 替换 instuct_judege.calculation_instuct_judege 时表示邀请判定失败的返回值。 """


def template_a() -> dict[str, list[object]]:
    """
    返回玩家角色 0 的群交模板 A 中各部位槽位字典。
    Return arguments:
    dict[str, list[object]] -- 部位名到 [目标角色编号, 行为编号] 列表的映射，-1 表示未选
    """
    return h_state.view(0).group_sex_body_template_dict["A"][0]


class SexSystemUiFreeTest(FastTestCase):
    """Script/System/Sex_System 各模块的无界面子进程导入测试。"""

    child: ChildRun
    """ setUpClass 运行无界面子进程后保存的 ChildRun 结果。 """

    @classmethod
    def setUpClass(cls) -> None:
        """以 boot=True 调用 run_ui_free 运行 LOAD_ALL 导入 MODULES 各模块，并将结果存入 cls.child。"""
        cls.child = run_ui_free(
            f"PACKAGE = {PACKAGE!r}\nMODULES = {MODULES!r}\n{LOAD_ALL}",
            boot=True,
        )

    def test_modules_load_without_ui(self) -> None:
        """
        断言 MODULES 包含 __init__、drunk_sex_common 与 h_mode_common。
        断言 child.payload 中各模块均为 None，且子进程未尝试导入也未加载受拦截模块。
        """
        self.assertTrue(
            {"__init__", "drunk_sex_common", "h_mode_common"} <= set(MODULES)
        )
        self.assertEqual(self.child.payload, dict.fromkeys(MODULES))
        self.assertEqual(self.child.attempted, [])
        self.assertEqual(self.child.loaded, [])


class GroupSexTemplatePanelTest(PanelCase):
    """群交模板编辑面板（Edit_Group_Sex_Temple_Panel）的开关、返回清理与重置按钮测试。"""

    def show(self, *answers: str) -> None:
        """
        以 WIDTH 构造 Edit_Group_Sex_Temple_Panel，并经 run_panel 按预设应答驱动其 draw 方法。
        Keyword arguments:
        answers -- tuple[str, ...]，按顺序传给面板的预设按钮返回值
        Return arguments:
        None -- 无返回值
        """
        self.run_panel(
            group_sex_panel.Edit_Group_Sex_Temple_Panel(WIDTH).draw, *answers
        )

    def test_toggles_change_player_settings(self) -> None:
        """
        先断言角色 0 的 group_sex_lock_flag、npc_ai_type_in_group_sex、all_group_sex_temple_run 为 (False, 0, False)。
        点选「锁定群交模板」「调整干员行动」「轮流用副模板」「返回」后，断言这三项变为 (True, 1, True)。
        同时断言第 3 页可选返回值不含「切换」，第 4 页可选返回值包含「切换」。
        """
        fields = (
            "group_sex_lock_flag",
            "npc_ai_type_in_group_sex",
            "all_group_sex_temple_run",
        )
        before = tuple(h_state.get(0, name) for name in fields)
        self.assertEqual(before, (False, 0, False))
        self.show("锁定群交模板", "调整干员行动", "轮流用副模板", "返回")
        after = tuple(h_state.get(0, name) for name in fields)
        self.assertEqual(after, (True, 1, True))
        self.assertNotIn("切换", self.clicks.offers[2])
        self.assertIn("切换", self.clicks.offers[3])

    def test_back_clears_half_filled_slots(self) -> None:
        """
        将模板 A 的 mouth 槽位仅设目标为 PARTNER（断言为 [PARTNER, -1]），将 anal 槽位设为 [PARTNER, FILLED]。
        打开面板并应答「返回」后，断言 mouth 槽位清空为 [-1, -1]，且 anal 槽位保持 [PARTNER, FILLED]。
        """
        kernel_data.put(editor.set_target_chara, "A", "mouth", PARTNER)
        kernel_data.put(editor.set_target_chara, "A", "anal", PARTNER)
        kernel_data.put(editor.set_status, "A", "anal", FILLED)
        self.assertEqual(template_a()["mouth"], [PARTNER, -1])
        self.show("返回")
        self.assertEqual(template_a()["mouth"], [-1, -1])
        self.assertEqual(template_a()["anal"], [PARTNER, FILLED])

    def test_reset_button_clears_template(self) -> None:
        """
        先将模板 A 的 anal 槽位设为 [PARTNER, FILLED] 并断言该值已写入。
        打开面板并依次应答「重置模板」「返回」后，断言 anal 槽位变为 [-1, -1]。
        """
        kernel_data.put(editor.set_target_chara, "A", "anal", PARTNER)
        kernel_data.put(editor.set_status, "A", "anal", FILLED)
        self.assertEqual(template_a()["anal"], [PARTNER, FILLED])
        self.show("重置模板", "返回")
        self.assertEqual(template_a()["anal"], [-1, -1])


class ModePanelCase(PanelCase):
    """在 PanelCase 基础上提供单次选定模式并提取所抛 player_pick.Chosen 行动数据的测试基类。"""

    def picked(
        self, show: Callable[[], None], answer: str
    ) -> Mapping[str, object]:
        """
        以单项预设应答在 kernel_data.writing() 内运行 show，断言抛出 player_pick.Chosen 且应答被消费。
        返回该异常 action.action_data 映射。
        Keyword arguments:
        show -- Callable[[], None]，打开并绘制模式选择面板的可调用对象
        answer -- str，触发模式选择的预设按钮返回值
        Return arguments:
        Mapping[str, object] -- 所抛 player_pick.Chosen 异常中的 action_data 映射
        """
        self.clicks.answers = [answer]
        with kernel_data.writing(), self.assertRaises(
            player_pick.Chosen
        ) as raised:
            show()
        self.assertEqual(self.clicks.answers, [])
        data = raised.exception.action.action_data
        assert isinstance(data, Mapping)
        return data


class HiddenSexModePanelTest(ModePanelCase):
    """隐奸模式选择面板（Select_Hidden_Sex_Mode_Panel）的选项过滤、发起与邀请失败测试。"""

    def test_mode_button_picks_ask_hidden_sex(self) -> None:
        """
        开启 debug 模式后打开 Select_Hidden_Sex_Mode_Panel 并应答 "4"。
        断言可选返回值列表为 ["1", "2", "3", "4", "返回"]，且所选行动的 behavior_id 为 ASK_HIDDEN_SEX。
        """
        kernel_data.put(modes.set_debug, True)
        panel = hidden_sex_panel.Select_Hidden_Sex_Mode_Panel(WIDTH)
        data = self.picked(panel.draw, "4")
        self.assertEqual(self.clicks.offers, [["1", "2", "3", "4", "返回"]])
        self.assertEqual(data["behavior_id"], constant.Behavior.ASK_HIDDEN_SEX)

    def test_third_person_leaves_only_open_mode(self) -> None:
        """
        在未开启 debug 模式且场景含三名清醒角色时，打开 Select_Hidden_Sex_Mode_Panel 并应答「返回」。
        断言可选返回值列表为 ["1", "返回"]。
        """
        panel = hidden_sex_panel.Select_Hidden_Sex_Mode_Panel(WIDTH)
        self.run_panel(panel.draw, "返回")
        self.assertEqual(self.clicks.offers, [["1", "返回"]])

    def test_failed_invite_from_discovery(self) -> None:
        """
        开启 debug 模式并以 sex_be_discovered_flag=True 构造隐奸面板，先断言 panel.invite_failed 为 False。
        将 calculation_instuct_judege 替换为 JUDGE_FAILS 后经 run_panel 应答 "4"。
        断言 panel.invite_failed 为 True，角色 0 与 PARTNER 的 hidden_sex_mode 均为 0，且面板退回 IN_SCENE。
        """
        kernel_data.put(modes.set_debug, True)
        panel = hidden_sex_panel.Select_Hidden_Sex_Mode_Panel(
            WIDTH, sex_be_discovered_flag=True
        )
        self.assertFalse(panel.invite_failed)
        with mock.patch.object(
            instuct_judege,
            "calculation_instuct_judege",
            return_value=JUDGE_FAILS,
        ):
            self.run_panel(panel.draw, "4")
        self.assertTrue(panel.invite_failed)
        self.assertEqual(
            (
                flags.get(0, "hidden_sex_mode"),
                flags.get(PARTNER, "hidden_sex_mode"),
            ),
            (0, 0),
        )


class ExhibitionismSexModePanelTest(ModePanelCase):
    """露出模式选择面板（Select_Exhibitionism_Sex_Mode_Panel）的发起与邀请失败测试。"""

    def test_mode_button_picks_ask_exhibitionism_sex(self) -> None:
        """
        开启 debug 模式后打开 Select_Exhibitionism_Sex_Mode_Panel 并应答 "3"。
        断言可选返回值列表为 ["1", "2", "3", "4", "返回"]，且所选行动的 behavior_id 为 ASK_EXHIBITIONISM_SEX。
        """
        kernel_data.put(modes.set_debug, True)
        panel = exhibitionism_sex_panel.Select_Exhibitionism_Sex_Mode_Panel(
            WIDTH
        )
        data = self.picked(panel.draw, "3")
        self.assertEqual(self.clicks.offers, [["1", "2", "3", "4", "返回"]])
        self.assertEqual(
            data["behavior_id"], constant.Behavior.ASK_EXHIBITIONISM_SEX
        )

    def test_failed_invite_from_discovery(self) -> None:
        """
        开启 debug 模式并以 sex_be_discovered_flag=True 构造露出面板，先断言 panel.invite_failed 为 False。
        将 calculation_instuct_judege 替换为 JUDGE_FAILS 后经 run_panel 应答 "3"。
        断言 panel.invite_failed 为 True，角色 0 与 PARTNER 的 exhibitionism_sex_mode 均为 0，且面板退回 IN_SCENE。
        """
        kernel_data.put(modes.set_debug, True)
        panel = exhibitionism_sex_panel.Select_Exhibitionism_Sex_Mode_Panel(
            WIDTH, sex_be_discovered_flag=True
        )
        self.assertFalse(panel.invite_failed)
        with mock.patch.object(
            instuct_judege,
            "calculation_instuct_judege",
            return_value=JUDGE_FAILS,
        ):
            self.run_panel(panel.draw, "3")
        self.assertTrue(panel.invite_failed)
        self.assertEqual(
            (
                flags.get(0, "exhibitionism_sex_mode"),
                flags.get(PARTNER, "exhibitionism_sex_mode"),
            ),
            (0, 0),
        )
