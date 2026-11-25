"""
文本生成AI设置服务测试
======================
覆盖设置读写、发送数据、密钥存取、模型连通测试与面板联动。
"""

import concurrent.futures
import http.server
import json
import os
import tempfile
import threading
from types import SimpleNamespace
from typing import Any
from unittest import mock

from google import genai

from Script.Config import normal_config
from Script.Core import game_type
from Script.Modules.gameplay_resolution import chat_ai_setting_service as svc
from Script.UI.Moudle import draw
from Script.UI.Panel import chat_ai_setting
from tests.fast.base import FastTestCase

OPENAI = "OPENAI_API_KEY"
""" OpenAI API密钥键名常量。 """
GEMINI = "GEMINI_API_KEY"
""" Gemini API密钥键名常量。 """
DEEPSEEK = "DEEPSEEK_API_KEY"
""" DeepSeek API密钥键名常量。 """


class FakeServer(http.server.BaseHTTPRequestHandler):
    """模拟 OpenAI 与 Gemini 接口响应的本地回环 HTTP 处理器。"""

    lines: list[str] = []
    """ 记录模拟服务收到的 HTTP 请求行列表。 """

    def do_POST(self) -> None:
        """记录请求行并按路径返回 Gemini 或 OpenAI 格式的成功响应。"""
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        self.lines.append(self.requestline)
        reply: dict = {"id": "c1", "object": "chat.completion", "choices": []}
        if "generateContent" in self.path:
            reply = {"candidates": []}
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        """屏蔽标准库 HTTP 服务器的默认访问日志输出。"""


class ChatAiCase(FastTestCase):
    """文本生成AI设置测试基类，隔离配置、代理环境变量与临时工作目录。"""

    def setUp(self) -> None:
        """初始化独立 AI 设置对象，清理代理环境变量并切换至临时目录。"""
        super().setUp()
        self.ai = game_type.Ai_Setting()
        self.enterContext(
            mock.patch.object(normal_config, "ai_setting", self.ai)
        )
        env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}
        self.enterContext(mock.patch.dict(os.environ, env, clear=True))
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(folder)

    def serve(self) -> str:
        """启动本地回环模拟 HTTP 服务并返回其基础地址。"""
        FakeServer.lines = []
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeServer)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return f"http://127.0.0.1:{server.server_address[1]}"

    def key_file(self) -> list[str]:
        """读取当前临时目录下的密钥 CSV 文件并按行返回。"""
        with open(svc.KEY_FILE, encoding="utf-8") as f:
            return f.read().splitlines()


class SettingRowsTest(ChatAiCase):
    """测试设置项默认值补全、总开关截断与主列表值标签。"""

    def test_defaults_fill_missing_ids_only(self) -> None:
        """验证默认值读取与补全仅填充未登记项而不覆盖已有值。"""
        self.assertEqual((svc.setting_of(7), svc.setting_of(2)), (1, 0))
        self.ai.ai_chat_setting[7] = 0
        svc.fill_defaults()
        self.assertEqual(sorted(self.ai.ai_chat_setting), list(range(1, 15)))
        on = [cid for cid, value in self.ai.ai_chat_setting.items() if value]
        self.assertEqual(on, [12, 14])

    def test_master_switch_off_lists_only_itself(self) -> None:
        """验证总开关关闭时主列表仅返回总开关自身一行。"""
        rows = svc.setting_rows()
        self.assertEqual(
            [(row.cid, row.name, row.value, row.option_len) for row in rows],
            [(1, "是否使用本功能", " [否] ", 2)],
        )

    def test_value_labels_follow_each_setting(self) -> None:
        """验证开启后模型、发送数据、自定义地址与代理等值标签格式。"""
        svc.fill_defaults()
        svc.cycle(1, 2)
        svc.set_model("gpt-test")
        svc.set_talk_count("4")
        svc.set_base_url("http://chat.test/v1")
        svc.set_proxy_url("http://127.0.0.1:9")
        svc.set_local_ip("1")
        values = {row.cid: row.value for row in svc.setting_rows()}
        self.assertEqual(sorted(values), list(range(1, 15)))
        self.assertEqual(values[1], " [是] ")
        self.assertEqual(values[5], " [gpt-test] ")
        self.assertEqual(values[6], " [调整发送的数据] ")
        self.assertEqual(values[9], " [4] ")
        self.assertEqual(values[10], " [是] http://chat.test/v1")
        self.assertEqual(values[11], " [是] ip：http://127.0.0.1:9")
        svc.set_local_ip("127.0.0.2")
        values = {row.cid: row.value for row in svc.setting_rows()}
        self.assertEqual(
            values[11], " [是] ip：http://127.0.0.1:9 port：127.0.0.2"
        )
        svc.switch_off(10)
        values = {row.cid: row.value for row in svc.setting_rows()}
        self.assertEqual(values[10], " [否] ")


