"""
食堂上架与收藏品结算后端服务测试
================================
- 食堂上架服务（canteen_service）：正常调味食物上架、非正常调味食物保留以及无正常调味食物时的提示行为。
- 收藏品结算服务（collection_service）：临时内裤与袜子收进永久收藏、空临时表提示、
  经 load_order 登记后的 Tk 提示绘制与成就通知，以及信物装备上限刷新。
"""

from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import game_type, get_text
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.domains import identity, inventory, kitchen
from Script.Modules.domains import player_collection
from Script.Modules.gameplay_resolution import achievement_service
from Script.Modules.gameplay_resolution import canteen_service
from Script.Modules.gameplay_resolution import collection_service
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase

OPERATOR = 1
""" 测试用干员角色编号 """
SPICY = 4
""" 测试用辣味调味编号（Seasoning.csv 编号 4） """
CLOTHING_ACHIEVEMENT = 221
""" 测试用服装收藏成就编号（Achievement.csv 编号 221） """


def make_food(name: str, recipe: int, seasoning: int) -> game_type.Food:
    """
    构造用于测试的 Food 对象。
    Keyword arguments:
    name -- str，食物名称
    recipe -- int，食谱编号
    seasoning -- int，调味编号
    Return arguments:
    Food -- 填好名称、食谱编号与调味编号的 Food 实例
    """
    food = game_type.Food()
    food.name = name
    food.recipe = recipe
    food.special_seasoning = seasoning
    return food


def clothing_ids() -> tuple[int, int, int]:
    """
    从服装模板表取出一组内裤编号、袜子编号与不存在的编号。
    Keyword arguments:
    无
    Return arguments:
    tuple[int, int, int] -- 依次为类型 9（内裤）的首个模板编号、类型 10（袜子）的首个模板编号
    与超出当前最大编号的缺失编号
    """
    by_type: dict[int, int] = {}
    for cid, tem in game_config.config_clothing_tem.items():
        by_type.setdefault(tem.clothing_type, cid)
    missing = max(game_config.config_clothing_tem) + 1
    return by_type[9], by_type[10], missing


