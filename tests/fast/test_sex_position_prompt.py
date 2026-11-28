# -*- coding: UTF-8 -*-
"""
性交体位选项提示测试
====================
SexPositionBackUiFreeTest 在无界面子进程中验证未登记报错、选返回退出与界面模块隔离。
SexPositionPromptTest 验证体位选项生成规则、界面绘制顺序、返回路径与八条指令的行动结算。
"""

from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import constant, flow_handle
from Script.Modules.domains import activity, flags, h_state, modes
from Script.Modules.gameplay_resolution import instruct_hooks, modal_hooks
from Script.Modules.tk_ui import player_pick
from Script.Protocol.modal_prompts import ChoicePrompt, ChoiceResult
from Script.System.Instruct_System import handle_instruct
from Script.UI.Moudle import draw, view
from tests import chara_abilities as ca, kernel_data
from tests.chara_activity import aim
from tests.fast.base import FastTestCase

NPC = 1
""" 测试用交互对象干员的角色编号（1）。 """
WAIST = 76
""" 角色 0 的腰技能力编号（76）。 """
FIELDS = {
    1: ("vaginal_sex_behavior_id", "性交"),
    2: ("cervix_sex_behavior_id", "W性交"),
    3: ("womb_sex_behavior_id", "W性交"),
    4: ("anal_sex_behavior_id", "A性交"),
    5: ("urethral_sex_behavior_id", "U性交"),
}
""" 性交类型编号（1 至 5）到体位配置行为字段名与判定名称的映射表。 """
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
""" 打开性交体位菜单的八条指令编号、对应性交类型与换体位标记的元组。 """
BACK_RUN = """
from Script.Modules.gameplay_resolution import instruct_hooks, modal_hooks
from Script.Modules.gameplay_resolution import sex_position_prompt
from Script.Protocol.modal_prompts import ChoiceOption, ChoiceResult
sex_position_prompt.position_options = lambda: (ChoiceOption("1", "甲"),)
try:
    instruct_hooks.choose_sex_position(1, False)
except RuntimeError as error:
    payload["unregistered"] = str(error)
asked = []
def answer(prompt):
    asked.append([prompt.prompt_id, prompt.title, [o.option_id for o in prompt.options]])
    return ChoiceResult(prompt.prompt_id, "back")
modal_hooks.on_choice(answer)
payload["back"] = instruct_hooks.choose_sex_position(4, True)
payload["asked"] = asked
"""
""" 无界面子进程脚本，替换体位选项后验证未登记报错与选返回退出并记录结果。 """


def position(**req: int) -> int:
    """
    在 game_config.config_sex_position_data 中查找首个编号大于 0 且字段值全匹配 req 的体位编号。
    Keyword arguments:
    req -- int，按体位配置属性名给出的精确匹配条件
    Return arguments:
    int -- 首个满足条件的性交体位编号
    """
    return next(
        key
        for key, data in game_config.config_sex_position_data.items()
        if key > 0
        and all(getattr(data, name) == value for name, value in req.items())
    )


class SexPositionBackUiFreeTest(FastTestCase):
    """无界面子进程中 choose_sex_position 的未登记报错、返回退出与模块隔离测试。"""

    def test_back_without_ui(self) -> None:
        """
        在无界面子进程中运行 BACK_RUN。
        验证未登记选择处理器时抛出含 "no choice handler for sex_position" 的 RuntimeError。
        验证登记返回 "back" 的处理器后，choose_sex_position 返回 None，
        发出的提示标识为 "sex_position"、标题为 "性交体位"、选项依次为 ["1", "back"]。
        验证子进程未尝试导入也未载入受拦截模块。
        """
        from tests.ui_free_subprocess import run_ui_free

        child = run_ui_free(BACK_RUN)
        self.assertEqual(
            child.payload["unregistered"], "no choice handler for sex_position"
        )
        self.assertIsNone(child.payload["back"])
        self.assertEqual(
            child.payload["asked"],
            [["sex_position", "性交体位", ["1", "back"]]],
        )
        self.assertEqual((child.attempted, child.loaded), ([], []))


