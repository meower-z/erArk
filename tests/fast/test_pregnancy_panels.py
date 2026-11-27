# -*- coding: UTF-8 -*-
"""
妊娠面板交互与妊娠系统无界面导入测试
====================================
PregnancySystemUiFreeTest 在无界面子进程中验证 Script/System/Pregnancy_System 各模块可无界面导入。
PanelCase 拦截 CenterButton 与 LeftButton 的 draw 方法以及 flow_handle.askfor_all，按预设应答驱动面板。
PregnancyOverviewPanelTest 覆盖怀孕总览面板的排序、阶段筛选与点选角色名跳入生育谱系图。
BornPanelTest 覆盖生育事件面板的胎生生产与带壳卵生破壳流程。
"""

from pathlib import Path
from unittest import mock

from Script.Core import constant, flow_handle
from Script.Design import map_handle
from Script.Kernel import core
from Script.Modules.domains import abilities, activity, identity, pregnancy
from Script.Modules.domains import relations
from Script.Modules.gameplay_resolution import working
from Script.System.Pregnancy_System import egg_handle, pregnancy_constant
from Script.UI.Moudle import draw, view
from Script.UI.Panel import born_event_panel, input_name_panel
from Script.UI.Panel import pregnancy_panel
from tests import chara_abilities as ca
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ChildRun, run_ui_free

MOTHER = 1
""" 测试使用的母亲角色编号 1。 """
HARD_EGG_RACE = 6
""" 带壳卵生种族编号 6。 """
CHILD_NAME = "小宝"
""" 测试赋予每名新生孩子的名字「小宝」。 """
INPATIENT = "Inpatient_Department"
""" 医疗部住院区的场景标签名 Inpatient_Department。 """
PACKAGE = "Script.System.Pregnancy_System"
""" 待测妊娠系统目录对应的点分包名。 """
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
""" 子进程脚本，依次导入 MODULES（__init__ 导入 PACKAGE），在 payload 记 None 或 ImportError 文本。 """


class PregnancySystemUiFreeTest(FastTestCase):
    """Script/System/Pregnancy_System 各模块的无界面子进程导入测试。"""

    child: ChildRun
    """ setUpClass 运行无界面子进程后保存的 ChildRun 结果。 """

    @classmethod
    def setUpClass(cls) -> None:
        """
        调用 run_ui_free 以默认拦截列表执行 LOAD_ALL 导入 MODULES，并将子进程运行结果存入 cls.child。
        Return arguments:
        None -- 无返回值
        """
        cls.child = run_ui_free(
            f"PACKAGE = {PACKAGE!r}\nMODULES = {MODULES!r}\n{LOAD_ALL}"
        )

    def test_modules_load_without_ui(self) -> None:
        """
        断言 egg_handle 与 pregnancy_handle 在 MODULES 中，且 child.payload 中各模块的值均为 None。
        同时断言子进程既未尝试导入也未加载受拦截模块。
        """
        self.assertTrue({"egg_handle", "pregnancy_handle"} <= set(MODULES))
        self.assertEqual(self.child.payload, dict.fromkeys(MODULES))
        self.assertEqual(self.child.attempted, [])
        self.assertEqual(self.child.loaded, [])


