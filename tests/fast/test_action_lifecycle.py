# -*- coding: UTF-8 -*-
"""
行动的一生：选行动、开始、收尾（行为的结束函数）
==============================================
内核按 LOAD_ORDER 加上本模块跑，本模块的 PickNextAction 输入钩子在最外层，照脚本交回玩家与干员1的意图。
玩家做 3 个等待（10、5、15 分钟），干员1先要对幼年阶段的干员2接吻（开始门换成 1 分钟的发呆），再等待 7 分钟。
干员2不在脚本里，交给内层的选择。time_hooks.tick_one 换成记录调用的替身；脚本不过 0 点。
- 干员由缓存投影时行动已开始，此后一轮一轮地 收尾、选、开始；玩家先选、开始，之后也是这样一轮一轮。
  一轮里三件事在同一时钟。
- 开始门拦下干员1的接吻：内核里是 1 分钟的发呆，缓存里也是，交互对象改回自己。
- 每一步之后 actions.drifted() 都为空；玩家第 4 次选行动时，时钟走过了 30 分钟。
测试先导入 update 再导入 Script.Modules，和游戏的导入顺序一样（反过来会循环导入）。
"""

import datetime
import sys
from collections.abc import Mapping
from unittest import mock

from Script.Design import update
from Script.Core import constant
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.gameplay_resolution import actions, intent, time_hooks
from tests import world
from tests import kernel_data
from tests.fast.base import FastTestCase

LOADED_FIRST = update
""" 先于 Script.Modules 导入的 update """
AMIYA = 1
""" 干员1的角色id """
KALTSIT = 2
""" 干员2的角色id，幼年阶段 """
CHILD = 102
""" 幼女素质的id """
START = datetime.datetime(2026, 5, 4, 10, 0)
""" 开始的游戏时间 """

log: list[tuple[str, str, int]] = []
""" (事件, 角色键, 时钟) """
script: dict[str, list[intent.Intent]] = {}
""" 角色键到它接下来的意图 """


class ScriptDone(BaseException):
    """玩家的脚本走完了"""


@core.input_hook(core.pick_next_action)
def scripted(who: str) -> tuple[str] | core.Intercept[core.Action]:
    """
    PickNextAction 最外层的输入钩子：脚本里的角色交回下一个意图，玩家的脚本走完时抛 ScriptDone
    Keyword arguments:
    who -- 角色键
    Return arguments:
    Intercept -- 脚本里的行动；别的角色原样交给内层
    """
    log.append(("pick", who, core.state().clock))
    queue = script.get(who)
    if queue is None:
        return (who,)
    if not queue:
        raise ScriptDone
    return core.Intercept(intent.behavior_action(int(who), queue.pop(0)))


@core.input_hook(core.start_action)
def starting(act: core.Action) -> tuple[core.Action]:
    """
    StartAction 最外层的输入钩子：记下开始
    Keyword arguments:
    act -- 要开始的行动
    Return arguments:
    tuple -- 原样交给内层
    """
    log.append(("start", act.who, core.state().clock))
    return (act,)


def wait(minutes: int) -> intent.Intent:
    """
    等待的意图
    Keyword arguments:
    minutes -- 分钟数
    Return arguments:
    Intent -- 意图
    """
    return intent.Intent(behavior_id=constant.Behavior.WAIT, minutes=minutes)


