# -*- coding: UTF-8 -*-
"""
行为快照：从几个起始状态经主循环推进，逐步录下全部游戏状态
============================================================
起始状态与玩家动作表在 tests/snapshot_states.py：
    time_stop_h        时停中的 H；时停结束后博士在岛上走动，夜里睡 8 小时，这一步跨过午夜；医疗部有坐诊与住院医生
    family_commission  妊娠、101 与 102（离线）、103（在线上课）与 104 的孩子；教师开讲时把学生拉进听课，博士也授一次课；
                       两项带载具的外勤委托；跨过午夜，推进到委托返回之后
每个测试开局选 tests.snapshot_states.FIRST_BONUS，构建一个状态，按动作表推进，每一步录一份快照（tests/snapshot.py），
写到 tests/snapshots/<状态名>.last.tsv.gz（不提交）。动作表里的指令此刻不成立、安排的按钮没有用掉时测试失败；行为是否变了由比较命令判断：
    python -m tests.snapshot compare tests/snapshots/<状态名>.tsv.gz tests/snapshots/<状态名>.last.tsv.gz
行为有意改变时，把 .last.tsv.gz 复制成基准 tests/snapshots/<状态名>.tsv.gz，随改动一起提交。
"""

import os

from tests import snapshot_states
from tests.slow.base import SlowTestCase
from tests.world import ROOT

SNAPSHOT_DIR = os.path.join(ROOT, "tests", "snapshots")
""" 快照目录 """


class SnapshotStatesTest(SlowTestCase):
  """每个起始状态各录一份快照"""

  time_limit = 600
  """ 构建与推进几百步，比默认时限长 """
  first_bonus = snapshot_states.FIRST_BONUS
  """ 开局选的初期奖励 """

  def record(self, state_name: str) -> None:
    """
    构建状态、按动作表推进并写出快照；动作表里的指令不成立、安排的按钮没用掉时抛 PlanError
    Keyword arguments:
    state_name -- 状态名
    Return arguments:
    无
    """
    recorder = snapshot_states.run(self.world, state_name)
    recorder.write(os.path.join(SNAPSHOT_DIR, f"{state_name}.last.tsv.gz"))

  def test_time_stop_h(self) -> None:
    """时停中的 H：构建、推进并录下快照"""
    self.record("time_stop_h")

  def test_family_commission(self) -> None:
    """孕产、各阶段的孩子与外勤委托：构建、推进并录下快照"""
    self.record("family_commission")
