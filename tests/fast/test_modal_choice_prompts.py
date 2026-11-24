"""
子事件纯数据选项协议与选项面板测试
==================================
- 协议类型（ChoiceTypesTest）：校验 ChoiceOption、ChoicePrompt 与 ChoiceResult 的约束与不可变性。
- 后端服务（EventOptionServiceTest）：覆盖两类子事件构建、重复标识去重与选择写回。
- 选项面板（EventOptionPanelTest）：覆盖两类面板按钮绘制、回调写回与无选项跳过。
- 模块边界（ModalPromptsBoundaryTest）：验证 modal_prompts.py 仅导入 Python 标准库。
"""

import ast
import dataclasses
import sys
from pathlib import Path
from unittest import mock

from Script.Config import game_config
from Script.Core import flow_handle, game_type, text_handle
from Script.Modules.domains import activity
from Script.Modules.gameplay_resolution import event_option_service
from Script.Protocol.modal_prompts import (
    ChoiceOption,
    ChoicePrompt,
    ChoiceResult,
)
from Script.UI.Moudle import draw
from Script.UI.Panel import event_option_panel
from tests import kernel_data, world
from tests.fast.base import FastTestCase

MODAL_PROMPTS = Path(world.ROOT) / "Script" / "Protocol" / "modal_prompts.py"
"""Script/Protocol/modal_prompts.py 的文件路径。"""
BEHAVIOR = "test_modal_choice"
"""测试用虚拟行为标识。"""
PLAYER = 0
"""测试用玩家角色编号。"""
TARGET = 1
"""测试用目标角色编号。"""
TARGET_ADV = 900
"""测试用目标角色的 adv 编号。"""
SON_KEY = "CVP_A1_Son|2_E_1"
"""测试用多层嵌套子事件前提键。"""
IS_PLAYER = "sys_0"
"""对玩家角色判定通过的前提键。"""
NO_PLAYER = "sys_1"
"""对玩家角色判定不通过的前提键。"""


def event(uid: str, text: str, *premises: str) -> game_type.Event:
    """按标识 uid、选项文本 text 与前提键 premises（权重均为 1）构造 BEHAVIOR 下的测试事件。"""
    now = game_type.Event()
    now.uid = uid
    now.behavior_id = BEHAVIOR
    now.text = text
    now.premise = dict.fromkeys(premises, 1)
    return now


EVENTS = {
    now.uid: now
    for now in (
        event("father", "父事件", IS_PLAYER),
        event("opt_a", "选项甲|甲的正文", "option_son", IS_PLAYER),
        event("opt_b", "选项乙", "option_son"),
        event("opt_c", "选项丙", IS_PLAYER),
        event("opt_d", "选项丁", "option_son", IS_PLAYER, NO_PLAYER),
        event("son_bare", "嵌套甲", SON_KEY),
        event("son_player", "嵌套乙|正文", SON_KEY, IS_PLAYER),
        event("son_not_player", "嵌套丙", SON_KEY, NO_PLAYER),
        event("son_other", "嵌套丁", "CVP_A1_Son|2_E_2"),
        event("son_target", "嵌套戊", SON_KEY),
    )
}
"""供测试注入 config_event 的虚构事件字典。"""
OPTION_EVENTS = ["opt_a", "opt_b", "opt_c", "opt_d"]
"""测试行为下的普通子事件候选标识列表。"""
PLAYER_ADV_EVENTS = ["son_bare", "son_player", "son_not_player", "son_other"]
"""玩家 adv 对应的多层嵌套子事件候选标识列表。"""