class PanelCase(FastTestCase):
    """妊娠面板交互测试基类，接管按钮绘制与选项输入并记录面板给出的选项列表。"""

    def setUp(self) -> None:
        """
        登记命令映射清理，初始化预设应答与选项记录列表，并创建编号 0 的玩家角色「博士」。
        用 self.bind 替换 CenterButton 与 LeftButton 的 draw 方法，并用 self.answer 替换 flow_handle.askfor_all。
        Return arguments:
        None -- 无返回值
        """
        super().setUp()
        self.addCleanup(flow_handle.cmd_map.clear)
        self.answers: list[str] = []
        """ 按消费顺序排列的预设按钮返回值文本列表。 """
        self.offers: list[list[str]] = []
        """ 记录 answer 每次收到的按钮返回值列表副本。 """
        for button in (draw.CenterButton, draw.LeftButton):
            self.enterContext(
                mock.patch.object(
                    button, "draw", autospec=True, side_effect=self.bind
                )
            )
        self.enterContext(
            mock.patch.object(flow_handle, "askfor_all", self.answer)
        )
        self.world.chara(0, "博士")

    def bind(self, button: draw.CenterButton) -> None:
        """
        当按钮绑定了回调函数时，经 flow_handle.bind_cmd 将其返回值、回调与参数写入命令映射。
        Keyword arguments:
        button -- draw.CenterButton，调用 draw 方法的按钮实例（含子类 draw.LeftButton）
        Return arguments:
        None -- 无返回值
        """
        if button.cmd_func is not None:
            flow_handle.bind_cmd(
                button.return_text, button.cmd_func, button.args
            )

    def answer(self, return_list: list[str], *args: object) -> str:
        """
        断言存在预设应答并取出队首项，断言其位于 return_list 中并记录 return_list 的副本。
        取出 flow_handle.cmd_map 中对应命令（无则取 null_func），清空映射后执行并返回该应答。
        Keyword arguments:
        return_list -- list[str]，面板本次给出的按钮返回值列表
        args -- tuple[object, ...]，其余位置参数，本方法不使用
        Return arguments:
        str -- 本次消费的预设按钮返回值文本
        """
        self.assertTrue(self.answers, return_list)
        wanted = self.answers.pop(0)
        self.assertIn(wanted, return_list)
        self.offers.append(list(return_list))
        command = flow_handle.cmd_map.get(wanted, flow_handle.null_func)
        flow_handle.cmd_map.clear()
        command()
        return wanted


class PregnancyOverviewPanelTest(PanelCase):
    """Pregnancy_Overview_Panel 排序、阶段筛选与角色名按钮跳转的交互测试。"""

    def setUp(self) -> None:
        """
        临时将总览面板排序、筛选与当前面板编号设为 0、0 与 PREGNANCY_OVERVIEW。
        创建角色 1「甲」与 2「乙」并打开工作集，将甲的 20 号素质（受精）与乙的 21 号素质（妊娠）设为 1。
        Return arguments:
        None -- 无返回值
        """
        super().setUp()
        for name, value in (
            ("pregnancy_panel_sort_type", 0),
            ("pregnancy_panel_filter_type", 0),
            ("now_panel_id", constant.Panel.PREGNANCY_OVERVIEW),
        ):
            self.enterContext(mock.patch.object(view, name, value))
        self.world.chara(1, "甲")
        self.world.chara(2, "乙")
        self.enterContext(working.based_on(core.state()))
        ca.talent(1)[20] = 1
        ca.talent(2)[21] = 1

    def test_sort_filter_and_name_buttons(self) -> None:
        """
        依次应答「切换排序」「妊娠」「2_乙」「返回」并绘制 Pregnancy_Overview_Panel(100)。
        断言四次绘制给出的角色名按钮依次为 [2_乙, 1_甲]、[1_甲, 2_乙]、[2_乙] 与空列表。
        同时断言排序为 1、筛选为 STAGE_PREGNANCY、页签与谱系中心为 (1, 2) 且面板编号回到 IN_SCENE。
        """
        self.answers = ["切换排序", "妊娠", "2_乙", "返回"]
        panel = pregnancy_panel.Pregnancy_Overview_Panel(100)
        panel.draw()
        rows = [
            [text for text in offer if text in ("1_甲", "2_乙")]
            for offer in self.offers
        ]
        self.assertEqual(
            rows, [["2_乙", "1_甲"], ["1_甲", "2_乙"], ["2_乙"], []]
        )
        self.assertEqual(view.pregnancy_panel_sort_type, 1)
        self.assertEqual(
            view.pregnancy_panel_filter_type,
            pregnancy_constant.STAGE_PREGNANCY,
        )
        self.assertEqual((panel.now_page, panel.tree_center_id), (1, 2))
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)


