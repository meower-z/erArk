# -*- coding: UTF-8 -*-
"""
本模块检查访客抵达后的住处在 en_US 和 ko_KR 下与 zh_CN 相同。每种语言各在一个 fork 出的
子进程里开一局新游戏。慢速层禁止测试模块在顶部导入 Script 下的模块。所以本模块在函数里经
game() 导入游戏模块。
"""

import json
import os
import signal
import traceback
from typing import Any

from tests.slow import remove_parent_guard
from tests.slow.base import SlowTestCase
from tests.slow.test_tag_logic_same_in_english import game, set_language

LANGUAGES = ("zh_CN", "en_US", "ko_KR")
""" 首项 zh_CN 是其他语言比较的基准。 """
VISITOR_COUNT = 2
""" collect 让抵达的访客人数。测试要求它等于访客区2级的访客上限。 """
CHILD_ERROR = "子进程出错"
""" 子进程出错时结果里唯一的键。它的值是异常堆栈。 """


def collect(language: str) -> dict[str, Any]:
  """
  以指定语言开一局新游戏。开局时初期奖励选启动资金。随后博士走到基建部，
  在建筑面板把访客区升到2级。可招募干员中编号最小的 VISITOR_COUNT 名
  再经 settle_visitor_arrivals 依次作为访客抵达。
  Keyword arguments:
  language -- 语言代码（str），如 zh_CN
  Return arguments:
  dict -- 结果有三个键。guest_rooms 为 constant.place_data["Guest_Room"]，
  即各客房的场景路径。visitor_max 为访客区升级后的访客上限。
  dormitory 列出各访客抵达后的住处。dormitory 按抵达顺序排列。
  """
  translate = set_language(language)
  world: Any = game("tests.world").FullWorld.load()
  cache = world.cache
  constant: Any = game("Script.Core.constant")
  snapshot_states: Any = game("tests.snapshot_states")
  # FullWorld.new_game 按下的按钮文字没有译成当前语言
  world.player.press(translate(" -【初次唤醒】-"))
  game("Script.UI.Flow.title_flow").title_panel()
  world.player.press(
      translate("我读完并理解了以上8条，我对自己负责，我不删，我要玩")
  )
  world.player.type(world.PLAYER_NAME)
  world.player.press(translate("启动资金"), translate("睁开双眼"))
  game("Script.UI.Flow.creator_character_flow").creator_character_panel()
  world.player.check_done()
  game("tests.world").seed_everything()
  # 把访客区升到2级，使访客上限等于 VISITOR_COUNT
  snapshot_states.walk(world, ["工程", "基建部"])
  snapshot_states.instruct(
      world,
      constant.Instruct.BUILDING,
      tuple(translate(text) for text in ("访客区", "【升级】", "返回")),
  )
  visitor_list = sorted(
      game("Script.UI.Panel.recruit_panel").find_recruitable_npc()
  )[:VISITOR_COUNT]
  invite_visitor_panel: Any = game("Script.UI.Panel.invite_visitor_panel")
  for visitor_id in visitor_list:
    invite_visitor_panel.settle_visitor_arrivals(visitor_id)
  return {
      "guest_rooms": constant.place_data["Guest_Room"],
      "visitor_max": cache.rhodes_island.visitor_max,
      "dormitory": [
          cache.character_data[cid].dormitory for cid in visitor_list
      ],
  }


class VisitorGuestRoomEveryLanguageTest(SlowTestCase):
  """检查访客抵达后的住处在 en_US 和 ko_KR 下与 zh_CN 相同"""

  time_limit = 600
  """ 本测试要依次开三局游戏，所以时限（秒）比默认的 TIME_LIMIT 长。 """

  def setUp(self) -> None:
    """
    不同于 SlowTestCase.setUp，本方法不启动游戏。
    各局游戏由 collect_in_child 在子进程里启动。
    """
    signal.signal(signal.SIGALRM, self._time_up)
    signal.alarm(self.time_limit)
    remove_parent_guard()

  def collect_in_child(self, language: str) -> dict[str, Any]:
    """
    在 fork 出的子进程里以指定语言运行 collect。子进程把结果写成 JSON，
    经管道传回父进程。子进程另设 time_limit 秒的时限。子进程超时也按出错返回。
    父进程读不出结果时，本方法强制结束子进程并让异常继续抛出。
    Keyword arguments:
    language -- 语言代码（str），如 zh_CN
    Return arguments:
    dict -- 子进程正常结束时为 collect 的结果。子进程出错时只有键 CHILD_ERROR，
    值为异常堆栈。
    """
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
      os.close(read_fd)
      signal.alarm(self.time_limit)
      result: dict[str, Any] = {CHILD_ERROR: "没有结果"}
      try:
        result = collect(language)
      finally:
        # collect 抛出的异常在 finally 里仍可由 traceback.format_exc 取到
        if CHILD_ERROR in result:
          result[CHILD_ERROR] = traceback.format_exc()
        with os.fdopen(write_fd, "w", encoding="utf-8") as pipe:
          json.dump(result, pipe, ensure_ascii=False)
        os._exit(0)
    os.close(write_fd)
    killed = True
    try:
      with os.fdopen(read_fd, "r", encoding="utf-8") as pipe:
        child_result: dict[str, Any] = json.load(pipe)
      killed = False
    finally:
      if killed:
        os.kill(pid, signal.SIGKILL)
      os.waitpid(pid, 0)
    return child_result

  def test_same_guest_rooms_as_chinese(self) -> None:
    """
    断言各子进程没有出错。断言中文下的访客上限等于 VISITOR_COUNT。
    断言中文下各访客住进互不相同的客房。
    断言 en_US 与 ko_KR 下各访客的住处与中文相同。
    """
    results = {
        language: self.collect_in_child(language) for language in LANGUAGES
    }
    for language, result in results.items():
      self.assertNotIn(
          CHILD_ERROR, result, f"{language}：{result.get(CHILD_ERROR)}"
      )
    chinese = results[LANGUAGES[0]]
    # 中文下若也没分到客房，其他语言与中文相同也说明不了分到了客房
    self.assertEqual(chinese["visitor_max"], VISITOR_COUNT)
    self.assertEqual(len(set(chinese["dormitory"])), VISITOR_COUNT)
    for room in chinese["dormitory"]:
      self.assertIn(room, chinese["guest_rooms"])
    self.assertEqual(
        {language: results[language]["dormitory"] for language in LANGUAGES},
        {language: chinese["dormitory"] for language in LANGUAGES},
    )
