# -*- coding: UTF-8 -*-
"""
43 号书与它的书籍类型（萝莉）不在游戏里，留着这本书的旧存档照常读档与读书
==========================================================================
- 开新游戏，博士走进图书馆打开借阅书籍面板、切到色情类书籍：没有类型为「萝莉」的书。
- 旧存档里可能留着 43 号书：图书馆借阅表里有它，有人借着它，博士把它的类型选进了阅读推荐。
  开新游戏后把这些写进游戏状态，存档到磁盘再读回，然后：
  - 博士借着它：读书面板显示没有书，借阅书籍面板显示已借 0 本，阅读推荐显示还能选 3 个；
  - 没人借它：读档时借阅表去掉这一项，其余每项不变，再存再读一次借阅表不变；每个干员都能判定借不借得到书、照常走娱乐读书，读的书都在书籍配置里；
  - 干员借着它、存档时正读着它：读档后她手上没有它，正读着的书号归零，她读完配置里所有书时判定借不到书；推进时间到她读满这一段的时长、停下来，她再走娱乐读书时读的是书籍配置里的书，借书卡上它记为已还；
  - 同上，另有阅读推荐与图书馆展示列表里的类型 43，打开游戏状态自检（系统设置 14）：读档后借书一致性自检 ISLAND-21 通过，存档里没有对它们的引用。
- 用户存档 99（不入库，装在 save/99 时才跑，没装时报跳过）：读档后借阅表里没有书籍配置里没有的书，其余每项仍在、借阅者不变或读档时还了书；再存再读一次借阅表不变。
断言只报成立与否，不把面板文字带进测试输出。
"""

import datetime
import os
import shutil
from typing import TYPE_CHECKING
from unittest import mock

from tests.slow.base import SlowTestCase

if TYPE_CHECKING:
  from typing import Any

BOOK = 43
""" 不在游戏里的书 """
BOOK_TYPE = 43
""" 不在游戏里的书籍类型 """
BOOK_TYPE_LABEL = "(萝莉)"
""" 借阅书籍面板的书行里这个类型的写法 """
LIBRARY = ["书", "图书馆"]
""" 图书馆 """
SAVE_ID = "test_book_43_removed"
""" 测试用的存档id """
PANEL_WIDTH = 100
""" 面板的绘制宽度 """
READ_MINUTES = 30
""" 读一次书的分钟数 """
ON_LOAN_TEXT = "仍在借阅中"
""" 借书卡上没还的书的还书时间 """
SELF_CHECK_SETTING = 14
""" 系统设置里「游戏状态自检」的编号：打开时读档后跑载入修复，主界面每轮跑全部自检 """
USER_SAVE_ID = "99"
""" 用户存档的存档id（不入库，装在 save/99） """


