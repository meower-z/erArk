"""
对话文本AI回调测试
==================
- TextAiHookTest：文本AI回调的登记、串行调用顺序与未登记透传行为。
- TalkTextAiTest：handle_talk_draw 各语言与开关分支及 must_show_talk_check 经由回调处理文本。
- TkTextAiCallbackTest：Tk 回调参数转发与启动阶段按需导入 handle_chat_ai。
- BackendIsolationTest：屏蔽界面与结算模块时在开启文本AI与翻译的条件下运行对话绘制。
"""

import json
import os
import subprocess
import sys
from types import SimpleNamespace
from typing import Any
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import constant
from Script.Design import talk
from Script.Kernel import core
from Script.Modules.domains import activity
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.Modules.tk_ui import callbacks
from Script.UI.Panel import chat_ai_panel
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

TARGET = 1
"""测试使用的目标角色编号（1）。"""
BLANK = constant.Behavior.SHARE_BLANKLY
"""测试口上与地文分支使用的基础行为编号。"""
PROBE = "text_ai_probe"
"""测试必显二段行为对话使用的行为编号。"""
STARTUP_RUN = """
import contextlib, io, json, sys
from Script.Config import normal_config
with contextlib.redirect_stdout(io.StringIO()):
    normal_config.init_normal_config()
from Script.Modules.gameplay_resolution import ui_hooks
fmt = lambda fns: [[f.__module__, f.__name__] for f in fns]
out = {"before": fmt(ui_hooks._text_ais)}
from Script.Kernel import core
from Script.Modules import load_order
with contextlib.redirect_stdout(io.StringIO()):
    core.load(load_order.LOAD_ORDER)
chat_ai = "Script.Design.handle_chat_ai"
out["after"] = fmt(ui_hooks._text_ais)
out["loaded_at_startup"] = chat_ai in sys.modules
normal_config.ai_setting.ai_chat_setting[1] = 0
with contextlib.redirect_stdout(io.StringIO()):
    out["text"] = ui_hooks.apply_text_ai(0, "share_blankly", "abc", translator=True)
out["loaded_after_call"] = chat_ai in sys.modules
print(json.dumps(out))
"""
"""子进程脚本：执行启动加载流程，检查文本AI回调登记状态及 handle_chat_ai 的按需导入时机。"""
BACKEND_RUN = """
import importlib.abc, sys
BLOCKED = ("Script.UI", "Script.Settle", "Script.Design.handle_chat_ai",
    "Script.Core.flow_handle", "Script.Core.io_init", "Script.Frontend",
    "Script.Modules.tk_ui", "tkinter", "_tkinter", "PIL")
attempted = []
def is_blocked(name):
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if is_blocked(fullname):
            attempted.append(fullname)
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Blocker())
import contextlib, io, json
from types import SimpleNamespace
from Script.Config import normal_config, game_config
with contextlib.redirect_stdout(io.StringIO()):
    normal_config.init_normal_config()
    game_config.init()
from Script.Core import constant, game_type
from Script.Design import attr_calculation, map_handle, talk
from Script.Kernel import core
from Script.Modules.domains import activity, identity, wardrobe
from Script.Modules.gameplay_resolution import ui_hooks, working
ai = normal_config.ai_setting
ai.ai_chat_translator_setting = 2
ai.ai_chat_setting[1] = 1
normal_config.system_setting.draw_setting[2] = 1
blank = "share_blankly"
game_config.config_talk["probe_adv"] = SimpleNamespace(
    behavior_id=blank, adv_id=1, context="")
game_config.config_talk["probe_must"] = SimpleNamespace(
    behavior_id="probe", adv_id=0, context="must")
game_config.config_talk_data_by_chara_adv["probe"] = {0: {1: ["probe_must"]}}
game_config.config_talk_premise_data["probe_must"] = {"high_1"}
game_config.config_behavior_effect_data["probe"] = []
talks, calls = [], []
ui_hooks.on_rich_talk(lambda text, **kw: talks.append(text))
def run_all():
    normal_config.config_normal.language = "en_US"
    talk.handle_talk_draw(0, "kou", "probe_adv")
    talk.handle_talk_draw(0, "di", "", common_behavior_id=blank)
    activity.set_second_behavior(0, "probe", 1)
    activity.set_must_show(0, ["probe"])
    talk.must_show_talk_check(0)
    normal_config.config_normal.language = "zh_CN"
    talk.handle_talk_draw(0, "gen", "", common_behavior_id=blank)
def record(cid, bid, text, *, translator):
    calls.append([cid, bid, text, translator])
    return text.upper()
out = {}
with working.based_on(core.state()):
    for cid, name in ((0, "P"), (1, "A")):
        identity.put(identity.Identity(cid, name=name))
        wardrobe.put(cid, attr_calculation.get_cloth_zero())
    activity.set_target(0, 1)
    here = map_handle.get_map_system_path_str_for_list(activity.position(0))
    constant.scene_data[here] = game_type.Scene()
    with contextlib.redirect_stdout(io.StringIO()):
        run_all()
        out["plain"] = list(talks)
        ui_hooks.on_text_ai(record)
        talks.clear()
        run_all()
    out["hooked"] = talks
    out["calls"] = calls
    out["must_show"] = activity.must_show(0)
out["attempted"] = sorted(set(attempted))
out["loaded"] = sorted(n for n in sys.modules if is_blocked(n))
print(json.dumps(out))
"""
"""子进程脚本：屏蔽界面、结算、Tk 与 handle_chat_ai 后开启翻译与生成设置，验证对话绘制无受限导入并经由回调处理。"""


