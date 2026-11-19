# -*- coding: UTF-8 -*-
"""
游戏时钟（GameTime）通过行为域自检的回归测试
============================================
游戏时钟 game_time.now()（内核时钟换算）与行为起时 behavior.start_time 都是 GameTime（datetime 的子类）。
自检 BEHAV-02（全局时钟健全性）与 BEHAV-07（行为核心字段类型）必须接受它们；否则打开自检后每局都报「状态不自洽」。
BEHAV-10/11/12/22 与 BEHAV-07 共用同一个类型判定，类型判定通过后它们才真正比较时间。
本测试的时钟与起时都用 game_time.to_game_time 构造；开局时刻 kernel_state.first_clock() 也用它生成时钟。
"""

import datetime
from typing import TYPE_CHECKING

import Script.Test.Static_Check  # noqa: F401  导入即注册全部检查
from Script.Design import game_time
from Script.Test.Static_Check.check_registry import get_all_checks
from tests.fast.base import FastTestCase
from tests import world

if TYPE_CHECKING:
    from Script.Test.Static_Check.check_registry import CheckFailure


def run(check_id: str) -> "list[CheckFailure]":
    """
    运行一条已注册的自检
    Keyword arguments:
    check_id -- 检查编号，如 "BEHAV-02"
    Return arguments:
    list[CheckFailure] -- 该检查报告的失败
    """
    return get_all_checks()[check_id][1]()


def messages(failures: "list[CheckFailure]") -> list[str]:
    """
    取失败记录的说明文字，供断言失败时打印
    Keyword arguments:
    failures -- 失败记录列表
    Return arguments:
    list[str] -- 每条失败的说明（截断到 200 字）
    """
    return [f.message[:200] for f in failures]


class GameClockPassesChecksTest(FastTestCase):
    """BEHAV-02 与 BEHAV-07 接受 GameTime；类型判定通过后其他条件照旧生效"""

    def setUp(self) -> None:
        """
        开局时钟：玩家 7:00 开始发呆 5 分钟，游戏时间 7:03
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        self.player = self.world.chara(0, "博士")
        self.player.behavior.behavior_id = "share_blankly"
        self.player.behavior.start_time = game_time.to_game_time(
            datetime.datetime(2020, 9, 10, 7, 0)
        )
        self.player.behavior.duration = 5
        world.set_clock(
            game_time.to_game_time(datetime.datetime(2020, 9, 10, 7, 3))
        )

    def test_checks_accept_game_time(self) -> None:
        """时钟与起时都是 GameTime，BEHAV-02 与 BEHAV-07 不报告失败"""
        self.assertIs(type(game_time.now()), game_time.GameTime)
        self.assertIs(type(self.player.behavior.start_time), game_time.GameTime)
        self.assertEqual(messages(run("BEHAV-02")), [])
        self.assertEqual(messages(run("BEHAV-07")), [])

    def test_start_time_after_clock_reported(self) -> None:
        """类型判定通过后，BEHAV-11 报告晚于游戏时间的起时"""
        self.player.behavior.start_time = game_time.to_game_time(
            datetime.datetime(2020, 9, 10, 8, 0)
        )
        failures = run("BEHAV-11")
        self.assertEqual(
            [f.check_id for f in failures], ["BEHAV-11"], messages(failures)
        )
