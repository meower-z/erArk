# -*- coding: UTF-8 -*-
"""
指令询问钩子测试
================
InstructPromptHooksUiFreeTest 在无界面子进程中验证 instruct_hooks 六个询问与显示入口的未登记行为与登记转发。
InstructPromptCallbacksTest 验证 instruct_callbacks 登记的六个入口按约定绘制按钮或调用面板。
HandleInstructPromptsTest 验证 handle_instruct 的指令经 instruct_hooks 询问，并按回答定下或放弃行动。
"""

from collections.abc import Callable, Mapping
from typing import cast
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import constant, flow_handle, get_text
from Script.Kernel import core
from Script.Modules.domains import activity, modes, official, scene_state
from Script.Modules.gameplay_resolution import instruct_hooks, intent
from Script.Modules.tk_ui import player_pick
from Script.System.Education_System import education_constant
from Script.System.Education_System import sex_class_handle
from Script.System.Instruct_System import handle_instruct
from Script.System.Official_Event_System import official_event_handle, ri_value
from Script.UI.Moudle import draw
from Script.UI.Panel import condom_panel, normal_panel, official_event_panel
from tests import chara_abilities as ca, kernel_data
from tests.chara_activity import aim
from tests.fast.base import FastTestCase

_ = get_text._

NPC = 1
""" 玩家的交互对象 """
WIDTH = normal_config.config_normal.text_width
""" 界面回调使用的绘制宽度 """
SKIPPED = "测试公务甲"
""" 处理公务测试中回答 0、以选项 0 记进履历并跳过的公务事件 uid """
EVENT = "测试公务乙"
""" 处理公务测试中选定并结算选项二的公务事件 uid """
EVENTS = {
    uid: {
        "cid": uid,
        "department": 15,
        "text": "正文",
        "option_1": "选项一",
        "option_2": "选项二",
        "option_2_effect": "CVE_RI_R|1_G_7",
    }
    for uid in (SKIPPED, EVENT)
}
""" 测试用公务事件配置表，选项二结算时罗德岛资源 1 增加 7 """
QUEUED: dict[str, object] = {"uid": EVENT, "chara_id": 0, "partner_id": 0}
""" 待决断队列里的测试公务事件乙 """
SELECTION: dict[str, object] = {"op": "drink", "part": None, "condom": [0]}
""" 测试用的避孕套面板选择结果 """
RUNS = """
payload["error"] = None
try:
    from Script.Modules.gameplay_resolution import instruct_hooks

    entries = [
        ("ask_close_door", ()),
        ("ask_sex_class_ability", ([70, 71],)),
        ("confirm_poor_music", ()),
        ("select_condom", ("hang",)),
        ("ask_official_option", ({"uid": "u"},)),
        ("show_official_result", ("u", 0, 0, 1)),
    ]

    def run_all():
        results = []
        for name, args in entries:
            try:
                results.append(["returned", getattr(instruct_hooks, name)(*args)])
            except RuntimeError as error:
                results.append(["RuntimeError", str(error)])
        return results

    payload["unregistered"] = run_all()
    calls = []
    instruct_hooks.on_prompts(
        lambda: calls.append(["door"]) or True,
        lambda ids: calls.append(["ability", list(ids)]) or 71,
        lambda: calls.append(["music"]) or False,
        lambda mode: calls.append(["condom", mode]) or {"op": mode},
        lambda queue_data: calls.append(["official", queue_data]) or 2,
        lambda *result: calls.append(["result", list(result)]),
    )
    payload["registered"] = run_all()
    payload["calls"] = calls
except Exception as error:
    payload["error"] = repr(error)
"""
""" 无界面子进程脚本，依次调用六个入口的未登记与登记后版本，并向 payload 记录结果。 """


