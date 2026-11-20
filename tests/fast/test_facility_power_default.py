# -*- coding: UTF-8 -*-
"""
设施效率读区块的供电策略：没有登记策略的区块按供电面板的默认值
============================================================
新游戏里供电策略表还是空的。未实装的区块（8、18、20）默认断电，其设施的效率与登记了断电时相同，与登记了标准时不同。
"""

from Script.Config import game_config
from Script.Core import cache_control
from Script.Design import basement
from Script.Kernel import core
from Script.Modules.domains import power
from tests.fast.base import FastTestCase


def _strategies(table: dict[str, int]) -> None:
    """内核换成全局键 base.power_strategy 为 table 的状态"""
    core.reset_state(core.with_value(core.state(), None, power.KEY, table))


class FacilityPowerDefaultTest(FastTestCase):
    """没有登记供电策略时，设施效率按面板的默认策略算"""

    def test_unbuilt_zone_defaults_to_cut_off(self) -> None:
        """未实装区块里的设施：空策略表下的效率等于登记断电时的效率"""
        unbuilt = power.UNBUILT_ZONES
        island = cache_control.cache.rhodes_island
        for cid in game_config.config_facility:
            island.facility_level.setdefault(cid, 1)
        cid, zone = next(
            (cid, f.type if f.type >= 0 else cid)
            for cid, f in game_config.config_facility.items()
            if (f.type if f.type >= 0 else cid) in unbuilt
        )
        _strategies({str(zone): 2})
        cut_off = basement.calc_facility_efficiency(cid)
        _strategies({str(zone): 0})
        standard = basement.calc_facility_efficiency(cid)
        self.assertNotEqual(cut_off, standard, "断电与标准的效率不同")
        _strategies({})
        self.assertEqual(basement.calc_facility_efficiency(cid), cut_off)