class SettingWritesTest(ChatAiCase):
    """测试设置循环切换、文本解析写入与语言翻译状态切换。"""

    def setUp(self) -> None:
        """在基类环境上补齐全部文本生成AI设置项默认值。"""
        super().setUp()
        svc.fill_defaults()

    def test_cycle_wraps_to_first_option(self) -> None:
        """验证普通设置项循环递增并在末尾后归零。"""
        seen = []
        for _ in range(3):
            svc.cycle(9, 10)
            seen.append(self.ai.ai_chat_setting[9])
        self.ai.ai_chat_setting[9] = 9
        svc.cycle(9, 10)
        self.assertEqual(seen + [self.ai.ai_chat_setting[9]], [1, 2, 3, 0])

    def test_talk_count_is_clamped(self) -> None:
        """验证生成数量输入减一后限制在 0 到 9 之间。"""
        counts = []
        for text in ("0", "5", "12"):
            svc.set_talk_count(text)
            counts.append(self.ai.ai_chat_setting[9])
        self.assertEqual(counts, [0, 4, 9])

    def test_base_url_drops_trailing_newline(self) -> None:
        """验证自定义接口地址去除末尾单个换行并开启设置项 10。"""
        svc.set_base_url("http://chat.test/v1\n")
        self.assertEqual(self.ai.now_ai_chat_base_url, "http://chat.test/v1")
        self.assertEqual(self.ai.ai_chat_setting[10], 1)

    def test_empty_text_clears_address(self) -> None:
        """验证写入空字符串时自定义地址、代理地址与本地 IP 均清空。"""
        svc.set_base_url("http://chat.test/v1")
        svc.set_proxy_url("http://127.0.0.1:9")
        svc.set_local_ip("127.0.0.2")
        for write in (svc.set_base_url, svc.set_proxy_url, svc.set_local_ip):
            write("")
        self.assertEqual(self.ai.now_ai_chat_base_url, "")
        self.assertEqual(self.ai.now_ai_chat_proxy, ["", ""])

    def test_local_ip_needs_three_dots(self) -> None:
        """验证本地 IP 仅在恰含三个点时保留并开启设置项 11。"""
        svc.set_proxy_url("http://127.0.0.1:9\n")
        svc.set_local_ip("1\n")
        self.assertEqual(self.ai.now_ai_chat_proxy, ["http://127.0.0.1:9", ""])
        self.assertEqual(self.ai.ai_chat_setting[11], 1)
        svc.set_local_ip("127.0.0.2\n")
        self.assertEqual(self.ai.now_ai_chat_proxy[1], "127.0.0.2")

    def test_translator_cycles_three_states(self) -> None:
        """验证翻译设置按三态循环，非法取值时标签返回 None。"""
        labels = [svc.translator_label()]
        for _ in range(3):
            svc.next_translator()
            labels.append(svc.translator_label())
        self.assertEqual(
            labels,
            [
                " [未开启] ",
                " [仅翻译地文] ",
                " [翻译地文和口上] ",
                " [未开启] ",
            ],
        )
        self.ai.ai_chat_translator_setting = 3
        self.assertIsNone(svc.translator_label())


