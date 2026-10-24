# -*- coding: UTF-8 -*-
"""
英文环境下，管理罗德岛面板的子系统按钮打开对应的子系统
==================================================
以 en_US 启动游戏并开新游戏（助理干员阿米娅），博士走到博士办公室，点「管理罗德岛」，
在「各部门工作概况」里按机库一栏的「外勤委托系统」按钮，外勤委托面板画出它的分类「常规外勤」后按两次「返回」回到主界面。
"""

import signal

from tests.slow import remove_parent_guard
from tests.slow.base import SlowTestCase
from tests.slow.test_tag_logic_same_in_english import ENGLISH, LanguageRun


class ManageBaseSubsystemInEnglishTest(SlowTestCase):
  """en_US 下，管理罗德岛面板的外勤委托系统按钮打开外勤委托面板"""

  def setUp(self) -> None:
    """只设时限；游戏在测试里以 en_US 启动"""
    signal.signal(signal.SIGALRM, self._time_up)
    signal.alarm(self.time_limit)
    remove_parent_guard()

  def test_field_commission_button(self) -> None:
    """按「外勤委托系统」打开外勤委托面板，返回后回到主界面"""
    run = LanguageRun(ENGLISH)
    from Script.Core import constant
    from tests import snapshot_states

    snapshot_states.walk(run.world, snapshot_states.DOCTOR_OFFICE)
    presses = tuple(
        run.translate(text)
        for text in ("各部门工作概况", "[外勤委托系统]", "返回", "返回")
    )
    run.instruct(constant.Instruct.MANAGE_BASEMENT, presses)
    self.assertIn(run.translate("常规外勤"), "".join(run.world.player.screen))
