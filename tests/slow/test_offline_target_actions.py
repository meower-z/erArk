# -*- coding: UTF-8 -*-
"""
以不在场的角色为交互对象的行动照常进行
======================================
婴儿和被装袋的干员不在 npc_id_got 里（不在场），玩家仍能以她们为对象行动：
- 育儿室的照顾婴儿面板里选一名婴儿、「抱一抱她」：开始的是抱孩子，30 分钟，开始门不换成发呆；
  玩家下次选行动时已过 30 分钟，婴儿的数据被这次照顾结算改过。
- 装着一名干员时选「从袋中放出来」：开始的是放出来；之后她回到在场名单、不再被装袋，
  也没有给她排上或开始一段等待（她在袋里时不在内核里，不陪玩家等）。
"""

import pickle
from collections.abc import Mapping
from typing import cast

from tests.slow.base import SlowTestCase
from tests import chara_abilities as ca

BABY = 101
""" 婴儿素质的id """


class OfflineTargetActionsTest(SlowTestCase):
    """以婴儿或袋里的干员为对象的玩家行动"""

    def setUp(self) -> None:
        """开新游戏，记下内核开始的每个行动"""
        super().setUp()
        from Script.Kernel import core

        self.started: list[core.Action] = []
        saved = core._bodies["kernel.StartAction"]

        def spy(act: core.Action) -> core.Effects:
            self.started.append(act)
            return saved(act)

        core._bodies["kernel.StartAction"] = spy
        self.addCleanup(core._bodies.__setitem__, "kernel.StartAction", saved)

    def starts_of(self, who: int) -> list[tuple[str, int, object]]:
        """
        记下的、角色开始的行动
        Keyword arguments:
        who -- 角色id
        Return arguments:
        list -- (行为id, 内核时长, 开始门没过的检查)
        """
        out = []
        for act in self.started:
            if act.who != str(who):
                continue
            data = cast(Mapping[str, object], act.action_data)
            args = cast(Mapping[str, object], data.get("args", {}))
            out.append(
                (str(data["behavior_id"]), act.duration, args.get("gate"))
            )
        return out

    def offline_chara(self) -> int:
        """
        一名有模板、不在场的角色
        Return arguments:
        int -- 角色id
        """
        return next(
            cid
            for cid in sorted(self.cache.npc_tem_data)
            if cid
            and cid in self.cache.character_data
            and cid not in self.cache.npc_id_got
        )

    def test_nursery_care_from_panel_cares(self) -> None:
        """照顾婴儿面板里抱一抱婴儿：开始的是 30 分钟的抱孩子，婴儿的数据被结算改过"""
        from Script.UI.Moudle import view
        from Script.Core import constant
        from Script.Kernel import core
        from tests import world

        baby_id = self.offline_chara()
        baby = self.cache.character_data[baby_id]
        ca.talent(baby_id)[BABY] = 1
        before = pickle.dumps(baby)
        clock = core.state().clock
        label = f"[{str(baby.adv).rjust(4, '0')}]:{baby.name}"
        self.world.player.press(label, "抱一抱她")

        def pick() -> None:
            view.now_panel_id = constant.Panel.TAKE_CARE_BABY
            constant.panel_data[constant.Panel.TAKE_CARE_BABY]()

        world.act(pick)
        self.world.player.check_done()
        self.assertEqual(
            self.starts_of(0)[:1], [(constant.Behavior.HOLD_CHILD, 30, None)]
        )
        self.assertGreaterEqual(core.state().clock - clock, 30)
        self.assertNotEqual(
            pickle.dumps(baby), before, "婴儿的数据没被照顾结算改过"
        )

    def test_release_from_bag_releases(self) -> None:
        """从袋中放出来：开始的是放出来，之后她在场、不在袋里，没有排上或开始等待"""
        from Script.Core import constant, game_type
        from Script.Design import game_time
        from Script.Modules.gameplay_resolution import plan_queue
        from Script.Settle import default
        from tests import world

        bagged_id = sorted(i for i in self.cache.npc_id_got if i)[0]
        player = self.cache.character_data[0]
        bagged = self.cache.character_data[bagged_id]
        self.world.move(bagged_id, player.position)
        player.target_character_id = bagged_id
        player.sp_flag.bagging_chara_id = bagged_id
        bagged.sp_flag.be_bagged = True
        default.handle_chara_off_line(
            bagged_id, 1, game_type.CharacterStatusChange(), game_time.now()
        )
        self.assertNotIn(bagged_id, self.cache.npc_id_got)

        def pick() -> None:
            """玩家点下从袋中放出来"""
            constant.handle_instruct_data[constant.Instruct.RELEASE_FROM_BAG]()

        world.act(pick)
        self.assertEqual(
            self.starts_of(0)[:1],
            [(constant.Behavior.RELEASE_FROM_BAG, 10, None)],
        )
        self.assertEqual(
            (bagged_id in self.cache.npc_id_got, bagged.sp_flag.be_bagged),
            (True, False),
            "（在场，被装袋）",
        )
        self.assertEqual(
            (
                plan_queue.planned(bagged_id),
                [
                    s
                    for s in self.starts_of(bagged_id)
                    if s[0] == constant.Behavior.WAIT
                ],
            ),
            ([], []),
            "（她排着的行动，她开始的等待）",
        )
