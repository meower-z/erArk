"""
指令模态选项提示测试
====================
- UiFreePromptTest：测试在拦截界面模块并载入配置的无界面子进程中调用 confirm_poor_music、ask_sex_class_ability
  与 ask_close_door。
- AnswerCheckTest：测试 modal_hooks._ask 返回候选外选项标识时 confirm_poor_music 与 ask_sex_class_ability
  抛出 ValueError。
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
from contextlib import ExitStack, nullcontext
from Script.Config import map_config
from Script.Core import constant
from Script.Design import map_handle
from Script.Kernel import core
from Script.Modules.domains import action_info, activity, identity
from Script.Modules.gameplay_resolution import instruct_hooks, modal_hooks
from Script.Modules.gameplay_resolution import pick_hooks, working
from Script.Protocol.modal_prompts import ChoiceResult
map_config.init_map_data()
state = ExitStack()
state.enter_context(working.based_on(core.state()))
identity.put(identity.Identity(0, name="player"))
def door(close_type):
    scene = next(
        key for key, value in constant.scene_data.items()
        if value.close_type == close_type
    )
    activity.set_position(0, map_handle.get_map_system_path_for_str(scene))
    return instruct_hooks.ask_close_door()
class Back(Exception):
    pass
def back():
    raise Back
pick_hooks.on_pick(back, back, nullcontext)
def run(call):
    try:
        return ["returned", call()]
    except (RuntimeError, Back) as error:
        return [type(error).__name__]
calls = [
    instruct_hooks.confirm_poor_music,
    instruct_hooks.confirm_poor_music,
    lambda: instruct_hooks.ask_sex_class_ability([70, 71]),
    lambda: instruct_hooks.ask_sex_class_ability([70, 71]),
    lambda: door(0),
    lambda: door(1),
    lambda: door(0),
]
payload["unregistered"] = [run(call) for call in calls[::2]]
picks = iter(["confirm", "cancel", "71", "back", "yes", "no", "no"])
seen = []
def answer(prompt):
    options = [[option.option_id, option.label] for option in prompt.options]
    seen.append([prompt.prompt_id, prompt.text, options])
    return ChoiceResult(prompt.prompt_id, next(picks))
modal_hooks.on_choice(answer)
payload["answers"] = [run(call) for call in calls]
action_info.set(0, "ask_close_door_flag", True)
payload["asked"] = run(lambda: door(1))
payload["seen"] = seen
"""
"""
无界面子进程脚本，在未登记与已登记 modal_hooks 时调用 confirm_poor_music、ask_sex_class_ability
与 ask_close_door 并记录结果。
"""


class UiFreePromptTest(FastTestCase):
    """
    测试在无界面子进程中经 modal_hooks 调用 confirm_poor_music、ask_sex_class_ability 与 ask_close_door
    的隔离与收发行为。
    """

    def test_prompts_without_ui(self) -> None:
        """
        在拦截界面模块并载入配置的子进程中调用 confirm_poor_music、ask_sex_class_ability 与 ask_close_door。
        验证未登记选择处理函数时三者均抛出 RuntimeError。
        验证登记选择处理函数后三者发出预期提示，并将回答解码为布尔值、能力编号、-1 或触发已登记的取消回调。
        验证置位 ask_close_door_flag 后 ask_close_door 返回 None 且不发起提示。
        验证子进程未尝试导入也未载入受拦截模块。
        """
        child = run_ui_free(UI_FREE_RUN, boot=True)
        self.assertEqual(child.payload["unregistered"], [["RuntimeError"]] * 4)
        self.assertEqual(
            child.payload["answers"],
            [
                *(["returned", answer] for answer in (True, False, 71, -1)),
                ["returned", True],
                ["returned", False],
                ["Back"],
            ],
        )
        self.assertEqual(child.payload["asked"], ["returned", None])
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
        seen = child.payload["seen"]
        assert isinstance(seen, list)
        self.assertEqual(seen[:4], [music, music, ability, ability])
        door_options = [["yes", _("是")], ["no", _("否")]]
        self.assertEqual(
            [[row[0], row[2]] for row in seen[4:]],
            [["close_door", door_options]] * 3,
        )
        cannot_close = _("\n当前地点无法关门，要继续吗：")
        self.assertEqual(seen[4][1], cannot_close)
        self.assertEqual(seen[6][1], cannot_close)
        self.assertTrue(seen[5][1].startswith("\n当前地点可以关门，"))
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
