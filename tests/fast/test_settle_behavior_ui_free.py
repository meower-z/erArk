"""
Script.Design.settle_behavior 无界面与回调测试
==============================================
SettleBehaviorUiFreeTest 在放行 Script.Settle 的独立无界面子进程中运行结算用例，拦截其余默认受禁模块。
子进程导入 Script.Design.settle_behavior，验证子事件、变化文本与 Father 效果的嵌套选项询问，并校验无受禁模块加载。
子进程失败时，setUpClass 抛出 RuntimeError。
SettleHooksTkAdapterTest 在本进程验证 tk_ui/callbacks.py 向 settle_hooks 登记的结算文本绘制回调。
"""

from typing import Any, cast
from unittest import mock

from Script.Config import game_config
from Script.Core import get_text, io_init
from Script.Modules.gameplay_resolution import settle_hooks
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import BLOCKED, run_ui_free

SON = "settle-ui-free-son"
""" 测试用合成子事件的事件编号。 """
NESTED = "settle-ui-free-nested"
""" 测试用合成多层嵌套子事件的事件编号。 """
CHILD_RUN = f"""
import datetime
from unittest import mock
from Script.Config import game_config, map_config, normal_config
from Script.Core import game_type
from Script.Design import settle_behavior
from Script.Kernel import core
from Script.Modules.domains import activity, identity, status
from Script.Modules.gameplay_resolution import modal_hooks, ui_hooks, working
from Script.Protocol.modal_prompts import ChoiceResult
from tests import chara_abilities, chara_data, kernel_data
from tests.chara_activity import aim, place, stand
from tests.world import DEFAULT_SCENE, STANDARD_OUTFIT, start_time

map_config.init_map_data()
kernel_data.reset_clock(start_time(), {{}})
for cid in (0, 1):
    kernel_data.put(identity.put, identity.Identity(cid, name=f"c{{cid}}", sex=cid))
    chara_abilities.zero_tables(cid)
    chara_data.seed(cid, STANDARD_OUTFIT)
    place(cid, DEFAULT_SCENE)
aim(0, 1)
stand(0, "share_blankly", start_time=start_time(), duration=5)
core.reset_state(kernel_data.reprojected(core.state()))
now_time = start_time() + datetime.timedelta(minutes=5)
son = game_type.Event()
son.uid, son.type, son.text = {SON!r}, 1, "子事件正文"
nested = game_type.Event()
nested.uid, nested.text = {NESTED!r}, "嵌套给{{TargetName}}|嵌套正文"
nested.premise = {{"CVP_A1_Son|7_E_3": 1}}
shown, options, settled = [], [], []


@ui_hooks.on_line_wait_text
def keep_line(text, style):
    shown.append([text, style])


@modal_hooks.on_choice
def answer(prompt):
    options.append(
        [prompt.prompt_id, [[o.option_id, o.label] for o in prompt.options]]
    )
    return ChoiceResult(prompt.prompt_id, prompt.options[0].option_id)


def no_change(event_id, character_id, add_time, change_data, now_time):
    settled.append(event_id)
    return change_data


with (
    working.based_on(core.state()),
    mock.patch.dict(
        game_config.config_event, {{{SON!r}: son, {NESTED!r}: nested}}
    ),
    mock.patch.dict(
        game_config.config_event_status_data_by_chara_adv,
        {{"share_blankly": {{0: [{NESTED!r}]}}}},
    ),
    mock.patch.object(settle_behavior, "handle_event_data", no_change),
):
    activity.update_event(0, son_event_id={SON!r})
    payload["son_return"] = settle_behavior.handle_settle_behavior(0, now_time, 0)
    payload["son_shown"] = list(shown)
    payload["son_settled"] = list(settled)
    payload["son_cleared"] = activity.event(0).son_event_id
    seen = min(game_config.config_character_state)
    status.set(1, seen, 2)
    change = game_type.CharacterStatusChange()
    change.target_change[1] = game_type.TargetChange()
    change.target_change[1].status_data = {{seen: 2}}
    normal_config.system_setting.draw_setting[7] = 1
    with mock.patch.object(
        settle_behavior, "handle_instruct_data", return_value=change
    ):
        payload["text"] = settle_behavior.handle_settle_behavior(0, now_time)
    payload["seen"] = seen
    payload["father"] = settle_behavior.handle_comprehensive_value_effect(
        0, ["A1", "Father|7", "E", "3"], game_type.CharacterStatusChange()
    )
    payload["options"] = list(options)
    payload["nested_son"] = activity.event(0).son_event_id
"""
""" 在无界面子进程中初始化测试状态并运行 Script.Design.settle_behavior 结算用例的代码片段。 """