class SendDataTest(ChatAiCase):
    """测试发送数据列表默认值初始化与单项开关翻转。"""

    def test_rows_fill_flags_from_defaults(self) -> None:
        """验证发送数据列表按配置默认标志初始化未登记项开关而不覆盖已有值。"""
        self.ai.send_data_flags[11] = False
        rows = {row.cid: row for row in svc.send_data_rows()}
        self.assertEqual(
            (rows[1].name, rows[1].size, rows[1].required, rows[1].chosen),
            ("角色名", "小", True, True),
        )
        self.assertEqual((rows[11].size, rows[11].chosen), ("中", False))
        self.assertEqual((rows[42].size, rows[42].chosen), ("小", False))
        self.assertEqual((rows[101].size, rows[101].required), ("大", False))
        self.assertEqual(set(self.ai.send_data_flags), set(rows))
        self.assertEqual(self.ai.send_data_flags[54], True)

    def test_toggle_flips_one_flag(self) -> None:
        """验证切换单个发送数据项仅翻转对应开关状态。"""
        svc.send_data_rows()
        svc.toggle_send_data(42)
        svc.toggle_send_data(54)
        chosen = {row.cid: row.chosen for row in svc.send_data_rows()}
        self.assertEqual(
            (chosen[42], chosen[54], chosen[41]), (True, False, True)
        )


class ApiKeyTest(ChatAiCase):
    """测试API密钥的内存与文件保存、读取与前缀校验。"""

    def test_save_writes_memory_and_file(self) -> None:
        """验证保存密钥同步更新内存并在 CSV 文件中覆盖或追加。"""
        svc.save_api_key(OPENAI, "sk-a")
        svc.save_api_key(GEMINI, "g-key")
        svc.save_api_key(OPENAI, "sk-b")
        self.assertEqual(self.key_file(), [f"{OPENAI},sk-b", f"{GEMINI},g-key"])
        self.assertEqual(
            self.ai.ai_chat_api_key, {OPENAI: "sk-b", GEMINI: "g-key"}
        )

    def test_failed_write_keeps_memory_key(self) -> None:
        """验证密钥文件写入抛出 OSError 时内存中的原密钥保持不变。"""
        self.ai.ai_chat_api_key[OPENAI] = "sk-old"
        self.enterContext(mock.patch.object(svc, "KEY_FILE", "no_dir/keys.csv"))
        with self.assertRaises(OSError):
            svc.save_api_key(OPENAI, "sk-new")
        self.assertEqual(self.ai.ai_chat_api_key, {OPENAI: "sk-old"})

    def test_load_reads_known_key_rows(self) -> None:
        """验证缺失文件时无改动，读取文件时仅载入已识别密钥类型。"""
        svc.load_api_keys()
        self.assertEqual(self.ai.ai_chat_api_key, {})
        with open(svc.KEY_FILE, "w", encoding="utf-8") as f:
            f.write(f"OTHER_KEY,x\n{DEEPSEEK},sk-d\n{GEMINI},\n")
        svc.load_api_keys()
        self.assertEqual(
            self.ai.ai_chat_api_key, {DEEPSEEK: "sk-d", GEMINI: ""}
        )
        self.assertEqual(
            [svc.key_filled(key) for key in svc.KEY_TYPES], [False, False, True]
        )

    def test_sk_prefix_checked_for_openai_format_keys(self) -> None:
        """验证 OpenAI 与 DeepSeek 校验 sk- 前缀而 Gemini 直接通过。"""
        checks = [
            svc.key_format_ok(OPENAI, "abc"),
            svc.key_format_ok(OPENAI, "sk-1"),
            svc.key_format_ok(DEEPSEEK, "abc"),
            svc.key_format_ok(GEMINI, "abc"),
        ]
        self.assertEqual(checks, [False, True, False, True])