class SexPositionPromptTest(FastTestCase):
    """性交体位提示选项规则、Tk 绘制序列、返回退出与八条指令结算的进程内测试。"""

    def setUp(self) -> None:
        """
        初始化含博士与干员的测试世界，开启调试模式并设置默认腰技 5 与场景家具等级 3。
        同时初始化输入队列与记录列表，并将四个绘制类的 draw 方法与
        flow_handle.askfor_all 替换为记录桩。
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(NPC, "干员")
        aim(0, NPC)
        kernel_data.put(modes.set_debug, True)
        ca.ability(0)[WAIST] = 5
        self.scene = self.world.scene(activity.position(0))
        """ 玩家当前所在测试场景对象，默认家具等级为 3。 """
        self.scene.have_furniture = 3
        self.answers: list[str] = []
        """ 待按顺序喂给打桩 flow_handle.askfor_all 的玩家回答列表。 """
        self.offers: list[list[str]] = []
        """ 每次打桩 flow_handle.askfor_all 收到的可选返回键列表记录。 """
        self.drawn: list[tuple[object, ...]] = []
        """ 打桩绘制方法按调用顺序记录的标题、按钮与文本元组列表。 """
        for shown in (
            draw.NormalDraw,
            draw.TitleLineDraw,
            draw.CenterButton,
            draw.LeftButton,
        ):
            self.enterContext(
                mock.patch.object(
                    shown, "draw", autospec=True, side_effect=self.record
                )
            )
        self.enterContext(
            mock.patch.object(flow_handle, "askfor_all", self.answer)
        )

    def record(
        self, shown: draw.NormalDraw | draw.TitleLineDraw | draw.CenterButton
    ) -> None:
        """
        记录一次绘制调用的条目到 self.drawn。
        CenterButton 及其子类 LeftButton 记为 ("button", text, return_text, width)。
        TitleLineDraw 记为 ("title", title, width)，NormalDraw 记为 ("text", text, style)。
        Keyword arguments:
        shown -- draw.NormalDraw | draw.TitleLineDraw | draw.CenterButton，被调用 draw 的绘制对象
        Return arguments:
        None -- 无返回值
        """
        if isinstance(shown, draw.CenterButton):
            self.drawn.append(
                ("button", shown.text, shown.return_text, shown.width)
            )
        elif isinstance(shown, draw.TitleLineDraw):
            self.drawn.append(("title", shown.title, shown.width))
        else:
            self.drawn.append(("text", shown.text, shown.style))

    def answer(self, return_list: list[str], *args: object) -> str:
        """
        从 self.answers 队首取出预设回答，断言其位于 return_list，
        记录 return_list 到 self.offers 后返回该回答。
        Keyword arguments:
        return_list -- list[str]，本次界面提供的可选返回键列表
        args -- object，其余位置参数，此桩实现不使用
        Return arguments:
        str -- 本次取出的预设回答
        """
        wanted = self.answers.pop(0)
        self.assertIn(wanted, return_list)
        self.offers.append(list(return_list))
        return wanted

    def options(
        self,
        furniture: int = 3,
        waist: int = 5,
        current: int = -1,
        mode: int = 0,
    ) -> dict[str, tuple[str, str]]:
        """
        设置家具等级、腰技、当前体位与隐奸模式后调用 choose_sex_position(1, False)，
        并以 "back" 拦截返回。
        验证末尾选项标识为 "back"，返回其余体位选项的 option_id 到
        (availability, label) 映射。
        Keyword arguments:
        furniture -- int，当前场景家具等级，默认 3
        waist -- int，角色 0 腰技等级，默认 5
        current -- int，角色 0 当前体位编号，默认 -1
        mode -- int，角色 0 隐奸模式值，默认 0
        Return arguments:
        dict[str, tuple[str, str]] -- 体位 option_id 到 (availability, label) 的映射
        """
        self.scene.have_furniture = furniture
        ca.ability(0)[WAIST] = waist
        kernel_data.put(h_state.set, 0, current_sex_position=current)
        kernel_data.put(flags.set, 0, hidden_sex_mode=mode)
        asked: list[ChoicePrompt] = []

        def back(prompt: ChoicePrompt) -> ChoiceResult:
            """
            记录收到的 ChoicePrompt 并返回选项标识为 "back" 的 ChoiceResult。
            Keyword arguments:
            prompt -- ChoicePrompt，本次拦截到的选项提示
            Return arguments:
            ChoiceResult -- 选择 "back" 的选择结果
            """
            asked.append(prompt)
            return ChoiceResult(prompt.prompt_id, "back")

        with mock.patch.object(modal_hooks, "_ask", back):
            self.assertIsNone(instruct_hooks.choose_sex_position(1, False))
        (prompt,) = asked
        self.assertEqual(prompt.options[-1].option_id, "back")
        return {
            option.option_id: (option.availability, option.label)
            for option in prompt.options[:-1]
        }

    def test_one_row_per_position(self) -> None:
        """
        验证默认状态下生成的选项标识与 config_sex_position_data 中编号大于 0 的条目顺序一致。
        同时验证每条标签以两位补零编号 "[NN]" 开头并以对应配置的 info 文本结尾。
        """
        table = game_config.config_sex_position_data
        rows = self.options()
        self.assertEqual(list(rows), [str(key) for key in table if key > 0])
        for key, (_, label) in rows.items():
            self.assertTrue(label.startswith(f"[{int(key):02d}]"), label)
            self.assertTrue(label.endswith(table[int(key)].info), label)

    def test_rules_set_availability(self) -> None:
        """
        分别在默认条件、家具不足、腰技不足与达标、当前体位与隐奸携带模式下调用 options。
        验证对应体位的 availability 取值及标签中是否包含预期原因或标记文本。
        """
        table = position(furniture_req=1, skill_req=0)
        bed = position(furniture_req=3, skill_req=0)
        skilled = position(furniture_req=0, skill_req=3)
        carried = instruct_hooks.sex_position_prompt.CARRY_POSITION
        checks = (
            ({}, table, "open", ""),
            ({}, bed, "open", ""),
            ({"furniture": 1}, table, "open", ""),
            ({"furniture": 1}, bed, "blocked", "(需要房间内有床铺等级的家具)"),
            (
                {"furniture": 0},
                table,
                "blocked",
                "(需要房间内有桌椅等级的家具)",
            ),
            ({"waist": 2}, skilled, "blocked", "(需要博士腰技至少为3级)"),
            ({"waist": 3}, skilled, "open", ""),
            ({"current": table}, table, "current", "(当前体位)"),
            ({"mode": 5}, carried, "open", ""),
            ({"mode": 5}, table, "blocked", "(携带中只能使用对面抱位)"),
        )
        for state, position_id, availability, reason in checks:
            with self.subTest(state=state, position=position_id):
                got = self.options(**state)[str(position_id)]
                self.assertEqual(got[0], availability)
                self.assertIn(reason, got[1])

    def test_panel_draws_rows_and_backs_out(self) -> None:
        """
        在家具等级为 1 且设有当前体位时运行 VAGINAL_SEX 指令并回答 "返回"。
        验证面板编号恢复为 IN_SCENE、提供给 askfor_all 的返回键列表仅含可选体位与 "返回"，
        且完整绘制序列与标题、各状态体位行、换行及 "[返回]" 按钮顺序一致。
        """
        table = position(furniture_req=1, skill_req=0)
        rows = self.options(furniture=1, current=table)
        self.drawn.clear()
        view.now_panel_id = constant.Panel.SEE_MAP
        self.answers = ["返回"]
        handle_instruct.handle_instruct(constant.Instruct.VAGINAL_SEX)
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
        opened = [key for key, (state, _) in rows.items() if state == "open"]
        self.assertEqual(self.offers, [[*opened, "返回"]])
        styles = {"current": "gold_enrod", "blocked": "deep_gray"}
        width = normal_config.config_normal.text_width
        line = ("text", "\n", "standard")
        expected: list[tuple[object, ...]] = [
            ("title", "性交体位", width),
            line,
        ]
        for key, (state, label) in rows.items():
            if state == "open":
                expected.append(("button", label, key, width))
            else:
                expected.append(("text", label, styles[state]))
            expected.append(line)
        expected += [line, line, ("button", "[返回]", "返回", width), line]
        self.assertEqual(self.drawn, expected)

    def test_instructs_settle_chosen_position(self) -> None:
        """
        依次触发 OPENERS 中的全部八条指令并选择指定体位。
        验证回答被消耗、面板编号恢复为 IN_SCENE、抛出 player_pick.Chosen，
        且动作数据中的 behavior_id、judge 与 args（change_position、target_wait、start）均符合预期。
        """
        for instruct_id, sex_type, change_position in OPENERS:
            with self.subTest(instruct=instruct_id):
                position_id = position(furniture_req=1, skill_req=0)
                view.now_panel_id = constant.Panel.SEE_MAP
                self.answers = [str(position_id)]
                with self.assertRaises(player_pick.Chosen) as raised:
                    handle_instruct.handle_instruct(instruct_id)
                self.assertEqual(self.answers, [])
                self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
                data = raised.exception.action.action_data
                assert isinstance(data, dict)
                field, judge = FIELDS[sex_type]
                chosen = game_config.config_sex_position_data[position_id]
                self.assertEqual(
                    (data["behavior_id"], data["judge"], data["args"]),
                    (
                        getattr(chosen, field),
                        judge,
                        {
                            "change_position": change_position,
                            "target_wait": True,
                            "start": "sex_position",
                        },
                    ),
                )
