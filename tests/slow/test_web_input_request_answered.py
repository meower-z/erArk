# -*- coding: UTF-8 -*-
"""
Web 模式下答完文字输入后，状态不带输入请求，没人等的文字不留给下一次输入
========================================================================
开新游戏后切到 Web 模式。游戏线程依次走开局输入姓名的 input_name_func、免责声明面板 confirm_game_info_panel
（等玩家点按钮）、再一次 input_name_func。玩家的页面（一个 Socket.IO 测试客户端）经输入框的提交接口送上姓名，
经按钮接口点按钮。
送上第一个姓名后，免责声明面板的常规更新与 /api/get_state 都不带 input_request；
免责声明面板等按钮时送到提交接口的文字被拒，第二次输入姓名拿到的是玩家在那里送上的姓名。
"""

import threading
import time

from typing import TYPE_CHECKING

from tests.slow.base import SlowTestCase

if TYPE_CHECKING:
  from collections.abc import Callable

WAIT_LIMIT = 30
""" 等游戏线程发出更新或拿到输入的时限，秒 """


class WebInputRequestAnsweredTest(SlowTestCase):
  """玩家答完文字输入后，常规更新不带输入请求，没人等时送上的文字不留给下一次输入"""

  def setUp(self) -> None:
    """
    开新游戏，切到 Web 模式，玩家的页面连上 Web 服务器；游戏线程开始走两次输入姓名、中间一个按钮面板
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().setUp()
    from Script.Core import web_server
    from Script.Design import character
    from Script.UI.Flow import creator_character_flow

    self.web_server = web_server
    self.cache.web_mode = True
    self.player_page = web_server.socketio.test_client(web_server.app)
    self.player_page.get_received()
    self.http = web_server.app.test_client()
    self.names: list[str] = []

    def play() -> None:
      """依次输入姓名、读免责声明、再输入姓名"""
      self.names.append(character.input_name_func("姓名？"))
      creator_character_flow.confirm_game_info_panel()
      self.names.append(character.input_name_func("姓名？"))

    self.game_thread = threading.Thread(target=play, daemon=True)
    self.game_thread.start()

  def next_state(self, wanted: "Callable[[dict], bool]") -> dict:
    """
    等玩家的页面收到满足条件的 game_state_update
    Keyword arguments:
    wanted -- 判断一条消息是否是要等的那条的函数
    Return arguments:
    dict -- 第一条满足条件的消息
    """
    deadline = time.monotonic() + WAIT_LIMIT
    while time.monotonic() < deadline:
      for packet in self.player_page.get_received():
        if packet["name"] == "game_state_update" and wanted(packet["args"][0]):
          return packet["args"][0]
      time.sleep(0.1)
    self.fail("玩家的页面没有收到要等的更新")

  def submit_name(self, name: str) -> dict:
    """
    玩家的页面等到输入请求，经输入框的提交接口送上姓名
    Keyword arguments:
    name -- 送上的姓名
    Return arguments:
    dict -- 提交接口的回复
    """
    self.next_state(lambda state: "input_request" in state)
    return self.http.post("/api/string_input", json={"value": name}).get_json()

  def wait_disclaimer(self) -> dict:
    """
    等玩家的页面收到免责声明面板的常规更新
    Keyword arguments:
    无
    Return arguments:
    dict -- 带免责声明按钮的那条更新
    """
    return self.next_state(lambda state: bool(state.get("buttons")))

  def test_update_after_answer(self) -> None:
    """送上姓名后，下一个面板的常规更新与 /api/get_state 都不带输入请求"""
    self.assertTrue(self.submit_name("Testdoc")["success"])
    disclaimer = self.wait_disclaimer()
    self.assertEqual(self.names, ["Testdoc"])
    self.assertNotIn("input_request", disclaimer)
    self.assertNotIn(
        "input_request", self.http.get("/api/get_state").get_json()
    )

  def test_text_while_no_input_wait(self) -> None:
    """免责声明面板等按钮时送上的文字被拒，第二次输入姓名拿到玩家在那里送上的姓名"""
    self.submit_name("Testdoc")
    disclaimer = self.wait_disclaimer()
    stray = self.http.post("/api/string_input", json={"value": "Stray"})
    self.http.post(
        "/api/button_click", json={"button_id": disclaimer["buttons"][0]["id"]}
    )
    self.submit_name("Second")
    self.game_thread.join(WAIT_LIMIT)
    self.assertEqual(self.names, ["Testdoc", "Second"])
    self.assertFalse(stray.get_json()["success"])