class InstructPromptHooksUiFreeTest(FastTestCase):
    """无界面子进程中 instruct_hooks 六个入口的未登记行为、登记转发与界面模块隔离测试。"""

    def test_prompts_without_ui(self) -> None:
        """
        验证未登记时五个询问入口抛出 RuntimeError，显示公务结果的入口返回 None 且不执行操作。
        登记后六个入口按顺序把参数交给登记函数并返回其结果，且子进程未尝试导入也未载入受拦截模块。
        """
        from tests.ui_free_subprocess import run_ui_free

        child = run_ui_free(RUNS)
        self.assertIsNone(child.payload["error"])
        unregistered = child.payload["unregistered"]
        assert isinstance(unregistered, list)
        self.assertEqual(
            [row[0] for row in unregistered],
            ["RuntimeError"] * 5 + ["returned"],
        )
        self.assertIsNone(unregistered[-1][1])
        self.assertEqual(
            child.payload["registered"],
            [
                ["returned", answer]
                for answer in (True, 71, False, {"op": "hang"}, 2, None)
            ],
        )
        self.assertEqual(
            child.payload["calls"],
            [
                ["door"],
                ["ability", [70, 71]],
                ["music"],
                ["condom", "hang"],
                ["official", {"uid": "u"}],
                ["result", ["u", 0, 0, 1]],
            ],
        )
        self.assertEqual(child.attempted, [])
        self.assertEqual(child.loaded, [])