class ChoiceTypesTest(FastTestCase):
    """测试 ChoiceOption、ChoicePrompt 与 ChoiceResult 的构造校验与不可变性。"""

    def test_valid_values_round_trip(self) -> None:
        """验证合法的 ChoicePrompt 与 ChoiceResult 原样保留选项与标识字段。"""
        prompt = ChoicePrompt(
            "pick", (ChoiceOption("a", "甲"), ChoiceOption("b", ""))
        )
        self.assertEqual(prompt.prompt_id, "pick")
        self.assertEqual(
            [(o.option_id, o.label) for o in prompt.options],
            [("a", "甲"), ("b", "")],
        )
        result = ChoiceResult("pick", "b")
        self.assertEqual(
            (result.prompt_id, result.selected_option_id), ("pick", "b")
        )

    def test_option_rejects_bad_fields(self) -> None:
        """验证 ChoiceOption 拒绝空 option_id 与非字符串字段。"""
        self.assertRaises(ValueError, ChoiceOption, "", "甲")
        self.assertRaises(TypeError, ChoiceOption, 1, "甲")
        self.assertRaises(TypeError, ChoiceOption, "a", None)

    def test_prompt_rejects_bad_options(self) -> None:
        """验证 ChoicePrompt 拒绝非法 prompt_id、空或非元组 options、非选项元素及重复标识。"""
        option = ChoiceOption("a", "甲")
        self.assertRaises(ValueError, ChoicePrompt, "", (option,))
        self.assertRaises(TypeError, ChoicePrompt, None, (option,))
        self.assertRaises(ValueError, ChoicePrompt, "pick", ())
        self.assertRaises(TypeError, ChoicePrompt, "pick", [option])
        self.assertRaises(TypeError, ChoicePrompt, "pick", (option, "b"))
        with self.assertRaises(ValueError):
            ChoicePrompt("pick", (option, ChoiceOption("a", "乙")))

    def test_result_rejects_empty_ids(self) -> None:
        """验证 ChoiceResult 拒绝空标识字符串及非字符串标识字段。"""
        self.assertRaises(ValueError, ChoiceResult, "", "a")
        self.assertRaises(ValueError, ChoiceResult, "pick", "")
        self.assertRaises(TypeError, ChoiceResult, "pick", 1)
        self.assertRaises(TypeError, ChoiceResult, 1, "a")

    def test_values_are_frozen(self) -> None:
        """验证修改三个协议数据类实例字段均抛出 FrozenInstanceError。"""
        option = ChoiceOption("a", "甲")
        prompt = ChoicePrompt("pick", (option,))
        result = ChoiceResult("pick", "a")
        for value, field in (
            (option, "label"),
            (prompt, "options"),
            (result, "selected_option_id"),
        ):
            with self.assertRaises(dataclasses.FrozenInstanceError):
                setattr(value, field, "x")


class EventChoiceCase(FastTestCase):
    """子事件服务与面板测试基类，注入虚构事件配置并准备玩家与目标角色。"""

    def setUp(self) -> None:
        """补丁事件配置表并创建测试用玩家角色、目标角色及当前行为与父事件。"""
        super().setUp()
        self.enterContext(mock.patch.dict(game_config.config_event, EVENTS))
        self.enterContext(
            mock.patch.dict(
                game_config.config_event_status_data,
                {BEHAVIOR: OPTION_EVENTS},
            )
        )
        self.enterContext(
            mock.patch.dict(
                game_config.config_event_status_data_by_chara_adv,
                {
                    BEHAVIOR: {
                        0: PLAYER_ADV_EVENTS,
                        TARGET_ADV: ["son_target"],
                    }
                },
            )
        )
        self.world.chara(PLAYER, "博士")
        self.world.chara(TARGET, "干员", adv=TARGET_ADV)
        kernel_data.put(activity.set_target, PLAYER, TARGET)
        kernel_data.put(activity.update_behavior, PLAYER, behavior_id=BEHAVIOR)
        kernel_data.put(activity.update_event, PLAYER, event_id="father")

    def options(self, prompt: ChoicePrompt | None) -> list[tuple[str, str]]:
        """从非空 ChoicePrompt 提取 (option_id, label) 列表以便断言。"""
        assert prompt is not None
        return [(o.option_id, o.label) for o in prompt.options]


