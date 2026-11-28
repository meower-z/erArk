"""
公务事件选项提示测试
====================
本模块测试 ChoicePrompt 的可选状态校验，以及 instruct_hooks.ask_official_option 在无界面子进程中的询问与跳过行为。
OpenOptionTest 验证 modal_hooks.ask 仅接受 "open" 选项，以及 ChoiceOption 与 ChoicePrompt 的字段约束。
OfficialOptionPromptTest 验证有可选选项时发送 ChoicePrompt，无可选选项时经 ui_hooks 输出提示且不导入界面模块。
"""

from unittest import mock

from Script.Modules.gameplay_resolution import modal_hooks
from Script.Protocol.modal_prompts import (
    ChoiceOption,
    ChoicePrompt,
    ChoiceResult,
)
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import run_ui_free

PROMPT = ChoicePrompt(
    "pick",
    (
        ChoiceOption("open", "甲"),
        ChoiceOption("blocked", "乙", "blocked", "原因"),
        ChoiceOption("current", "丙", "current"),
    ),
)
""" 含 "open"、"blocked"（带原因）与 "current" 三种可用状态选项的测试用 ChoicePrompt。 """
EVENTS = {
    "可决断": {
        "cid": "可决断",
        "department": 15,
        "text": "正文",
        "option_1": "选项一",
        "option_2": "选项二",
        "option_2_premise": "CVP_RI_R|1_G_100",
        "option_2_reason": "原因",
        "option_3": "选项三",
    },
    "不可决断": {
        "cid": "不可决断",
        "department": 15,
        "text": "正文",
        "option_1": "选项一",
        "option_1_premise": "CVP_RI_R|1_G_100",
    },
}
""" 测试用公务事件配置表，包含含可选与置灰项的「可决断」事件和全部置灰的「不可决断」事件。 """
UI_FREE_RUN = f"""
from Script.Config import game_config
from Script.Modules.gameplay_resolution import instruct_hooks, modal_hooks, ui_hooks
from Script.Protocol.modal_prompts import ChoiceResult
from Script.System.Official_Event_System import official_event_handle
game_config.config_official_event = {EVENTS!r}
prompts = []
def answer(prompt):
    prompts.append([
        prompt.prompt_id,
        prompt.title,
        prompt.text,
        [[o.option_id, o.label, o.availability, o.note] for o in prompt.options],
    ])
    return ChoiceResult(prompt.prompt_id, "3")
modal_hooks.on_choice(answer)
shown = []
ui_hooks.on_notice(lambda text, **options: shown.append([text, options]))
ui_hooks.on_divider(lambda char: shown.append(["divider", char]))
payload["department"] = official_event_handle.get_department_name(15)
payload["answers"] = [
    instruct_hooks.ask_official_option({{"uid": uid, "chara_id": 0, "partner_id": 0}})
    for uid in ("可决断", "不可决断")
]
payload["prompts"] = prompts
payload["shown"] = shown
"""
"""
无界面子进程脚本，登记选择与提示回调后依次对「可决断」与「不可决断」事件
调用 instruct_hooks.ask_official_option 并记录结果。
"""


class OpenOptionTest(FastTestCase):
    """ChoiceOption、ChoicePrompt 的可用状态约束与 modal_hooks.ask 可选校验测试。"""

    def setUp(self) -> None:
        """调用父类 setUp，并在当前用例期间将 modal_hooks._ask 置为 None。"""
        super().setUp()
        self.enterContext(mock.patch.object(modal_hooks, "_ask", None))

    def test_ask_accepts_only_open_options(self) -> None:
        """
        对含三种可用状态选项的 PROMPT 依次登记返回 "open"、"blocked" 与 "current" 的处理函数。
        验证 modal_hooks.ask 接受 "open" 并返回该选项标识，对 "blocked" 与 "current" 均抛出 ValueError。
        """
        for picked in ("open", "blocked", "current"):
            with self.subTest(picked=picked):
                modal_hooks.on_choice(
                    lambda prompt, picked=picked: ChoiceResult("pick", picked)
                )
                if picked == "open":
                    self.assertEqual(
                        modal_hooks.ask(PROMPT).selected_option_id, "open"
                    )
                    continue
                with self.assertRaises(ValueError):
                    modal_hooks.ask(PROMPT)

    def test_prompt_needs_an_open_option(self) -> None:
        """验证构造仅含 "blocked" 与 "current" 选项的 ChoicePrompt 时抛出 ValueError。"""
        with self.assertRaises(ValueError):
            ChoicePrompt(
                "pick",
                (
                    ChoiceOption("blocked", "乙", "blocked"),
                    ChoiceOption("current", "丙", "current"),
                ),
            )

    def test_rejects_bad_fields(self) -> None:
        """验证非法 availability 值抛出 ValueError，非字符串 note 与 title 均抛出 TypeError。"""
        option = ChoiceOption("a", "甲")
        self.assertRaises(ValueError, ChoiceOption, "a", "甲", "hidden")
        self.assertRaises(TypeError, ChoiceOption, "a", "甲", "open", None)
        self.assertRaises(TypeError, ChoicePrompt, "pick", (option,), "", None)


class OfficialOptionPromptTest(FastTestCase):
    """无界面子进程中 instruct_hooks.ask_official_option 的提示发送与界面模块隔离测试。"""

    def test_asks_open_events_and_shows_closed_ones(self) -> None:
        """
        在无界面子进程中依次对「可决断」与「不可决断」事件调用 instruct_hooks.ask_official_option。
        验证返回值依次为 3 与 0，
        且仅对「可决断」事件发送一条标识为 "official_option"、含抬头、正文与三项状态选项的提示。
        验证对「不可决断」事件依次经 ui_hooks 输出换行、抬头、正文、跳过提示与 "-" 分隔线。
        验证子进程未尝试导入也未载入受拦截模块。
        """
        child = run_ui_free(UI_FREE_RUN)
        title = "【公务事件】" + str(child.payload["department"])
        self.assertEqual(child.payload["answers"], [3, 0])
        self.assertEqual(
            child.payload["prompts"],
            [
                [
                    "official_option",
                    title,
                    "\n  正文\n\n",
                    [
                        ["1", "选项一", "open", ""],
                        ["2", "选项二", "blocked", "原因"],
                        ["3", "选项三", "open", ""],
                    ],
                ]
            ],
        )
        width = {"wait": False, "use_text_width": True}
        self.assertEqual(
            child.payload["shown"],
            [
                ["\n", {"wait": False, "style": None, "use_text_width": False}],
                [title + "\n", {**width, "style": "sontitle"}],
                ["\n  正文\n\n", {**width, "style": None}],
                [
                    "  （这件事已经不需要你来决定了）\n",
                    {**width, "style": "deep_gray"},
                ],
                ["divider", "-"],
            ],
        )
        self.assertEqual((child.attempted, child.loaded), ([], []))
