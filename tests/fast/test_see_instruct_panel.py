# -*- coding: UTF-8 -*-
"""
指令菜单面板与指令系统无界面导入测试
====================================
InstructSystemUiFreeTest 在无界面子进程中验证 Script/System/Instruct_System 各模块无需界面即可导入。
SeeInstructPanelTest 验证 SeeInstructPanel 的指令类型筛选切换与点击指令按钮发起对应行为。
该测试类拦截 CenterButton 与 LeftButton 的 draw 方法，经 flow_handle.bind_cmd 绑定按钮回调。
"""

from collections.abc import Callable
from pathlib import Path
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import constant, flow_handle
from Script.Design import attr_calculation
from Script.Modules.domains import inventory
from Script.Modules.tk_ui import player_pick
from Script.UI.Moudle import draw
from Script.UI.Panel import see_instruct_panel
from tests import kernel_data
from tests.chara_activity import aim
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import BLOCKED, ChildRun, run_ui_free

NPC = 1
""" 测试中作为玩家交互目标的干员角色编号 1。 """
WIDTH = 100
""" 测试中传给 SeeInstructPanel 的绘制宽度 100。 """
FILTERS = (
    "instruct_type_filter",
    "instruct_sex_type_filter",
    "instruct_index_filter",
)
""" 测试前后需经 mock.patch.dict 复原的 system_setting 三项指令过滤字典属性名元组。 """
PACKAGE = "Script.System.Instruct_System"
""" 待测指令系统目录对应的点分包名。 """
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
import importlib.util
import sys
import types

if importlib.util.find_spec("pandas") is None:
    stub = types.ModuleType("pandas")
    stub.DataFrame = object
    sys.modules["pandas"] = stub
for name in MODULES:
    try:
        importlib.import_module(PACKAGE + "." + name)
    except ImportError as error:
        payload[name] = repr(error)
    else:
        payload[name] = None
