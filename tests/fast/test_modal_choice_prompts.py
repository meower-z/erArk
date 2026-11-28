"""
子事件纯数据选项协议与选项面板测试
==================================
- 协议类型（ChoiceTypesTest）：校验 ChoiceOption、ChoicePrompt 与 ChoiceResult 的约束与不可变性。
- 后端服务（EventOptionServiceTest）：覆盖两类子事件提示构建、标签转换、去重与选择写回。
- 选项询问（EventOptionAskTest）：验证两类子事件经 settle_hooks 与 Tk 渲染路径完成绘制、翻页与结果写入。
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
from Script.Modules.gameplay_resolution import (
    event_option_service,
    settle_hooks,
)
from Script.Protocol.modal_prompts import (
    ChoiceOption,
    ChoicePrompt,
    ChoiceResult,
)
from Script.UI.Moudle import draw
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
        event(
            "opt_d", "选项丁给{TargetName}", "option_son", IS_PLAYER, NO_PLAYER
        ),
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

    def test_prompt_text_defaults_empty_and_is_kept(self) -> None:
        """验证 ChoicePrompt.text 省略时默认为空字符串，传入字符串时原样保留。"""
        option = ChoiceOption("a", "甲")
        self.assertEqual(ChoicePrompt("pick", (option,)).text, "")
        self.assertEqual(ChoicePrompt("pick", (option,), "问").text, "问")

    def test_prompt_rejects_non_str_text(self) -> None:
        """验证 ChoicePrompt 在 text 不是 str 时抛出 TypeError。"""
        option = ChoiceOption("a", "甲")
        self.assertRaises(TypeError, ChoicePrompt, "pick", (option,), None)

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
    """子事件服务与选项询问测试基类，注入虚构事件配置并准备玩家与目标角色。"""

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
        """
        验证 build_son_event_prompt 仅保留含 option_son 且涵盖父事件前提键的子事件。
        同时断言标签中的 {TargetName} 转为目标名，且提示标识为 settle_hooks.SON_EVENT_PROMPT_ID。
        """
        prompt = event_option_service.build_son_event_prompt(PLAYER)
        self.assertEqual(
            self.options(prompt),
            [("opt_a", "选项甲"), ("opt_d", "选项丁给干员")],
        )
        assert prompt is not None
        self.assertEqual(prompt.prompt_id, settle_hooks.SON_EVENT_PROMPT_ID)

    def test_son_event_prompt_lists_repeated_event_once(self) -> None:
        """验证行为事件表中重复出现的事件标识在 build_son_event_prompt 结果中只列一次。"""
        with mock.patch.dict(
            game_config.config_event_status_data,
            {BEHAVIOR: [*OPTION_EVENTS, "opt_a"]},
        ):
            prompt = event_option_service.build_son_event_prompt(PLAYER)
        self.assertEqual(
            self.options(prompt),
            [("opt_a", "选项甲"), ("opt_d", "选项丁给干员")],
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
        """
        验证 build_multi_layer_event_prompt 按角色后目标顺序汇总匹配子事件。
        断言提示标识为 settle_hooks.NESTED_EVENT_PROMPT_ID，无匹配子事件时返回 None。
        """
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
        assert prompt is not None
        self.assertEqual(prompt.prompt_id, settle_hooks.NESTED_EVENT_PROMPT_ID)
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


class EventOptionAskTest(EventChoiceCase):
    """测试经 settle_hooks 与已登记的 Tk 渲染函数完成普通与多层嵌套子事件选项绘制、翻页与选择写回。"""

    def setUp(self) -> None:
        """初始化绘制与询问记录列表，并拦截 NormalDraw、CenterButton 与 LeftButton 的 draw 方法交由 self.drawn 记录。"""
        super().setUp()
        self.screen: list[tuple[str, ...]] = []
        """ 按绘制顺序记录的非空文本项与按钮元组列表。 """
        self.buttons: list[draw.CenterButton] = []
        """ 当前页已绘制、等待下一次询问消费的按钮实例列表。 """
        self.offered: list[list[str]] = []
        """ 每次调用 askfor_all 时屏幕上可见按钮文本列表的记录。 """
        self.asked: list[list[str]] = []
        """ 每次调用 askfor_all 时传入的候选返回标识列表记录。 """
        for drawable in (draw.NormalDraw, draw.CenterButton, draw.LeftButton):
            self.enterContext(
                mock.patch.object(
                    drawable, "draw", autospec=True, side_effect=self.drawn
                )
            )

    def drawn(self, now: draw.NormalDraw | draw.CenterButton) -> None:
        """
        记录按钮对象及其文本与返回值，或记录非空 NormalDraw 的文本。
        Keyword arguments:
        now -- draw.NormalDraw | draw.CenterButton，被调用 draw 的绘制对象
        Return arguments:
        None -- 无返回值
        """
        if isinstance(now, draw.CenterButton):
            self.buttons.append(now)
            self.screen.append((now.text, now.return_text))
        elif now.text:
            self.screen.append((now.text,))

    def press(self, *labels: str) -> None:
        """
        在当前用例期间用模拟函数拦截 flow_handle.askfor_all，按传入顺序匹配按钮文本片段并执行按钮回调。
        Keyword arguments:
        labels -- str，按询问顺序用于匹配按钮文本的子串序列
        Return arguments:
        None -- 无返回值
        """
        answers = list(labels)

        def askfor_all(return_list: list[str], *args: object) -> str:
            """
            按队首文本片段查找当前页按钮并记录本轮 offered 与 asked。
            清空 self.buttons 后断言该按钮返回值在 return_list 中，执行其非空 cmd_func 并返回 return_text。
            Keyword arguments:
            return_list -- list[str]，本次允许返回的按钮标识列表
            args -- object，其余位置参数，本函数不使用
            Return arguments:
            str -- 所选按钮的 return_text
            """
            chosen = next(b for b in self.buttons if answers[0] in b.text)
            answers.pop(0)
            self.offered.append([b.text for b in self.buttons])
            self.asked.append(list(return_list))
            self.buttons.clear()
            self.assertIn(chosen.return_text, return_list)
            if chosen.cmd_func is not None:
                chosen.cmd_func()
            return chosen.return_text

        self.enterContext(
            mock.patch.object(flow_handle, "askfor_all", askfor_all)
        )

    def page(self, *labels: str) -> list[tuple[str, ...]]:
        """
        按选项标签序列构造单页绘制结果的预期记录列表。
        每个标签生成一条带编号前缀的按钮元组与一次换行，列表末尾追加一次换行。
        Keyword arguments:
        labels -- str，当前页依次显示的选项标签文本
        Return arguments:
        list[tuple[str, ...]] -- 预期的屏幕绘制记录列表
        """
        rows: list[tuple[str, ...]] = []
        for index, label in enumerate(labels):
            rows.append((f"{text_handle.id_index(index)}{label}", str(index)))
            rows.append(("\n",))
        return [*rows, ("\n",)]

    def test_son_options_are_drawn_and_choice_recorded(self) -> None:
        """验证普通子事件选项先绘制两次换行再绘制当前页，询问候选 ["0", "1"] 并将所选 opt_d 写入 son_event_id。"""
        self.press("选项丁")
        with kernel_data.writing():
            settle_hooks.emit_event_options(PLAYER)
        self.assertEqual(
            self.screen,
            [("\n",), ("\n",), *self.page("选项甲", "选项丁给干员")],
        )
        self.assertEqual(self.asked, [["0", "1"]])
        self.assertEqual(activity.event(PLAYER).son_event_id, "opt_d")

    def test_nested_options_are_drawn_and_choice_recorded(self) -> None:
        """
        验证多层嵌套子事件选项先绘制一次换行再绘制当前页。
        断言询问候选为 ["0", "1", "2"]，且所选 son_target 写入 son_event_id。
        """
        self.press("嵌套戊")
        with kernel_data.writing():
            settle_hooks.emit_nested_event_options(PLAYER, 2, 1)
        self.assertEqual(
            self.screen, [("\n",), *self.page("嵌套甲", "嵌套乙", "嵌套戊")]
        )
        self.assertEqual(self.asked, [["0", "1", "2"]])
        self.assertEqual(activity.event(PLAYER).son_event_id, "son_target")

    def test_no_options_skip_asking(self) -> None:
        """验证多层嵌套子事件与普通子事件在无候选项时均不绘制、不调用 askfor_all，且 son_event_id 保持为空。"""
        askfor_all = self.enterContext(
            mock.patch.object(flow_handle, "askfor_all")
        )
        with kernel_data.writing():
            settle_hooks.emit_nested_event_options(PLAYER, 3, 1)
            activity.update_behavior(PLAYER, behavior_id="none")
            settle_hooks.emit_event_options(PLAYER)
        askfor_all.assert_not_called()
        self.assertEqual(self.screen, [])
        self.assertEqual(activity.event(PLAYER).son_event_id, "")

    def test_pages_turn_until_an_option_is_chosen(self) -> None:
        """
        验证 25 个子事件分页时，连续点击下一页、上一页、下一页后页面往返切换并持续等待选择。
        最终选中选项23后，断言当前事件的 son_event_id 写入 many_23。
        """
        many = {
            f"many_{index:02d}": event(
                f"many_{index:02d}", f"选项{index:02d}", "option_son", IS_PLAYER
            )
            for index in range(25)
        }
        self.enterContext(mock.patch.dict(game_config.config_event, many))
        self.enterContext(
            mock.patch.dict(
                game_config.config_event_status_data, {BEHAVIOR: list(many)}
            )
        )
        self.press("下一页", "上一页", "下一页", "选项23")
        with kernel_data.writing():
            settle_hooks.emit_event_options(PLAYER)
        first_page = [str(index) for index in range(22)]
        second_page = [str(index) for index in range(7)]
        self.assertEqual(
            self.asked, [first_page, second_page, first_page, second_page]
        )
        self.assertEqual(
            [texts[0] for texts in self.offered],
            ["[000]选项00", "[000]选项20", "[000]选项00", "[000]选项20"],
        )
        self.assertEqual(activity.event(PLAYER).son_event_id, "many_23")


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