class Book43RemovedTest(SlowTestCase):
  """图书馆不列出 43 号书；旧存档里的 43 号书不妨碍读档、借书与读书"""

  def setUp(self) -> None:
    """
    开新游戏，测试结束时删掉测试用的存档
    Keyword arguments:
    无
    Return arguments:
    无
    """
    super().setUp()
    self.addCleanup(shutil.rmtree, os.path.join("save", SAVE_ID), True)

  def save_and_load(self) -> None:
    """
    把当前游戏存到磁盘再读回，与玩家在存档面板里读档后的状态相同
    Keyword arguments:
    无
    Return arguments:
    无
    """
    from Script.Core import constant, save_handle

    save_handle.establish_save(SAVE_ID)
    save_handle.input_load_save(SAVE_ID)
    self.cache.now_panel_id = constant.Panel.IN_SCENE

  def library_text(self, *tabs: str) -> str:
    """
    博士走进图书馆，打开借阅书籍面板，依次按下 tabs 里的页签再按「返回」
    Keyword arguments:
    tabs -- 要按下的页签
    Return arguments:
    str -- 面板画出的文字与按钮文字（可借的书是按钮）
    """
    from Script.Core import constant, io_init

    self.walk(LIBRARY)
    self.instruct(constant.Instruct.BORROW_BOOK)
    player_input = self.world.player
    player_input.screen.clear()
    button_text_list = []
    real_print_cmd = io_init.io_print_cmd

    def record_print_cmd(cmd_str: str, *args: "Any", **kwargs: "Any") -> None:
      """
      记下按钮文字后照常交给 PlayerInput
      Keyword arguments:
      cmd_str -- 按钮文字
      Return arguments:
      无
      """
      button_text_list.append(str(cmd_str))
      return real_print_cmd(cmd_str, *args, **kwargs)

    player_input.press(*tabs, "返回")
    with mock.patch.object(
        io_init, "io_print_cmd", side_effect=record_print_cmd
    ):
      self.show_panel()
    player_input.check_done()
    return "".join(player_input.screen) + "".join(button_text_list)

  def test_library_lists_no_book_of_removed_type(self) -> None:
    """借阅书籍面板的色情类书籍里有书，没有类型为「萝莉」的书"""
    text = self.library_text("色情类书籍")
    self.assertTrue("(可借阅)" in text, "色情类书籍页列出了可借阅的书")
    self.assertFalse(
        BOOK_TYPE_LABEL in text, "色情类书籍页没有类型为「萝莉」的书"
    )

  def test_old_save_player_holds_book(self) -> None:
    """博士借着 43 号书、阅读推荐里有它的类型：读档后读书面板、借阅书籍面板与阅读推荐都照常显示，不算这本书"""
    from Script.UI.Panel import borrow_book_panel, manage_library, read_book_panel

    player = self.cache.character_data[0]
    player.entertainment.borrow_book_id_set.add(BOOK)
    player.entertainment.read_book_progress[BOOK] = 40
    borrow_book_panel.add_borrow_history_record(0, BOOK)
    self.cache.rhodes_island.book_borrow_dict[BOOK] = 0
    self.cache.rhodes_island.recommend_book_type_set.add(BOOK_TYPE)
    self.save_and_load()
    player_input = self.world.player
    player_input.screen.clear()
    player_input.press("返回")
    read_book_panel.Read_Book_Panel(PANEL_WIDTH).draw()
    player_input.check_done()
    self.assertTrue(
        "当前未持有书籍" in "".join(player_input.screen),
        "读书面板显示博士没有书",
    )

    self.assertTrue(
        "已借书量/最大借书量：0/3" in self.library_text(),
        "借阅书籍面板显示博士已借 0 本",
    )

    player_input.screen.clear()
    player_input.press("阅读推荐", "返回", "返回")
    manage_library.Manage_Library_Panel(PANEL_WIDTH).draw()
    player_input.check_done()
    self.assertTrue(
        "当前剩余可选推荐 3" in "".join(player_input.screen),
        "阅读推荐显示还能选 3 个",
    )

  def read_as_entertainment(self, character_id: int) -> None:
    """
    让干员走一次娱乐读书（状态机 ENTERTAIN_READ），与她的行为循环选中这项娱乐时相同
    Keyword arguments:
    character_id -- 角色id
    Return arguments:
    无
    """
    from Script.Core import constant
    from Script.Design import handle_state_machine

    handle_state_machine.handle_state_machine(
        constant.StateMachine.ENTERTAIN_READ, character_id
    )

  def test_old_save_nobody_holds_book(self) -> None:
    """43 号书在借阅表里、没人借：读档时借阅表去掉这一项、其余每项不变，再存再读一次不变；每个干员照常判定借书、走娱乐读书，读的书都在书籍配置里"""
    from Script.Config import game_config
    from Script.Core import constant
    from Script.UI.Panel import borrow_book_panel

    book_borrow_dict = self.cache.rhodes_island.book_borrow_dict
    book_borrow_dict[BOOK] = -1
    kept = {
        book_id: holder
        for book_id, holder in book_borrow_dict.items()
        if book_id != BOOK
    }
    self.save_and_load()
    book_borrow_dict = self.cache.rhodes_island.book_borrow_dict
    self.assertNotIn(
        BOOK, book_borrow_dict, "读档时借阅表去掉了没人借的 43 号书"
    )
    self.assertEqual(book_borrow_dict, kept, "借阅表其余每项不变")
    self.save_and_load()
    self.assertEqual(
        self.cache.rhodes_island.book_borrow_dict,
        kept,
        "再存再读一次，借阅表不变",
    )

    npc_list = sorted(cid for cid in self.cache.npc_id_got if cid != 0)
    self.assertTrue(npc_list, "本局有干员")
    reader_count = 0
    for character_id in npc_list:
      borrow_book_panel.judge_can_get_read_book(character_id)
      self.read_as_entertainment(character_id)
      behavior = self.cache.character_data[character_id].behavior
      if behavior.behavior_id == constant.Behavior.READ_BOOK:
        reader_count += 1
        self.assertIn(
            behavior.book_id,
            game_config.config_book,
            f"干员 {character_id} 读的书在书籍配置里",
        )
    self.assertTrue(reader_count, "有干员借到书在读")

  def test_old_save_npc_reads_book(self) -> None:
    """干员借着 43 号书、存档时正读着它：读档后她手上没有 43 号书、正读着的书号归零，读完配置里所有书时判定借不到书；她读满这一段，再走娱乐读书时读的是书籍配置里的书，借书卡上 43 号书记为已还"""
    from Script.Config import game_config
    from Script.Core import constant
    from Script.UI.Panel import borrow_book_panel, manage_library

    character_id = self.lend_and_read_book()
    self.save_and_load()
    character_data = self.cache.character_data[character_id]
    self.assertNotIn(
        BOOK,
        character_data.entertainment.borrow_book_id_set,
        "读档后她手上没有 43 号书",
    )
    self.assertEqual(
        (character_data.behavior.behavior_id, character_data.behavior.book_id),
        (constant.Behavior.READ_BOOK, 0),
        "读档后她还在读书，书号归零",
    )

    # 她把书籍配置里的书都读完了时，判定借不到书
    read_book_progress = dict(character_data.entertainment.read_book_progress)
    character_data.entertainment.read_book_progress.update(
        {book_id: 100 for book_id in game_config.config_book}
    )
    self.assertFalse(
        borrow_book_panel.judge_can_get_read_book(character_id),
        "读完了配置里的每本书：判定借不到书",
    )
    character_data.entertainment.read_book_progress = read_book_progress
    self.assertTrue(
        borrow_book_panel.judge_can_get_read_book(character_id),
        "还有没读完的书：判定借得到书",
    )

    read_start = character_data.behavior.start_time

    def done() -> bool:
      """她读完了存档时正读的这一段"""
      behavior = self.cache.character_data[character_id].behavior
      return (
          behavior.behavior_id != constant.Behavior.READ_BOOK
          or behavior.start_time != read_start
      )

    read_end = read_start + datetime.timedelta(minutes=READ_MINUTES)
    self.assertTrue(
        self.wait_until(done, READ_MINUTES * 2),
        f"{READ_MINUTES * 2} 分钟内她读完了这一段",
    )
    self.assertGreaterEqual(
        self.cache.game_time,
        read_end,
        f"她读满 {READ_MINUTES} 分钟才停下，没有中途被打断",
    )
    self.read_as_entertainment(character_id)
    self.assertEqual(
        character_data.behavior.behavior_id,
        constant.Behavior.READ_BOOK,
        "她在读书",
    )
    self.assertIn(
        character_data.behavior.book_id,
        game_config.config_book,
        "她读的书在书籍配置里",
    )

    player_input = self.world.player
    player_input.screen.clear()
    player_input.press("返回")
    manage_library.Manage_Library_Panel(PANEL_WIDTH).show_character_history(
        character_id
    )
    player_input.check_done()
    on_loan_count = "".join(player_input.screen).count(ON_LOAN_TEXT)
    self.assertEqual(
        on_loan_count,
        len(character_data.entertainment.borrow_book_id_set),
        "她的借书卡上记为仍在借阅中的，只有她手上的书",
    )

  def lend_and_read_book(self) -> int:
    """
    让本局 id 最小的干员借着 43 号书（借阅表与借书卡都记上），并正在读它
    Keyword arguments:
    无
    Return arguments:
    int -- 干员的角色id
    """
    from Script.Core import constant
    from Script.UI.Panel import borrow_book_panel

    character_id = min(cid for cid in self.cache.npc_id_got if cid != 0)
    character_data = self.cache.character_data[character_id]
    character_data.entertainment.borrow_book_id_set.add(BOOK)
    self.cache.rhodes_island.book_borrow_dict[BOOK] = character_id
    borrow_book_panel.add_borrow_history_record(character_id, BOOK)
    character_data.behavior.behavior_id = constant.Behavior.READ_BOOK
    character_data.state = constant.CharacterStatus.STATUS_READ_BOOK
    character_data.behavior.book_id = BOOK
    character_data.behavior.start_time = self.cache.game_time
    character_data.behavior.duration = READ_MINUTES
    return character_id

  def test_old_save_loaned_book_passes_island_21(self) -> None:
    """干员借着、正读着 43 号书，阅读推荐与图书馆展示列表里有它：打开游戏状态自检时读档，借书一致性自检 ISLAND-21 随即通过，存档里没有对 43 号书与类型 43 的引用；再存再读一次，借阅表不变"""
    from Script.Test.Static_Check.checks import check_island

    self.cache.all_system_setting.base_setting[SELF_CHECK_SETTING] = 1
    self.lend_and_read_book()
    rhodes_island = self.cache.rhodes_island
    rhodes_island.recommend_book_type_set.add(BOOK_TYPE)
    rhodes_island.now_show_book_cid_of_type[BOOK_TYPE] = [BOOK]
    self.save_and_load()
    self.assertEqual(
        check_island.check_island_21_book_borrow_consistency(),
        [],
        "读档后 ISLAND-21 通过",
    )
    rhodes_island = self.cache.rhodes_island
    references = []
    if BOOK in rhodes_island.book_borrow_dict:
      references.append("借阅表")
    if BOOK_TYPE in rhodes_island.now_show_book_cid_of_type:
      references.append("图书馆展示列表")
    if BOOK_TYPE in rhodes_island.recommend_book_type_set:
      references.append("阅读推荐")
    for character_id, character_data in self.cache.character_data.items():
      entertainment = character_data.entertainment
      if BOOK in entertainment.borrow_book_id_set:
        references.append(f"角色 {character_id} 的借书集合")
      if any(
          record.get("book_id") == BOOK and record.get("return_time") is None
          for record in entertainment.borrow_book_history
      ):
        references.append(f"角色 {character_id} 借书卡上没还的记录")
      if character_data.behavior.book_id == BOOK:
        references.append(f"角色 {character_id} 正读着的书")
    self.assertEqual(references, [], "存档里没有对 43 号书与类型 43 的引用")
    book_borrow_dict = dict(rhodes_island.book_borrow_dict)
    self.save_and_load()
    self.assertEqual(
        self.cache.rhodes_island.book_borrow_dict,
        book_borrow_dict,
        "再存再读一次，借阅表不变",
    )

  def test_user_save_99_drops_unknown_books(self) -> None:
    """用户存档 99：读档后借阅表里没有书籍配置里没有的书，其余每项仍在、借阅者不变或读档时还了书；再存再读一次，借阅表不变"""
    from Script.Config import game_config
    from Script.Core import constant, save_handle

    if not os.path.isfile(os.path.join("save", USER_SAVE_ID, "1")):
      self.skipTest("save/99 fixture not installed")
    saved = dict(
        save_handle.load_save(USER_SAVE_ID).rhodes_island.book_borrow_dict
    )
    unknown = {
        book_id for book_id in saved if book_id not in game_config.config_book
    }
    self.assertTrue(unknown, "存档 99 的借阅表里有书籍配置里没有的书")
    save_handle.input_load_save(USER_SAVE_ID)
    self.cache.now_panel_id = constant.Panel.IN_SCENE
    book_borrow_dict = self.cache.rhodes_island.book_borrow_dict
    self.assertFalse(
        unknown & set(book_borrow_dict), "读档后借阅表里没有这些项"
    )
    # 别的读档转换会还掉一些书（例如离线幼年女儿借的书）：借阅者变成 -1，原借阅者手上也没有这本书
    changed = []
    for book_id, holder in saved.items():
      if book_id in unknown:
        continue
      now_holder = book_borrow_dict.get(book_id, "missing")
      holder_data = self.cache.character_data.get(holder)
      returned = now_holder == -1 and (
          holder_data is None
          or book_id not in holder_data.entertainment.borrow_book_id_set
      )
      if now_holder != holder and not returned:
        changed.append((book_id, holder, now_holder))
    self.assertEqual(
        changed, [], "借阅表其余每项仍在，借阅者不变或读档时还了书"
    )
    loaded = dict(book_borrow_dict)
    self.save_and_load()
    self.assertEqual(
        self.cache.rhodes_island.book_borrow_dict,
        loaded,
        "再存再读一次，借阅表不变",
    )
