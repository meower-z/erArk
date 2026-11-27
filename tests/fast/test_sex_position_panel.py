# -*- coding: UTF-8 -*-
"""
性交体位选择面板与钩子测试
==========================
SexPositionHookUiFreeTest 在无界面子进程中验证 instruct_hooks.choose_sex_position 的未登记报错、登记转发与界面隔离。
SexPositionPanelTest 验证体位面板的选项过滤、八条性交指令经钩子打开面板以及替换槽位回调的效果。
该测试类拦截按钮 draw 方法经 flow_handle.bind_cmd 绑定回调。同时该类以预设应答替换 flow_handle.askfor_all。
"""

from collections.abc import Callable, Mapping
from functools import partial
from unittest import mock

from Script.Config import game_config
from Script.Core import constant, flow_handle
from Script.Modules.domains import modes
from Script.Modules.gameplay_resolution import instruct_hooks
from Script.Modules.tk_ui import instruct_callbacks, player_pick
from Script.System.Instruct_System import handle_instruct
from Script.UI.Moudle import draw, view
from Script.UI.Panel import sex_position_panel
from tests import chara_abilities as ca, kernel_data
from tests.chara_activity import aim
from tests.fast.base import FastTestCase

NPC = 1
""" 测试中与玩家交互的干员角色编号 1。 """
WAIST = 76
""" 能力项腰技的能力编号 76。 """
FIELDS = {
    1: "vaginal_sex_behavior_id",
    2: "cervix_sex_behavior_id",
    3: "womb_sex_behavior_id",
    4: "anal_sex_behavior_id",
    5: "urethral_sex_behavior_id",
}
""" 性交类型编号 1 至 5 到体位配置中对应行为编号字段名的映射。 """
OPENERS = (
    (constant.Instruct.VAGINAL_SEX, 1, False),
    (constant.Instruct.CHANGE_VAGINAL_SEX_POSITION, 1, True),
    (constant.Instruct.CHANGE_CERVIX_SEX_POSITION, 2, True),
    (constant.Instruct.CHANGE_WOMB_SEX_POSITION, 3, True),
    (constant.Instruct.ANAL_SEX, 4, False),
    (constant.Instruct.CHANGE_ANAL_SEX_POSITION, 4, True),
    (constant.Instruct.URETHRAL_SEX, 5, False),
    (constant.Instruct.CHANGE_URETHRAL_SEX_POSITION, 5, True),
)
""" 八条打开体位面板的指令编号及其预期性交类型与换体位标记元组。 """
RUNS = """
payload["error"] = None
try:
    from Script.Modules.gameplay_resolution import instruct_hooks

    try:
        payload["unregistered"] = [
            "returned", instruct_hooks.choose_sex_position(4, True)
        ]
    except RuntimeError as error:
        payload["unregistered"] = ["RuntimeError", str(error)]
    calls = []
    instruct_hooks.on_sex_position(lambda *args: calls.append(list(args)))
    payload["registered"] = instruct_hooks.choose_sex_position(3, False)
    payload["calls"] = calls
except Exception as error:
    payload["error"] = repr(error)
"""
""" 无界面子进程脚本，依次测试 choose_sex_position 未登记与登记后的调用并将结果写入 payload。 """


def open_position(sex_type: int) -> int:
    """
    返回指定性交类型下首个无需家具且配置了有效行为编号的体位编号。
    Keyword arguments:
    sex_type -- int，性交类型编号（1 阴道、2 子宫口、3 子宫、4 肛门、5 尿道）
    Return arguments:
    int -- 满足条件的首个正数体位配置编号
    """
    return next(
        key
        for key, data in game_config.config_sex_position_data.items()
        if key > 0
        and data.furniture_req == 0
        and getattr(data, FIELDS[sex_type], "") not in ("", "0")
    )


