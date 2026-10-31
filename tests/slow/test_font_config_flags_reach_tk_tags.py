# -*- coding: UTF-8 -*-
"""
字体配置里的加粗、下划线、斜体到达 Tk 文本框的标签
==================================================
照游戏启动的顺序：载入游戏，导入 Tk 主窗口模块 Script.Core.main_frame，再调用 io_init.init_style；
样式定义经输出队列送到 main_frame，main_frame.read_queue 读出后注册成文本框的标签。
每个字体配置样式的标签字体所带的修饰词（bold、underline、italic）就是它在字体配置里设为真的那几个标志；
三个修饰符标签与每个样式的修饰符组合标签各带名字里的修饰词。
没有可用的显示时跳过测试。不开新游戏。
"""

import queue
import signal
import tkinter
from itertools import combinations

from tests.slow import remove_parent_guard
from tests.slow.base import SlowTestCase
from tests.world import FullWorld

MODIFIERS = ("bold", "underline", "italic")
""" 字体修饰词，也是字体配置的三个标志列名与三个修饰符标签名 """


class FontConfigFlagsReachTkTagsTest(SlowTestCase):
  """字体配置样式的标签字体带上它设为真的标志，修饰符标签与组合标签带上名字里的修饰词"""

  def setUp(self) -> None:
    """
    设好时限，载入游戏，接上 Tk 文本框，照启动流程注册全部样式
    Keyword arguments:
    无
    Return arguments:
    无
    """
    signal.signal(signal.SIGALRM, self._time_up)
    signal.alarm(self.time_limit)
    remove_parent_guard()
    self.world = FullWorld.load()
    self.cache = self.world.cache
    from Script.Core import io_init

    try:
      from Script.Core import main_frame
    except tkinter.TclError as error:
      self.skipTest(f"没有可用的显示，无法创建 Tk 窗口：{error}")
    messages: queue.Queue[str] = queue.Queue()

    def put_queue(message: str) -> None:
      """
      替换 io_init.put_queue：把消息放进接给 main_frame 的队列
      Keyword arguments:
      message -- 推送的信息
      Return arguments:
      无
      """
      messages.put_nowait(message)

    io_init.put_queue = put_queue
    main_frame.bind_queue(messages)
    io_init.init_style()
    main_frame.read_queue()
    self.textbox = main_frame.textbox

  def font_modifiers(self, tag: str) -> set[str]:
    """
    取文本框标签的字体里的修饰词
    Keyword arguments:
    tag -- 标签名
    Return arguments:
    set[str] -- 字体选项里出现的 MODIFIERS 中的词
    """
    font = self.textbox.tag_cget(tag, "font")
    return set(self.textbox.tk.splitlist(font)) & set(MODIFIERS)

  def test_config_style_tags(self) -> None:
    """带修饰词的字体配置样式标签，正是设了标志的样式，各带它设为真的标志；至少有一个样式设了标志"""
    from Script.Config import game_config

    expected: dict[tuple[int, str], set[str]] = {}
    actual: dict[tuple[int, str], set[str]] = {}
    for cid, style in game_config.config_font.items():
      expected[cid, style.name] = {
          name for name in MODIFIERS if getattr(style, name)
      }
      actual[cid, style.name] = self.font_modifiers(style.name)
    flagged = {key: names for key, names in expected.items() if names}
    self.assertTrue(flagged, "字体配置里没有设了标志的样式")
    self.assertEqual(
        {key: names for key, names in actual.items() if names}, flagged
    )

  def test_modifier_tags(self) -> None:
    """三个修饰符标签与每个样式的修饰符组合标签（样式名_修饰词…）各带名字里的修饰词"""
    from Script.Config import game_config

    expected: dict[str, set[str]] = {name: {name} for name in MODIFIERS}
    for base in game_config.config_font_data:
      for count in range(1, len(MODIFIERS) + 1):
        for combo in combinations(MODIFIERS, count):
          expected[base + "_" + "_".join(combo)] = set(combo)
    actual = {tag: self.font_modifiers(tag) for tag in expected}
    self.assertEqual(actual, expected)
