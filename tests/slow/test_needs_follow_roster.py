# -*- coding: UTF-8 -*-
"""
角色的生理需求跟着角色进出花名册
================================
开新游戏，一名在场干员的乳汁设为 37/8、饥饿设为 100。
- 这名干员离开当前干员列表（缓存的 npc_id_got）后等待一次：不在 GameState.characters 里，生理需求在 roster.offstage 里，
  乳汁仍是 37/8。回到列表后等待一次：回到 GameState.characters，生理需求跟着回来，roster.offstage 里没有这名干员。
- 上线的结算（default.handle_chara_on_line）把饥饿、疲劳、尿意清零，乳汁不变。
"""

import datetime
import importlib
from fractions import Fraction
from types import ModuleType

from tests.slow.base import SlowTestCase

MILK = Fraction(37, 8)
""" 测试设的乳汁 """


def game(name: str) -> ModuleType:
    """按模块全名 name 导入游戏模块，返回模块"""
    return importlib.import_module(name)


class NeedsFollowRosterTest(SlowTestCase):
    """生理需求在角色进出花名册时跟着走"""

    def setUp(self) -> None:
        """开新游戏，取一名在场干员，等待一次，把乳汁设为 37/8、饥饿设为 100，再等待一次"""
        super().setUp()
        core = game("Script.Kernel.core")
        needs = game("Script.Modules.domains.needs")
        working = game("Script.Modules.gameplay_resolution.working")
        self.cid = min(cid for cid in self.cache.npc_id_got if cid != 0)
        self.wait()
        with working.based_on(core.state()) as buffer:
            needs.set(self.cid, milk=MILK, hunger=100)
            effects = buffer.effects()
        core.reset_state(core.preview(core.state(), effects))
        self.wait()

    def wait(self) -> None:
        """玩家等待一次（constant.Instruct.WAIT），游戏推进到玩家下一次选行动"""
        from tests.snapshot_states import instruct

        constant = game("Script.Core.constant")
        instruct(self.world, constant.Instruct.WAIT)

    def test_milk_survives_leaving_and_coming_back(self) -> None:
        """离开列表时数据进 roster.offstage，乳汁不变。回到列表时数据回到角色身上"""
        core = game("Script.Kernel.core")
        needs = game("Script.Modules.domains.needs")
        working = game("Script.Modules.gameplay_resolution.working")
        who = str(self.cid)
        self.cache.npc_id_got.discard(self.cid)
        self.wait()
        state = core.state()
        self.assertNotIn(who, state.characters)
        self.assertIn(who, state.data[working.OFFSTAGE])
        self.assertEqual(needs.of(self.cid)["milk"], MILK)
        self.cache.npc_id_got.add(self.cid)
        self.wait()
        state = core.state()
        self.assertIn(needs.KEY, state.characters[who].data)
        self.assertNotIn(who, state.data.get(working.OFFSTAGE, {}))
        self.assertEqual(needs.of(self.cid)["milk"], MILK)

    def test_online_reset_keeps_milk(self) -> None:
        """上线的结算把饥饿、疲劳、尿意清零，乳汁不变。只比较 body.needs 里这四项"""
        core = game("Script.Kernel.core")
        game_type = game("Script.Core.game_type")
        default = game("Script.Settle.default")
        needs = game("Script.Modules.domains.needs")
        working = game("Script.Modules.gameplay_resolution.working")
        with working.based_on(core.state()):
            needs.set(self.cid, tired=50, urine=60)
            default.handle_chara_on_line(
                self.cid,
                1,
                game_type.CharacterStatusChange(),
                datetime.datetime.now(),
            )
            got = needs.of(self.cid)
        self.assertEqual(
            {k: got[k] for k in ("tired", "hunger", "urine", "milk")},
            {"tired": 0, "hunger": 0, "urine": 0, "milk": MILK},
        )
