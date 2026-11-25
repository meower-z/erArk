"""
文本生成AI设置服务导入隔离测试
==============================
在拦截界面与结算模块的独立子进程中验证服务调用边界。
"""

import json
import os
import subprocess
import sys
import tempfile

from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

OPENAI = "OPENAI_API_KEY"
""" OpenAI API密钥键名常量。 """
GEMINI = "GEMINI_API_KEY"
""" Gemini API密钥键名常量。 """
BACKEND_RUN = """
import contextlib, importlib.abc, io, json, os, sys, threading
from types import SimpleNamespace
BLOCKED = ("Script.UI", "Script.Settle",
    "Script.System.Instruct_System.handle_instruct", "Script.Core.flow_handle",
    "Script.Core.io_init", "Script.Frontend", "Script.Modules.tk_ui",
    "tkinter", "_tkinter", "PIL.ImageTk")
attempted = []
def blocked(name):
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if blocked(fullname):
            attempted.append(fullname)
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Blocker())
sys.path.insert(0, sys.argv[1])
from Script.Config import game_config, normal_config
with contextlib.redirect_stdout(io.StringIO()):
    normal_config.init_normal_config()
    game_config.init()
from Script.Modules.gameplay_resolution import chat_ai_setting_service as svc
ai = normal_config.ai_setting
os.chdir(sys.argv[2])
out = {}
out["off"] = [row.cid for row in svc.setting_rows()]
svc.fill_defaults()
svc.cycle(1, 2)
svc.set_model("gpt-test")
svc.set_talk_count("12")
svc.set_base_url("http://chat.test/v1\\n")
svc.set_proxy_url("http://127.0.0.1:9\\n")
svc.set_local_ip("127.0.0.2\\n")
out["rows"] = [[row.cid, row.value, row.option_len] for row in svc.setting_rows()]
svc.switch_off(11)
svc.next_translator()
out["translator"] = svc.translator_label()
rows = svc.send_data_rows()
svc.toggle_send_data(42)
out["send"] = [[row.cid, row.size, row.required, row.chosen] for row in rows[:4]]
out["flag42"] = ai.send_data_flags[42]
svc.save_api_key("OPENAI_API_KEY", "sk-a")
svc.save_api_key("GEMINI_API_KEY", "g-key")
ai.ai_chat_api_key.clear()
svc.load_api_keys()
out["keys"] = dict(ai.ai_chat_api_key)
out["format"] = [svc.key_format_ok("DEEPSEEK_API_KEY", "x"), svc.key_filled("GEMINI_API_KEY")]
out["model"] = list(svc.model_key())
ai.ai_chat_api_key["DEEPSEEK_API_KEY"] = "sk-d"
out["deepseek"] = str(svc.make_client("DEEPSEEK_API_KEY").base_url)
ai.ai_chat_setting[11] = 1
out["openai"] = str(svc.make_client("OPENAI_API_KEY").base_url)
ai.ai_chat_setting[12] = 1
out["gemini"] = type(svc.make_client("GEMINI_API_KEY")).__module__
reply = SimpleNamespace(create=lambda **kw: kw["model"])
shown = []
out["pass"] = svc.ping(SimpleNamespace(chat=SimpleNamespace(completions=reply)), "OPENAI_API_KEY", shown.append)
def fail(**kw):
    raise RuntimeError("boom")
out["fail"] = svc.ping(SimpleNamespace(models=SimpleNamespace(generate_content=fail)), "GEMINI_API_KEY", shown.append)
gate = threading.Event()
svc.TEST_SECONDS = 0.05
slow = SimpleNamespace(create=lambda **kw: gate.wait(5))
def release(text):
    shown.append(text)
    gate.set()
out["slow"] = svc.ping(SimpleNamespace(chat=SimpleNamespace(completions=slow)), "OPENAI_API_KEY", release)
out["shown"] = shown
out["attempted"] = attempted
out["loaded"] = sorted(
    name for name in sys.modules
    if name.startswith(("Script.UI", "Script.Settle")) or blocked(name)
)
print(json.dumps(out))
"""
""" 在拦截界面与结算模块的子进程中运行服务各接口的脚本。 """


class BackendIsolationTest(FastTestCase):
    """测试服务在拦截界面与结算模块的独立子进程中的导入边界。"""

    def test_fresh_backend_process_loads_no_ui_or_settle(self) -> None:
        """验证独立子进程执行服务各接口时未加载或尝试导入受限模块。"""
        env = {k: v for k, v in os.environ.items() if "proxy" not in k.lower()}
        env["PYTHONIOENCODING"] = "utf-8"
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run(
                [sys.executable, "-c", BACKEND_RUN, str(ROOT), folder],
                cwd=ROOT,
                env=env,
                check=False,
                capture_output=True,
                encoding="utf-8",
                timeout=300,
            )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        out = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(out["attempted"], [])
        self.assertEqual(out["loaded"], [])
        self.assertEqual(out["off"], [1])
        rows = {cid: [value, size] for cid, value, size in out["rows"]}
        self.assertEqual(len(rows), 14)
        self.assertEqual(rows[1], [" [是] ", 2])
        self.assertEqual(rows[5], [" [gpt-test] ", 7])
        self.assertEqual(rows[9], [" [10] ", 10])
        self.assertEqual(rows[10], [" [是] http://chat.test/v1", 2])
        self.assertEqual(
            rows[11], [" [是] ip：http://127.0.0.1:9 port：127.0.0.2", 2]
        )
        self.assertEqual(out["translator"], " [仅翻译地文] ")
        self.assertEqual(
            out["send"],
            [
                [1, "小", True, True],
                [2, "小", True, True],
                [3, "小", True, True],
                [11, "中", False, True],
            ],
        )
        self.assertTrue(out["flag42"])
        self.assertEqual(out["keys"], {OPENAI: "sk-a", GEMINI: "g-key"})
        self.assertEqual(out["format"], [False, True])
        self.assertEqual(out["model"], [OPENAI, True])
        self.assertEqual(out["deepseek"], "http://chat.test/v1/")
        self.assertEqual(out["openai"], "http://chat.test/v1/")
        self.assertEqual(out["gemini"], "google.genai.client")
        self.assertEqual(
            [out["pass"], out["fail"], out["slow"]],
            [None, "boom", "连接超时"],
        )
        self.assertEqual(
            out["shown"],
            [
                " \n  测试通过\n",
                " \n  测试不通过，原因：boom\n",
                " \n  测试不通过，原因：连接超时\n",
            ],
        )
