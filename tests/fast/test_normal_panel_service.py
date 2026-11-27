"""
日常小面板规则与状态服务测试
==============================
覆盖关门询问提示与取消规则、照顾婴儿筛选与行为选择、初始奖励能力筛选与设置写入、
冰箱母乳列表与带走转化、酒店订房扣费赠品与面板提示适配，以及无界面无结算导入边界。
"""

import datetime
import json
import subprocess
import sys
from types import SimpleNamespace
from typing import Any
from unittest import mock

from Script.Config import game_config
from Script.Core import constant, flow_handle
from Script.Design import game_time
from Script.Kernel import core
from Script.Modules.domains import abilities, action_info, activity
from Script.Modules.domains import entertainment, fridge, inventory
from Script.Modules.domains import npc_template, playthrough, warehouse
from Script.Modules.gameplay_resolution import normal_panel_service as svc
from Script.Modules.gameplay_resolution import working
from Script.Modules.tk_ui import player_pick
from Script.UI.Panel import normal_panel
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

CANNOT_CLOSE = "\n当前地点无法关门，要继续吗："
""" 无法关门场景对应的本地化提示文本常量。 """
CARE = (
    ("抱一抱她", constant.Behavior.HOLD_CHILD),
    ("哼唱儿歌", constant.Behavior.SING_CHILDREN_SONG),
    ("喂奶", constant.Behavior.NUIRSE_CHILD),
    ("换尿布", constant.Behavior.CHANGE_DIAPERS),
    ("教她说话", constant.Behavior.TEACH_TALK),
    ("给她玩玩具", constant.Behavior.GIVE_TOY),
)
""" 六项照顾婴儿按钮文案与对应行为常量的期望顺序表。 """
BACKEND_RUN = """
import contextlib, datetime, importlib.abc, io, json, sys
BLOCKED = ("Script.UI", "Script.Settle",
    "Script.System.Instruct_System.handle_instruct", "Script.Core.flow_handle",
    "Script.Core.io_init", "Script.Frontend", "Script.Modules.tk_ui",
    "tkinter", "_tkinter", "PIL.ImageTk")
attempted = []
def blocked(name):
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if blocked(fullname):
            attempted.append(fullname)
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Blocker())
sys.path.insert(0, sys.argv[1])
from types import MappingProxyType
from Script.Config import game_config, map_config, normal_config
with contextlib.redirect_stdout(io.StringIO()):
    normal_config.init_normal_config()
    game_config.init()
    map_config.init_map_data()
from Script.Core import constant
from Script.Design import game_time, map_handle
from Script.Kernel import core
from Script.Modules.domains import action_info, activity, entertainment
from Script.Modules.domains import fridge, identity, inventory, warehouse
from Script.Modules.gameplay_resolution import normal_panel_service as svc
from Script.Modules.gameplay_resolution import working
start = game_time.minutes(datetime.datetime(2020, 5, 3)) + 9 * 60 + 41
core.reset_state(core.GameState(start, MappingProxyType({}), MappingProxyType({})))
scene = next(k for k, v in constant.scene_data.items() if v.close_type == 0)
out = {}
with working.based_on(core.state()):
    warehouse.start({})
    identity.put(identity.Identity(0, name="player"))
    identity.put(identity.Identity(7, name="cow", adv=12))
    activity.set_position(0, map_handle.get_map_system_path_for_str(scene))
    ask = svc.door_ask()
    out["door"] = [ask.prompt, ask.cancel_on_no]
    fridge.add(fridge.MILK, 7, 80)
    out["rows"] = [row.label for row in svc.milk_rows()]
    out["take"] = svc.take_milk(7)
    out["bag"] = [food.milk_ml for food in inventory.foods(0).values()]
    fridge.add(fridge.MILK, 7, 30)
    out["turn"] = svc.turn_milk(7)
    out["fresh"] = warehouse.amount(svc.FRESH_MILK)
    out["poor"] = svc.order_room(0)
    warehouse.add(svc.PINK_VOUCHER, 12)
    for item_id in (100, 120):
        inventory.set_item(0, item_id, 0)
    out["booked"] = svc.order_room(1)
    out["left"] = warehouse.amount(svc.PINK_VOUCHER)
    out["room"] = entertainment.hotel_room()
    out["items"] = [inventory.items(0)[100], inventory.items(0)[120]]
    out["now"] = str(game_time.now())
    out["checkout"] = str(action_info.get(0, "check_out_time"))
    out["status"] = svc.booked_text()
out["attempted"] = attempted
out["loaded"] = sorted(
    name for name in sys.modules
    if name.startswith(("Script.UI", "Script.Settle")) or blocked(name)
)
print(json.dumps(out))
"""
""" 在拦截界面、结算与窗口模块的独立子进程中执行 normal_panel_service 核心接口并输出 JSON 结果的脚本。 """


