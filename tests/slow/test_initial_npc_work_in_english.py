# -*- coding: UTF-8 -*-
"""
英文环境下，开新游戏后初始干员照样有初始工作
==========================================
以 en_US 启动游戏并开新游戏（助理干员阿米娅），可露希尔、凯尔希、华法琳、特蕾西娅、杜宾的工作
与 character_handle.first_NPC_work 给的初始工作相同。
"""

import signal

from tests.slow import remove_parent_guard
from tests.slow.base import SlowTestCase
from tests.slow.test_tag_logic_same_in_english import ENGLISH, LanguageRun

FIRST_WORK_DICT = {7: 21, 3: 61, 171: 61, 56: 71, 130: 91}
""" 角色id -> 初始工作id：可露希尔、凯尔希、华法琳、特蕾西娅、杜宾 """


class InitialNpcWorkInEnglishTest(SlowTestCase):
  """en_US 下，开新游戏后五名初始干员各有初始工作"""

  def setUp(self) -> None:
    """只设时限；游戏在测试里以 en_US 启动"""
    signal.signal(signal.SIGALRM, self._time_up)
    signal.alarm(self.time_limit)
    remove_parent_guard()

  def test_first_work(self) -> None:
    """五名初始干员的工作是初始工作"""
    run = LanguageRun(ENGLISH)
    work_dict = {
        chara_id: run.cache.character_data[chara_id].work.work_type
        for chara_id in FIRST_WORK_DICT
    }
    self.assertEqual(work_dict, FIRST_WORK_DICT)
