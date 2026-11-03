# -*- coding: UTF-8 -*-
"""
文本生成AI的自定义代理
======================
在「文本生成AI设置」面板里开启自定义代理后，OpenAI 类模型的请求要经代理发出，聊天的地文显示生成的文本，面板的测试也要通过。

每个测试在新游戏里让博士走到 NPC_NAME 指定的角色身边，再经面板的按钮与输入填好全部设置。
代理是本进程里只监听 127.0.0.1 的假代理，它按聊天接口的格式回一段固定文本。
接口地址用 http://，请求因此以明文到达假代理，假代理能记下完整的请求行。
面板写的密钥文件与 AI 地文记录都落在临时目录里。
"""

import http.server
import importlib
import json
import os
import tempfile
import threading

from tests import snapshot_states
from tests.slow.base import SlowTestCase

BASE_URL = "http://chat.test/v1"
""" 面板里填的自定义接口地址 """

MODEL = "test-chat-model"
""" 面板里填的模型名，游戏按 OpenAI 类模型调用它 """

REPLY_TEXT = "假代理返回的地文"
""" 假代理回的生成文本 """

NPC_NAME = "杜宾"
""" 博士聊天对象的名字，该角色没有自己的口上，所以聊天的文本是地文 """


class FakeProxy(http.server.BaseHTTPRequestHandler):
  """假的 HTTP 代理：记下收到的请求行，按聊天接口的格式回 REPLY_TEXT"""

  request_lines: list[str] = []
  """ 本测试里假代理收到的请求行，按收到的顺序 """

  def handle_one_request(self) -> None:
    """
    读一个请求并记下请求行，请求体要求流式时按流式格式回 REPLY_TEXT，否则回一次性的 JSON
    Keyword arguments:
    无
    Return arguments:
    无
    """
    self.raw_requestline = self.rfile.readline(65537)
    if not self.parse_request():
      return
    body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
    self.request_lines.append(self.requestline)
    if json.loads(body).get("stream"):
      chunk = {
          "id": "c1",
          "object": "chat.completion.chunk",
          "created": 0,
          "model": MODEL,
          "choices": [
              {
                  "index": 0,
                  "delta": {"role": "assistant", "content": REPLY_TEXT},
                  "finish_reason": None,
              }
          ],
      }
      payload = (
          f"data: {json.dumps(chunk, ensure_ascii=False)}\n\ndata: [DONE]\n\n"
      )
      content_type = "text/event-stream"
    else:
      reply = {
          "id": "c1",
          "object": "chat.completion",
          "created": 0,
          "model": MODEL,
          "choices": [
              {
                  "index": 0,
                  "message": {"role": "assistant", "content": REPLY_TEXT},
                  "finish_reason": "stop",
              }
          ],
      }
      payload = json.dumps(reply, ensure_ascii=False)
      content_type = "application/json"
    data = payload.encode()
    self.send_response(200)
    self.send_header("Content-Type", content_type)
    self.send_header("Content-Length", str(len(data)))
    self.send_header("Connection", "close")
    self.end_headers()
    self.wfile.write(data)

  def log_message(self, *args: object) -> None:
    """不打印访问日志"""


class ChatAiCustomProxyTest(SlowTestCase):
  """开启自定义代理后，聊天的地文与面板的测试都要经代理拿到生成结果"""

  def setUp(self) -> None:
    """
    启动假代理，让博士走到 NPC_NAME 指定的角色身边并选该角色为交互对象，再把工作目录换成临时目录
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().setUp()
    self.constant = importlib.import_module("Script.Core.constant")
    FakeProxy.request_lines = []
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeProxy)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    self.addCleanup(server.server_close)
    self.addCleanup(server.shutdown)
    self.proxy_url = f"http://127.0.0.1:{server.server_address[1]}"
    npc = snapshot_states.npc_id(self.world, NPC_NAME)
    pl = self.cache.character_data[0]
    for _ in range(10):
      if self.cache.character_data[npc].position == pl.position:
        break
      snapshot_states.walk(
          self.world, list(self.cache.character_data[npc].position)
      )
    self.assertEqual(self.cache.character_data[npc].position, pl.position)
    pl.target_character_id = npc
    temp_dir = tempfile.TemporaryDirectory()
    self.addCleanup(temp_dir.cleanup)
    self.addCleanup(os.chdir, os.getcwd())
    os.chdir(temp_dir.name)

  def enter_settings(self, local_ip: str) -> None:
    """
    经「文本生成AI设置」面板开启文本生成AI，设为对所有地文生成，并填模型名、自定义代理、本地绑定 IP、自定义接口地址与 API 密钥
    Keyword arguments:
    local_ip -- 面板询问本地绑定 IP 时输入的文字
    Return arguments:
    无
    """
    player = self.world.player
    player.press(
        "[文本生成AI设置]",
        "我已阅读并同意以上所有免责事项",
        "[否]",
        "[仅当文本为",
        " [0] ",
    )
    player.type(MODEL)
    # 几个按钮都含 [否] 时，press 按最后画出的那个。
    # 此时显示 [否] 的按画出顺序是选项 10、11、13，所以第一下把选项 13 切成是，第二下才按到选项 11，面板随后询问代理与本地 IP。
    player.press("[否]", "[否]")
    player.type(self.proxy_url)
    player.type(local_ip)
    player.press("[否]")
    player.type(BASE_URL)
    player.press("[更改OpenAI API密钥]")
    player.type("sk-test")
    player.press("[确定]", "[返回]", "[返回]")
    snapshot_states.instruct(self.world, self.constant.Instruct.SYSTEM_SETTING)
    self.assertEqual(self.cache.ai_setting.now_ai_chat_proxy[0], self.proxy_url)

  def check_chat_and_test_button(self) -> None:
    """
    博士用聊天指令后屏幕显示假代理的文本，面板的测试显示测试通过，假代理正好收到两个发往自定义接口地址的请求
    Keyword arguments:
    无
    Return arguments:
    无
    """
    player = self.world.player
    start = len(player.screen)
    snapshot_states.instruct(self.world, self.constant.Instruct.CHAT)
    self.assertTrue(
        any(REPLY_TEXT in line for line in player.screen[start:]),
        "聊天的地文显示假代理返回的文本",
    )
    player.planned.clear()
    self.cache.now_panel_id = self.constant.Panel.IN_SCENE
    start = len(player.screen)
    snapshot_states.instruct(
        self.world,
        self.constant.Instruct.SYSTEM_SETTING,
        ("[文本生成AI设置]", "[测试]", "[返回]", "[返回]"),
    )
    self.assertTrue(
        any("测试通过" in line for line in player.screen[start:]),
        "面板的测试通过",
    )
    self.assertEqual(
        FakeProxy.request_lines,
        [f"POST {BASE_URL}/chat/completions HTTP/1.1"] * 2,
    )

  def test_proxy(self) -> None:
    """本地 IP 一栏输入数字 1，面板把本地 IP 存为空"""
    self.enter_settings("1")
    self.assertEqual(self.cache.ai_setting.now_ai_chat_proxy[1], "")
    self.check_chat_and_test_button()

  def test_proxy_with_local_ip(self) -> None:
    """本地 IP 一栏输入 127.0.0.2，面板存下这个本地 IP"""
    self.enter_settings("127.0.0.2")
    self.assertEqual(self.cache.ai_setting.now_ai_chat_proxy[1], "127.0.0.2")
    self.check_chat_and_test_button()
