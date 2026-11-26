"""
文本生成AI无界面运行与导入边界测试
==================================
检查 handle_chat_ai 源码不导入界面、Tk、输入输出或 handle_instruct 模块。
在拦截界面模块且屏蔽网络连接的新子进程中，用替身客户端与记录输出对象运行 25 组用例。
核对无受限模块加载、零网络连接，以及返回值、输出顺序、请求参数、记录保存与直接结算。
"""

from typing import Any, cast

from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports
from tests.fast.test_ejaculation_services import imports_in
from tests.ui_free_subprocess import run_ui_free

CHILD_RUN = """
import os
import socket
import tempfile
from types import SimpleNamespace
from unittest import mock
from Script.Config import game_config, normal_config
from Script.Kernel import core
from Script.Modules.domains import identity
from Script.Modules.gameplay_resolution import working
from tests import chara_abilities, kernel_data
from tests.chara_activity import aim, place
from tests.world import DEFAULT_SCENE, start_time

connects = []

def no_network(*args, **kwargs):
    connects.append(1)
    raise OSError("network blocked")

mock.patch.object(socket.socket, "connect", no_network).start()
mock.patch.object(socket, "create_connection", no_network).start()
kernel_data.reset_clock(start_time(), {})
for cid in (0, 1):
    kernel_data.put(identity.put, identity.Identity(cid, name=f"c{cid}", sex=1))
    chara_abilities.zero_tables(cid)
    place(cid, DEFAULT_SCENE)
aim(0, 1)
ai = normal_config.ai_setting
ai.send_data_flags = {cid: False for cid in game_config.config_ai_chat_send_data}
ai.now_ai_chat_base_url = "http://base.invalid"
ai.now_ai_chat_proxy = ["http://proxy.invalid"]
from Script.Design import handle_chat_ai as hca

log = []
reply = {"text": "", "chunks": [], "fail": False}

class Out:
    def show(self, text, *, full_width=False):
        log.append(["show", text, full_width])

    def line_break(self):
        log.append(["break"])

    def flush(self):
        log.append(["flush"])

    def flushing(self, items):
        for item in items:
            yield item
            log.append(["flush"])

def answer(stream):
    if reply["fail"]:
        raise RuntimeError("model down")
    return stream

class Completions:
    def create(self, model, messages, stream=False):
        log.append(["openai.create", model, [m["role"] for m in messages], stream])
        answer(stream)
        if stream:
            return [
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=c))])
                for c in reply["chunks"]
            ]
        message = SimpleNamespace(content=reply["text"])
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

class OpenAI:
    def __init__(self, api_key):
        log.append(["openai", api_key])
        self.chat = SimpleNamespace(completions=Completions())

    def with_options(self, **options):
        log.append(["openai.options", sorted(str(v) for v in options.values())])
        return self

class Models:
    def generate_content(self, model, contents, config):
        log.append(["genai.generate", model, bool(config.system_instruction)])
        answer(False)
        return SimpleNamespace(text=reply["text"])

    def generate_content_stream(self, model, contents, config):
        log.append(["genai.stream", model, bool(config.system_instruction)])
        answer(True)
        return [SimpleNamespace(text=c) for c in reply["chunks"]]

class Client:
    def __init__(self, api_key, http_options=None):
        opts = None
        if http_options is not None:
            opts = [http_options.api_version, http_options.base_url]
        log.append(["genai", api_key, opts])
        self.models = Models()

class Settled(Exception):
    pass

def settle(result):
    log.append(["settle", dict(result)])
    raise Settled

mock.patch.object(hca.openai, "OpenAI", OpenAI).start()
mock.patch.object(hca.openai, "DefaultHttpxClient", lambda proxy: f"httpx:{proxy}").start()
mock.patch.object(hca.genai, "Client", Client).start()
BASE = {1: 1, 2: 1, 3: 1, 4: 1, 5: "m-test", 7: 0, 8: 1, 9: 0, 10: 0, 11: 0, 12: 0, 13: 0, 14: 0}
KEYS = {"OPENAI_API_KEY": "k-o", "GEMINI_API_KEY": "k-g", "DEEPSEEK_API_KEY": "k-d"}
DIRECT = "time:7\\ntired:3\\nrelationship:4\\ncharacter_state:9,25\\nexperience:81\\n"
CASES = [
    ("off", {1: 0}, {}),
    ("no_model", {5: ""}, {}),
    ("no_key", {}, {"keys": {}}),
    ("unsafe", {2: 0}, {"behavior": "hand_in_hand"}),
    ("safe", {2: 0}, {"text": "ok"}),
    ("not_di", {3: 0}, {"original": "口上"}),
    ("di", {3: 0}, {"original": "地文", "text": "ok"}),
    ("no_target", {}, {"target": 0}),
    ("openai", {4: 0, 8: 0}, {"text": "你 好\\n世界"}),
    ("openai_stream", {14: 1}, {"chunks": ["你", None, "好 ", "\\n"]}),
    ("deepseek", {5: "deepseek-chat", 10: 1, 11: 1}, {"text": "ok"}),
    ("gemini", {5: "gemini-x", 10: 1, 12: 1}, {"text": "ok"}),
    ("gemini_stream", {5: "gemini-x", 14: 1}, {"chunks": ["a", "", "b"]}),
    ("fail", {}, {"fail": True}),
    ("fail_stream", {14: 1}, {"fail": True}),
    ("think", {13: 1}, {"text": "<think>x</think>答"}),
    ("translator", {3: 0, 7: 1}, {"translator": True, "text": "a b\\nc"}),
    ("save", {7: 1}, {"text": "c1说c0"}),
    ("direct_off", {1: 0}, {"direct": True}),
    ("direct", {2: 0, 3: 0, 8: 0}, {"direct": True, "text": DIRECT + "text:你好\\\\n世界"}),
    ("direct_bad", {}, {"direct": True, "text": "time:x\\ncharacter_state:a,b\\nexperience:z\\nhi"}),
    ("direct_stream", {14: 1, 13: 1}, {
        "direct": True,
        "chunks": [DIRECT, "text", ":", "你好\\\\", "n世界", "<think>t</think>text:尾"],
    }),
    ("direct_stream_split", {14: 1}, {"direct": True, "chunks": ["time:1\\nte", "xt:末尾"]}),
    ("direct_stream_late", {14: 1}, {"direct": True, "chunks": ["time:3\\ntext:", "晚到"]}),
    ("direct_stream_inline", {14: 1}, {"direct": True, "chunks": ["tired:1\\ntext:开头", "下一段"]}),
]
payload["cases"] = {}
here = os.getcwd()
with working.based_on(core.state()):
    for name, settings, extra in CASES:
        ai.ai_chat_setting = {**BASE, **settings}
        ai.ai_chat_api_key = extra.get("keys", KEYS)
        reply.update(text=extra.get("text", ""), chunks=extra.get("chunks", []), fail=extra.get("fail", False))
        aim(0, extra.get("target", 1))
        log.clear()
        with tempfile.TemporaryDirectory() as folder:
            os.chdir(folder)
            try:
                try:
                    ret = hca.judge_use_text_ai(
                        0,
                        extra.get("behavior", "share_blankly"),
                        extra.get("original", "原文"),
                        Out(),
                        translator=extra.get("translator", False),
                        settle=settle if extra.get("direct") else None,
                    )
                except Settled:
                    ret = "<settled>"
                saved = None
                if os.path.exists("data/talk/ai/ai_talk.csv"):
                    with open("data/talk/ai/ai_talk.csv", encoding="utf-8") as file:
                        saved = file.read().splitlines()[5:]
            finally:
                os.chdir(here)
        payload["cases"][name] = {"ret": ret, "log": list(log), "saved": saved}
payload["connects"] = len(connects)
"""
""" 无界面子进程执行脚本：屏蔽网络连接并替换为替身客户端，依次运行 25 组文本AI用例。 """
NOTICE = ["show", "\n（正在调用m-test）\n", True]
""" 调用提示在输出日志中的记录项 """
OPENAI = "openai k-o | openai.create m-test ['system', 'user']"
""" openai 替身客户端默认请求日志前缀 """
SOURCE = "Script/Design/handle_chat_ai.py"
""" 待检导入边界的文本AI模块相对路径 """
FIELDS = (
    "time",
    "tired",
    "relationship",
    "character_state",
    "experience",
    "text",
)
""" DirectModeResult 的六个固定字段名元组 """