class BornPanelTest(PanelCase):
    """Born_Panel 胎生生产与带壳卵生破壳流程的交互测试。"""

    def setUp(self) -> None:
        """
        调用父类 setUp，并将 input_name_panel.input_name_func 打桩为固定返回 CHILD_NAME。
        Return arguments:
        None -- 无返回值
        """
        super().setUp()
        self.enterContext(
            mock.patch.object(
                input_name_panel, "input_name_func", return_value=CHILD_NAME
            )
        )

    def mother(self, race: int = 0) -> None:
        """
        以指定种族创建母亲角色并打开工作集，断言母亲初始场景不含 INPATIENT 标签，并将预设应答设为焦急等待按钮的返回值。
        Keyword arguments:
        race -- int，母亲角色的种族编号，默认为 0
        Return arguments:
        None -- 无返回值
        """
        self.world.chara(MOTHER, "母亲", race=race)
        self.enterContext(working.based_on(core.state()))
        self.assertNotIn(INPATIENT, self.scene_tag(MOTHER))
        self.answers = ["\n"]

    def scene_tag(self, cid: int) -> list[str]:
        """
        返回指定角色当前所在场景的 scene_tag 列表。
        Keyword arguments:
        cid -- int，目标角色编号
        Return arguments:
        list[str] -- 目标角色当前场景的标签名列表
        """
        path = map_handle.get_map_system_path_str_for_list(
            activity.position(cid)
        )
        return constant.scene_data[path].scene_tag

    def children(self) -> list[str]:
        """
        断言玩家与母亲的子女编号列表一致，并返回母亲名下各子女的名字列表。
        Return arguments:
        list[str] -- 母亲子女的角色名列表
        """
        self.assertEqual(
            relations.child_id_list(0), relations.child_id_list(MOTHER)
        )
        return [
            identity.of(cid).name for cid in relations.child_id_list(MOTHER)
        ]

    def test_live_birth(self) -> None:
        """
        为母亲设置临盆（22）、孕肚（26）与单胎后绘制 Born_Panel，断言素质 22/23（产后）/26 变为 0/1/0。
        断言妊娠经验（86）为 1、fetus_count 为 0 且子女名为 [CHILD_NAME]。
        同时断言母亲位于住院区、玩家与母亲同处一场景，且面板仅给出一次仅含焦急等待按钮的选项列表。
        """
        self.mother()
        talent = ca.talent(MOTHER)
        talent[22] = 1
        talent[26] = 1
        pregnancy.update(MOTHER, fetus_count=1)
        born_event_panel.Born_Panel(MOTHER).draw()
        talent = abilities.talent(MOTHER)
        self.assertEqual((talent[22], talent[23], talent[26]), (0, 1, 0))
        self.assertEqual(abilities.experience(MOTHER)[86], 1)
        self.assertEqual(pregnancy.of(MOTHER).fetus_count, 0)
        self.assertEqual(self.children(), [CHILD_NAME])
        self.assertIn(INPATIENT, self.scene_tag(MOTHER))
        self.assertEqual(activity.position(0), activity.position(MOTHER))
        self.assertEqual(self.offers, [["\n"]])

    def test_hard_egg_hatch(self) -> None:
        """
        为带壳卵生母亲添加一枚受精卵并断言其写入 eggs，再以破壳模式绘制 Born_Panel。
        断言素质 22（临盆）/24（育儿）/27（泌乳）为 0/1/1，且母亲 eggs 清空、妊娠经验（86）为 1。
        同时断言子女名为 [CHILD_NAME]，且母亲处于含 INPATIENT 标签的住院区场景。
        """
        self.mother(HARD_EGG_RACE)
        egg_id = egg_handle.add_egg(MOTHER, True)
        self.assertIn(egg_id, pregnancy.of(MOTHER).eggs)
        born_event_panel.Born_Panel(
            MOTHER, egg_mode=True, egg_id_list=[egg_id]
        ).draw()
        talent = abilities.talent(MOTHER)
        self.assertEqual((talent[22], talent[24], talent[27]), (0, 1, 1))
        self.assertEqual(pregnancy.of(MOTHER).eggs, {})
        self.assertEqual(abilities.experience(MOTHER)[86], 1)
        self.assertEqual(self.children(), [CHILD_NAME])
        self.assertIn(INPATIENT, self.scene_tag(MOTHER))
