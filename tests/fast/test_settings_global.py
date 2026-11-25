# -*- coding: UTF-8 -*-
"""
全局设置与调试改时钟
====================
设置插件 save_load.settings 每个测试写到自己的临时 settings.json，内核只载入这一个插件。
- 换掉 normal_config 上的设置对象后，内核的 Reset 之后装着的仍是全局设置，
  改过的绘制设定与玩家的面板选择还在，并已写进 settings.json。
- settings.json 来回：写出的设置（含玩家的面板选择）在新进程（全局对象还没建）里装回来时完全一样；
  还没有这个文件时，第一次装取 normal_config 上此刻的设置。
- 读档交来存档里的面板选择：settings.json 里还没有面板选择时收下一次，之后读别的存档不改；文件里已有时不收。
- 调试面板改时钟只调用一次 reset_state：时钟、ticked 换成新时刻；往后跳过 0 点时 settled_day 不变（新的一天还要结算），
  往前跳时 settled_day 是新时刻的那一天。
"""

import datetime
import json
import os
import tempfile
from types import MappingProxyType
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import game_type
from Script.Design import attr_calculation, game_time
from Script.Kernel import core
from Script.Modules.gameplay_resolution import actions, debug_world_service
from Script.Modules.save_load import settings
from tests.fast.base import FastTestCase

START = game_time.to_game_time(datetime.datetime(2020, 12, 22, 10, 0))
""" 起始游戏时间 """


def empty_game(clock: int = 0) -> core.GameState:
    """
    没有角色的 GameState，带 ticked 与 settled_day
    Keyword arguments:
    clock -- 时钟分钟数
    Return arguments:
    GameState -- 新的 GameState
    """
    data = {actions.TICKED: clock, actions.SETTLED_DAY: game_time.day(clock)}
    return core.GameState(clock, MappingProxyType({}), MappingProxyType(data))


class SettingsTestCase(FastTestCase):
    """设置文件在临时目录，全局对象每个测试重新建，内核只载入设置插件"""

    def setUp(self) -> None:
        """复原小世界，换上临时的 settings.json"""
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.path = os.path.join(folder, "settings.json")
        self.enterContext(mock.patch.object(settings, "path", self.path))
        self.enterContext(mock.patch.object(settings, "_live", None))
        self.enterContext(mock.patch.object(settings, "_saved", None))
        self.enterContext(
            mock.patch.object(settings, "_has_preferences", False)
        )
        core.load((settings,))

    def fresh_process(self) -> None:
        """像新进程一样：全局对象还没建，normal_config 上是一个空的设置对象"""
        settings._live = None
        settings._saved = None
        settings._has_preferences = False
        normal_config.system_setting = game_type.System_Setting()


class LoadKeepsGlobalSettings(SettingsTestCase):
    """读档不改全局设置"""

    def test_reset_keeps_draw_setting(self) -> None:
        """normal_config 上换了一个设置对象，Reset 之后装着的仍是改过的全局设置，改动已写进文件"""
        draw_id = min(game_config.config_draw_setting)
        settings.install()
        changed = normal_config.system_setting.draw_setting[draw_id] + 1
        normal_config.system_setting.draw_setting[draw_id] = changed
        normal_config.system_setting = (
            attr_calculation.get_system_setting_zero()
        )
        core.reset_state(empty_game())
        self.assertEqual(
            normal_config.system_setting.draw_setting[draw_id], changed
        )
        with open(self.path, encoding="utf-8") as setting_file:
            on_disk = json.load(setting_file)
        self.assertEqual(on_disk["draw_setting"][str(draw_id)], changed)

    def test_reset_keeps_preferences(self) -> None:
        """改过指令过滤与场景面板开关，Reset 之后还在，并已写进文件"""
        settings.install()
        normal_config.system_setting.instruct_type_filter[3] = False
        normal_config.system_setting.scene_panel_show[4] = False
        core.reset_state(empty_game())
        setting = normal_config.system_setting
        self.assertEqual(
            (setting.instruct_type_filter[3], setting.scene_panel_show[4]),
            (False, False),
        )
        with open(self.path, encoding="utf-8") as setting_file:
            on_disk = json.load(setting_file)
        self.assertEqual(
            (
                on_disk["instruct_type_filter"]["3"],
                on_disk["scene_panel_show"][4],
            ),
            (False, False),
        )