class NormalPanelCase(FastTestCase):
    """日常小面板测试基类，初始化博士角色并开启临时状态写缓冲。"""

    def setUp(self) -> None:
        """创建角色 0（博士）并进入当前内核状态的临时写缓冲。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))

    def scene_type(self, close_type: int) -> None:
        """
        设置玩家当前所在场景的关门类型。
        Keyword arguments:
        close_type -- int，目标场景的 close_type 值
        Return arguments:
        None -- 无返回值
        """
        self.world.scene(activity.position(0)).close_type = close_type


class DoorAskTest(NormalPanelCase):
    """关门询问服务与 Close_Door_Panel 交互行为测试。"""

    def test_prompt_and_cancel_follow_close_type(self) -> None:
        """验证 close_type 为 0、1、2 时 door_ask 返回对应提示前缀与取消标志。"""
        cases = (
            (0, CANNOT_CLOSE, True),
            (1, "\n当前地点可以关门，", False),
            (2, "\n你正在一个可以关门的小隔间内，", False),
        )
        for close_type, start, cancel in cases:
            with self.subTest(close_type=close_type):
                self.scene_type(close_type)
                ask = svc.door_ask()
                assert ask is not None
                self.assertTrue(ask.prompt.startswith(start))
                self.assertEqual(ask.cancel_on_no, cancel)

    def test_asked_scene_is_skipped(self) -> None:
        """验证 ask_close_door_flag 置位时 door_ask 与面板均返回 None 且不弹出询问。"""
        action_info.set(0, "ask_close_door_flag", True)
        self.assertIsNone(svc.door_ask())
        with mock.patch.object(flow_handle, "askfor_all") as ask:
            self.assertIsNone(normal_panel.Close_Door_Panel(80).draw())
        ask.assert_not_called()

    def test_panel_answers(self) -> None:
        """验证不同关门类型下选择是与否的返回值，以及类型 0 选择否时抛出 Back。"""
        cases = ((1, 0, True), (1, 1, False), (0, 0, True), (2, 1, False))
        for close_type, pick, answer in cases:
            with self.subTest(close_type=close_type, pick=pick):
                self.scene_type(close_type)
                self.assertEqual(self.answer(pick), answer)
        self.scene_type(0)
        with self.assertRaises(player_pick.Back):
            self.answer(1)

    def answer(self, pick: int) -> bool | None:
        """
        以固定按钮下标模拟输入并运行 Close_Door_Panel.draw。
        Keyword arguments:
        pick -- int，从返回键列表中选取的选项下标
        Return arguments:
        bool | None -- 面板绘制调用的返回值
        """
        with mock.patch.object(
            flow_handle, "askfor_all", lambda keys: keys[pick]
        ):
            return normal_panel.Close_Door_Panel(80).draw()


class BabyCareTest(NormalPanelCase):
    """育儿室婴儿筛选与照顾行为选择测试。"""

    def test_babies_lists_talent_holders_in_template_order(self) -> None:
        """验证 babies 仅按模板顺序返回持有素质 101 的角色及其编号与补零标签。"""
        ids = [cid for cid in npc_template.ids() if cid][:3]
        for index, cid in enumerate(ids):
            self.world.chara(cid, f"婴儿{index}", adv=index + 7)
            abilities.talent(cid)[101] = int(index != 1)
        babies = svc.babies()
        self.assertEqual([baby.chara_id for baby in babies], [ids[0], ids[2]])
        self.assertEqual(
            [baby.label for baby in babies],
            ["[0007]:婴儿0 ", "[0009]:婴儿2 "],
        )
        self.assertEqual([baby.adv for baby in babies], [7, 9])

    def test_each_care_button_chooses_its_behavior(self) -> None:
        """验证照顾标题、六项选项顺序，以及每个按钮下标均触发对应行为、目标 1 与 30 分钟的 Chosen。"""
        self.world.chara(1, "婴儿")
        self.assertEqual(svc.care_title(1), "\n选择照顾[婴儿]的方式：\n\n")
        labels = [option.label for option in svc.care_options()]
        self.assertEqual(labels, [label for label, _ in CARE])
        stand_in: Any = SimpleNamespace(target_chara_id=1)
        for index, (_, behavior_id) in enumerate(CARE):
            with self.subTest(index=index):
                with self.assertRaises(player_pick.Chosen) as raised:
                    normal_panel.Take_Care_Baby_Panel.settle_take_care(
                        stand_in, index
                    )
                action = raised.exception.action
                data = json.loads(json.dumps(action.action_data))
                self.assertEqual(data["behavior_id"], behavior_id)
                self.assertEqual(data["target"], 1)
                self.assertEqual(data["minutes"], 30)


class FirstBonusTest(NormalPanelCase):
    """初始奖励能力筛选、提示文案与设置写入测试。"""

    def test_offers_abilities_forty_to_forty_nine(self) -> None:
        """验证 bonus_abilities 按配置顺序仅列出编号 40 至 49 的能力及格式化标签。"""
        table = game_config.config_ability
        expected = [cid for cid in table if 40 <= cid <= 49]
        offers = svc.bonus_abilities()
        self.assertEqual([offer.ability_id for offer in offers], expected)
        first = offers[0]
        self.assertEqual(
            first.label, f"[{expected[0]}]{table[expected[0]].name}"
        )

    def test_choice_writes_setting_and_prompt(self) -> None:
        """验证未选与已选时的提示文本，以及面板选定后同步更新实例属性与设置键 21。"""
        self.assertEqual(svc.bonus_prompt(0), "当前没有选择能力，请选择：")
        ability_id = svc.bonus_abilities()[1].ability_id
        name = game_config.config_ability[ability_id].name
        self.assertEqual(
            svc.bonus_prompt(ability_id),
            f"当前选择的能力为{name}，请选择新的能力：",
        )
        panel = normal_panel.Chose_First_bonus_ability_Panel(80)
        panel.chose_this_ability(ability_id)
        self.assertEqual(panel.chose_ability_id, ability_id)
        self.assertEqual(
            playthrough.setting(playthrough.FIRST_BONUS, 21),
            ability_id,
        )


class FridgeTest(NormalPanelCase):
    """冰箱母乳列表展示、带走入包与资源转化测试。"""

    def setUp(self) -> None:
        """创建角色甲与角色乙并向冰箱写入两笔测试母乳库存。"""
        super().setUp()
        self.world.chara(1, "甲", adv=12)
        self.world.chara(2, "乙", adv=305)
        fridge.add(fridge.MILK, 1, 120)
        fridge.add(fridge.MILK, 2, 45)

    def test_rows_show_each_stock(self) -> None:
        """验证 milk_rows 返回补齐至 20 字符的库存行，清空冰箱后返回空元组。"""
        rows = svc.milk_rows()
        self.assertEqual([row.chara_id for row in rows], [1, 2])
        self.assertEqual(rows[0].label, "  [0012]甲：120ml".ljust(20, "　"))
        fridge.clear(fridge.MILK)
        self.assertEqual(svc.milk_rows(), ())

    def test_take_puts_milk_food_in_bag(self) -> None:
        """验证面板带走操作绘制单条等待提示、向背包写入菜谱 1001 食物并扣减冰箱对应库存。"""
        panel = normal_panel.Fridge_Panel(80)
        panel.take_milk(1)
        self.assertEqual(
            self.world.wait_texts, ["\n  你将甲的母乳（120ml）放进了背包\n"]
        )
        (food,) = inventory.foods(0).values()
        self.assertEqual(
            (food.recipe, food.milk_ml, food.maker), (1001, 120, "甲")
        )
        self.assertEqual(fridge.table(fridge.MILK), {2: 45})

    def test_turn_stores_fresh_milk(self) -> None:
        """验证转化操作将对应冰箱母乳计入资源鲜母乳，返回提示文本且不向背包写入食物。"""
        before = warehouse.amount(svc.FRESH_MILK)
        text = svc.turn_milk(2)
        self.assertEqual(text, "\n  你将乙的母乳（45ml）转化为了【鲜母乳】\n")
        self.assertEqual(warehouse.amount(svc.FRESH_MILK), before + 45)
        self.assertEqual(fridge.table(fridge.MILK), {1: 120})
        self.assertEqual(dict(inventory.foods(0)), {})


class HotelTest(NormalPanelCase):
    """酒店订房扣费、退房时间、赠品与面板绘制适配测试。"""

    def setUp(self) -> None:
        """将玩家背包中的赠品道具 100 与 120 初始数量清零。"""
        super().setUp()
        for item_id in (100, 120):
            inventory.set_item(0, item_id, 0)

    def test_short_of_vouchers_changes_nothing(self) -> None:
        """验证粉红凭证不足时返回拒绝提示，且不扣减凭证、不修改已订房型。"""
        warehouse.add(svc.PINK_VOUCHER, 9)
        self.assertEqual(len(svc.room_offers()), 3)
        self.assertIsNone(svc.booked_text())
        text = svc.order_room(1)
        self.assertEqual(text, "\n粉红凭证不足，无法预订情趣主题房\n")
        self.assertEqual(warehouse.amount(svc.PINK_VOUCHER), 9)
        self.assertEqual(entertainment.hotel_room(), 0)

    def test_booking_charges_and_sets_checkout(self) -> None:
        """验证三种房型预订均正确扣费、记录房型、设定次日 12 点退房、仅房型 1 发放赠品并更新状态文案。"""
        cases = ((0, 2, [0, 0]), (1, 10, [1, 5]), (2, 100, [0, 0]))
        for room_id, price, gifts in cases:
            with self.subTest(room_id=room_id):
                entertainment.set_hotel_room(0)
                for item_id in (100, 120):
                    inventory.set_item(0, item_id, 0)
                warehouse.set(svc.PINK_VOUCHER, 105)
                now = game_time.now()
                text = svc.order_room(room_id)
                checkout = action_info.get(0, "check_out_time")
                tomorrow = now + datetime.timedelta(days=1)
                self.assertEqual(checkout, tomorrow.replace(hour=12))
                self.assertEqual(
                    warehouse.amount(svc.PINK_VOUCHER), 105 - price
                )
                self.assertEqual(entertainment.hotel_room(), room_id + 1)
                items = inventory.items(0)
                self.assertEqual([items[100], items[120]], gifts)
                self.assertTrue(text.startswith("\n成功预订了"))
                self.assertIn(str(checkout), text)
                self.assertEqual(svc.room_offers(), ())
                self.assertEqual(
                    svc.booked_text(),
                    f"当前已预订{('标间', '情趣主题房', '顶级套房')[room_id]}，"
                    f"退房时间为{checkout.day}日12点\n",
                )

    def test_panel_draws_service_reply(self) -> None:
        """验证 Order_Hotel_Room_Panel.order_room 绘制服务返回的凭证不足等待提示。"""
        normal_panel.Order_Hotel_Room_Panel(80).order_room(2)
        self.assertEqual(
            self.world.wait_texts, ["\n粉红凭证不足，无法预订顶级套房\n"]
        )


class BackendIsolationTest(FastTestCase):
    """normal_panel_service 无界面与无结算导入边界的独立子进程测试。"""

    def test_fresh_backend_process_loads_no_ui_or_settle(self) -> None:
        """在拦截界面、结算与窗口模块的独立子进程中执行服务核心接口，验证结果正确且无受限模块加载。"""
        result = subprocess.run(
            [sys.executable, "-c", BACKEND_RUN, str(ROOT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        out = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(out["attempted"], [])
        self.assertEqual(out["loaded"], [])
        self.assertEqual(out["door"], [CANNOT_CLOSE, True])
        self.assertEqual(out["rows"], ["  [0012]cow：80ml".ljust(20, "　")])
        self.assertEqual(out["take"], "\n  你将cow的母乳（80ml）放进了背包\n")
        self.assertEqual(out["bag"], [80])
        self.assertIn("（30ml）转化为了【鲜母乳】", out["turn"])
        self.assertEqual(out["fresh"], 30)
        self.assertEqual(out["poor"], "\n粉红凭证不足，无法预订标间\n")
        self.assertEqual(out["left"], 2)
        self.assertEqual(out["room"], 2)
        self.assertEqual(out["items"], [1, 5])
        now = datetime.datetime.fromisoformat(out["now"])
        self.assertEqual((now.hour, now.minute), (9, 41))
        checkout = now + datetime.timedelta(days=1)
        self.assertEqual(out["checkout"], str(checkout.replace(hour=12)))
        self.assertEqual(
            out["booked"],
            f"\n成功预订了情趣主题房，退房时间为{out['checkout']}\n",
        )
        self.assertEqual(
            out["status"],
            f"当前已预订情趣主题房，退房时间为{checkout.day}日12点\n",
        )
