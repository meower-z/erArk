# -*- coding: UTF-8 -*-
"""
借还书、脱衣结算与调教前准备后端辅助测试
========================================
- 借还书服务（library_service）：阅读难度门槛、无书可借判定、借书装配、阅读次数与还书历史更新。
- 脱衣结算（panel_starters.start_undress）：脱衣后已脱衣物列表去重，并移除仍在穿着的衣物编号。
- 调教前准备（training_prep）：道具表映射校验，以及移入场景、清洁、道具消耗与排入等待流程。
- 后端模块依赖检查：library_service 与 training_prep 的模块全局命名空间不含界面或 Tk 模块。
"""

from types import ModuleType

from Script.Config import game_config
from Script.Core import constant
from Script.Design import map_handle
from Script.Kernel import core
from Script.Modules.domains import activity, chara_life, dirty, h_state
from Script.Modules.domains import inventory, library, prison, status
from Script.Modules.domains import wardrobe, work
from Script.Modules.gameplay_resolution import intent, library_service
from Script.Modules.gameplay_resolution import panel_starters, plan_queue
from Script.Modules.gameplay_resolution import training_prep, working
from tests import chara_abilities as ca
from tests.fast.base import FastTestCase

READER = 1
""" 测试用读者角色编号 """
EASY_SKILL_BOOK = 1000
""" 难度 1 的技能类测试书籍编号（类型 11） """
NORMAL_SKILL_BOOK = 1005
""" 难度 2 的技能类测试书籍编号（类型 11） """
HARD_SKILL_BOOK = 1010
""" 难度 3 的技能类测试书籍编号（类型 11） """
SKILL_ABILITY = 40
""" 测试书籍类型 11 对应的能力编号 """


