"""
载具服务测试
============
覆盖机库状态与文本、载具列表筛选与排序、分页与循环翻页、交易判定与买卖写入、写缓冲外只读查询，以及屏蔽界面与结算模块的独立子进程运行。
"""

import json
import subprocess
import sys

from Script.Config import game_config
from Script.Core import get_text
from Script.Kernel import core
from Script.Modules.domains import commission, facility, warehouse
from Script.Modules.gameplay_resolution import vehicle_service as svc
from Script.Modules.gameplay_resolution import working
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

_ = get_text._
""" 翻译api """

BASIC_BY_PRICE_DESC = [6, 7, 10, 9, 2, 3, 8, 4, 5, 1]
""" 常规载具按价格降序且同价按编号升序排列的预期编号顺序。 """

ISOLATED_RUN = """
import importlib.abc, sys
BLOCKED = (
    "Script.UI",
    "Script.Settle",
    "Script.System.Instruct_System.handle_instruct",
    "Script.Core.flow_handle",
    "tkinter",
    "_tkinter",
    "PIL.ImageTk",
)
ALLOWED = ("Script.Modules.tk_ui", "Script.Modules.tk_ui.orders")
def blocked(name):
    if name in ALLOWED:
        return False
    return any(name == b or name.startswith(b + ".") for b in BLOCKED)
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if blocked(fullname):
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Block())
import contextlib, io, json
from Script.Config import normal_config
normal_config.init_normal_config()
from Script.Config import game_config
with contextlib.redirect_stdout(io.StringIO()):
    game_config.init()
from Script.Kernel import core
from Script.Modules.domains import commission, facility, warehouse
from Script.Modules.gameplay_resolution import vehicle_service as svc
from Script.Modules.gameplay_resolution import working
with working.based_on(core.state()):
    warehouse.start({1: 200000})
    facility.set_level(14, 3)
    bought = [svc.buy_vehicle(1), svc.buy_vehicle(6)]
    status = svc.hangar_status()
    rows = svc.listed_vehicles(svc._("常规载具"), svc._("持有量"), False)
    page = svc.page_of(rows, 9, 4)
    trade = svc.trade_status(1, status.owned)
    sold = svc.sell_vehicle(1)
    out = {
        "bought": bought,
        "status": [status.level, status.limit, status.owned, status.money],
        "first": [rows[0].cid, rows[0].owned],
        "page": [page.page, page.total, page.prev, page.next, len(page.rows)],
        "trade": [trade.can_buy, trade.can_sell, trade.space_left],
        "sold": sold,
        "after": [commission.vehicles()[1][0], warehouse.amount(1)],
    }
out["loaded"] = sorted(
    name
    for name in sys.modules
    if blocked(name) or name.startswith(("Script.UI", "Script.Settle"))
)
print(json.dumps(out))
"""
""" 在屏蔽界面、结算、指令处理与窗口模块的独立子进程中导入并调用载具服务买卖与查询接口，输出 JSON 结果的脚本。 """


class VehicleServiceCase(FastTestCase):
    """载具服务测试基类，在每个用例前开启写缓冲并提供载具持有量与机库上限辅助方法。"""

    def setUp(self) -> None:
        """初始化快速测试环境并进入内核状态写缓冲。"""
        super().setUp()
        self.enterContext(working.based_on(core.state()))

    def own(self, cid: int, owned: int, out: int = 0) -> None:
        """为指定载具编号增加持有数量与外勤中数量。"""
        commission.add_vehicle(cid, owned=owned, out=out)

    def limit(self, level: int) -> int:
        """从设施效果配置读取指定机库等级对应的载具容量上限。"""
        name = game_config.config_facility[svc.HANGAR].name
        cid = game_config.config_facility_effect_data[name][level]
        return game_config.config_facility_effect[cid].effect


class HangarTest(VehicleServiceCase):
    """机库状态与机库说明文本测试。"""

    def test_status_follows_level_table_and_money(self) -> None:
        """验证机库状态按机库等级表、全部载具总持有量与龙门币汇总，并生成对应的三行文本。"""
        facility.set_level(svc.HANGAR, 3)
        warehouse.add(svc.MONEY, 4321)
        self.own(1, 2, 1)
        self.own(51, 1)
        status = svc.hangar_status()
        self.assertEqual(status, svc.HangarStatus(3, self.limit(3), 3, 4321))
        self.assertEqual(
            svc.hangar_text(status),
            "○载具用于给执行外勤委托的干员提供交通和其他方面的辅助，提高委托效率\n"
            + f"○当前机库等级：3，载具数量：3/{self.limit(3)}\n"
            + "○当前龙门币数量：4321\n",
        )


