# -*- coding: UTF-8 -*-
"""
韩文环境下，模板名字相同的 1 号与 448 号角色在开局与读档时各是各的
==================================================================
ko_KR 的翻译里 1 号与 448 号角色的模板名字相同。
- 开局：zh_CN 与 ko_KR 各在 fork 出的子进程里开新游戏（助理干员选 1 号），记下开局后已有的角色id
  （npc_id_got）、助理的角色id（assistant）与选助理面板列出的角色id（candidates，
  assistant_panel.get_assistant_candidates），两种语言的每一项都相同。
- 读档：zh_CN 与 ko_KR 各在子进程里开新游戏（不选初期奖励），给 1 号与 448 号各设一个不同的好感度，
  经 save_handle 真实写盘、读档；读档后 1 号键与 448 号键下的角色 cid、adv 都是键本身，好感度是写盘前设的值。
"""

import json
import os
import shutil
import signal
import traceback
from typing import Callable

from tests.slow import remove_parent_guard
from tests.slow.base import SlowTestCase
from tests.slow.test_tag_logic_same_in_english import (
    CHINESE,
    LanguageRun,
    game,
)

KOREAN = "ko_KR"
""" 被测语言 """
SAVE_ID = "test_same_name_characters_kept_apart"
""" 本测试写入 save/ 的存档id，读档后删掉 """
FAVORABILITY_DICT = {1: 1234, 448: 4321}
""" 写盘前设的好感度：角色id -> 对玩家的好感度 """
CHILD_ERROR = "子进程出错"
""" 子进程出错时结果里唯一的键 """


class NoBonusRun(LanguageRun):
  """不选初期奖励开新游戏的 LanguageRun"""

  def new_game(self) -> None:
    """与 LanguageRun.new_game 相同的开新游戏流程，但不选助理干员"""
    flow = game("Script.UI.Flow.creator_character_flow")
    self.press(" -【初次唤醒】-")
    game("Script.UI.Flow.title_flow").title_panel()
    now_panel_id = self.cache.now_panel_id
    if now_panel_id != self.constant.Panel.CREATOR_CHARACTER:
      raise AssertionError(f"标题画面没有进入创建角色：{now_panel_id}")
    self.press("我读完并理解了以上8条，我对自己负责，我不删，我要玩")
    self.world.player.type(self.world.PLAYER_NAME)
    self.press("睁开双眼")
    flow.creator_character_panel()
    self.world.player.check_done()
    game("tests.world").seed_everything()


def collect_new_game(language: str) -> dict[str, list[int]]:
  """
  以一种语言开新游戏（助理干员选 1 号），收集开局的结果
  Keyword arguments:
  language -- 语言
  Return arguments:
  dict -- npc_id_got、assistant 与 candidates，见模块文档字符串
  """
  run = LanguageRun(language)
  cache = run.cache
  assistant_panel = game("Script.UI.Panel.assistant_panel")
  return {
      "npc_id_got": sorted(cache.npc_id_got),
      "assistant": [cache.character_data[0].assistant_character_id],
      "candidates": assistant_panel.get_assistant_candidates(),
  }


def collect_load(language: str) -> dict[str, list[int]]:
  """
  以一种语言开新游戏（不选初期奖励），设好好感度后写盘再读档，收集读档后的结果
  Keyword arguments:
  language -- 语言
  Return arguments:
  dict -- 角色id（字符串）-> 读档后该键下角色的 [cid, adv, 好感度]
  """
  run = NoBonusRun(language)
  cache = run.cache
  save_handle = game("Script.Core.save_handle")
  for chara_id, favorability in FAVORABILITY_DICT.items():
    cache.character_data[chara_id].favorability[0] = favorability
  save_handle.establish_save(SAVE_ID)
  try:
    save_handle.input_load_save(SAVE_ID)
  finally:
    shutil.rmtree(save_handle.get_save_dir_path(SAVE_ID), ignore_errors=True)
  loaded: dict[str, list[int]] = {}
  for chara_id in FAVORABILITY_DICT:
    character = cache.character_data[chara_id]
    loaded[str(chara_id)] = [
        character.cid,
        character.adv,
        character.favorability[0],
    ]
  return loaded


class SameNameCharactersKeptApartTest(SlowTestCase):
  """ko_KR 下 1 号与 448 号角色在开局与读档时各是各的"""

  time_limit = 600
  """ 多次启动游戏，比默认时限长 """

  def setUp(self) -> None:
    """只设时限；各局游戏在测试里各自启动"""
    signal.signal(signal.SIGALRM, self._time_up)
    signal.alarm(self.time_limit)
    remove_parent_guard()

  def collect_in_child(
      self, collect: Callable[[str], dict[str, list[int]]], language: str
  ) -> dict[str, list[int]]:
    """
    在 fork 出的子进程里以指定语言收集结果，经管道传回；子进程出错时测试失败并给出堆栈
    Keyword arguments:
    collect -- 收集函数，collect_new_game 或 collect_load
    language -- 语言
    Return arguments:
    dict -- collect 的结果
    """
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
      os.close(read_fd)
      signal.alarm(self.time_limit)
      result: dict[str, object] = {CHILD_ERROR: "没有结果"}
      try:
        result = dict(collect(language))
      finally:
        # 出错时 finally 里仍能取到正在传出的异常
        if CHILD_ERROR in result:
          result[CHILD_ERROR] = traceback.format_exc()
        with os.fdopen(write_fd, "w", encoding="utf-8") as pipe:
          json.dump(result, pipe, ensure_ascii=False)
        os._exit(0)
    os.close(write_fd)
    killed = True
    try:
      with os.fdopen(read_fd, "r", encoding="utf-8") as pipe:
        child_result: dict[str, list[int]] = json.load(pipe)
      killed = False
    finally:
      if killed:
        os.kill(pid, signal.SIGKILL)
      os.waitpid(pid, 0)
    self.assertNotIn(CHILD_ERROR, child_result, child_result.get(CHILD_ERROR))
    return child_result

  def test_new_game_same_as_chinese(self) -> None:
    """ko_KR 下开局已有的角色、助理与助理候选都与 zh_CN 相同"""
    chinese = self.collect_in_child(collect_new_game, CHINESE)
    korean = self.collect_in_child(collect_new_game, KOREAN)
    self.assertEqual(chinese["assistant"], [1], "zh_CN 下助理是 1 号")
    self.assertEqual(korean, chinese)

  def test_load_keeps_each_character(self) -> None:
    """zh_CN 与 ko_KR 下读档后 1 号与 448 号键下都仍是各自的角色与写盘前的好感度"""
    expected = {
        str(chara_id): [chara_id, chara_id, favorability]
        for chara_id, favorability in FAVORABILITY_DICT.items()
    }
    for language in (CHINESE, KOREAN):
      loaded = self.collect_in_child(collect_load, language)
      self.assertEqual(loaded, expected, language)