class NoticeCase(FastTestCase):
    """记录 ui_hooks 提示调用的测试基类"""

    def setUp(self) -> None:
        """创建玩家与干员角色、打开工作集上下文并接管提示回调列表"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(OPERATOR, "干员1")
        self.enterContext(working.based_on(core.state()))
        self.notices: list[tuple[str, bool, str | None, bool]] = []
        self.enterContext(mock.patch.object(ui_hooks, "_notices", [self.note]))

    def note(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """
        记录一次提示回调收到的参数元组。
        Keyword arguments:
        text -- str，提示文本
        wait -- bool，是否等待玩家确认
        style -- str | None，文本样式名
        use_text_width -- bool，是否按配置的文本宽度排版
        Return arguments:
        None -- 无返回值，将四元组追加到 self.notices
        """
        self.notices.append((text, wait, style, use_text_width))


class CanteenServiceTest(NoticeCase):
    """食堂上架服务（canteen_service）的单元测试"""

    def test_normal_foods_go_to_the_canteen(self) -> None:
        """验证正常调味食物移入对应食谱的食堂货架、辣味食物留在背包并发出开始与逐份上架提示"""
        rice = make_food("米饭", 7, 0)
        soup = make_food("汤", 8, 0)
        spicy = make_food("辣汤", 8, SPICY)
        for food in (rice, spicy, soup):
            inventory.put_food(0, food)
        canteen_service.put_selfmade_food_in()
        self.assertEqual(list(inventory.foods(0)), [spicy.uid])
        shelves = kitchen.shelves()
        self.assertEqual(set(shelves), {"7", "8"})
        self.assertEqual(list(shelves["7"]), [rice.uid])
        self.assertEqual(list(shelves["8"]), [soup.uid])
        start = get_text._("{0}开始将身上没有调味的食物放进食堂取餐区里\n")
        stocked = get_text._("{0}已放入食堂\n")
        self.assertEqual(
            self.notices,
            [
                (start.format(identity.of(0).name), False, None, True),
                (stocked.format("米饭"), False, None, True),
                (stocked.format("汤"), False, None, True),
            ],
        )

    def test_without_normal_food_nothing_moves(self) -> None:
        """验证背包中无正常调味食物时食堂货架保持为空且发出无正常调味食物提示"""
        spicy = make_food("辣汤", 8, SPICY)
        inventory.put_food(0, spicy)
        canteen_service.put_selfmade_food_in()
        self.assertEqual(list(inventory.foods(0)), [spicy.uid])
        self.assertEqual(kitchen.shelves(), {})
        none_text = get_text._("{0}身上没有正常调味的食物\n")
        self.assertEqual(
            self.notices,
            [(none_text.format(identity.of(0).name), False, None, True)],
        )


class CollapseCollectionTest(NoticeCase):
    """收藏品收起逻辑（collapse_collection）的单元测试"""

    def test_temp_items_join_the_collection(self) -> None:
        """
        验证临时内裤与袜子跳过角色 0 和缺失编号后进入永久收藏、清空临时表、
        按序发出六条提示（末条为成就 221 的金色等待提示）并调用收藏服装成就结算
        """
        panty, sock, missing = clothing_ids()
        player_collection.update(
            npc_panties_tem={0: [panty], OPERATOR: [panty, missing]},
            npc_socks_tem={OPERATOR: [sock]},
        )
        settle = self.enterContext(
            mock.patch.object(
                achievement_service,
                "settle_and_notify",
                wraps=achievement_service.settle_and_notify,
            )
        )
        collection_service.collapse_collection()
        panty_name = game_config.config_clothing_tem[panty].name
        sock_name = game_config.config_clothing_tem[sock].name
        self.assertEqual(
            player_collection.get("npc_panties"), {OPERATOR: [panty_name]}
        )
        self.assertEqual(
            player_collection.get("npc_socks"), {OPERATOR: [sock_name]}
        )
        self.assertEqual(player_collection.get("npc_panties_tem"), {})
        self.assertEqual(player_collection.get("npc_socks_tem"), {})
        added = get_text._("增加了藏品：{0}的{1}\n")
        name = identity.of(OPERATOR).name
        self.assertEqual(
            self.notices,
            [
                (get_text._("\n开始摆放藏品\n"), True, None, True),
                ("", False, None, True),
                ("", False, None, True),
                (
                    added.format(name, panty_name)
                    + added.format(name, sock_name),
                    False,
                    None,
                    True,
                ),
                (get_text._("\n摆放藏品结束\n"), True, None, True),
                (
                    achievement_service.unlocked_text(CLOTHING_ACHIEVEMENT),
                    True,
                    "gold_enrod",
                    False,
                ),
            ],
        )
        settle.assert_called_once_with(get_text._("收藏服装"))

    def test_empty_temp_lists_still_notify(self) -> None:
        """验证临时藏品字典为空时按序发出开始、空汇总与结束三条提示且不触发成就解锁"""
        collection_service.collapse_collection()
        self.assertEqual(
            self.notices,
            [
                (get_text._("\n开始摆放藏品\n"), True, None, True),
                ("", False, None, True),
                (get_text._("\n摆放藏品结束\n"), True, None, True),
            ],
        )


class CollapseCollectionTkTest(FastTestCase):
    """经 load_order 登记 Tk 回调后 collapse_collection 的绘制与成就通知测试"""

    def setUp(self) -> None:
        """加载启动模块顺序、创建角色并拦截 NormalDraw 与 WaitDraw 的绘制调用"""
        super().setUp()
        core.load(load_order.LOAD_ORDER)
        self.world.chara(0, "博士")
        self.world.chara(OPERATOR, "干员1")
        self.enterContext(working.based_on(core.state()))
        self.shown: list[tuple[str, float, str, str]] = []
        for cls in (draw.NormalDraw, draw.WaitDraw):
            self.enterContext(
                mock.patch.object(
                    cls, "draw", autospec=True, side_effect=self.keep
                )
            )

    def keep(self, now: draw.NormalDraw) -> None:
        """
        记录一次文本绘制对象的类名、宽度、样式与文本内容。
        Keyword arguments:
        now -- NormalDraw，被调用的绘制对象实例
        Return arguments:
        None -- 无返回值，将四元组追加到 self.shown
        """
        self.shown.append((type(now).__name__, now.width, now.style, now.text))

    def test_notices_draw_like_the_panel_did(self) -> None:
        """
        验证收起一条临时内裤后依次绘制等待开始、空文本、汇总、等待结束四条标准样式文本
        以及一条 gold_enrod 样式等待成就提示
        """
        panty, _sock, _missing = clothing_ids()
        player_collection.update(npc_panties_tem={OPERATOR: [panty]})
        collection_service.collapse_collection()
        width = normal_config.config_normal.text_width
        added = get_text._("增加了藏品：{0}的{1}\n").format(
            identity.of(OPERATOR).name,
            game_config.config_clothing_tem[panty].name,
        )
        self.assertEqual(
            self.shown[:4],
            [
                ("WaitDraw", width, "standard", get_text._("\n开始摆放藏品\n")),
                ("NormalDraw", width, "standard", ""),
                ("NormalDraw", width, "standard", added),
                ("WaitDraw", width, "standard", get_text._("\n摆放藏品结束\n")),
            ],
        )
        self.assertEqual(
            [(cls, style) for cls, _w, style, _t in self.shown[4:]],
            [("WaitDraw", "gold_enrod")],
        )


class RefreshAllBonusTest(FastTestCase):
    """信物装备上限刷新（refresh_all_bonus）的单元测试"""

    def setUp(self) -> None:
        """创建玩家角色、打开工作集上下文并缓存收集奖励配置表"""
        super().setUp()
        self.world.chara(0, "博士")
        self.enterContext(working.based_on(core.state()))
        self.bonus = game_config.config_collection_bonus_data

    def test_unlocked_bonus_raises_token_limit(self) -> None:
        """验证已获得奖励 1 与 3 时将信物装备上限提高到奖励 3 的 effect_2 并保留已装备列表"""
        for bonus_id in (1, 3):
            player_collection.set_bonus(bonus_id)
        player_collection.set_eqip_token(1, [OPERATOR])
        collection_service.refresh_all_bonus()
        self.assertEqual(
            player_collection.get("eqip_token"),
            [self.bonus[3].effect_2, [OPERATOR]],
        )

    def test_limit_already_high_stays(self) -> None:
        """验证当前信物装备上限高于已获得奖励对应值时保持上限与已装备列表不变"""
        for bonus_id in (1, 2):
            player_collection.set_bonus(bonus_id)
        high = self.bonus[7].effect_2
        player_collection.set_eqip_token(high, [OPERATOR])
        collection_service.refresh_all_bonus()
        self.assertEqual(
            player_collection.get("eqip_token"), [high, [OPERATOR]]
        )
