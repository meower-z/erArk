# -*- coding: UTF-8 -*-
"""
工程部与体检的数据存进存档再读回
================================
开新游戏（SlowTestCase.setUp），存档目录换成临时目录。给工程部与体检的十二项数据都写上值，再存档、读档。
每项读回的值、类型与先后都与存档前相同。再存一次，文件 "2" 里这十二个键与上一次存的相同。
"""

import importlib
import json
import os
import tempfile
from typing import Any
from unittest import mock

from tests import kernel_data
from tests.slow.base import SlowTestCase

SLOT = "sw"
""" 测试写的存档id """


def game(name: str) -> Any:
    """
    按名字导入一个游戏模块。测试在游戏启动之后才调用它
    Keyword arguments:
    name -- 模块名
    Return arguments:
    Any -- 模块
    """
    return importlib.import_module(name)


class MaintenanceExamSaveTest(SlowTestCase):
    """工程部与体检十二项数据的存档与读档"""

    def setUp(self) -> None:
        """开新游戏（SlowTestCase.setUp），存档目录换成临时目录"""
        super().setUp()
        index = game("Script.Modules.save_load.index")
        self.folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", self.folder))

    def fill(self) -> None:
        """给十二项数据都写上值，用到两名在编干员、两个真实场景与两项检查"""
        m = game("Script.Modules.domains.maintenance")
        px = game("Script.Modules.domains.physical_exam")
        map_handle = game("Script.Design.map_handle")
        a, b = sorted(kernel_data.domain("roster").active() - {0})[:2]
        office = map_handle.get_map_system_path_str_for_list(
            ["中枢", "博士办公室"]
        )
        exam_room = map_handle.get_map_system_path_str_for_list(
            ["医疗", "体检科"]
        )
        m.set_damage(exam_room, 2)
        m.set_damage(office, 1)
        m.set_place(b, office)
        m.set_place(a, exam_room)
        m.set_repair(b, a)
        m.set_setting(3, 1)
        m.toggle_operator(b)
        m.toggle_operator(a)
        px.set_setting(4, 2)
        px.record_check(a, "check_b")
        px.finish(a, {"check_a", "check_b"})
        px.record_check(b, "check_a")
        px.add(px.WAITING, b)
        px.add(px.CHOSEN, a)
        px.toggle_week_day(5)
        px.toggle_week_day(2)

    def values(self) -> list[object]:
        """
        十二项数据此刻的值，带类型与先后
        Return arguments:
        list -- 各项的 repr。表取 (键, 值) 列表的 repr，三份体检名单先排序
        """
        m = game("Script.Modules.domains.maintenance")
        px = game("Script.Modules.domains.physical_exam")
        tables: list[object] = [
            m.damage(),
            m.places(),
            m.repairs(),
            m.settings(),
            m.operators(),
            px.settings(),
            px.checks(px.TODAY),
            px.checks(px.IN_PROGRESS),
            *(sorted(px.ids(key)) for key in px.ID_LISTS),
            px.week_days(),
        ]
        return [
            repr(list(t.items())) if isinstance(t, dict) else repr(t)
            for t in tables
        ]

    def stored(self) -> dict[str, object]:
        """
        存档文件 "2" 里工程部与体检的十二个键
        Return arguments:
        dict -- 键到存下的 JSON 值，文件里没有的键为 None
        """
        m = game("Script.Modules.domains.maintenance")
        px = game("Script.Modules.domains.physical_exam")
        keys = {m.DAMAGE, m.PLACES, m.REPAIRS, m.SETTING, m.OPERATORS}
        keys |= {
            px.SETTING,
            px.TODAY,
            px.IN_PROGRESS,
            *px.ID_LISTS,
            px.WEEK_DAYS,
        }
        with open(os.path.join(self.folder, SLOT, "2"), encoding="utf-8") as f:
            data = json.load(f)["data"]
        return {key: data.get(key) for key in sorted(keys)}

    def test_save_and_load_keep_values(self) -> None:
        """存档再读档，十二项的值、类型与先后不变。再存一次，文件 "2" 里这十二个键不变"""
        save_handle = game("Script.Core.save_handle")
        kernel_data.written(self.fill)
        before = self.values()
        save_handle.establish_save(SLOT)
        first = self.stored()
        self.assertEqual(sum(v is not None for v in first.values()), 12)
        save_handle.input_load_save(SLOT)
        self.assertEqual(self.values(), before)
        save_handle.establish_save(SLOT)
        self.assertEqual(self.stored(), first)