class SettingsFileRoundTrip(SettingsTestCase):
    """settings.json 来回"""

    def test_round_trip(self) -> None:
        """每一类设置改过后写出，新进程装回来时与写出的一样"""
        settings.install()
        setting = normal_config.system_setting
        base_id = max(game_config.config_system_setting)
        adv_id = next(iter(setting.character_text_version))
        setting.base_setting[base_id] += 1
        setting.draw_setting[min(setting.draw_setting)] += 2
        setting.character_text_version[adv_id] = 2
        setting.line_before_main_update = 7
        setting.value_draw["npc"] = True
        setting.instruct_type_filter.update({0: True, 5: False})
        setting.instruct_sex_type_filter[2] = True
        setting.instruct_index_filter["kiss"] = False
        setting.scene_panel_show[1] = False
        setting.makefood_cook_mode[1] = 1
        setting.makefood_make_count[2] = 4
        settings.save()
        written = vars(setting)
        self.fresh_process()
        settings.install()
        self.assertIsNot(normal_config.system_setting, setting)
        self.assertEqual(vars(normal_config.system_setting), written)

    def test_save_skips_unchanged(self) -> None:
        """装好后没改设置，save 不写文件；改了才写，再次 save 不重写"""
        settings.install()
        settings.save()
        self.assertFalse(os.path.exists(self.path))
        normal_config.system_setting.line_before_main_update += 1
        settings.save()
        self.assertTrue(os.path.exists(self.path))
        os.remove(self.path)
        settings.save()
        self.assertFalse(os.path.exists(self.path))

    def test_daughters_text_version_not_written(self) -> None:
        """本存档女儿的口上版本（键不是角色模板的剧情编号）不写进 settings.json，模板角色的照写"""
        settings.install()
        text_version = normal_config.system_setting.character_text_version
        adv_id = next(iter(text_version))
        daughter_id = max(text_version) + 9000
        text_version[daughter_id] = 1
        text_version[adv_id] = 2
        settings.save()
        with open(self.path, encoding="utf-8") as setting_file:
            written = json.load(setting_file)["character_text_version"]
        self.assertNotIn(str(daughter_id), written)
        self.assertEqual(written[str(adv_id)], 2)

    def test_old_save_settings_adopted_once(self) -> None:
        """还没有 settings.json 时读旧存档：存档的设置成为全局设置并写出；之后再读别的存档不改"""
        draw_id = min(game_config.config_draw_setting)
        settings.install()
        from_save = attr_calculation.get_system_setting_zero()
        from_save.draw_setting[draw_id] += 3
        settings.adopt(from_save, {})
        adopted = normal_config.system_setting.draw_setting[draw_id]
        other_save = attr_calculation.get_system_setting_zero()
        other_save.draw_setting[draw_id] += 5
        settings.adopt(other_save, {})
        self.assertEqual(
            (adopted, normal_config.system_setting.draw_setting[draw_id]),
            (from_save.draw_setting[draw_id], from_save.draw_setting[draw_id]),
        )
        self.assertTrue(os.path.exists(self.path))

    def test_older_build_preferences_taken_once(self) -> None:
        """
        settings.json 是旧版本写的（没有面板选择）：读档时收下存档里的面板选择并写出；
        之后再读别的存档、或在新进程里读档，都不改
        """
        older = {"line_before_main_update": 5}
        with open(self.path, "w", encoding="utf-8") as setting_file:
            json.dump(older, setting_file)
        settings.install()
        first = {
            "instruct_type_filter": {1: False},
            "makefood_make_count": {0: 3},
        }
        settings.adopt(None, first)
        settings.adopt(None, {"instruct_type_filter": {1: True}})
        self.fresh_process()
        settings.install()
        settings.adopt(None, {"makefood_make_count": {0: 9}})
        setting = normal_config.system_setting
        self.assertEqual(
            (setting.instruct_type_filter[1], setting.makefood_make_count[0]),
            (False, 3),
        )

    def test_first_install_takes_holder_settings(self) -> None:
        """还没有 settings.json：第一次装取 normal_config 上此刻的设置"""
        draw_id = min(game_config.config_draw_setting)
        from_save = attr_calculation.get_system_setting_zero()
        from_save.draw_setting[draw_id] += 3
        settings._live = None
        normal_config.system_setting = from_save
        settings.install()
        self.assertIsNot(normal_config.system_setting, from_save)
        self.assertEqual(vars(normal_config.system_setting), vars(from_save))


class DebugClockEdit(SettingsTestCase):
    """调试面板改时钟"""

    def setUp(self) -> None:
        """内核从 START 开始"""
        super().setUp()
        self.start = game_time.minutes(START)
        core.reset_state(empty_game(self.start))

    def edit(self, new_time: datetime.datetime) -> core.GameState:
        """
        改时钟，查 reset_state 只调用了一次
        Keyword arguments:
        new_time -- 新的游戏时间
        Return arguments:
        GameState -- 改完后的 GameState
        """
        with mock.patch.object(
            core, "reset_state", wraps=core.reset_state
        ) as reset_state:
            debug_world_service.set_clock(new_time)
        reset_state.assert_called_once()
        return core.state()

    def test_forward_past_midnight(self) -> None:
        """往后跳两天：时钟与 ticked 是新时刻，settled_day 不变，新的一天还要结算"""
        new_time = START + datetime.timedelta(days=2, hours=3)
        game = self.edit(new_time)
        clock = game_time.minutes(new_time)
        self.assertEqual(game.clock, clock)
        self.assertEqual(game.data[actions.TICKED], clock)
        self.assertEqual(
            game.data[actions.SETTLED_DAY], game_time.day(self.start)
        )

    def test_backward(self) -> None:
        """往前跳一天：settled_day 是新时刻的那一天"""
        new_time = START - datetime.timedelta(days=1)
        game = self.edit(new_time)
        clock = game_time.minutes(new_time)
        self.assertEqual(game.clock, clock)
        self.assertEqual(game.data[actions.TICKED], clock)
        self.assertEqual(game.data[actions.SETTLED_DAY], game_time.day(clock))