def result(*values: object) -> Any:
    """按 FIELDS 顺序将六个值组装为直接对话结果字典。"""
    return dict(zip(FIELDS, values, strict=True))


class ImportBoundaryTest(FastTestCase):
    """文本生成AI模块源码静态导入边界测试。"""

    def test_source_imports_no_ui(self) -> None:
        """断言 handle_chat_ai.py 不含受禁界面导入且不导入 handle_instruct。"""
        source = (ROOT / SOURCE).read_bytes()
        self.assertEqual(banned_imports(source, SOURCE), [])
        self.assertNotIn(
            "Script.System.Instruct_System.handle_instruct",
            imports_in(source.decode("utf-8"), "Script.Design"),
        )


class ChatAiUiFreeTest(FastTestCase):
    """无界面子进程下文本生成AI全流程用例测试。"""

    @classmethod
    def setUpClass(cls) -> None:
        """启动一次无界面子进程并缓存全部 25 组用例结果。"""
        super().setUpClass()
        cls.child = run_ui_free(CHILD_RUN, boot=True)
        cls.cases = cast(dict[str, dict[str, Any]], cls.child.payload["cases"])

    def case(self, name: str) -> tuple[Any, list[Any], Any]:
        """按用例名读取子进程返回的文本、输出日志与保存记录。"""
        found = self.cases[name]
        return found["ret"], found["log"], found["saved"]

    def shown(self, name: str) -> list[str]:
        """收集指定用例日志中各次 show 调用的显示文本列表。"""
        return [entry[1] for entry in self.case(name)[1] if entry[0] == "show"]

    def test_runs_without_ui_or_network(self) -> None:
        """断言子进程未加载或尝试导入受限模块且零网络连接。"""
        self.assertEqual((self.child.loaded, self.child.attempted), ([], []))
        self.assertEqual(self.child.payload["connects"], 0)

    def test_gates_return_original_text(self) -> None:
        """断言开关、模型、密钥、安全标签、地文规则与目标前置不满足时返回原文。"""
        for name in ("off", "no_model", "no_key", "unsafe", "no_target"):
            with self.subTest(name):
                self.assertEqual(self.case(name), ("原文", [], None))
        self.assertEqual(self.case("direct_off"), ("原文", [], None))
        self.assertEqual(self.case("not_di"), ("口上", [], None))

    def trace(self, name: str) -> tuple[Any, str]:
        """返回指定用例的结果文本及拼接后的日志摘要字符串。"""
        ret, log, _saved = self.case(name)
        return ret, " | ".join(" ".join(map(str, entry)) for entry in log)

    def test_openai_reply(self) -> None:
        """验证 openai 非流式回复、调用提示刷新、原文本拼接以及安全与地文放行分支。"""
        notice = "show \n（正在调用m-test）\n True | flush"
        self.assertEqual(
            self.trace("openai"),
            ("(原文本)原文\n你好世界", f"{notice} | {OPENAI} False"),
        )
        self.assertEqual(self.trace("safe"), ("ok", f"{OPENAI} False"))
        self.assertEqual(self.trace("di"), ("ok", f"{OPENAI} False"))

    def test_streams_show_each_chunk(self) -> None:
        """验证两套客户端库流式输出逐块刷新并在末尾输出等待换行。"""
        chunks = "show 你 False | flush | flush | show 好  False | flush"
        self.assertEqual(
            self.trace("openai_stream"),
            (
                "你好",
                f"{OPENAI} True | {chunks} | show \n False | flush | break",
            ),
        )
        self.assertEqual(
            self.trace("gemini_stream"),
            (
                "ab",
                "genai k-g None | genai.stream gemini-x True | show a False"
                " | flush | flush | show b False | flush | break",
            ),
        )

    def test_client_options(self) -> None:
        """验证自定义接口地址、代理与接口版本选项正确传给两套客户端库。"""
        self.assertEqual(
            self.trace("deepseek"),
            (
                "ok",
                "openai k-d | openai.options ['https://api.deepseek.com']"
                " | openai.options ['http://base.invalid']"
                " | openai.options ['httpx:http://proxy.invalid']"
                " | openai.create deepseek-chat ['system', 'user'] False",
            ),
        )
        self.assertEqual(
            self.trace("gemini"),
            (
                "ok",
                "genai k-g ['v1alpha', 'http://base.invalid']"
                " | genai.generate gemini-x True",
            ),
        )

    def test_failure_falls_back_to_original(self) -> None:
        """验证非流式与流式接口异常时回退原文本且流式异常不触发末尾换行。"""
        self.assertEqual(self.case("fail")[0], "(生成失败，使用原文本)原文")
        self.assertEqual(
            self.case("fail_stream")[0], "(生成失败，使用原文本)原文"
        )
        self.assertNotIn(["break"], self.case("fail_stream")[1])

    def test_text_cleanup(self) -> None:
        """验证思考标签过滤与翻译模式下保留空格的文本清理规则。"""
        self.assertEqual(self.case("think")[0], "答")
        self.assertEqual(self.case("translator")[0], "a bc")

    def test_save_record(self) -> None:
        """验证开启保存时写入替换角色名占位符的记录行且翻译模式不保存。"""
        self.assertEqual(
            self.case("save")[2],
            [
                "0,share_blankly,0,generate_by_ai&sys_0&sys_5,{TargetName}说{Name}"
            ],
        )
        self.assertIsNone(self.case("translator")[2])

    def test_direct_mode_settles_parsed_result(self) -> None:
        """验证直接对话模式解析结构化字段及非法数值回退默认值并传给 settle。"""
        ret, log, saved = self.case("direct")
        self.assertEqual((ret, saved), ("<settled>", None))
        self.assertEqual(log[0], NOTICE)
        parsed = result(7, 3, 4, [9, 25], 81, "你好\\n世界")
        self.assertEqual(log[-1], ["settle", parsed])
        defaults = result(5, 2, 2, -1, -1, "hi")
        self.assertEqual(self.case("direct_bad")[1][-1], ["settle", defaults])

    def test_direct_stream_shows_text_part(self) -> None:
        """验证直接对话流式输出在完整、拆分、延后与行内 text: 标记下按预期显示正文。"""
        log = self.case("direct_stream")[1]
        self.assertEqual(
            self.shown("direct_stream"),
            ["", "你好", "\n世界", "<think>t</think>尾"],
        )
        self.assertEqual(log[-2], ["break"])
        self.assertEqual(log[-1][1]["text"], "你好\\n世界text:尾")
        self.assertEqual(self.shown("direct_stream_late"), ["", "晚到"])
        self.assertEqual(self.shown("direct_stream_inline"), ["开头", "下一段"])
        self.assertEqual(self.shown("direct_stream_split"), ["末尾"])
