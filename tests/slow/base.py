# -*- coding: UTF-8 -*-
"""
慢速层测试的基类
================
每个测试由 pytest --forked 放进自己的新进程。setUp 在其中完整启动游戏（FullWorld）并开新游戏，
测试再用玩家指令（instruct）与走路（walk）推进：有行动时长的指令与走路都经游戏主循环 update.game_update_flow 结算时间；打开面板的指令只换面板，由 show_panel 显示。
"""

import signal
import unittest

from tests.slow import remove_parent_guard
from tests.world import FullWorld

TIME_LIMIT = 300
""" 每个测试（含启动与开局）的默认时限，秒；测试类可用 time_limit 另设 """


class SlowTestTimeout(AssertionError):
  """测试超过时限仍未结束"""


class SlowTestCase(unittest.TestCase):
  """慢速层测试的基类：self.world 为刚开新游戏的 FullWorld，self.cache 为游戏缓存"""

  time_limit = TIME_LIMIT
  """ 这个类的每个测试的时限，秒 """
  first_bonus = ()
  """ 开新游戏时选的初期奖励按钮，见 FullWorld.new_game """

  def setUp(self):
    """
    设好时限，启动游戏并开新游戏
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
    self.world.new_game(self.first_bonus)

  def _time_up(self, signum, frame):
    """
    SIGALRM 的处理函数：抛 SlowTestTimeout，测试以失败结束而不是卡住整批
    Keyword arguments:
    signum -- 信号编号
    frame -- 当前栈帧
    Return arguments:
    无
    """
    raise SlowTestTimeout(f"测试超过 {self.time_limit} 秒")

  def tearDown(self):
    """
    取消时限
    Keyword arguments:
    无
    Return arguments:
    无
    """
    signal.alarm(0)

  def subTest(self, msg=None, **params):
    """
    慢速层不用子测试，调用即抛 TypeError：pytest-forked 只把测试本身的报告带回父进程，子测试的失败会丢失
    Keyword arguments:
    msg -- 不使用
    params -- 不使用
    Return arguments:
    无
    """
    raise TypeError(
        "慢速层不用 subTest（--forked 下子测试的失败不会报告）：在断言的 msg 里写明是哪一组"
    )

  def npc(self, name: str) -> int:
    """
    按名字找本局已有的干员
    Keyword arguments:
    name -- 干员名字
    Return arguments:
    int -- 角色id
    """
    found = [
        cid
        for cid in self.cache.npc_id_got
        if self.cache.character_data[cid].name == name
    ]
    self.assertEqual(len(found), 1, f"本局应有一名「{name}」")
    return found[0]

  def instruct(self, instruct_id: str):
    """
    像玩家在主界面点下指令一样执行它：先确认它的前提都成立（主界面才会列出），再交给 handle_instruct
    Keyword arguments:
    instruct_id -- 指令id（constant.Instruct 中的值）
    Return arguments:
    无
    """
    from Script.Core import constant
    from Script.Design import handle_premise
    from Script.System.Instruct_System import handle_instruct

    failed = [
        premise
        for premise in constant.instruct_premise_data.get(instruct_id, ())
        if not handle_premise.handle_premise(premise, 0)
    ]
    self.assertEqual(failed, [], f"指令 {instruct_id} 此刻不会出现在主界面")
    handle_instruct.handle_instruct(instruct_id)

  def show_panel(self):
    """
    显示指令打开的面板（如「干员位置一览」），与游戏主流程 start_flow.start_frame 每一轮做的相同；面板里的选择由 self.world.player 安排
    Keyword arguments:
    无
    Return arguments:
    无
    """
    from Script.Core import constant

    constant.panel_data[self.cache.now_panel_id]()

  def wait_until(self, done, minutes: int) -> bool:
    """
    反复用「等待五分钟」指令推进时间，直到 done() 为真或已等满 minutes 分钟
    Keyword arguments:
    done -- 无参数、返回 bool 的函数
    minutes -- 最多等待的分钟数
    Return arguments:
    bool -- done() 最后的结果
    """
    from Script.Core import constant

    for _ in range(minutes // 5):
      if done():
        return True
      self.instruct(constant.Instruct.WAIT)
    return done()

  def walk(self, path: list):
    """
    像玩家在地图上点选目的地一样让博士走过去，每一段路都经主循环结算
    Keyword arguments:
    path -- 目标场景路径列表
    Return arguments:
    无
    """
    from Script.Design import character_move

    self.world.scene(path)
    character_move.own_charcter_move(list(path))
