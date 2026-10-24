# -*- coding: UTF-8 -*-
"""
Web 模式下游戏等玩家输入文字时，有页面连上后各页面收到的完整游戏状态与常规更新相同
==================================================================================
开新游戏后切到 Web 模式，游戏线程走开局输入姓名的 input_name_func，停在 Web 版 askfor_str 等输入；
玩家的页面（一个 Socket.IO 测试客户端）收下常规更新，其中的 input_request 让前端把输入框里的文字提交给游戏。
另一个页面这时连上，服务器的 connect 处理函数把完整游戏状态 send_full_game_state 发给两个页面：
它的每个字段都与常规更新的相同（instruct_texts 与 other_texts 除外：这两项是常规更新从缓存取走的回溯文本），
其中有同样的 input_request。经输入框的提交接口送上姓名后，游戏线程拿到这个姓名。
"""

import threading
import time

from tests.slow.base import SlowTestCase

ONE_SHOT_FIELDS = {"instruct_texts", "other_texts"}
""" 常规更新从缓存取走、发出一次就清空的回溯文本字段 """

WAIT_LIMIT = 30
""" 等游戏线程发出输入请求或拿到输入的时限，秒 """


class WebFullStateInputWaitTest(SlowTestCase):
  """游戏等输入文字时，完整游戏状态与常规更新一样带着输入请求"""

  def setUp(self):
    """
    开新游戏，切到 Web 模式，玩家的页面连上 Web 服务器
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().setUp()
    from Script.Core import web_server

    self.web_server = web_server
    self.cache.web_mode = True
    self.player_page = web_server.socketio.test_client(web_server.app)
    self.player_page.get_received()

  def states(self, client) -> list:
    """
    取出客户端新收到的 game_state_update 消息
    Keyword arguments:
    client -- Socket.IO 测试客户端
    Return arguments:
    list -- 消息内容的列表
    """
    return [
        packet["args"][0]
        for packet in client.get_received()
        if packet["name"] == "game_state_update"
    ]

  def wait_for_input_request(self) -> dict:
    """
    等玩家的页面收到带输入请求的常规更新
    Keyword arguments:
    无
    Return arguments:
    dict -- 最后一条带 input_request 的消息
    """
    deadline = time.monotonic() + WAIT_LIMIT
    while time.monotonic() < deadline:
      received = [
          state
          for state in self.states(self.player_page)
          if "input_request" in state
      ]
      if received:
        return received[-1]
      time.sleep(0.1)
    self.fail("游戏没有发出输入请求")

  def full_state(self) -> dict:
    """
    另一个页面连上服务器
    Keyword arguments:
    无
    Return arguments:
    dict -- 这个页面连上时收到的完整游戏状态（玩家的页面收到同样的一条）
    """
    page = self.web_server.socketio.test_client(self.web_server.app)
    received = self.states(page)
    page.disconnect()
    self.assertEqual(len(received), 1)
    self.assertEqual(self.states(self.player_page), received)
    return received[0]

  def test_name_input(self):
    """开局输入姓名时：完整状态与常规更新相同，提交的姓名送到游戏线程"""
    from Script.Design import character

    names = []
    game_thread = threading.Thread(
        target=lambda: names.append(character.input_name_func("姓名？")),
        daemon=True,
    )
    game_thread.start()
    regular = self.wait_for_input_request()
    self.assertEqual(regular["input_request"]["type"], "string")
    full = self.full_state()
    fields = set(regular) - ONE_SHOT_FIELDS
    self.assertEqual(
        {field: full.get(field) for field in fields},
        {field: regular[field] for field in fields},
    )
    response = self.web_server.app.test_client().post(
        "/api/string_input", json={"value": "Testdoc"}
    )
    self.assertTrue(response.get_json()["success"])
    game_thread.join(WAIT_LIMIT)
    self.assertEqual(names, ["Testdoc"])
