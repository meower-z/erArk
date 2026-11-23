# -*- coding: UTF-8 -*-
"""
基地生产线的状态（base.production）
===================================
- 设施升级开放生产线：制造加工区 3 级有 3 条流水线，药田 4 级有 3 条线。0 号流水线仍生产配方 1，新线不生产。
- 任命主负责人：不在工人名单里的角色不任命。同一角色任命到另一条线时从原来的线撤下。再选同一角色时撤下。
- 换生产：不生产的线随时能换。正在生产的线只在这个小时结算过时能换。
- 刷新岗位：职位变了的主负责人撤下，也不在工人名单里。职位没变的主负责人留任。
- 流水线结算：按小时数与效率生产，每个产品扣 10 个原料，记下结算的小时。
- 读档：罗德岛对象带着旧的生产线属性时，值写进 GameState，属性从对象上删掉。元组照列表读，短列表补 0，
  列表形式的主负责人取其中的id。之后换id时，主负责人与工人名单跟着换。对象上没有这些属性时 GameState 不变。
  类型不符的属性也删掉，这一项取默认值。production.adopt_old_save 交回旧存档缺了或类型不符的属性个数。
- 自检：合法时 ISLAND-13 与 ISLAND-15 都不报。配方id不在配置里时 ISLAND-13 报，主负责人不在工人名单里时 ISLAND-15 报。
"""

from types import SimpleNamespace

from Script.Config import game_config
from Script.Design import basement, game_time
from Script.Kernel import core
from Script.Modules.domains import production, roster, warehouse
from Script.Modules.gameplay_resolution import assembly_service, working
from Script.Modules.save_load import upgrade
from Script.Test.Static_Check.check_registry import get_all_checks
from tests import kernel_data
from tests.fast.base import FastTestCase
from Script.Modules.domains import chara_life

HERB_GARDEN = 41
""" 药田的设施id """
WORKSHOP = 12
""" 制造加工区的设施id """