class EventOptionServiceTest(EventChoiceCase):
    """测试 event_option_service 的提示构建、子事件筛选与选择写回逻辑。"""

    def test_son_event_prompt_lists_matching_options(self) -> None:
        """验证 build_son_event_prompt 仅保留含 option_son 且涵盖父事件前提的子事件。"""
        prompt = event_option_service.build_son_event_prompt(PLAYER)
        self.assertEqual(
            self.options(prompt), [("opt_a", "选项甲"), ("opt_d", "选项丁")]
        )

    def test_son_event_prompt_lists_repeated_event_once(self) -> None:
        """验证行为事件表中重复出现的事件标识在 build_son_event_prompt 结果中只列一次。"""
        with mock.patch.dict(
            game_config.config_event_status_data,
            {BEHAVIOR: [*OPTION_EVENTS, "opt_a"]},
        ):
            prompt = event_option_service.build_son_event_prompt(PLAYER)
        self.assertEqual(
            self.options(prompt), [("opt_a", "选项甲"), ("opt_d", "选项丁")]
        )

    def test_son_event_prompt_is_none_without_options(self) -> None:
        """验证行为无事件表或无匹配子事件时 build_son_event_prompt 返回 None。"""
        kernel_data.put(activity.update_behavior, PLAYER, behavior_id="none")
        self.assertIsNone(event_option_service.build_son_event_prompt(PLAYER))
        kernel_data.put(activity.update_behavior, PLAYER, behavior_id=BEHAVIOR)
        kernel_data.put(activity.update_event, PLAYER, event_id="son_bare")
        self.assertIsNone(event_option_service.build_son_event_prompt(PLAYER))

    def test_son_events_filtered_by_parent_and_premises(self) -> None:
        """验证 check_son_event_list_from_event_list 按父子前提键与其余前提权重筛选子事件。"""
        self.assertEqual(
            event_option_service.check_son_event_list_from_event_list(
                PLAYER_ADV_EVENTS, PLAYER, 2, 1
            ),
            ["son_bare", "son_player"],
        )
        self.assertEqual(
            event_option_service.check_son_event_list_from_event_list(
                PLAYER_ADV_EVENTS, PLAYER, 2, 2
            ),
            ["son_other"],
        )

    def test_multi_layer_prompt_joins_actor_and_target_events(self) -> None:
        """验证 build_multi_layer_event_prompt 按角色后目标顺序汇总匹配子事件，无匹配返回 None。"""
        prompt = event_option_service.build_multi_layer_event_prompt(
            PLAYER, 2, 1
        )
        self.assertEqual(
            self.options(prompt),
            [
                ("son_bare", "嵌套甲"),
                ("son_player", "嵌套乙"),
                ("son_target", "嵌套戊"),
            ],
        )
        self.assertIsNone(
            event_option_service.build_multi_layer_event_prompt(PLAYER, 3, 1)
        )

    def test_multi_layer_prompt_lists_shared_adv_once(self) -> None:
        """验证目标角色与玩家共用 adv 时，build_multi_layer_event_prompt 对该 adv 事件只列一次。"""
        self.world.chara(2, "干员乙")
        kernel_data.put(activity.set_target, PLAYER, 2)
        prompt = event_option_service.build_multi_layer_event_prompt(
            PLAYER, 2, 1
        )
        self.assertEqual(
            self.options(prompt),
            [("son_bare", "嵌套甲"), ("son_player", "嵌套乙")],
        )

    def test_apply_event_choice_writes_son_event(self) -> None:
        """验证 apply_event_choice 将合法选择写入角色当前事件的 son_event_id。"""
        prompt = event_option_service.build_son_event_prompt(PLAYER)
        assert prompt is not None
        with kernel_data.writing():
            event_option_service.apply_event_choice(
                PLAYER, ChoiceResult(prompt.prompt_id, "opt_d")
            )
        self.assertEqual(activity.event(PLAYER).son_event_id, "opt_d")

    def test_apply_event_choice_rejects_foreign_results(self) -> None:
        """验证 apply_event_choice 对未知 prompt_id 或未配置事件标识抛出 ValueError 且不写入。"""
        prompt = event_option_service.build_son_event_prompt(PLAYER)
        assert prompt is not None
        for result in (
            ChoiceResult("other_prompt", "opt_d"),
            ChoiceResult(prompt.prompt_id, "missing_event"),
        ):
            with kernel_data.writing(), self.assertRaises(ValueError):
                event_option_service.apply_event_choice(PLAYER, result)
        self.assertEqual(activity.event(PLAYER).son_event_id, "")