def run_json(script: str) -> dict[str, Any]:
    """
    在独立子进程中以 cp1252 编码运行脚本，校验末行仅含 ASCII 字符并解析为 JSON 字典。
    Keyword arguments:
    script -- str，通过 python -c 执行的脚本源码
    Return arguments:
    dict[str, Any] -- 子进程标准输出末行解析得到的字典
    """
    env = {**os.environ, "PYTHONIOENCODING": "cp1252"}
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        encoding="cp1252",
        timeout=300,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr[-2000:])
    line = result.stdout.splitlines()[-1]
    if not line.isascii():
        raise AssertionError(line)
    return json.loads(line)


class TextAiHookTest(FastTestCase):
    """文本AI回调的登记、链式调用顺序与未登记透传行为测试。"""

    def setUp(self) -> None:
        """将 ui_hooks._text_ais 临时替换为空列表以隔离已登记回调。"""
        super().setUp()
        self.enterContext(mock.patch.object(ui_hooks, "_text_ais", []))

    def test_unregistered_returns_original_text(self) -> None:
        """验证未登记回调时，translator 为 False 或 True 时 apply_text_ai 均原样返回原始文本。"""
        for translator in (False, True):
            with self.subTest(translator=translator):
                self.assertEqual(
                    ui_hooks.apply_text_ai(
                        0, BLANK, "原文", translator=translator
                    ),
                    "原文",
                )

    def test_callbacks_chain_in_registration_order(self) -> None:
        """验证 on_text_ai 原样返回回调，apply_text_ai 按登记顺序将前一个结果与 translator 标志传给下一个回调。"""
        calls = mock.Mock()
        calls.first.side_effect = lambda c, b, text, **kw: text + "甲"
        calls.second.side_effect = lambda c, b, text, **kw: text + "乙"
        self.assertIs(ui_hooks.on_text_ai(calls.first), calls.first)
        self.assertIs(ui_hooks.on_text_ai(calls.second), calls.second)
        self.assertEqual(ui_hooks.apply_text_ai(3, BLANK, "文"), "文甲乙")
        self.assertEqual(
            ui_hooks.apply_text_ai(3, BLANK, "译", translator=True), "译甲乙"
        )
        self.assertEqual(
            calls.mock_calls,
            [
                mock.call.first(3, BLANK, "文", translator=False),
                mock.call.second(3, BLANK, "文甲", translator=False),
                mock.call.first(3, BLANK, "译", translator=True),
                mock.call.second(3, BLANK, "译甲", translator=True),
            ],
        )


