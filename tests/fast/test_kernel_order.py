# -*- coding: UTF-8 -*-
"""
同一分钟里的结算顺序：一步只结算一件事，core.instant() 给出 (分钟, 序号)
========================================

- 两个角色同一分钟行动结束：名单在前的先选行动并在同一步开始，下一步后者才在前者开始后的状态上选。
- 名单顺序就是 GameState.characters 的插入顺序；时钟走动后序号回到 0。
- 同样的起点跑两遍，顺序一样。
"""

from Script.Kernel import core
from tests.fast.kernel_toys import KernelTestCase, Toy, game

type Log = list[tuple[str, str, tuple[int, int]]]


class SameMinuteOrderTest(KernelTestCase):
    """同一分钟里选行动与行动开始的顺序"""

    def run_steps(self, ends: dict[str, int], steps: int) -> Log:
        """
        两个玩具角色在第 10 分钟同时结束，每次选 1 分钟的 Work，记下每次选与开始
        Keyword arguments:
        ends -- 角色键到行动结束的分钟，按名单顺序
        steps -- 跑几步
        Return arguments:
        Log -- (种类, 角色, instant()) 的列表
        """
        toy = Toy()
        log: Log = []
        self.seen: dict[str, core.Action] = {}
        self.work_name = toy.name("Work")

        @toy.action("Work")
        def work(act: core.Action) -> core.Effects:
            return ()

        @toy.input_hook(core.pick_next_action)
        def pick(who: str) -> core.Intercept[core.Action]:
            log.append(("pick", who, core.instant()))
            for other, c in core.state().characters.items():
                self.seen.setdefault(f"{who} sees {other}", c.action)
            return core.Intercept(core.new_action(work, who, 1))

        @toy.input_hook(core.start_action)
        def start(act: core.Action) -> tuple[core.Action]:
            log.append(("start", act.who, core.instant()))
            return (act,)

        @toy.input_hook(core.time_elapse)
        def elapse(begin: int, end: int) -> tuple[int, int]:
            log.append(("elapse", "", core.instant()))
            return (begin, end)

        self.start(game(10, ends), toy)
        for _ in range(steps):
            core.step()
        return log

    def test_first_in_roster_picks_and_starts_first(self) -> None:
        """A 在 (10,0) 选并开始，B 在 (10,1) 在 A 开始后的状态上选，然后时间流逝，到 11 分序号回 0"""
        log = self.run_steps({"A": 10, "B": 10}, 4)
        self.assertEqual(
            log,
            [
                ("pick", "A", (10, 0)),
                ("start", "A", (10, 0)),
                ("pick", "B", (10, 1)),
                ("start", "B", (10, 1)),
                ("elapse", "", (10, 2)),
                ("pick", "A", (11, 0)),
                ("start", "A", (11, 0)),
            ],
        )
        a_at_b_pick = self.seen["B sees A"]
        self.assertEqual(
            (a_at_b_pick.action_id, a_at_b_pick.start), (self.work_name, 10)
        )

    def test_roster_order_decides(self) -> None:
        """名单里 B 在 A 前时 B 先选"""
        log = self.run_steps({"B": 10, "A": 10}, 2)
        self.assertEqual(
            [entry[:2] for entry in log],
            [("pick", "B"), ("start", "B"), ("pick", "A"), ("start", "A")],
        )

    def test_same_start_same_order(self) -> None:
        """同样的起点跑两遍，记录一样"""
        first = self.run_steps({"A": 10, "B": 10}, 5)
        self.assertEqual(self.run_steps({"A": 10, "B": 10}, 5), first)