class InstructPromptCallbacksTest(FastTestCase):
    """载入 load_order 后，instruct_hooks 的六个入口经 instruct_callbacks 绘制按钮或调用面板的测试。"""

    def setUp(self) -> None:
        """
        调用父类准备，拦截 CenterButton.draw 与 NormalDraw.draw 记录按钮和文本。
        同时以 self.answer 替换 flow_handle.askfor_all。
        """
        super().setUp()
        self.buttons: list[tuple[str, str, int]] = []
        """ 绘制过的按钮：(按钮文字, 返回值, 宽度) """
        self.texts: list[str] = []
        """ NormalDraw 绘制过的文本 """
        self.offered: list[list[str]] = []
        """ 每次 askfor_all 收到的返回值列表 """
        self.reply: Callable[[list[str]], str] = lambda options: options[0]
        """ 根据返回值列表给出玩家回答的函数 """
        self.enterContext(
            mock.patch.object(
                draw.CenterButton,
                "draw",
                autospec=True,
                side_effect=lambda button: self.buttons.append(
                    (button.text, button.return_text, button.width)
                ),
            )
        )
        self.enterContext(
            mock.patch.object(
                draw.NormalDraw,
                "draw",
                autospec=True,
                side_effect=lambda text: self.texts.append(text.text),
            )
        )
        self.enterContext(
            mock.patch.object(flow_handle, "askfor_all", self.answer)
        )

    def answer(self, options: list[str], *args: object) -> str:
        """
        记下返回值列表，并按 self.reply 给出回答。
        Keyword arguments:
        options -- list[str]，本次可选的返回值列表
        args -- object，其余位置参数，本方法不使用
        Return arguments:
        str -- self.reply 给出的返回值
        """
        self.offered.append(list(options))
        return self.reply(options)

    def test_sex_class_ability_buttons(self) -> None:
        """
        验证主修科目询问为每门科目画一个四分之一宽的按钮，再画同宽的返回按钮。
        选中第二门科目时返回其能力编号，选返回按钮时返回 -1。
        """
        ids = education_constant.SEX_CLASS_ABILITY_LIST[:2]
        names = [game_config.config_ability[i].name for i in ids]
        for pick, expected in ((1, ids[1]), (2, -1)):
            with self.subTest(pick=pick):
                self.buttons.clear()
                self.texts.clear()
                self.offered.clear()
                self.reply = lambda options, n=pick: options[n]
                self.assertEqual(
                    instruct_hooks.ask_sex_class_ability(ids), expected
                )
                self.assertEqual(
                    self.buttons,
                    [
                        *(
                            (_("[{0}]").format(n), n, int(WIDTH / 4))
                            for n in names
                        ),
                        (_("[返回]"), _("返回"), int(WIDTH / 4)),
                    ],
                )
                self.assertEqual(self.offered, [[*names, _("返回")]])
                self.assertEqual(
                    self.texts,
                    [
                        _(
                            "\n这节实操课主要练哪一门？\n（其他动作照样可以做，只是不会有本门的加成）\n\n"
                        ),
                        "\n",
                    ],
                )

    def test_poor_music_confirm_buttons(self) -> None:
        """
        验证音乐能力确认先等待显示提示，再画三分之一宽的取消与确定按钮。
        选确定时返回 True，选取消时返回 False。
        """
        prompt = _(
            "\n当前音乐能力小于等于2，可能会让对方感觉不适，确认要继续吗\n\n"
        )
        for pick, expected in ((1, True), (0, False)):
            with self.subTest(pick=pick):
                self.buttons.clear()
                self.offered.clear()
                self.world.wait_texts.clear()
                self.reply = lambda options, n=pick: options[n]
                self.assertIs(instruct_hooks.confirm_poor_music(), expected)
                self.assertEqual(self.world.wait_texts, [prompt])
                self.assertEqual(
                    self.buttons,
                    [
                        (_("[取消]"), _("\n取消"), int(WIDTH / 3)),
                        (_("[确定]"), _("\n确定"), int(WIDTH / 3)),
                    ],
                )
                self.assertEqual(self.offered, [[_("\n取消"), _("\n确定")]])

    def test_panels_are_looked_up_at_call_time(self) -> None:
        """
        替换关门、避孕套与公务事件面板入口后调用对应钩子入口。
        验证各入口以界面宽度与原样参数调用替换对象，并返回其结果。
        """
        door = self.enterContext(
            mock.patch.object(
                normal_panel.Close_Door_Panel,
                "draw",
                autospec=True,
                return_value=False,
            )
        )
        condom = self.enterContext(
            mock.patch.object(
                condom_panel.Condom_Select_Panel,
                "draw",
                autospec=True,
                return_value=SELECTION,
            )
        )
        official = self.enterContext(
            mock.patch.object(official_event_panel, "Official_Event_Draw")
        )
        official.return_value.draw.return_value = 2
        self.assertIs(instruct_hooks.ask_close_door(), False)
        self.assertEqual(door.call_args.args[0].width, WIDTH)
        self.assertIs(instruct_hooks.select_condom("drink"), SELECTION)
        panel = condom.call_args.args[0]
        self.assertEqual((panel.width, panel.mode), (WIDTH, "drink"))
        self.assertEqual(instruct_hooks.ask_official_option(QUEUED), 2)
        official.assert_called_once_with(QUEUED, WIDTH)
        official.reset_mock()
        instruct_hooks.show_official_result(EVENT, 0, 0, 2)
        official.assert_called_once_with(QUEUED, WIDTH)
        official.return_value.draw_result.assert_called_once_with(2)