class ProductionStateTest(FastTestCase):
    """生产线的开放、任命、换生产、岗位刷新、结算、读档与自检"""

    def setUp(self) -> None:
        """放进博士，再以 core.state() 为底开一个缓冲区，测试里对 GameState 的读写都记在里面"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))

    def workers(self, kind: str, *cids: int) -> None:
        """
        造几名干员，职位设为这类生产线的职位，再用这些角色换掉这类的工人名单
        Keyword arguments:
        kind -- KINDS 里的种类
        cids -- 角色id，按名单的顺序
        """
        for cid in cids:
            self.world.chara(cid, f"干员{cid}")
            kernel_data.put(
                chara_life.work_type.set, cid, production.KINDS[kind]
            )
        production.set_workers(kind, cids)

    def flagged(self, check_id: str) -> bool:
        """
        跑一项静态自检
        Keyword arguments:
        check_id -- 检查编号
        Return arguments:
        bool -- 这项检查报了问题时为 True
        """
        _name, run = get_all_checks()[check_id]
        return bool(run())

    def test_upgrades_open_lines(self) -> None:
        """制造加工区 3 级时有 0、1、2 号流水线，0 号仍生产配方 1，新线不生产。药田 4 级时有 0、1、2 号线"""
        kernel_data.set_facility_level(WORKSHOP, 3)
        kernel_data.set_facility_level(HERB_GARDEN, 4)
        basement.get_base_updata()
        lines = production.lines("assembly")
        self.assertEqual(list(lines), [0, 1, 2])
        self.assertEqual(
            [line["product"] for line in lines.values()], [1, 0, 0]
        )
        self.assertEqual(list(production.lines("herb_garden")), [0, 1, 2])

    def test_appoint(self) -> None:
        """不在工人名单里的角色不任命。同一角色任命到另一条线时从原线撤下。再选同一角色时撤下"""
        kernel_data.set_facility_level(WORKSHOP, 2)
        basement.get_base_updata()
        self.workers("assembly", 1)
        self.world.chara(2, "干员2")
        production.appoint("assembly", 0, 2)
        production.appoint("assembly", 0, 1)
        production.appoint("assembly", 1, 1)
        mains = [line["main"] for line in production.lines("assembly").values()]
        self.assertEqual(mains, [0, 1])
        production.appoint("assembly", 1, 1)
        self.assertEqual(production.lines("assembly")[1]["main"], 0)

    def test_change_product(self) -> None:
        """不生产的线随时能换。正在生产的线只在这个小时结算过时能换"""
        hour = game_time.now().hour
        production.change_product("herb_garden", 0, 11)
        production.set_line("herb_garden", 0, hour=(hour + 1) % 24)
        production.change_product("herb_garden", 0, 0)
        self.assertEqual(production.lines("herb_garden")[0]["product"], 11)
        production.set_line("herb_garden", 0, hour=hour)
        production.change_product("herb_garden", 0, 0)
        self.assertEqual(production.lines("herb_garden")[0]["product"], 0)

    def test_work_refresh(self) -> None:
        """刷新岗位后，职位变了的主负责人撤下，也不在工人名单里。职位没变的主负责人留任"""
        self.workers("assembly", 3, 1)
        self.workers("green_house", 2)
        production.appoint("assembly", 0, 3)
        production.appoint("green_house", 0, 2)
        kernel_data.put(chara_life.work_type.set, 3, 0)
        roster.set_active({1, 2, 3})
        basement.update_work_people()
        self.assertEqual(production.workers("assembly"), [1])
        self.assertEqual(production.workers("green_house"), [2])
        self.assertEqual(production.lines("assembly")[0]["main"], 0)
        self.assertEqual(production.lines("green_house")[0]["main"], 2)

    def test_assembly_settle(self) -> None:
        """上次结算在 4 小时前。结算按效率生产产品，每个产品扣 10 个原料，并记下这个小时"""
        hour = game_time.now().hour
        self.assertGreaterEqual(hour, 4, "前提：开局时刻不早于 4 点")
        production.set_line("assembly", 0, hour=hour - 4)
        warehouse.set(11, 1000)
        before = warehouse.amount(21)
        _text, rate = assembly_service.calculate_assembly_line_efficiency(0)
        made = int(4 * rate / 100)
        self.assertGreater(made, 0, "前提：4 小时能生产")
        assembly_service.settle_assembly_line(draw_flag=False)
        self.assertEqual(warehouse.amount(21) - before, made)
        self.assertEqual(warehouse.amount(11), 1000 - 10 * made)
        self.assertEqual(production.lines("assembly")[0]["hour"], hour)

    def test_old_island_moves_into_state(self) -> None:
        """
        旧存档的生产线与工人名单写进 GameState，属性从对象上删掉。六个属性都在且类型相符，交回 0。
        元组照列表读，短列表补 0，列表形式的主负责人取其中的id。换id后主负责人与工人名单是新id
        """
        island = SimpleNamespace(
            assembly_line={0: [3, [5], 0.0, 0, 7], 1: (2, 0, 0.0, 0, 9)},
            production_worker_ids=[5, 6],
            herb_garden_line={0: [11, 6, 1.2, 0]},
            herb_garden_operator_ids=[6],
            green_house_line={},
            green_house_operator_ids=[],
            effectiveness=100,
        )
        missing = production.adopt_old_save({"rhodes_island": island}, 0)
        self.assertEqual(missing, 0)
        self.assertEqual(
            production.lines("assembly"),
            {
                0: {"product": 3, "main": 5, "hour": 7},
                1: {"product": 2, "main": 0, "hour": 9},
            },
        )
        self.assertEqual(production.workers("assembly"), [5, 6])
        self.assertEqual(
            production.lines("herb_garden"),
            {0: {"product": 11, "main": 6, "hour": 0}},
        )
        self.assertEqual(production.lines("green_house"), {})
        self.assertEqual(vars(island), {"effectiveness": 100})
        production.remap({5: 50, 6: 60})
        self.assertEqual(production.lines("assembly")[0]["main"], 50)
        self.assertEqual(production.workers("assembly"), [50, 60])
        self.assertEqual(production.lines("herb_garden")[0]["main"], 60)

    def test_current_island_leaves_state(self) -> None:
        """当前版本的存档，罗德岛对象上没有这些属性。GameState 不变，交回 0"""
        before = working.get(None, production.KEY)
        missing = production.adopt_old_save(
            {"rhodes_island": SimpleNamespace()}, upgrade.CURRENT
        )
        self.assertEqual(missing, 0)
        self.assertEqual(working.get(None, production.KEY), before)

    def test_wrong_type_reads_default(self) -> None:
        """旧存档只带一个集合形式的工人名单时交回 6。流水线的工人名单取默认的空表，属性从对象上删掉"""
        island = SimpleNamespace(production_worker_ids={5})
        missing = production.adopt_old_save({"rhodes_island": island}, 0)
        self.assertEqual(missing, 6)
        self.assertEqual(production.workers("assembly"), [])
        self.assertEqual(vars(island), {})

    def test_checks(self) -> None:
        """合法时两项都不报。ISLAND-13 在配方id不在配置里时报。ISLAND-15 在主负责人不在工人名单里时报"""
        kernel_data.set_facility_level(WORKSHOP, 1)
        self.workers("assembly", 1)
        production.appoint("assembly", 0, 1)
        self.assertFalse(self.flagged("ISLAND-13"))
        self.assertFalse(self.flagged("ISLAND-15"))
        missing = max(game_config.config_productformula) + 1
        production.set_line("assembly", 0, product=missing)
        self.assertTrue(self.flagged("ISLAND-13"))
        production.set_workers("assembly", [])
        self.assertTrue(self.flagged("ISLAND-15"))
