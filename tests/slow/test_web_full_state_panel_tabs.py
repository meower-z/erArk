# -*- coding: UTF-8 -*-
"""
Web 模式下新客户端连接时收到的完整游戏状态，带着与常规更新相同的面板选项卡
==========================================================================
开新游戏后，玩家的页面（一个 Socket.IO 测试客户端）先连上，收下常规更新 update_game_state；
另一个页面再连上时，服务器的 connect 处理函数发出完整游戏状态 send_full_game_state。
主界面：完整状态的 panel_tabs 列出主面板与满足前提的系统面板选项卡，系统面板选项卡的名字是指令名。
打开系统面板（子面板模式）后：完整状态同常规更新一样带 sub_panel_mode 与 sub_panel_data，
前端靠这两项在子面板上方画场景信息栏与选项卡栏；完整状态的两份选项卡都与常规更新的相同。
"""

from typing import TYPE_CHECKING

from tests.slow.base import SlowTestCase

if TYPE_CHECKING:
  from flask_socketio import SocketIOTestClient


class WebFullStatePanelTabsTest(SlowTestCase):
  """新客户端连接时的完整游戏状态与常规更新带同样的面板选项卡"""

  def setUp(self) -> None:
    """
    开新游戏，玩家的页面连上 Web 服务器
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().setUp()
    from Script.Core import web_server

    self.web_server = web_server
    self.player_page = web_server.socketio.test_client(web_server.app)
    self.player_page.get_received()

  def states(self, client: "SocketIOTestClient") -> list:
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

  def regular_update(self) -> dict:
    """
    像面板画完一屏时那样推送一次常规更新
    Keyword arguments:
    无
    Return arguments:
    dict -- 玩家的页面收到的那条消息
    """
    self.web_server.update_game_state([{"type": "text", "text": "面板内容"}])
    received = self.states(self.player_page)
    self.assertEqual(len(received), 1)
    return received[0]

  def full_state(self) -> dict:
    """
    另一个页面连上服务器
    Keyword arguments:
    无
    Return arguments:
    dict -- 这个页面连上时收到的完整游戏状态
    """
    page = self.web_server.socketio.test_client(self.web_server.app)
    received = self.states(page)
    page.disconnect()
    self.player_page.get_received()
    self.assertEqual(len(received), 1)
    return received[0]

  def assert_named_tabs(self, tabs: list) -> None:
    """
    选项卡里有主面板，系统面板选项卡至少一个，且各自的名字是对应指令的名字
    Keyword arguments:
    tabs -- 选项卡列表
    Return arguments:
    无
    """
    from Script.Core import constant

    self.assertEqual([tab["type"] for tab in tabs].count("main"), 1)
    panel_tabs = [tab for tab in tabs if tab["type"] == "panel"]
    self.assertTrue(panel_tabs)
    for tab in panel_tabs:
      self.assertEqual(
          tab["name"], constant.handle_instruct_name_data[tab["id"]]
      )

  def test_main_scene(self) -> None:
    """主界面：完整状态列出主面板与系统面板选项卡，不在子面板模式"""
    self.regular_update()
    full = self.full_state()
    self.assert_named_tabs(full["panel_tabs"])
    self.assertFalse(full["sub_panel_mode"])

  def test_sub_panel(self) -> None:
    """打开系统面板后：完整状态的子面板数据与选项卡与常规更新的相同"""
    from Script.System.Web_Draw_System import TabMenu, enter_sub_panel_mode

    main_tabs = TabMenu().get_panel_tabs()
    opened = next(tab for tab in main_tabs if tab["type"] == "panel")
    enter_sub_panel_mode(opened["id"], opened["name"])
    regular = self.regular_update()
    full = self.full_state()
    self.assertTrue(full["sub_panel_mode"])
    self.assertEqual(full["sub_panel_data"], regular["sub_panel_data"])
    self.assert_named_tabs(full["panel_tabs"])
    self.assertEqual(
        full["panel_tabs"], regular["sub_panel_data"]["panel_tabs"]
    )
    active = [tab["id"] for tab in full["panel_tabs"] if tab["active"]]
    self.assertEqual(active, [opened["id"]])