class UnfilledSettingTest(ChatAiCase):
    """测试未补全默认值时模型密钥识别与客户端构造的默认读取。"""

    def test_client_reads_defaults_before_fill(self) -> None:
        """验证未补全默认值时 model_key 返回 None 且 make_client 按默认设置构造客户端。"""
        self.assertIsNone(svc.model_key())
        self.ai.ai_chat_api_key[DEEPSEEK] = "sk-d"
        client = svc.make_client(DEEPSEEK)
        self.assertEqual(str(client.base_url), "https://api.deepseek.com")
        svc.set_model("gemini-test")
        svc.set_base_url(self.serve() + "/")
        self.ai.ai_chat_api_key[GEMINI] = "g-key"
        error = svc.ping(svc.make_client(GEMINI), GEMINI, lambda text: None)
        self.assertIsNone(error)
        self.assertIn("/v1alpha/models/gemini-test:", FakeServer.lines[0])


class ModelTest(ChatAiCase):
    """测试模型密钥类型识别、客户端配置、代理请求与超时错误处理。"""

    def setUp(self) -> None:
        """在基类环境上补齐全部文本生成AI设置项默认值。"""
        super().setUp()
        svc.fill_defaults()

    def test_model_name_picks_key_type(self) -> None:
        """验证未设模型返回 None，已知前缀匹配对应密钥，未知回退 OpenAI。"""
        expected = {
            0: None,
            "0": None,
            "gpt-4o": (OPENAI, True),
            "deepseek-chat": (DEEPSEEK, True),
            "gemini-2.5-pro": (GEMINI, True),
            "x": (OPENAI, False),
        }
        for model, key in expected.items():
            with self.subTest(model=model):
                self.ai.ai_chat_setting[5] = model
                self.assertEqual(svc.model_key(), key)

    def test_client_needs_saved_key(self) -> None:
        """验证未保存密钥时返回 None，DeepSeek 默认使用官方接口地址。"""
        self.assertIsNone(svc.make_client(OPENAI))
        self.ai.ai_chat_api_key[DEEPSEEK] = "sk-d"
        client = svc.make_client(DEEPSEEK)
        self.assertEqual(str(client.base_url), "https://api.deepseek.com")

    def test_ping_reaches_custom_base_url(self) -> None:
        """验证开启自定义地址时连通测试请求发往指定回环服务。"""
        svc.set_model("gpt-test")
        svc.set_base_url(self.serve() + "/v1")
        self.ai.ai_chat_api_key[OPENAI] = "sk-a"
        shown: list[str] = []
        error = svc.ping(svc.make_client(OPENAI), OPENAI, shown.append)
        self.assertEqual((error, shown), (None, [" \n  测试通过\n"]))
        self.assertEqual(
            FakeServer.lines, ["POST /v1/chat/completions HTTP/1.1"]
        )

    def test_ping_goes_through_proxy(self) -> None:
        """验证开启代理时 OpenAI 连通测试请求经由代理地址发送。"""
        svc.set_model("gpt-test")
        svc.set_base_url("http://chat.test/v1")
        svc.set_proxy_url(self.serve())
        svc.set_local_ip("1")
        self.ai.ai_chat_api_key[OPENAI] = "sk-a"
        error = svc.ping(svc.make_client(OPENAI), OPENAI, lambda text: None)
        self.assertIsNone(error)
        self.assertEqual(
            FakeServer.lines,
            ["POST http://chat.test/v1/chat/completions HTTP/1.1"],
        )

    def test_gemini_rest_option_picks_api_version(self) -> None:
        """验证设置项 12 控制 google.genai 请求在 v1alpha 与默认接口版本间切换。"""
        svc.set_model("gemini-test")
        url = self.serve() + "/"
        svc.set_base_url(url)
        self.ai.ai_chat_api_key[GEMINI] = "g-key"
        for _ in range(2):
            error = svc.ping(svc.make_client(GEMINI), GEMINI, lambda text: None)
            self.assertIsNone(error)
            svc.cycle(12, 2)
        options = genai.types.HttpOptions(base_url=url)
        sdk = genai.Client(api_key="g-key", http_options=options)
        sdk.models.generate_content(model="gemini-test", contents="1")
        alpha, off, default = FakeServer.lines
        self.assertIn("POST /v1alpha/models/gemini-test:generateContent", alpha)
        self.assertNotIn("v1alpha", default)
        self.assertEqual(off, default)

    def test_failed_call_reports_error(self) -> None:
        """验证模型调用抛出异常时返回异常文本并回调展示失败信息。"""

        def fail(**kwargs: object) -> None:
            """模拟模型接口调用抛出 RuntimeError 异常。"""
            raise RuntimeError("boom")

        client = SimpleNamespace(models=SimpleNamespace(generate_content=fail))
        shown: list[str] = []
        error = svc.ping(client, GEMINI, shown.append)
        self.assertEqual(
            (error, shown), ("boom", [" \n  测试不通过，原因：boom\n"])
        )

    def test_timeout_is_shown_before_waiting_for_call(self) -> None:
        """验证请求超时时先回调展示超时信息再等待后台调用结束。"""
        gate = threading.Event()
        started = threading.Event()
        released: list[bool] = []
        shown: list[str] = []

        def create(**kwargs: object) -> None:
            """标记请求已启动，阻塞等待放行事件并记录等待结果。"""
            started.set()
            released.append(gate.wait(5))

        submit = concurrent.futures.ThreadPoolExecutor.submit

        def submit_started(
            pool: concurrent.futures.ThreadPoolExecutor, *args: Any
        ) -> concurrent.futures.Future:
            """提交线程池任务并等待后台请求启动后再返回 future。"""
            future = submit(pool, *args)
            started.wait(5)
            return future

        def show(text: str) -> None:
            """记录回调文本并释放阻塞中的模拟请求线程。"""
            shown.append(text)
            gate.set()

        pool = concurrent.futures.ThreadPoolExecutor
        self.enterContext(mock.patch.object(pool, "submit", submit_started))
        self.enterContext(mock.patch.object(svc, "TEST_SECONDS", 0.05))
        completions = SimpleNamespace(create=create)
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        error = svc.ping(client, OPENAI, show)
        self.assertEqual(
            (error, shown, released),
            ("连接超时", [" \n  测试不通过，原因：连接超时\n"], [True]),
        )