class SexPositionHookUiFreeTest(FastTestCase):
    """无界面子进程中 instruct_hooks.choose_sex_position 的未登记报错、登记转发与界面模块隔离测试。"""

    def test_hook_without_ui(self) -> None:
        """
        在无界面子进程中，验证未登记调用 choose_sex_position(4, True) 抛出带约定信息的 RuntimeError。
        验证经 on_sex_position 登记后调用 choose_sex_position(3, False) 返回 None 且记录参数 [3, False]。
        同时断言子进程未发生异常，且未尝试导入也未载入受拦截模块。
        """
        from tests.ui_free_subprocess import run_ui_free

        child = run_ui_free(RUNS)
        self.assertIsNone(child.payload["error"])
        self.assertEqual(
            child.payload["unregistered"],
            [
                "RuntimeError",
                "no instruct prompt handler registered in instruct_hooks",
            ],
        )
        self.assertIsNone(child.payload["registered"])
        self.assertEqual(child.payload["calls"], [[3, False]])
        self.assertEqual(child.attempted, [])
        self.assertEqual(child.loaded, [])


class SexPositionPanelTest(FastTestCase):
    """性交体位选择面板的选项过滤、指令经钩子打开面板以及槽位回调替换测试。"""

    def setUp(self) -> None:
        """
        创建博士与干员并令博士瞄准干员，开启调试模式并将博士腰技设为 5，同时登记命令表与体位钩子清理。
        初始化预设应答与选项记录列表，拦截 CenterButton 和 LeftButton 的 draw 方法为 self.bind。
        同时以 self.answer 替换 flow_handle.askfor_all。
        Return arguments:
        None -- 无返回值
        """
        super().setUp()
        self.addCleanup(flow_handle.cmd_map.clear)
        self.addCleanup(
            instruct_hooks.on_sex_position,
            instruct_callbacks.choose_sex_position,
        )
        self.world.chara(0, "博士")
        self.world.chara(NPC, "干员")
        aim(0, NPC)
        kernel_data.put(modes.set_debug, True)
        ca.ability(0)[WAIST] = 5
        self.answers: list[str] = []
        """ 按消费顺序排列的预设按钮返回值队列。 """
        self.offers: list[list[str]] = []
        """ 每次应答时面板给出的可选返回值列表副本。 """
        for button in (draw.CenterButton, draw.LeftButton):
            self.enterContext(
                mock.patch.object(
                    button, "draw", autospec=True, side_effect=self.bind
                )
            )
        self.enterContext(
            mock.patch.object(flow_handle, "askfor_all", self.answer)
        )

    def bind(self, button: draw.CenterButton) -> None:
        """
        将按钮的返回值、回调函数与参数经 flow_handle.bind_cmd 写入命令映射。
        Keyword arguments:
        button -- draw.CenterButton，调用 draw 的按钮实例（含子类 draw.LeftButton）
        Return arguments:
        None -- 无返回值
        """
        flow_handle.bind_cmd(button.return_text, button.cmd_func, button.args)

    def answer(self, return_list: list[str], *args: object) -> str:
        """
        取出队首预设应答，断言其位于 return_list 中并记录本次可选返回值列表。
        从 flow_handle.cmd_map 取出对应命令，清空命令映射并执行该命令，最后返回该应答。
        Keyword arguments:
        return_list -- list[str]，面板本次给出的可选返回值列表
        args -- object，其余位置参数，本方法不使用
        Return arguments:
        str -- 本次消费的预设按钮返回值
        """
        self.assertTrue(self.answers, return_list)
        wanted = self.answers.pop(0)
        self.assertIn(wanted, return_list)
        self.offers.append(list(return_list))
        command = flow_handle.cmd_map.get(wanted, flow_handle.null_func)
        flow_handle.cmd_map.clear()
        command()
        return wanted

    def run_panel(self, show: Callable[[], object], answer: str) -> None:
        """
        将当前面板设为 SEE_MAP，设置单条预设应答并清空选项记录，然后调用 show。
        Keyword arguments:
        show -- Callable[[], object]，打开面板或执行指令的可调用对象
        answer -- str，供面板读取的单条预设返回值
        Return arguments:
        None -- 无返回值
        """
        view.now_panel_id = constant.Panel.SEE_MAP
        self.answers = [answer]
        self.offers = []
        show()

    def chosen(
        self, show: Callable[[], object], answer: str
    ) -> Mapping[str, object]:
        """
        运行面板并断言抛出 player_pick.Chosen，同时断言预设应答已耗尽且面板回到 IN_SCENE。
        返回所选行动的 action_data 字典。
        Keyword arguments:
        show -- Callable[[], object]，打开面板或执行指令的可调用对象
        answer -- str，供面板读取的单条预设返回值
        Return arguments:
        Mapping[str, object] -- 所选行动的 action_data 字典
        """
        with self.assertRaises(player_pick.Chosen) as raised:
            self.run_panel(show, answer)
        self.assertEqual(self.answers, [])
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
        data = raised.exception.action.action_data
        assert isinstance(data, dict)
        return data

    def test_back_offers_only_reachable_positions(self) -> None:
        """
        取首个无需家具且有腰技要求的体位，分别在腰技差一级与达标时打开面板并回答「返回」。
        断言预设应答已耗尽、面板回到 IN_SCENE、记录列表仅有一页且该页末项为「返回」。
        同时断言腰技差一级时选项不含该体位编号，达标时包含该体位编号。
        """
        skilled = next(
            key
            for key, data in game_config.config_sex_position_data.items()
            if data.furniture_req == 0 and data.skill_req > 0
        )
        need = game_config.config_sex_position_data[skilled].skill_req
        for skill, offered in ((need - 1, False), (need, True)):
            with self.subTest(skill=skill):
                ca.ability(0)[WAIST] = skill
                self.run_panel(
                    sex_position_panel.Sex_Position_Panel(10).draw, "返回"
                )
                self.assertEqual(self.answers, [])
                self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
                self.assertEqual(len(self.offers), 1)
                self.assertEqual(self.offers[0][-1], "返回")
                self.assertIs(str(skilled) in self.offers[0], offered)

    def test_instructs_open_panel_through_hook(self) -> None:
        """
        遍历 OPENERS 八条指令，经 handle_instruct.handle_instruct 执行并以首个无家具且有对应行为的体位编号作答。
        断言每条指令抛出 player_pick.Chosen、耗尽应答并使面板回到 IN_SCENE。
        同时断言行动的 behavior_id 与该性交类型字段一致，且 args["change_position"] 与预期标记一致。
        """
        for instruct_id, sex_type, change_position in OPENERS:
            with self.subTest(instruct=instruct_id):
                position_id = open_position(sex_type)
                data = self.chosen(
                    partial(handle_instruct.handle_instruct, instruct_id),
                    str(position_id),
                )
                position = game_config.config_sex_position_data[position_id]
                self.assertEqual(
                    data["behavior_id"], getattr(position, FIELDS[sex_type])
                )
                args = data["args"]
                assert isinstance(args, dict)
                self.assertIs(args["change_position"], change_position)

    def test_registered_handler_replaces_panel(self) -> None:
        """
        以记录函数替换体位钩子后经 handle_instruct.handle_instruct 执行 ANAL_SEX，断言记录为 [(4, False)]。
        此时应答未消耗且面板留在 SEE_MAP。重新登记 instruct_callbacks.choose_sex_position 后再执行该指令。
        断言记录保持 [(4, False)]，预设应答「返回」已被消耗且面板切回 IN_SCENE。
        """
        calls: list[tuple[int, bool]] = []
        instruct_hooks.on_sex_position(
            lambda sex_type, change: calls.append((sex_type, change))
        )
        self.run_panel(
            partial(
                handle_instruct.handle_instruct, constant.Instruct.ANAL_SEX
            ),
            "返回",
        )
        self.assertEqual(calls, [(4, False)])
        self.assertEqual(self.answers, ["返回"])
        self.assertEqual(view.now_panel_id, constant.Panel.SEE_MAP)
        instruct_hooks.on_sex_position(instruct_callbacks.choose_sex_position)
        self.run_panel(
            partial(
                handle_instruct.handle_instruct, constant.Instruct.ANAL_SEX
            ),
            "返回",
        )
        self.assertEqual(calls, [(4, False)])
        self.assertEqual(self.answers, [])
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
