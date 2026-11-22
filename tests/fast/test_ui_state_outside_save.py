# -*- coding: UTF-8 -*-
"""
界面状态与玩家的面板选择不随存档
================================
- 存档之后只改界面状态与面板选择（当前面板、做饭排序、怀孕面板筛选、指令过滤、场景面板开关），再存一次：
  两次存档的 save.json 去掉 head 后完全相同。
- 读档不改界面状态与全局的面板选择，面板回到场景面板。
- 旧版本的存档在文件 "1" 与罗德岛对象上带着界面状态与面板选择（鼠标状态是旧 game_type 类的对象）：
  还没有 settings.json 时，存档里的面板选择成为全局的，当前界面状态保持不变。
- 隐奸中显示非H指令的开关在读档时关掉。
存档都写在临时目录里（index.SAVE_DIR 换成它）。
"""

import tempfile
from unittest import mock

from Script.Config import normal_config
from Script.Core import constant, game_type, save_handle
from Script.Modules.domains import country, roster
from Script.Modules.save_load import index
from Script.UI.Moudle import view
from tests import kernel_data, legacy_save
from tests.fast.base import FastTestCase

FIRST = "ui_state_first"
""" 第一个存档 """
SECOND = "ui_state_second"
""" 第二个存档 """


def saved_state(save_id: str) -> dict[str, object]:
    """
    读取槽位的 save.json 并去掉 head 字段
    Keyword arguments:
    save_id -- 存档id
    Return arguments:
    dict -- 不含 head 的 JSON 对象
    """
    data = index.document(save_id)
    del data["head"]
    return data


class UiStateOutsideSaveTest(FastTestCase):
    """界面状态与面板选择不随存档"""

    def setUp(self) -> None:
        """复原小世界，存档写进临时目录，有玩家角色"""
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))
        self.world.chara(0, "博士")
        kernel_data.put(roster.set_active, {0})
        kernel_data.written(country.fill)

    def test_ui_choices_leave_save_alone(self) -> None:
        """存档后只改界面状态与面板选择再存一次，两份存档去掉 head 后状态相同"""
        save_handle.establish_save(FIRST)
        view.now_panel_id = constant.Panel.SEE_MAP
        view.makefood_sort_type = 2
        view.pregnancy_panel_filter_type = 3
        normal_config.system_setting.instruct_type_filter[2] = False
        normal_config.system_setting.scene_panel_show[0] = False
        save_handle.establish_save(SECOND)
        self.assertTrue(saved_state(FIRST) == saved_state(SECOND))

    def test_load_keeps_ui_state_and_preferences(self) -> None:
        """存档后改界面状态与面板选择，再读档：都还是改过的，面板回到场景面板"""
        save_handle.establish_save(FIRST)
        view.now_panel_id = constant.Panel.SEE_MAP
        view.makefood_sort_type = 2
        normal_config.system_setting.instruct_type_filter[2] = False
        normal_config.system_setting.makefood_make_count[0] = 4
        save_handle.input_load_save(FIRST)
        setting = normal_config.system_setting
        self.assertEqual(
            (
                view.now_panel_id,
                view.makefood_sort_type,
                setting.instruct_type_filter[2],
                setting.makefood_make_count[0],
            ),
            (constant.Panel.IN_SCENE, 2, False, 4),
        )

    def test_older_build_save(self) -> None:
        """
        旧存档带着界面状态、面板选择与旧 game_type 鼠标对象：
        尚无 settings.json 时面板选择成为全局设置，界面状态保持不变
        """
        save_handle.establish_save(FIRST)
        old_mouse = type("WFrameMouse", (), {"__module__": game_type.__name__})
        older = legacy_save.old(
            "Cache",
            now_panel_id=constant.Panel.SEE_MAP,
            instruct_type_filter={0: True, 1: False},
            scene_panel_show=[False, True, True, True, True],
            is_collection=True,
            rhodes_island=legacy_save.old(
                "Rhodes_Island",
                makefood_sort_type=3,
                makefood_make_count={0: 5, 1: 1, 2: 1},
                reader_now=7,
            ),
            wframe_mouse=old_mouse(),
        )
        with mock.patch.object(
            game_type, "WFrameMouse", old_mouse, create=True
        ):
            legacy_save.to_legacy(FIRST, older)
        view.makefood_sort_type = 1
        save_handle.input_load_save(FIRST)
        setting = normal_config.system_setting
        self.assertEqual(
            (
                setting.instruct_type_filter[1],
                setting.scene_panel_show[0],
                setting.makefood_make_count[0],
                view.makefood_sort_type,
            ),
            (False, False, 5, 1),
        )


class HiddenSexToggleOffAfterLoadTest(FastTestCase):
    """读档关掉隐奸中显示非H指令的开关，只看这个开关"""

    def setUp(self) -> None:
        """复原小世界，存档写进临时目录；只建存档与读档要用的玩家角色（存档头写他的名字）与国家数据"""
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))
        self.world.chara(0, "博士")
        kernel_data.written(country.fill)

    def test_load_turns_toggle_off(self) -> None:
        """开关关着时存档，打开开关后读这个档：开关是关的"""
        view.show_non_h_in_hidden_sex = False
        save_handle.establish_save(FIRST)
        view.show_non_h_in_hidden_sex = True
        save_handle.input_load_save(FIRST)
        self.assertFalse(view.show_non_h_in_hidden_sex)