class ListingTest(VehicleServiceCase):
    """载具列表标签筛选与排序规则测试。"""

    def ids(self, tab: str, sort_by: str, ascending: bool = True) -> list:
        """按给定标签页、排序条件与升降序查询载具列表并返回载具编号列表。"""
        rows = svc.listed_vehicles(_(tab), _(sort_by), ascending)
        return [row.cid for row in rows]

    def test_regular_tab_lists_basic_vehicles_by_id(self) -> None:
        """验证常规载具标签仅列出基础载具，并按编号支持升序与降序排列。"""
        self.own(51, 1)
        self.assertEqual(self.ids("常规载具", "默认"), list(range(1, 11)))
        self.assertEqual(
            self.ids("常规载具", "默认", False), list(range(10, 0, -1))
        )

    def test_special_tab_hides_unowned_vehicles(self) -> None:
        """验证特殊载具标签隐藏未持有的特殊载具，并在持有后返回对应行数据。"""
        self.own(1, 3)
        self.assertEqual(self.ids("特殊载具", "默认"), [])
        self.own(51, 2, 1)
        rows = svc.listed_vehicles(_("特殊载具"), _("默认"), True)
        self.assertEqual(rows, [svc.VehicleRow(51, 2, 1)])

    def test_price_sort_keeps_id_order_among_ties(self) -> None:
        """验证按价格降序与升序排序时，同价载具保持编号顺序。"""
        self.assertEqual(
            self.ids("常规载具", "价钱", False), BASIC_BY_PRICE_DESC
        )
        ascending = self.ids("常规载具", "价钱")
        self.assertEqual(ascending[:4], [1, 5, 4, 2])
        self.assertEqual(ascending[4:6], [3, 8])

    def test_owned_speed_and_capacity_sorts(self) -> None:
        """验证按持有量、速度与运载量排序的结果顺序。"""
        self.own(4, 5)
        self.own(9, 2, 2)
        self.own(1, 1)
        self.assertEqual(self.ids("常规载具", "持有量", False)[:3], [4, 9, 1])
        speed = self.ids("常规载具", "速度", False)
        self.assertEqual(speed[:4], [2, 8, 9, 3])
        capacity = self.ids("常规载具", "运载量")
        self.assertEqual(capacity[:3], [6, 7, 2])
        self.assertEqual(capacity[-2:], [1, 10])


class PageTest(FastTestCase):
    """载具列表分页切片、页码修正与循环翻页测试。"""

    rows = [svc.VehicleRow(cid, 0, 0) for cid in range(1, 12)]
    """ 包含 11 条载具行的分页测试固定样本。 """

    def test_pages_wrap_and_clamp(self) -> None:
        """验证首页循环翻至末页、超界页码下调至末页以及末页循环翻回首页。"""
        first = svc.page_of(self.rows, 1, 3)
        self.assertEqual(
            [first.page, first.total, first.prev, first.next], [1, 4, 4, 2]
        )
        self.assertEqual([row.cid for row in first.rows], [1, 2, 3])
        last = svc.page_of(self.rows, 9, 3)
        self.assertEqual([last.page, last.prev, last.next], [4, 3, 1])
        self.assertEqual([row.cid for row in last.rows], [10, 11])

    def test_empty_list_has_one_page(self) -> None:
        """验证空列表分页返回页码、总页数、上一页与下一页均为 1 的空页结果。"""
        page = svc.page_of([], 2, 10)
        self.assertEqual(page, svc.VehiclePage((), 1, 1, 1, 1))