class EventOptionPanelTest(EventChoiceCase):
    """测试两类子事件选项面板的按钮绘制、交互回调与空选项处理。"""

    def setUp(self) -> None:
        """初始化绘制与询问记录列表，并打桩 SonEventDraw.draw 以收集绘制的按钮对象。"""
        super().setUp()
        self.drawn: list[event_option_panel.SonEventDraw] = []
        """每次 SonEventDraw.draw 被调用时收集的绘制对象列表。"""
        self.offered: list[list[tuple[str, str]]] = []
        """每次调用 askfor_all 时面板绘制的 (按钮文本, 返回值) 列表记录。"""
        self.asked: list[list[str]] = []
        """每次调用 askfor_all 时传入的合法返回值列表记录。"""
        self.enterContext(
            mock.patch.object(
                event_option_panel.SonEventDraw,
                "draw",
                autospec=True,
                side_effect=self.drawn.append,
            )
        )

    def click(self, label: str) -> None:
        """打桩 flow_handle.askfor_all，从已绘制按钮中触发文本含 label 的按钮回调。"""

        def askfor_all(return_list: list[str], *args: object) -> str:
            """读取本次已绘制的按钮列表并执行匹配 label 按钮的回调函数。"""
            buttons = [
                drawn.now_draw
                for drawn in self.drawn
                if isinstance(drawn.now_draw, draw.LeftButton)
            ]
            self.assertEqual(len(buttons), len(self.drawn))
            self.drawn.clear()
            self.offered.append([(b.text, b.return_text) for b in buttons])
            self.asked.append(list(return_list))
            chosen = next(b for b in buttons if label in b.text)
            assert chosen.cmd_func is not None
            self.assertEqual(chosen.args, ())
            chosen.cmd_func()
            return chosen.return_text

        self.enterContext(
            mock.patch.object(flow_handle, "askfor_all", askfor_all)
        )

    def buttons(self, *texts: str) -> list[tuple[str, str]]:
        """按索引生成面板数字按钮预期的 (带序号文本, 序号字符串) 列表。"""
        return [
            (f"{text_handle.id_index(index)}{text}", str(index))
            for index, text in enumerate(texts)
        ]

    def test_option_panel_offers_options_and_records_choice(self) -> None:
        """验证 Event_option_Panel 绘制普通子事件按钮并在点击后写入对应 son_event_id。"""
        self.click("选项丁")
        with kernel_data.writing():
            event_option_panel.Event_option_Panel(PLAYER, 60).draw()
        self.assertEqual(self.offered, [self.buttons("选项甲", "选项丁")])
        self.assertEqual(self.asked, [["0", "1"]])
        self.assertEqual(activity.event(PLAYER).son_event_id, "opt_d")

    def test_multi_layer_panel_offers_options_and_records_choice(self) -> None:
        """验证 multi_layer_event_option_Panel 绘制多层子事件按钮并在点击后写入对应 son_event_id。"""
        self.click("嵌套戊")
        with kernel_data.writing():
            event_option_panel.multi_layer_event_option_Panel(
                PLAYER, 60, 2, 1
            ).draw()
        self.assertEqual(
            self.offered, [self.buttons("嵌套甲", "嵌套乙", "嵌套戊")]
        )
        self.assertEqual(self.asked, [["0", "1", "2"]])
        self.assertEqual(activity.event(PLAYER).son_event_id, "son_target")

    def test_panels_skip_asking_without_options(self) -> None:
        """验证两类面板在无匹配子事件时不绘制按钮、不调用 askfor_all 且不写入 son_event_id。"""
        askfor_all = self.enterContext(
            mock.patch.object(flow_handle, "askfor_all")
        )
        with kernel_data.writing():
            event_option_panel.multi_layer_event_option_Panel(
                PLAYER, 60, 3, 1
            ).draw()
            activity.update_behavior(PLAYER, behavior_id="none")
            event_option_panel.Event_option_Panel(PLAYER, 60).draw()
        askfor_all.assert_not_called()
        self.assertEqual(self.drawn, [])
        self.assertEqual(activity.event(PLAYER).son_event_id, "")


class ModalPromptsBoundaryTest(FastTestCase):
    """检查 Script/Protocol/modal_prompts.py 导入边界的测试类。"""

    def test_imports_only_stdlib(self) -> None:
        """验证 modal_prompts.py 中的每项导入均属于 Python 标准库。"""
        tree = ast.parse(MODAL_PROMPTS.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add("." * node.level + (node.module or ""))
        self.assertEqual(
            {
                name
                for name in imported
                if name.split(".")[0] not in sys.stdlib_module_names
            },
            set(),
        )
