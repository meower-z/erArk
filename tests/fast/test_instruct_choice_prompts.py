"""
指令模态选项提示测试
====================
- UiFreePromptTest：测试在拦截界面模块并载入配置的无界面子进程中调用 confirm_poor_music 与 ask_sex_class_ability。
- AnswerCheckTest：测试 modal_hooks._ask 返回候选外选项标识时两个入口抛出 ValueError。
"""

from unittest import mock

from Script.Config import game_config
from Script.Core import get_text
from Script.Modules.gameplay_resolution import instruct_hooks, modal_hooks
from Script.Protocol.modal_prompts import ChoiceResult
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import run_ui_free

_ = get_text._
""" 文本翻译函数，指向 get_text._。 """
UI_FREE_RUN = """
from Script.Modules.gameplay_resolution import instruct_hooks, modal_hooks
from Script.Protocol.modal_prompts import ChoiceResult
calls = [
    instruct_hooks.confirm_poor_music,
    instruct_hooks.confirm_poor_music,
    lambda: instruct_hooks.ask_sex_class_ability([70, 71]),
    lambda: instruct_hooks.ask_sex_class_ability([70, 71]),
]
unregistered = []
for call in calls[::2]:
    try:
        unregistered.append(["returned", call()])
    except RuntimeError:
        unregistered.append(["RuntimeError"])
payload["unregistered"] = unregistered
picks = iter(["confirm", "cancel", "71", "back"])
seen = []
def answer(prompt):
    options = [[option.option_id, option.label] for option in prompt.options]
    seen.append([prompt.prompt_id, prompt.text, options])
    return ChoiceResult(prompt.prompt_id, next(picks))
modal_hooks.on_choice(answer)
payload["answers"] = [call() for call in calls]
payload["seen"] = seen
"""
"""
无界面子进程代码片段：先在未登记处理函数时调用 confirm_poor_music 与 ask_sex_class_ability，
再登记记录函数并各调用两次，通过 payload 回传结果。
"""


class UiFreePromptTest(FastTestCase):
    """测试在无界面子进程中经 modal_hooks 调用 confirm_poor_music 与 ask_sex_class_ability 的隔离与收发行为。"""

    def test_prompts_without_ui(self) -> None:
        """
        在拦截界面模块并初始化配置的子进程中调用 confirm_poor_music 与 ask_sex_class_ability。
        验证未登记选择处理函数时两个入口均抛出 RuntimeError。
        验证登记处理函数后，两个入口发出预期的提示标识、文本与选项列表，并把回答解码为布尔值、能力编号或 -1。
        验证子进程未尝试导入也未载入受拦截模块。
        """
        child = run_ui_free(UI_FREE_RUN, boot=True)
        self.assertEqual(child.payload["unregistered"], [["RuntimeError"]] * 2)
        self.assertEqual(child.payload["answers"], [True, False, 71, -1])
        music = [
            "poor_music",
            _(
                "\n当前音乐能力小于等于2，可能会让对方感觉不适，确认要继续吗\n\n"
            ),
            [["cancel", _("取消")], ["confirm", _("确定")]],
        ]
        ability = [
            "sex_class_ability",
            _(
                "\n这节实操课主要练哪一门？\n（其他动作照样可以做，只是不会有本门的加成）\n\n"
            ),
            [
                *(
                    [str(i), game_config.config_ability[i].name]
                    for i in (70, 71)
                ),
                ["back", _("返回")],
            ],
        ]
        self.assertEqual(
            child.payload["seen"], [music, music, ability, ability]
        )
        self.assertEqual((child.attempted, child.loaded), ([], []))


class AnswerCheckTest(FastTestCase):
    """测试 confirm_poor_music 与 ask_sex_class_ability 对候选外选项标识的校验。"""

    def test_unoffered_answer_raises(self) -> None:
        """
        将 modal_hooks._ask 替换为返回不在 prompt.options 中的选项标识的桩函数。
        验证 confirm_poor_music 收到 "back" 与 ask_sex_class_ability([70, 71]) 收到 "72" 时均抛出 ValueError。
        """
        for call, answer in (
            (instruct_hooks.confirm_poor_music, "back"),
            (lambda: instruct_hooks.ask_sex_class_ability([70, 71]), "72"),
        ):
            with self.subTest(answer=answer):
                self.enterContext(
                    mock.patch.object(
                        modal_hooks,
                        "_ask",
                        lambda prompt, pick=answer: ChoiceResult(
                            prompt.prompt_id, pick
                        ),
                    )
                )
                with self.assertRaises(ValueError):
                    call()