class TradeTest(VehicleServiceCase):
    """载具买卖资格判定与资金库存变动测试。"""

    def setUp(self) -> None:
        """将机库设为 2 级并记录 1 号载具购入价格。"""
        super().setUp()
        facility.set_level(svc.HANGAR, 2)
        self.price = game_config.config_vehicle[1].price

    def test_buy_needs_room_and_money(self) -> None:
        """验证购买资格同时要求机库留有空位且龙门币不少于载具价格。"""
        warehouse.add(svc.MONEY, self.price)
        room = svc.trade_status(1, self.limit(2) - 1)
        self.assertEqual(
            [room.can_buy, room.money_left, room.space_left], [True, 0, 1]
        )
        full = svc.trade_status(1, self.limit(2))
        self.assertEqual([full.can_buy, full.space_left], [False, 0])
        warehouse.add(svc.MONEY, -1)
        poor = svc.trade_status(1, 0)
        self.assertEqual([poor.can_buy, poor.money_left], [False, -1])

    def test_sell_needs_an_idle_basic_vehicle(self) -> None:
        """验证基础载具在全部外勤中不可出售，存在闲置数量时允许出售。"""
        self.own(1, 2, 2)
        self.assertFalse(svc.trade_status(1, 2).can_sell)
        self.own(1, 1)
        self.assertTrue(svc.trade_status(1, 3).can_sell)

    def test_special_vehicle_cannot_be_traded(self) -> None:
        """验证特殊载具即使资金充足且已持有也不能购买或出售。"""
        warehouse.add(svc.MONEY, 10**7)
        self.own(51, 2)
        trade = svc.trade_status(51, 0)
        self.assertEqual(
            [trade.owned, trade.can_buy, trade.can_sell], [2, False, False]
        )

    def test_buy_and_sell_move_money_and_stock(self) -> None:
        """验证购买扣款入库、资金不足拒绝购买以及出售按 0.8 倍回收龙门币并减库存。"""
        warehouse.add(svc.MONEY, self.price + 5)
        self.assertTrue(svc.buy_vehicle(1))
        self.assertEqual(commission.vehicles()[1], (1, 0))
        self.assertEqual(warehouse.amount(svc.MONEY), 5)
        self.assertFalse(svc.buy_vehicle(1))
        self.assertEqual(commission.vehicles()[1], (1, 0))
        self.assertEqual(svc.sell_vehicle(1), int(self.price * 0.8))
        self.assertEqual(commission.vehicles()[1], (0, 0))
        self.assertEqual(warehouse.amount(svc.MONEY), 5 + int(self.price * 0.8))


class ReadOnlyTest(FastTestCase):
    """写缓冲外只读接口安全性测试。"""

    def test_reads_outside_write_buffer(self) -> None:
        """验证机库状态、列表查询、交易状态与说明文本接口可在写缓冲外运行且不改变内核状态对象。"""
        kernel_data.written(facility.set_level, svc.HANGAR, 2)
        kernel_data.written(warehouse.add, svc.MONEY, 30000)
        kernel_data.written(commission.add_vehicle, 4, owned=1)
        before = core.state()
        status = svc.hangar_status()
        rows = svc.listed_vehicles(_("常规载具"), _("持有量"), False)
        trade = svc.trade_status(4, status.owned)
        svc.hangar_text(status)
        svc.detail_text(4, trade)
        self.assertEqual([status.owned, status.money], [1, 30000])
        self.assertEqual(rows[0], svc.VehicleRow(4, 1, 0))
        self.assertEqual([trade.can_buy, trade.can_sell], [False, True])
        self.assertIs(core.state(), before)


class IsolatedImportTest(VehicleServiceCase):
    """载具服务无界面、无结算依赖的隔离运行测试。"""

    def test_service_runs_without_ui_or_settle_modules(self) -> None:
        """验证在屏蔽界面、结算、指令处理与窗口模块的子进程中调用载具服务买卖与查询接口后不加载受限模块且返回预期结果。"""
        done = subprocess.run(
            [sys.executable, "-c", ISOLATED_RUN],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout.strip().splitlines()[-1])
        price = game_config.config_vehicle[1].price
        self.assertEqual(out["loaded"], [])
        self.assertEqual(out["bought"], [True, False])
        self.assertEqual(out["status"], [3, self.limit(3), 1, 200000 - price])
        self.assertEqual(out["first"], [1, 1])
        self.assertEqual(out["page"], [3, 3, 2, 1, 2])
        self.assertEqual(out["trade"], [True, True, 4])
        self.assertEqual(out["sold"], int(price * 0.8))
        self.assertEqual(out["after"], [0, 200000 - price + int(price * 0.8)])