class ActionLifecycleTest(FastTestCase):
    """内核里一个行动的收尾、选与开始"""

    def setUp(self) -> None:
        """
        玩家与干员1、干员2在同一场景，干员2处于幼年阶段；时钟拨到 START，由缓存投影出 GameState
        Keyword arguments:
        无
        Return arguments:
        无
        """
        super().setUp()
        log.clear()
        world.set_clock(START)
        self.world.chara(0, "博士")
        self.world.chara(AMIYA, "阿米娅")
        self.kaltsit = self.world.chara(KALTSIT, "凯尔希")
        self.kaltsit.talent[CHILD] = 1
        script.clear()
        script["0"] = [wait(10), wait(5), wait(15)]
        kiss = intent.Intent(
            behavior_id=constant.Behavior.KISS_H, minutes=10, target=KALTSIT
        )
        script[str(AMIYA)] = [kiss, wait(7)] + [wait(30)] * 3
        core.load((*load_order.LOAD_ORDER, sys.modules[__name__]))
        core.reset_state(kernel_data.reprojected(core.state()))
        ticks = mock.patch.object(time_hooks, "tick_one", side_effect=self.over)
        ticks.start()
        self.addCleanup(ticks.stop)
        self.drift: list[list[int]] = []
        self.gated: core.Action | None = None
        self.gated_cache: tuple = ()

    def over(self, who: int) -> None:
        """
        tick_one 的替身：行为结束函数（actions.wrap_up）的第一件事，记下收尾
        Keyword arguments:
        who -- 角色id
        """
        log.append(("over", str(who), core.state().clock))

    def run_script(self) -> None:
        """一步一步跑到玩家的脚本走完，记下每一步之后的 drifted() 与干员1第一次开始的行动"""
        try:
            while True:
                core.step()
                self.drift.append(actions.drifted())
                if self.gated is None and ("start", "1") in [
                    entry[:2] for entry in log
                ]:
                    self.gated = core.state().characters["1"].action
                    amiya = self.cache.character_data[AMIYA]
                    self.gated_cache = (
                        amiya.behavior.behavior_id,
                        amiya.behavior.duration,
                        amiya.target_character_id,
                    )
        except ScriptDone:
            pass

    def test_over_pick_start_in_order(self) -> None:
        """每个角色：选、开始，此后每一轮收尾、选、开始；收尾与选在同一时钟"""
        self.run_script()
        for who in ("0", str(AMIYA), str(KALTSIT)):
            mine = [(name, clock) for name, w, clock in log if w == who]
            if who == "0":
                self.assertEqual([n for n, _ in mine[:2]], ["pick", "start"])
                mine = mine[2:]
            names = [name for name, _ in mine]
            whole = len(names) // 3 * 3
            self.assertGreater(whole, 0, who)
            self.assertEqual(
                names[:whole], ["over", "pick", "start"] * (whole // 3), who
            )
            for i in range(0, whole, 3):
                self.assertEqual(mine[i][1], mine[i + 1][1], f"{who} 收尾与选")
                self.assertEqual(
                    mine[i + 1][1], mine[i + 2][1], f"{who} 选与开始"
                )
        player = [clock for name, w, clock in log if (name, w) == ("pick", "0")]
        self.assertEqual(len(player), 4, "玩家选了 4 次，第 4 次脚本走完")
        start = game_time.minutes(START)
        self.assertEqual(
            [m - start for m in player], [0, 10, 15, 30], "玩家选行动的时钟"
        )

    def test_gate_stops_ai_intent(self) -> None:
        """干员1对幼年阶段的干员2接吻：开始门换成 1 分钟的发呆，缓存里同样"""
        self.run_script()
        act = self.gated
        assert act is not None
        data = act.action_data
        assert isinstance(data, Mapping)
        args = data["args"]
        assert isinstance(args, Mapping)
        self.assertEqual(
            (data["behavior_id"], act.duration, args["gate"]),
            (constant.Behavior.SHARE_BLANKLY, 1, "child_stage"),
        )
        self.assertEqual(
            self.gated_cache,
            (constant.Behavior.SHARE_BLANKLY, 1, AMIYA),
            "缓存里的（行为，时长，交互对象）",
        )
        amiya = [(n, c) for n, w, c in log if w == str(AMIYA)]
        self.assertEqual(amiya[3][1] - amiya[2][1], 1, "发呆 1 分钟后收尾")

    def test_no_drift(self) -> None:
        """三个玩家行动里，每一步之后缓存里进行中的行为都与内核一致"""
        self.run_script()
        self.assertTrue(self.drift, "跑了几步")
        self.assertEqual([d for d in self.drift if d], [], "drifted() 为空")
