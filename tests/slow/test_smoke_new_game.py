# -*- coding: UTF-8 -*-
"""
冒烟测试：新开局后经主循环跑几个游戏小时，每小时跑全部静态自检，并录下行为快照
================================================================================
开新游戏（开局时间为 tests.world.START_TIME，10:00）后，博士在原地反复用「等待五分钟」，主循环推进 HOURS 个小时，
其间至少一名干员吃饭；每一步结束都记一份行为快照（tests/snapshot.py）。
开局时和此后每个整点各跑一遍全部静态自检（Script.Test.Static_Check.run_all_checks，系统设置 14 打开时，游戏在主界面等待输入前经 run_turn_check 调用它），
任何一条失败都让测试失败，失败信息写明整点与检查编号。

快照写到 LAST_RUN；与提交在仓库里的基准比较：python -m tests.snapshot compare tests/snapshots/smoke_new_game.tsv tests/snapshots/smoke_new_game.last.tsv
行为有意改变时，把 LAST_RUN 复制成基准 tests/snapshots/smoke_new_game.tsv，随改动一起提交。
"""

import os

from tests.slow.base import SlowTestCase
from tests.world import ROOT

HOURS = 6
""" 推进的游戏小时数：10:00 到 16:00 """
STEP_MINUTES = 5
""" 每一步「等待五分钟」推进的分钟数 """
LAST_RUN = os.path.join(ROOT, "tests", "snapshots", "smoke_new_game.last.tsv")
""" 本次运行写出的快照（不提交） """


class SmokeNewGameTest(SlowTestCase):
  """新开局跑几个游戏小时，静态自检全部通过"""

  def test_hours_pass_static_checks(self):
    """10:00 到 16:00 有干员吃饭，每个整点的全部静态自检都通过；逐步录下行为快照"""
    from Script.Core import constant
    from Script.Test import Static_Check
    from Script.Test.Static_Check import checks
    from tests.snapshot import Recorder, capture

    checks_dir = os.path.dirname(checks.__file__)
    modules = sorted(
        name[:-3]
        for name in os.listdir(checks_dir)
        if name.startswith("check_") and name.endswith(".py")
    )
    missing = [name for name in modules if not hasattr(checks, name)]
    self.assertEqual(missing, [], "这些检查模块没有载入，它们的检查没有注册")

    failures = []
    """ 失败的自检：「整点 检查编号 检查名: 说明」 """

    def run_checks():
      """
      跑一遍全部静态自检，失败记进 failures
      Keyword arguments:
      无
      Return arguments:
      无
      """
      hour = self.cache.game_time.strftime("%m-%d %H:%M")
      for f in Static_Check.run_all_checks():
        failures.append(
            f"{hour} {f.check_id} {f.check_name}: {f.message[:300]}"
        )

    recorder = Recorder()
    npc_behaviors = set()
    """ 干员在各步结束时的行为id """
    start = self.cache.game_time
    recorder.record(start.strftime("%Y-%m-%d %H:%M"), capture(self.cache))
    run_checks()
    for _ in range(HOURS * 60 // STEP_MINUTES):
      self.instruct(constant.Instruct.WAIT)
      now = self.cache.game_time
      recorder.record(now.strftime("%Y-%m-%d %H:%M"), capture(self.cache))
      npc_behaviors.update(
          self.cache.character_data[cid].behavior.behavior_id
          for cid in self.cache.npc_id_got
      )
      if now.minute == 0:
        run_checks()
    os.makedirs(os.path.dirname(LAST_RUN), exist_ok=True)
    recorder.write(LAST_RUN)
    self.assertEqual(
        (self.cache.game_time - start).total_seconds(),
        HOURS * 3600,
        "主循环推进的时间",
    )
    self.assertIn(constant.Behavior.EAT, npc_behaviors, "没有干员吃饭")
    self.maxDiff = None
    self.assertEqual(failures, [])
