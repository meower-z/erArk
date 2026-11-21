# -*- coding: UTF-8 -*-
"""
外勤委托与载具的状态（base.commission 与 base.vehicles）
========================================================
- 结算到期的委托后，委托不在进行中，记为已完成，派出的载具的外勤中数减 1。
- 委托奖励 m：-1 记为不可进行，1 记为已完成。0 先去掉不可进行的一记，委托不是不可进行的才去掉已完成的一记。
- 新游戏的载具表每种配置载具一行 (0, 0)。补表在表不缺时不写。存下的表缺一种载具时，补表把它补在最后，其余行不变。
- 读档：罗德岛对象带着旧的委托与载具属性时，值写进 GameState，属性从对象上删掉。返回时刻不是时间的委托不留。
  commission.adopt_old_save 交回缺了或类型不符的属性个数。换id后队伍里是新id。对象上没有这些属性时 GameState 不变。
"""

import datetime
from types import SimpleNamespace

from Script.Config import game_config
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import commission
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import upgrade
from Script.System.Field_Commission_System import field_commission_function
from tests.fast.base import FastTestCase

COMMISSION = 2
""" 测试用的委托id，在 Commission.csv 里，奖励只有资源 r_11_10 """


class CommissionStateTest(FastTestCase):
    """委托的结算、委托奖励的标记、载具表与读档"""

    def setUp(self) -> None:
        """
        放进玩家（角色id 0），再以 core.state() 为底开一个缓冲区，测试里对 GameState 的读写都记在里面。
        self.vehicle 是最小的载具id
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))
        self.vehicle = min(game_config.config_vehicle)

    def test_due_commission_settles(self) -> None:
        """派出一项已过返回时刻、带一辆载具的委托。结算后它不在进行中，记为已完成，这种载具的外勤中数回到 0"""
        commission.add_vehicle(self.vehicle, owned=2, out=1)
        due = game_time.now() - datetime.timedelta(minutes=1)
        commission.start(COMMISSION, [], due, [self.vehicle])
        field_commission_function.judge_field_commission_finish()
        self.assertEqual(commission.ongoing(), {})
        self.assertIn(COMMISSION, commission.finished())
        self.assertEqual(commission.vehicles()[self.vehicle][1], 0)

    def test_reward_marks(self) -> None:
        """同一项委托先记 -1 再记 1。第一次记 0 只去掉不可进行，第二次记 0 去掉已完成"""
        commission.mark(COMMISSION, -1)
        commission.mark(COMMISSION, 1)
        commission.mark(COMMISSION, 0)
        self.assertEqual(commission.shut_down(), frozenset())
        self.assertEqual(commission.finished(), {COMMISSION})
        commission.mark(COMMISSION, 0)
        self.assertEqual(commission.finished(), frozenset())

    def test_new_game_vehicles_and_repair(self) -> None:
        """
        新游戏的载具表每种配置载具一行 (0, 0)，补表不写。存下的表缺第一种载具时，补表把它补在最后，记为 (0, 0)。
        其余行不变
        """
        ids = list(game_config.config_vehicle)
        self.assertEqual(commission.vehicles(), dict.fromkeys(ids, (0, 0)))
        pick = working.open_pick()
        commission.fill_vehicles()
        self.assertEqual(working.close_pick(pick), ())
        stored = {str(vid): (1, 0) for vid in ids[1:]}
        working.put(None, commission.VEHICLES, stored)
        commission.fill_vehicles()
        self.assertEqual(list(commission.vehicles()), [*ids[1:], ids[0]])
        self.assertEqual(commission.vehicles()[ids[0]], (0, 0))
        self.assertEqual(commission.vehicles()[ids[1]], (1, 0))

    def test_old_island_moves_into_state(self) -> None:
        """
        旧罗德岛对象缺了不可进行的集合时交回 1。返回时刻不是时间的委托不留，其余值写进 GameState，属性从对象上删掉。
        换id后队伍里是新id
        """
        end = game_time.at(core.state().clock + 600)
        island = SimpleNamespace(
            ongoing_field_commissions={9: [[3, 4], end, [5, 5]], 10: [[], 0]},
            vehicles={5: [2, 2]},
            finished_field_commissions_set={9, 2},
            effectiveness=100,
        )
        missing = commission.adopt_old_save({"rhodes_island": island}, 0)
        self.assertEqual(missing, 1)
        self.assertEqual(
            commission.ongoing(), {9: commission.Ongoing((3, 4), end, (5, 5))}
        )
        self.assertEqual(commission.vehicles(), {5: (2, 2)})
        self.assertEqual(commission.finished(), {2, 9})
        self.assertEqual(vars(island), {"effectiveness": 100})
        commission.remap({3: 30})
        self.assertEqual(commission.ongoing()[9].team, (30, 4))

    def test_current_island_leaves_state(self) -> None:
        """当前版本的存档的罗德岛对象没有这些属性。adopt_old_save 之后 GameState 不变，交回 0"""
        before = working.get(None, commission.KEY)
        missing = commission.adopt_old_save(
            {"rhodes_island": SimpleNamespace()}, upgrade.CURRENT
        )
        self.assertEqual(missing, 0)
        self.assertEqual(working.get(None, commission.KEY), before)