class SettleBehaviorUiFreeTest(FastTestCase):
    """Script.Design.settle_behavior 的无界面子进程导入与运行测试。"""

    @classmethod
    def setUpClass(cls) -> None:
        """放行 Script.Settle 并在无界面子进程中执行 CHILD_RUN。子进程失败时抛出 RuntimeError。"""
        super().setUpClass()
        cls.child = run_ui_free(
            CHILD_RUN, boot=True, blocked=BLOCKED - {"Script.Settle"}
        )
        cls.payload = cast(dict[str, Any], cls.child.payload)

    def test_no_blocked_module_loaded(self) -> None:
        """断言子进程未加载也未尝试导入任何受拦截模块。"""
        self.assertEqual((self.child.loaded, self.child.attempted), ([], []))

    def test_son_event_text_goes_to_line_wait_hook(self) -> None:
        """
        断言子事件文本以 standard 样式经逐行等待回调输出。断言结算记录依次为主事件空编号与 SON。
        断言 son_event_id 为空字符串。断言 handle_settle_behavior 返回 None。
        """
        self.assertEqual(
            self.payload["son_shown"], [["\n子事件正文", "standard"]]
        )
        self.assertEqual(self.payload["son_settled"], ["", SON])
        self.assertEqual(self.payload["son_cleared"], "")
        self.assertIsNone(self.payload["son_return"])

    def test_settle_text_lists_visible_change(self) -> None:
        """
        断言 handle_settle_behavior 返回字符串。断言返回文本包含角色 1 变化状态的显示名与 +2。
        断言返回文本以角色 c0 经过 5 分钟的耗时行结尾。
        """
        text = self.payload["text"]
        name = game_config.config_character_state[self.payload["seen"]].name
        self.assertIsInstance(text, str)
        self.assertIn(name, text)
        self.assertIn("+2", text)
        self.assertTrue(
            text.endswith(
                get_text._("\n\n {0}的时间过去了{1}分钟\n").format("c0", "5")
            )
        )

    def test_father_effect_asks_nested_options(self) -> None:
        """
        断言 Father 效果经 modal_hooks 发出标识为 nested_event、选项为 (NESTED, "嵌套给c1") 的单次提示。
        同时断言当前事件的 son_event_id 等于 NESTED，且效果返回 1。
        """
        self.assertEqual(
            self.payload["options"],
            [["nested_event", [[NESTED, "嵌套给c1"]]]],
        )
        self.assertEqual(self.payload["nested_son"], NESTED)
        self.assertEqual(self.payload["father"], 1)


class SettleHooksTkAdapterTest(FastTestCase):
    """tk_ui/callbacks.py 向 settle_hooks 登记的结算文本绘制回调测试。"""

    def test_settle_text_draws_rich_text_pieces(self) -> None:
        """
        断言 settle_hooks.emit_settle_text 按序绘制富文本各段及其样式（standard 与 persian_pink）。
        同时断言末尾经 io_init.era_print 输出一个换行符。
        """
        drawn: list[tuple[str, str]] = []
        with (
            mock.patch.object(
                draw.NormalDraw,
                "draw",
                autospec=True,
                side_effect=lambda now: drawn.append((now.text, now.style)),
            ),
            mock.patch.object(
                io_init,
                "era_print",
                side_effect=lambda text, *args, **kwargs: drawn.append(
                    (text, "print")
                ),
            ),
        ):
            settle_hooks.emit_settle_text(
                "\n<standard>c1:</standard>\n  <persian_pink>甲+2</persian_pink>\n"
            )
        self.assertEqual(
            drawn,
            [
                ("\n", "standard"),
                ("c1:", "standard"),
                ("\n", "standard"),
                ("  ", "standard"),
                ("甲+2", "persian_pink"),
                ("\n", "standard"),
                ("\n", "print"),
            ],
        )