class HandleInstructPromptsTest(FastTestCase):
    """handle_instruct 的指令经 instruct_hooks 询问玩家，并按回答定下或放弃行动的测试。"""

    def setUp(self) -> None:
        """玩家与交互对象干员同在一处，内核状态由领域数据投影。"""
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.world.chara(NPC, "干员")
        aim(self.player.cid, NPC)
        core.reset_state(kernel_data.reprojected(core.state()))

    def answer(self, slot: str, *replies: object) -> list[tuple[object, ...]]:
        """
        把 instruct_hooks 的一个槽位换成依次返回 replies 的记录函数。
        Keyword arguments:
        slot -- str，instruct_hooks 的槽位名
        replies -- object，按调用顺序排列的返回值
        Return arguments:
        list[tuple[object, ...]] -- 每次调用收到的参数元组列表
        """
        asked: list[tuple[object, ...]] = []
        queue = list(replies)

        def ask(*args: object) -> object:
            """记下询问参数并返回下一个回答。"""
            asked.append(args)
            return queue.pop(0)

        self.enterContext(mock.patch.object(instruct_hooks, slot, ask))
        return asked

    def pick(self, instruct_id: str) -> core.Action | None:
        """
        执行一条指令。
        Keyword arguments:
        instruct_id -- str，指令编号
        Return arguments:
        core.Action | None -- 定下的行动，未定下时为 None
        """
        try:
            handle_instruct.handle_instruct(instruct_id)
        except player_pick.Chosen as chosen:
            return chosen.action
        return None

    def chosen(
        self, instruct_id: str
    ) -> tuple[Mapping[str, object], Mapping[str, object]]:
        """
        执行一条指令并断言它定下行动。
        Keyword arguments:
        instruct_id -- str，指令编号
        Return arguments:
        tuple[Mapping[str, object], Mapping[str, object]] -- 行动的意图数据与其中的 args 映射
        """
        action = self.pick(instruct_id)
        assert action is not None, instruct_id
        data = action.action_data
        assert isinstance(data, dict)
        args = data.get("args", {})
        assert isinstance(args, dict)
        return data, args

    def test_poor_music_confirm_decides_action(self) -> None:
        """
        音乐能力为 0 且场景内有他人时，唱歌与演奏乐器各询问一次。
        回答取消时不定下行动，回答确定时定下对应行为。
        """
        ca.ability(0)[44] = 0
        for instruct_id, behavior_id in (
            (constant.Instruct.SINGING, constant.Behavior.SINGING),
            (
                constant.Instruct.PLAY_INSTRUMENT,
                constant.Behavior.PLAY_INSTRUMENT,
            ),
        ):
            with self.subTest(instruct=instruct_id):
                asked = self.answer("_confirm_poor_music", False, True)
                self.assertIsNone(self.pick(instruct_id))
                data, _args = self.chosen(instruct_id)
                self.assertEqual(data["behavior_id"], behavior_id)
                self.assertEqual(asked, [(), ()])

    def test_skilled_music_does_not_ask(self) -> None:
        """音乐能力为 3 时唱歌不询问，直接定下唱歌行为。"""
        ca.ability(0)[44] = 3
        asked = self.answer("_confirm_poor_music")
        data, _args = self.chosen(constant.Instruct.SINGING)
        self.assertEqual(data["behavior_id"], constant.Behavior.SINGING)
        self.assertEqual(asked, [])

    def test_sex_class_ability_choice(self) -> None:
        """
        场景内有学生且没有预定课程时，开课询问主修科目并传入可选科目列表。
        回答 -1 时不开课，回答一门科目时开课行动带上该科目与学生列表。
        """
        self.enterContext(
            mock.patch.object(
                sex_class_handle, "get_scene_student_list", return_value=[NPC]
            )
        )
        offered = education_constant.SEX_CLASS_ABILITY_LIST
        asked = self.answer("_ask_sex_class_ability", -1, offered[0])
        self.assertIsNone(self.pick(constant.Instruct.START_SEX_CLASS))
        data, args = self.chosen(constant.Instruct.START_SEX_CLASS)
        self.assertEqual(asked, [(offered,), (offered,)])
        self.assertEqual(data["behavior_id"], constant.Behavior.START_SEX_CLASS)
        self.assertEqual(args["ability_id"], offered[0])
        self.assertEqual(args["students"], [NPC])

    def test_close_door_answer_reaches_action(self) -> None:
        """门未关时催眠询问关门，回答关门时行动参数记下关门，回答 None 时不含关门。"""
        scene = self.world.scene(activity.position(0))
        kernel_data.put(scene_state.set_close_flag, scene.scene_path, 0)
        asked = self.answer("_ask_close_door", True, None)
        _data, args = self.chosen(constant.Instruct.HYPNOSIS_ONE)
        self.assertIs(args[handle_instruct.CLOSE_DOOR], True)
        _data, args = self.chosen(constant.Instruct.HYPNOSIS_ONE)
        self.assertNotIn(handle_instruct.CLOSE_DOOR, args)
        self.assertEqual(asked, [(), ()])

    def test_condom_selection_reaches_action(self) -> None:
        """
        调试模式下判定必过，饮用避孕套询问选择面板并传入操作类型。
        回答 None 时退出选择，回答选择结果时行动以 condom 开始代码带上该结果。
        """
        kernel_data.put(modes.set_debug, True)
        asked = self.answer("_select_condom", None, SELECTION)
        with self.assertRaises(player_pick.Back):
            self.pick(constant.Instruct.DRINK_CONDOM_SEMEN)
        data, args = self.chosen(constant.Instruct.DRINK_CONDOM_SEMEN)
        self.assertEqual(asked, [("drink",), ("drink",)])
        self.assertEqual(
            data["behavior_id"], constant.Behavior.DRINK_CONDOM_SEMEN
        )
        self.assertEqual(args, {**SELECTION, handle_instruct.START: "condom"})

    def test_prepare_training_chooses_wait(self) -> None:
        """调教前准备定下以交互对象为目标、种类为 prepare_training 的 10 分钟等待。"""
        action = self.pick(constant.Instruct.PREPARE_TRAINING)
        assert action is not None
        self.assertEqual(action.duration, 10)
        self.assertEqual(
            action.action_id, intent.KIND_PREFIX + "prepare_training"
        )
        data, _args = self.chosen(constant.Instruct.PREPARE_TRAINING)
        self.assertEqual(data["behavior_id"], constant.Behavior.WAIT)
        self.assertEqual(data["target"], NPC)
        self.assertEqual(data["state"], constant.CharacterStatus.STATUS_WAIT)

    def test_official_option_chosen_then_settled(self) -> None:
        """
        处理公务逐条询问队列事件，回答 0 时以选项 0 记进履历，回答 2 时行动带上选项二。
        行动开始时结算选项二并记进履历，再把结算结果交给显示入口。
        """
        self.enterContext(
            mock.patch.object(game_config, "config_official_event", EVENTS)
        )
        official_event_handle.init_provider()
        kernel_data.put(
            official.set_queue, [{**QUEUED, "uid": SKIPPED}, QUEUED]
        )
        asked = self.answer("_ask_official_option", 0, 2)
        with kernel_data.writing():
            data, args = self.chosen(constant.Instruct.OFFICIAL_WORK)
        uids = [a[0]["uid"] for a in asked if isinstance(a[0], dict)]
        self.assertEqual(uids, [SKIPPED, EVENT])
        self.assertEqual(official.queue(), [])
        self.assertEqual(list(official.history()), [SKIPPED])
        self.assertEqual(official.history()[SKIPPED]["choice"], 0)
        self.assertEqual(data["behavior_id"], constant.Behavior.OFFICIAL_WORK)
        self.assertEqual(args[handle_instruct.START], "official_option")
        self.assertEqual(
            {k: args[k] for k in (*QUEUED, "option")}, {**QUEUED, "option": 2}
        )
        shown = self.answer("_show_official_result", None)
        self.assertEqual(ri_value.get_ri_value("R|1"), 0)
        with kernel_data.writing():
            handle_instruct.start_instruct(0, cast(intent.Intent, data))
        self.assertEqual(ri_value.get_ri_value("R|1"), 7)
        self.assertEqual(official.history()[EVENT]["choice"], 2)
        self.assertEqual(shown, [(EVENT, 0, 0, 2)])

    def test_empty_official_queue_asks_nothing(self) -> None:
        """待决断队列为空时处理公务不询问，行动不带开始代码。"""
        kernel_data.put(official.set_queue, [])
        asked = self.answer("_ask_official_option")
        _data, args = self.chosen(constant.Instruct.OFFICIAL_WORK)
        self.assertNotIn(handle_instruct.START, args)
        self.assertEqual(asked, [])
