# -*- coding: UTF-8 -*-
"""
收藏地点、debug 模式与输入记录
==============================
- 收藏地点（map.bookmarks）与 debug 模式（mode.debug）随 kernel_state 编解码往返。
- 「当前地点在收藏列表中」的前提随收藏与取消收藏变化。建玩家时收藏四个地点。
- 读版本 26 的旧存档时，文件 "1" 里的 debug 模式、收藏地点与输入记录（input_cache）写进 GameState
  （对应 mode.debug、map.bookmarks 与 log.inputs）。界面输入历史（view.input_cache）不随读档改变。
- 医疗部初始化后的日结算照常完成。
- 静态检查日志的最近输入文本读取界面输入历史（view.input_cache）的末尾十条。
存档写在临时目录里（index.SAVE_DIR 换成它）。
"""

import tempfile
from unittest import mock

from Script.Core import constant_promise, save_handle
from Script.Design import character, handle_premise
from Script.Kernel import core
from Script.Modules.domains import activity, bookmarks, country, history, modes
from Script.Modules.save_load import index, kernel_state
from Script.System.Medical_System import medical_service
from Script.Test.Static_Check import check_log
from Script.UI.Moudle import draw, view
from tests import kernel_data, legacy_save
from tests.fast.base import FastTestCase

SLOT = "bookmarks_debug"
""" 测试用的存档id """


class Quiet:
    """不画的绘制对象，代替 NormalDraw 与 LeftDraw"""

    def __init__(self) -> None:
        """初始化为空文本、0 宽度与空样式"""
        self.text = ""
        self.width = 0
        self.style = ""

    def draw(self) -> None:
        """什么也不画"""


class BookmarksDebugStateTest(FastTestCase):
    """收藏地点与 debug 模式在 GameState 里，输入记录在界面上"""

    def setUp(self) -> None:
        """复原小世界，存档写进临时目录，建玩家角色"""
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))
        self.world.chara(0, "博士")

    def in_bookmarks(self) -> float:
        """
        求玩家所在地点的「在收藏列表中」前提权重
        Return arguments:
        float -- 前提权重
        """
        premise = constant_promise.Premise.PALCE_IN_COLLECTION_LIST
        return handle_premise.handle_premise(premise, 0)

    def test_codec_round_trip(self) -> None:
        """收藏两个地点并打开 debug 模式后编解码，读回的值相同"""
        with kernel_data.writing():
            bookmarks.add(["中枢", "博士房间"])
            bookmarks.add(["书", "藏品馆"])
            modes.set_debug(True)
        decoded = kernel_state.decode(
            kernel_state.encode(core.state()), tagged=True
        )
        self.assertEqual(
            bookmarks.places(decoded), [["中枢", "博士房间"], ["书", "藏品馆"]]
        )
        self.assertTrue(modes.debug(decoded))

    def test_premise_follows_bookmarks(self) -> None:
        """收藏玩家所在地点后前提成立，取消收藏后不成立。取消没收藏的地点时报 ValueError"""
        here = activity.position(0)
        self.assertEqual(self.in_bookmarks(), 0)
        kernel_data.put(bookmarks.add, here)
        self.assertEqual(self.in_bookmarks(), 1)
        kernel_data.put(bookmarks.remove, here)
        self.assertEqual(self.in_bookmarks(), 0)
        with self.assertRaises(ValueError), kernel_data.writing():
            bookmarks.remove(here)

    def test_player_starts_with_four_bookmarks(self) -> None:
        """建玩家（character.init_attr(0)）后收藏着博士房间、博士办公室、成人用品店与藏品馆"""
        kernel_data.written(character.init_attr, 0)
        self.assertEqual(
            bookmarks.places(),
            [
                ["中枢", "博士房间"],
                ["中枢", "博士办公室"],
                ["贸易", "成人用品店"],
                ["书", "藏品馆"],
            ],
        )

    def test_v26_save_moves_fields(self) -> None:
        """
        版本 26 的旧存档带着六个字段：读档后 debug 模式、收藏地点与最近输入（log.inputs）取自存档，
        界面输入历史（view.input_cache）不变
        """
        old = legacy_save.old(
            "Cache",
            debug_mode=True,
            collect_position_list=[["中枢", "博士办公室"]],
            input_cache=["9"],
            old_character_id=1,
            over_behavior_character={0},
            rhodes_island=legacy_save.old("Rhodes_Island"),
        )
        legacy_save.write_cache(SLOT, old)
        self.enterContext(mock.patch.object(view, "input_cache", ["1", "2"]))
        with (
            mock.patch.object(draw, "NormalDraw", Quiet),
            mock.patch.object(draw, "LeftDraw", Quiet),
            mock.patch.object(country, "fill", lambda: None),
            kernel_data.writing(),
        ):
            save_handle.install_save(SLOT, 26)
            self.assertTrue(modes.debug())
            self.assertEqual(bookmarks.places(), [["中枢", "博士办公室"]])
            self.assertEqual(history.inputs(), ["9"])
        self.assertEqual(view.input_cache, ["1", "2"])

    def test_medical_settles_without_island(self) -> None:
        """医疗部初始化后的日结算成功"""
        with kernel_data.writing():
            medical_service.init_medical_department_data()
            report = medical_service.settle_medical_department(draw_flag=False)
        self.assertTrue(report["success"])

    def test_check_log_reads_input_history(self) -> None:
        """界面输入记录有 12 条时，静态检查日志的最近输入文本取末尾 10 条"""
        history = [str(i) for i in range(12)]
        self.enterContext(mock.patch.object(view, "input_cache", history))
        self.assertEqual(
            check_log._build_recent_input_text(), str(history[-10:])
        )