class PanelTest(ChatAiCase):
    """测试设置面板与服务在模型测试与结果绘制上的联动。"""

    def setUp(self) -> None:
        """替换面板文本绘制方法以收集输出，并开启主开关与默认值。"""
        super().setUp()
        self.texts: list[str] = []

        def record(drawn: draw.NormalDraw) -> None:
            """收集面板绘制对象的文本内容到列表。"""
            self.texts.append(drawn.text)

        for cls in (draw.NormalDraw, draw.WaitDraw):
            self.enterContext(mock.patch.object(cls, "draw", record))
        svc.fill_defaults()
        svc.cycle(1, 2)

    def test_test_button_shows_result_and_model(self) -> None:
        """验证未设模型给出提示，测试通过后更新标志并绘制当前模型名。"""
        now_panel = chat_ai_setting.Chat_Ai_Setting_Panel(80)
        now_panel.test_ai()
        self.assertEqual(self.texts, [" \n  未设置模型，请先选择模型\n"])
        svc.set_model("gpt-test")
        svc.set_base_url(self.serve() + "/v1")
        self.ai.ai_chat_api_key[OPENAI] = "sk-a"
        now_panel.test_ai()
        self.texts.clear()
        now_panel.draw_test([])
        self.assertIn(" \n  测试通过，当前调用的模型为：gpt-test\n", self.texts)
        self.assertEqual(now_panel.test_flag, 1)