class LibraryServiceTest(FastTestCase):
    """图书馆借还书服务（library_service）的能力门槛、借阅装配、阅读计数与还书测试"""

    def setUp(self) -> None:
        """创建玩家与读者角色并打开基于当前状态的工作集上下文"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(READER, "读者")
        self.enterContext(working.based_on(core.state()))

    def lend_all_but(self, *free_books: int) -> None:
        """
        将指定书籍设为未借出，其余配置书籍全部标记为由玩家持有
        Keyword arguments:
        free_books -- int，保持未借出状态的书籍编号列表
        Return arguments:
        None -- 直接写入图书馆借阅表
        """
        library.put_holders(
            {
                book_id: library.FREE if book_id in free_books else 0
                for book_id in game_config.config_book
            }
        )

    def test_can_read_book_follows_difficulty_and_ability(self) -> None:
        """技能类书籍在难度 1、2、3 下按对应能力值 2、3、6 正确判定能否阅读"""
        ca.ability(READER)[SKILL_ABILITY] = 2
        self.assertTrue(library_service.can_read_book(READER, EASY_SKILL_BOOK))
        self.assertFalse(
            library_service.can_read_book(READER, NORMAL_SKILL_BOOK)
        )
        ca.ability(READER)[SKILL_ABILITY] = 3
        self.assertTrue(
            library_service.can_read_book(READER, NORMAL_SKILL_BOOK)
        )
        self.assertFalse(library_service.can_read_book(READER, HARD_SKILL_BOOK))
        ca.ability(READER)[SKILL_ABILITY] = 6
        self.assertTrue(library_service.can_read_book(READER, HARD_SKILL_BOOK))

    def test_no_book_when_free_books_are_too_hard_or_finished(self) -> None:
        """空闲书籍已读完或难度过高时，只读判定、随机借书与装配均失败且不写入借阅记录"""
        self.lend_all_but(EASY_SKILL_BOOK, NORMAL_SKILL_BOOK)
        chara_life.read_book_progress.set_item(READER, EASY_SKILL_BOOK, 100)
        self.assertFalse(library_service.judge_can_get_read_book(READER))
        self.assertEqual(library_service.check_random_borrow_book(READER), 0)
        self.assertFalse(library_service.prepare_npc_read_book(READER))
        self.assertEqual(chara_life.borrow_book_id_set(READER), set())
        self.assertEqual(chara_life.borrow_book_history(READER), [])

    def test_prepare_borrows_the_only_readable_book(self) -> None:
        """存在唯一可读空闲书时借出并写入行为与历史记录，已持书时全库借出仍判为可读"""
        self.lend_all_but(EASY_SKILL_BOOK, NORMAL_SKILL_BOOK)
        chara_life.read_book_progress.set_item(READER, EASY_SKILL_BOOK, 100)
        ca.ability(READER)[SKILL_ABILITY] = 3
        self.assertTrue(library_service.judge_can_get_read_book(READER))
        self.assertTrue(library_service.prepare_npc_read_book(READER))
        self.assertEqual(
            chara_life.borrow_book_id_set(READER), {NORMAL_SKILL_BOOK}
        )
        self.assertEqual(library.holders()[NORMAL_SKILL_BOOK], READER)
        behavior = activity.behavior(READER)
        self.assertEqual(behavior.book_id, NORMAL_SKILL_BOOK)
        self.assertEqual(
            behavior.book_name, game_config.config_book[NORMAL_SKILL_BOOK].name
        )
        (record,) = chara_life.borrow_book_history(READER)
        self.assertEqual(record["book_id"], NORMAL_SKILL_BOOK)
        self.assertIsNone(record["return_time"])
        self.assertEqual(record["total_read_count"], 0)
        self.lend_all_but()
        self.assertTrue(library_service.judge_can_get_read_book(READER))
        self.assertEqual(library_service.check_random_borrow_book(READER), 1)

    def test_read_count_and_return(self) -> None:
        """验证阅读次数累加、还书概率为 0 时不归还，以及触发还书后释放书籍并更新历史记录"""
        self.lend_all_but(EASY_SKILL_BOOK)
        self.assertEqual(library_service.check_return_book(READER), 0)
        self.assertEqual(library_service.check_random_borrow_book(READER), 1)
        library_service.update_read_count_in_history(READER, EASY_SKILL_BOOK)
        library_service.update_read_count_in_history(READER, EASY_SKILL_BOOK)
        (record,) = chara_life.borrow_book_history(READER)
        self.assertEqual(record["total_read_count"], 2)
        chara_life.book_return_possibility.set(READER, 0)
        self.assertEqual(library_service.check_return_book(READER), 0)
        self.assertEqual(library.holders()[EASY_SKILL_BOOK], READER)
        chara_life.read_book_progress.set_item(READER, EASY_SKILL_BOOK, 95)
        chara_life.book_return_possibility.set(READER, 101)
        self.assertEqual(library_service.check_return_book(READER), 1)
        self.assertEqual(library.holders()[EASY_SKILL_BOOK], library.FREE)
        self.assertEqual(chara_life.borrow_book_id_set(READER), set())
        (record,) = chara_life.borrow_book_history(READER)
        self.assertIsNotNone(record["return_time"])
        self.assertEqual(record["total_read_count"], 3)


class UndressSettleTest(FastTestCase):
    """脱衣开始函数（panel_starters.start_undress）的脱衣后列表去重与清理测试"""

    def setUp(self) -> None:
        """创建玩家与交互对象，打开工作集上下文并设置交互目标"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "对方")
        self.enterContext(working.based_on(core.state()))
        activity.set_target(0, 1)

    def test_cloth_off_has_no_duplicate_or_worn_item(self) -> None:
        """脱去外衣后，已脱列表对重复编号去重，并移除仍在穿着部位的衣物编号"""
        wardrobe.set_part(1, "cloth_off", 5, [501])
        wardrobe.set_part(1, "cloth_off", 9, [951])
        chosen = intent.Intent(
            behavior_id=constant.Behavior.WAIT, minutes=1, args={"choice": 0}
        )
        panel_starters.start_undress(0, chosen)
        cloth = wardrobe.of(1)
        self.assertEqual(list(cloth.cloth_wear[5]), [])
        self.assertEqual(list(cloth.cloth_off[5]), [501])
        self.assertEqual(list(cloth.cloth_wear[9]), [951])
        self.assertEqual(list(cloth.cloth_off[9]), [])


