# -*- coding: UTF-8 -*-
"""
基地仓库（base.stock 与 base.warehouse_modules）
================================================
- 一个缓冲区里的几次写入依次叠加，读到的是叠加后的值。套用效果后的状态与之相同，资源按配置的先后排列。
- 读旧存档：罗德岛对象带着库存与扩展模块数时，库存按存档里的先后写进 GameState，存档里缺的配置资源补在最后、记为 0。
  扩展模块数写进 GameState，仓库容量算上这些模块，对象上不再有这两个属性。
- 冰箱里的母乳入库后超过仓库容量时，库存停在容量上。
- 自检 ISLAND-05、NUM-25 与 SUPP-07 各试一种合法情形与一种违规情形。
"""

import pickle
from dataclasses import replace
from types import MappingProxyType
from unittest import mock

from Script.Config import game_config
from Script.Core import save_handle
from Script.Design import basement
from Script.Kernel import core
from Script.Modules.domains import country, warehouse
from Script.Modules.gameplay_resolution import working
from Script.Test.Static_Check.check_registry import get_all_checks
from Script.UI.Moudle import draw
from tests import kernel_data
from tests.fast.base import FastTestCase

SLOT = "warehouse"
""" 读档用的存档id。测试换掉 save_handle.load_save，不读文件 """


class WarehouseTest(FastTestCase):
    """基地仓库的写入、读旧存档、入库上限与自检"""

    def setUp(self) -> None:
        """建角色 0，按配置的先后记下全部资源id"""
        super().setUp()
        self.world.chara(0, "博士")
        self.ids = list(game_config.config_resouce)

    def flagged(self, check_id: str) -> bool:
        """
        跑一项自检
        Keyword arguments:
        check_id -- 检查编号
        Return arguments:
        bool -- 这项检查报了问题时为 True
        """
        _name, run = get_all_checks()[check_id]
        return bool(run())

    def test_writes_in_one_step_add_up(self) -> None:
        """
        以当前状态为底的缓冲区里先开局（资源 1 为 100），再减 30、加 5，把资源 31 设为 7。
        缓冲区里读到资源 1 为 75。套用效果后资源 1 为 75、资源 31 为 7、其余为 0，资源按配置的先后排列
        """
        with working.based_on(core.state()) as buffer:
            warehouse.start({1: 100})
            warehouse.add(1, -30)
            warehouse.add(1, 5)
            warehouse.set(31, 7)
            self.assertEqual(warehouse.amount(1), 75)
            effects = buffer.effects()
        game = core.preview(core.state(), effects)
        expected = {rid: 0 for rid in self.ids} | {1: 75, 31: 7}
        self.assertEqual(warehouse.stock(game), expected)
        self.assertEqual(list(warehouse.stock(game)), self.ids)

    def test_old_save_moves_into_state(self) -> None:
        """
        存档的罗德岛对象带着倒序的库存（缺最后一种配置资源）与 2 个扩展模块，内核状态里没有 base.stock。
        读档后库存按存档里的先后，缺的资源补在最后、记为 0，扩展模块数为 2，对象上不再有这两个属性。
        把模块数改回 0 再算设施上限，仓库容量少 400
        """
        old = {rid: index_ + 1 for index_, rid in enumerate(self.ids[:-1])}
        old = dict(reversed(old.items()))
        saved = pickle.loads(pickle.dumps(self.cache))
        vars(saved.rhodes_island).update(
            materials_resouce=old, used_extra_warehouse_capacity_module=2
        )
        self.without_stock()
        with mock.patch.object(save_handle, "load_save", lambda _id: saved):
            self.install()
        self.assertEqual(warehouse.stock(), old | {self.ids[-1]: 0})
        self.assertEqual(list(warehouse.stock()), [*old, self.ids[-1]])
        self.assertEqual(warehouse.extra_modules(), 2)
        island = self.cache.rhodes_island
        self.assertFalse(hasattr(island, "materials_resouce"))
        self.assertFalse(
            hasattr(island, "used_extra_warehouse_capacity_module")
        )
        with_modules = island.warehouse_capacity
        with kernel_data.writing():
            warehouse.set_extra_modules(0)
            basement.update_facility_limits(island)
        self.assertEqual(with_modules - island.warehouse_capacity, 400)

    def without_stock(self, kept: dict[str, int] | None = None) -> None:
        """
        把内核状态换成没有 base.stock 的（如同旧存档的文件 "2"）。给了 kept 时 base.stock 只有 kept
        Keyword arguments:
        kept -- 资源id的字符串到库存
        """
        data = dict(core.state().data)
        del data[warehouse.KEY]
        game = replace(core.state(), data=MappingProxyType(data))
        if kept is not None:
            game = core.with_value(game, None, warehouse.KEY, kept)
        core.reset_state(game)

    def install(self) -> None:
        """
        按版本 3 跑读档的 Reset 步骤，读入存档 SLOT，写下的数据在结束时套用到内核状态。
        画面输出换成不画的对象。小世界没有国家数据，国家的重算换成原样返回
        """

        class Quiet:
            """不画的绘制对象，代替 NormalDraw 与 LeftDraw"""

            def __init__(self) -> None:
                """文本为空，宽度为 0"""
                self.text = ""
                self.width = 0

            def draw(self) -> None:
                """什么也不画"""

        with (
            mock.patch.object(draw, "NormalDraw", Quiet),
            mock.patch.object(draw, "LeftDraw", Quiet),
            mock.patch.object(country, "fill", lambda: None),
            kernel_data.writing(),
        ):
            save_handle.install_save(SLOT, 3)

    def test_milk_stops_at_capacity(self) -> None:
        """仓库容量 50，冰箱里有角色 0 的 80 毫升母乳。母乳结算后资源 31 的库存为 50"""
        island = self.cache.rhodes_island
        island.warehouse_capacity = 50
        island.milk_in_fridge = {0: 80}
        with kernel_data.writing():
            warehouse.start({})
            basement.settle_milk()
        self.assertEqual(warehouse.amount(31), 50)

    def test_stock_checks(self) -> None:
        """
        每种资源记为 0 时，ISLAND-05 与 NUM-25 都不报。资源 1 为 -5 时 ISLAND-05 报。
        base.stock 只有资源 1 时 NUM-25 报
        """
        with working.based_on(core.state()):
            warehouse.start({})
            self.assertFalse(self.flagged("ISLAND-05"))
            self.assertFalse(self.flagged("NUM-25"))
            warehouse.set(1, -5)
            self.assertTrue(self.flagged("ISLAND-05"))
        self.without_stock({"1": 0})
        self.assertTrue(self.flagged("NUM-25"))

    def test_module_check(self) -> None:
        """SUPP-07 对 0 个扩展模块不报，对 -1 个报"""
        with working.based_on(core.state()):
            warehouse.set_extra_modules(0)
            self.assertFalse(self.flagged("SUPP-07"))
            warehouse.set_extra_modules(-1)
            self.assertTrue(self.flagged("SUPP-07"))