"""
""" 子进程脚本，缺 pandas 时注入替身并导入 MODULES，在 payload 中记 None 或 ImportError 文本。 """


class InstructSystemUiFreeTest(FastTestCase):
    """Script/System/Instruct_System 各模块的无界面子进程导入测试。"""

    child: ChildRun
    """ setUpClass 运行无界面子进程后保存的 ChildRun 结果。 """

    @classmethod
    def setUpClass(cls) -> None:
        """
        调用 run_ui_free 执行 LOAD_ALL 导入 MODULES 各模块，并将子进程运行结果存入 cls.child。
        拦截集合从 BLOCKED 中移除 Script.System.Instruct_System.handle_instruct，boot 保持默认 False。
        Return arguments:
        None -- 无返回值
        """
        cls.child = run_ui_free(
            f"PACKAGE = {PACKAGE!r}\nMODULES = {MODULES!r}\n{LOAD_ALL}",
            blocked=BLOCKED - {PACKAGE + ".handle_instruct"},
        )

    def test_modules_load_without_ui(self) -> None:
        """
        断言 MODULES 包含 Instruct 与 handle_instruct，且 child.payload 中各模块的值均为 None。
        同时断言子进程既未尝试导入也未加载任何受拦截模块。
        """
        self.assertTrue({"Instruct", "handle_instruct"} <= set(MODULES))
        self.assertEqual(self.child.payload, dict.fromkeys(MODULES))
        self.assertEqual(self.child.attempted, [])
        self.assertEqual(self.child.loaded, [])


class SeeInstructPanelTest(FastTestCase):
    """SeeInstructPanel 的指令类型筛选切换与指令按钮发起行为测试。"""

    def setUp(self) -> None:
        """
        登记命令映射清理，并用 mock.patch.dict 保护 FILTERS 指定的三项过滤字典。
        创建博士与干员角色，将双方道具表初始化为零值后令博士瞄准干员。
        将 CenterButton 与 LeftButton 的 draw 方法替换为 self.bind，并构造 SeeInstructPanel(WIDTH)。
        Return arguments:
        None -- 无返回值
        """
        super().setUp()
        self.addCleanup(flow_handle.cmd_map.clear)
        for name in FILTERS:
            self.enterContext(
                mock.patch.dict(getattr(normal_config.system_setting, name))
            )
        self.world.chara(0, "博士")
        self.world.chara(NPC, "干员")
        for cid in (0, NPC):
            kernel_data.put(
                inventory.replace_items, cid, attr_calculation.get_item_zero({})
            )
        aim(0, NPC)
        for button in (draw.CenterButton, draw.LeftButton):
            self.enterContext(
                mock.patch.object(
                    button, "draw", autospec=True, side_effect=self.bind
                )
            )
        self.panel = see_instruct_panel.SeeInstructPanel(WIDTH)
        """ 当前用例待测的 SeeInstructPanel 实例。 """

    def bind(self, button: draw.CenterButton) -> None:
        """
        将按钮的返回值、回调函数与参数经 flow_handle.bind_cmd 写入命令映射。
        Keyword arguments:
        button -- draw.CenterButton，调用 draw 的按钮实例（含子类 draw.LeftButton）
        Return arguments:
        None -- 无返回值
        """
        flow_handle.bind_cmd(button.return_text, button.cmd_func, button.args)

    def listed(self) -> dict[int, list[str]]:
        """
        清空命令映射并重绘面板，将 return_list 中的纯数字条目经 constant.cid_to_instruct_id 映射为指令标识。
        按 constant.instruct_type_data 中的指令类型分组返回各类型下已列出的指令标识列表。
        Return arguments:
        dict[int, list[str]] -- 指令类型编号到已列出指令标识列表的映射
        """
        flow_handle.cmd_map.clear()
        self.panel.draw()
        type_of = {
            instruct_id: instruct_type
            for instruct_type, ids in constant.instruct_type_data.items()
            for instruct_id in ids
        }
        shown: dict[int, list[str]] = {}
        for text in self.panel.return_list:
            if text.isdigit():
                instruct_id = constant.cid_to_instruct_id[int(text)]
                shown.setdefault(type_of[instruct_id], []).append(instruct_id)
        return shown

    def press(self, return_text: str) -> Callable[[], object]:
        """
        断言指定返回值位于当前面板的 return_list 中，并返回其在 flow_handle.cmd_map 中绑定的命令。
        Keyword arguments:
        return_text -- str，目标按钮的返回值文本
        Return arguments:
        Callable[[], object] -- flow_handle.cmd_map 中与 return_text 对应的零参命令对象
        """
        self.assertIn(return_text, self.panel.return_list)
        return flow_handle.cmd_map[return_text]

    def test_type_button_toggles_its_instructs(self) -> None:
        """
        断言初始绘制时 PLAY 分类含 singing 且 DAILY 分类含 wait。
        点击 PLAY 分类按钮后，断言重绘结果不含 PLAY 分类且 DAILY 分类列表不变。
        再次点击该分类按钮后，断言重绘结果恢复为初始列表。
        """
        play = constant.InstructType.PLAY
        name = game_config.config_instruct_type[play].name
        before = self.listed()
        self.assertIn("singing", before[play])
        self.assertIn("wait", before[constant.InstructType.DAILY])
        self.press(name)()
        hidden = self.listed()
        self.assertNotIn(play, hidden)
        self.assertEqual(
            hidden[constant.InstructType.DAILY],
            before[constant.InstructType.DAILY],
        )
        self.press(name)()
        self.assertEqual(self.listed(), before)

    def test_instruct_button_starts_its_behavior(self) -> None:
        """
        绘制面板后，依次触发 wait 与 chat 按钮回调，并以 wait 的数字 cid 字符串调用 panel.handle_instruct。
        断言三项子测试均抛出 player_pick.Chosen，行动数据中的 behavior_id 等于对应指令且 target 等于 NPC。
        """
        self.listed()
        wait, chat = (
            str(constant.instruct_id_to_cid[name]) for name in ("wait", "chat")
        )
        cases = (
            ("wait", self.press(wait)),
            ("chat", self.press(chat)),
            ("wait", lambda: self.panel.handle_instruct(wait)),
        )
        for behavior_id, command in cases:
            with self.subTest(behavior=behavior_id):
                with self.assertRaises(player_pick.Chosen) as raised:
                    command()
                data = raised.exception.action.action_data
                assert isinstance(data, dict)
                self.assertEqual(data["behavior_id"], behavior_id)
                self.assertEqual(data["target"], NPC)