class TrainingPrepTest(FastTestCase):
    """调教前准备模块（training_prep）的道具表映射与准备流程测试"""

    def setUp(self) -> None:
        """创建玩家、目标与监狱长角色，设置监狱长与交互目标并重置监禁设置"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "对方")
        self.world.chara(2, "监狱长")
        self.enterContext(working.based_on(core.state()))
        self.addCleanup(plan_queue.forget)
        work.set_warden(2)
        activity.set_target(2, 1)
        prison.reset_settings()

    def test_body_items_map_to_item_config(self) -> None:
        """道具表含 14 项且有效序号均映射到 config_item，越界序号返回 -1"""
        count = len(training_prep.body_item_list)
        self.assertEqual(count, 14)
        for index in range(count):
            item_id = training_prep.get_item_id_from_body_item_list(index)
            self.assertIn(item_id, game_config.config_item)
        self.assertEqual(training_prep.get_item_id_from_body_item_list(-1), -1)
        self.assertEqual(
            training_prep.get_item_id_from_body_item_list(count), -1
        )

    def test_preparation_moves_cleans_uses_items_and_waits(self) -> None:
        """验证调教前准备移入调教室、清洁、消耗物品 100 及启用道具库存，并为目标与监狱长排入等待"""
        dirty.set(1, a_clean=2)
        prison.set_cleaning(True)
        prison.set_lubrication(True)
        for tool in (4, 6, 9, 13):
            prison.set_tool(tool, 1)
        stock = ((100, 1), (133, 0), (132, 1), (107, 2), (120, 3))
        for item_id, count in stock:
            inventory.set_item(0, item_id, count)
        training_prep.start_training_preparation(1)

        rooms = constant.place_data["Humiliation_Room"]
        room = activity.position(0)
        self.assertIn(map_handle.get_map_system_path_str_for_list(room), rooms)
        self.assertEqual(activity.position(1), room)
        self.assertEqual(activity.position(2), room)
        self.assertEqual(dirty.get(1, "a_clean"), 0)
        self.assertEqual(inventory.items(0)[100], 0)
        self.assertGreater(status.of(1)[8], 0)
        self.assertFalse(h_state.body_item_on(1, 4))
        self.assertTrue(h_state.body_item_on(1, 6))
        self.assertEqual(inventory.items(0)[132], 1)
        self.assertTrue(h_state.body_item_on(1, 9))
        self.assertEqual(inventory.items(0)[107], 1)
        self.assertTrue(h_state.body_item_on(0, 13))
        self.assertEqual(inventory.items(0)[120], 2)
        for waiting_id in (1, 2):
            planned = plan_queue.planned(waiting_id)[-1]
            self.assertEqual(planned["behavior_id"], constant.Behavior.WAIT)
            self.assertEqual(planned["minutes"], 10)
            self.assertEqual(planned["target"], 1)


class BackendImportTest(FastTestCase):
    """后端辅助模块的界面依赖隔离测试"""

    def test_backend_modules_hold_no_ui_module(self) -> None:
        """验证 library_service 与 training_prep 的模块全局命名空间不含界面或 Tk 模块"""
        banned = ("Script.UI", "Script.Modules.tk_ui", "tkinter")
        for module in (library_service, training_prep):
            for value in vars(module).values():
                if isinstance(value, ModuleType):
                    self.assertFalse(
                        value.__name__.startswith(banned),
                        f"{module.__name__} 导入了 {value.__name__}",
                    )