class TalkTextAiTest(FastTestCase):
    """handle_talk_draw 与 must_show_talk_check 经由文本AI回调处理文本的分支测试。"""

    def setUp(self) -> None:
        """初始化角色、工作集、测试口上配置与隔离后的回调列表，并将语言与AI开关设为默认值。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(TARGET, "测试干员")
        self.enterContext(working.based_on(core.state()))
        activity.set_target(0, TARGET)
        self.calls: list[tuple[int, str, str, bool]] = []
        self.talks: list[str] = []
        self.enterContext(
            mock.patch.object(ui_hooks, "_text_ais", [self.transform])
        )
        self.enterContext(
            mock.patch.object(
                ui_hooks, "_rich_talks", [lambda t, **kw: self.talks.append(t)]
            )
        )
        adv_talk = SimpleNamespace(behavior_id=BLANK, adv_id=TARGET, context="")
        must_talk = SimpleNamespace(behavior_id=PROBE, adv_id=0, context="必显")
        self.enterContext(
            mock.patch.dict(
                game_config.config_talk,
                {"probe_adv": adv_talk, "probe_must": must_talk},
            )
        )
        self.ai = normal_config.ai_setting
        self.enterContext(
            mock.patch.dict(self.ai.ai_chat_setting, {1: 0}, clear=False)
        )
        self.enterContext(
            mock.patch.object(self.ai, "ai_chat_translator_setting", 0)
        )
        self.enterContext(
            mock.patch.object(normal_config.config_normal, "language", "zh_CN")
        )

    def transform(
        self, cid: int, bid: str, text: str, *, translator: bool
    ) -> str:
        """
        记录回调收到的参数，并返回带模式标记的测试文本。
        Keyword arguments:
        cid -- int，角色编号
        bid -- str，行为编号
        text -- str，传入的待处理文本
        translator -- bool，为真时附加翻译标记，为假时附加生成标记
        Return arguments:
        str -- 附加标记后的文本
        """
        self.calls.append((cid, bid, text, translator))
        return f"{text}<{'译' if translator else '生'}>"

    def configure(self, language: str, translator: int, ai_on: int) -> None:
        """
        设置当前语言、翻译开关与文本生成AI总开关。
        Keyword arguments:
        language -- str，语言代码
        translator -- int，翻译范围设置值
        ai_on -- int，文本生成AI总开关值
        Return arguments:
        None -- 无返回值
        """
        normal_config.config_normal.language = language
        self.ai.ai_chat_translator_setting = translator
        self.ai.ai_chat_setting[1] = ai_on

    def test_handle_talk_draw_branches(self) -> None:
        """验证八组语言、翻译设置、AI开关与文本类型组合下 handle_talk_draw 的回调触发条件、参数传递与最终输出。"""
        cases = (
            ("en_US", 2, 1, "probe_adv", True),
            ("en_US", 1, 1, "probe_adv", None),
            ("zh_CN", 2, 1, "probe_adv", None),
            ("en_US", 1, 0, "", True),
            ("en_US", 2, 1, "", True),
            ("zh_CN", 2, 1, "", False),
            ("en_US", 0, 1, "", False),
            ("zh_CN", 0, 0, "", None),
        )
        for language, translator, ai_on, talk_id, expected in cases:
            with self.subTest(
                language=language,
                translator=translator,
                ai_on=ai_on,
                talk_id=talk_id,
            ):
                self.configure(language, translator, ai_on)
                self.calls.clear()
                self.talks.clear()
                common = None if talk_id else BLANK
                talk.handle_talk_draw(0, "台词", talk_id, "", common)
                if expected is None:
                    self.assertEqual((self.calls, self.talks), ([], ["台词"]))
                    continue
                mark = "译" if expected else "生"
                self.assertEqual(
                    (self.calls, self.talks),
                    ([(0, BLANK, "台词", expected)], [f"台词<{mark}>"]),
                )

    def test_must_show_talk_check_routes_through_hook(self) -> None:
        """验证 must_show_talk_check 经由文本AI回调以翻译模式处理必显地文，并清空必显列表与二段行为计数。"""
        self.configure("en_US", 2, 1)
        self.enterContext(
            mock.patch.dict(
                game_config.config_talk_data_by_chara_adv,
                {PROBE: {0: {1: ["probe_must"]}}},
            )
        )
        self.enterContext(
            mock.patch.dict(
                game_config.config_talk_premise_data, {"probe_must": {"high_1"}}
            )
        )
        self.enterContext(
            mock.patch.dict(
                game_config.config_behavior_effect_data, {PROBE: []}
            )
        )
        self.enterContext(
            mock.patch.dict(normal_config.system_setting.draw_setting, {2: 1})
        )
        activity.set_second_behavior(0, PROBE, 1)
        activity.set_must_show(0, [PROBE])
        talk.must_show_talk_check(0)
        self.assertEqual(
            (self.calls, self.talks),
            ([(0, PROBE, "必显", True)], ["必显<译>"]),
        )
        self.assertEqual(
            (activity.must_show(0), activity.second_behavior(0, PROBE)),
            ([], 0),
        )


class TkTextAiCallbackTest(FastTestCase):
    """Tk 端 use_text_ai 回调的参数转发与延迟导入行为测试。"""

    def test_use_text_ai_forwards_to_judge_use_text_ai(self) -> None:
        """验证 use_text_ai 将参数与 chat_ai_panel.OUTPUT 转发给 judge_use_text_ai。"""
        target = "Script.Design.handle_chat_ai.judge_use_text_ai"
        for translator in (False, True):
            with self.subTest(translator=translator):
                with mock.patch(target, return_value="新文") as judge:
                    ret = callbacks.use_text_ai(
                        TARGET, BLANK, "原文", translator=translator
                    )
                self.assertEqual(ret, "新文")
                judge.assert_called_once_with(
                    TARGET,
                    BLANK,
                    "原文",
                    chat_ai_panel.OUTPUT,
                    translator=translator,
                )

    def test_startup_registers_text_ai_lazily(self) -> None:
        """验证正常启动加载登记 use_text_ai 且不提前导入 handle_chat_ai，直到首次调用 apply_text_ai 时才导入。"""
        out = run_json(STARTUP_RUN)
        self.assertEqual(
            out,
            {
                "before": [],
                "after": [["Script.Modules.tk_ui.callbacks", "use_text_ai"]],
                "loaded_at_startup": False,
                "text": "abc",
                "loaded_after_call": True,
            },
        )


class BackendIsolationTest(FastTestCase):
    """开启文本AI与翻译时对话模块脱离界面、结算与 Tk 运行的导入隔离测试。"""

    def test_talk_draws_without_ui_when_text_ai_enabled(self) -> None:
        """
        验证屏蔽界面、结算、handle_chat_ai 与 Tk 后，开启翻译和生成设置运行对话绘制不触发受限导入，
        未登记时原文透传，登记后输出回调结果。
        """
        out = run_json(BACKEND_RUN)
        self.assertEqual((out["attempted"], out["loaded"]), ([], []))
        self.assertEqual(out["plain"], ["kou", "di", "must", "gen"])
        self.assertEqual(out["hooked"], ["KOU", "DI", "MUST", "GEN"])
        self.assertEqual(
            out["calls"],
            [
                [0, BLANK, "kou", True],
                [0, BLANK, "di", True],
                [0, "probe", "must", True],
                [0, BLANK, "gen", False],
            ],
        )
        self.assertEqual(out["must_show"], [])
