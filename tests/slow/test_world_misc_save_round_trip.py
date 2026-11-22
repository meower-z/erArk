# -*- coding: UTF-8 -*-
"""
全局设定、周目、国家、模式、吵醒名单、成就、事件与输入记录、计划队列随存档存读往返并可继续推进
==============================================================================================
新游戏里等待三次后写下非默认设定、周目、声望、成就、事件、每日记录与最近输入，经 save_handle 写盘存档。
存档后改写周目、设定、声望、成就、今日事件、每日记录与最近输入，再读档验证全部 15 个全局键回到存档值。
读档后继续等待 15 分钟，时钟随之推进。
"""

import importlib
import shutil
from types import ModuleType

from tests import kernel_data
from tests.slow.base import SlowTestCase

SAVE_ID = "test_world_misc_save_round_trip"
""" 本测试写入 save/ 的存档id，测试结束时删掉 """


def game(name: str) -> ModuleType:
    """按模块全名 name 导入游戏模块，返回模块"""
    return importlib.import_module(name)


class WorldMiscSaveRoundTripTest(SlowTestCase):
    """15 个全局杂项键随新游戏存档存下、读档还原，并可继续推进"""

    def test_world_misc_keys_survive_save_load_and_continue(self) -> None:
        """存档后改写全局杂项键，读档还原为存档值，之后继续等待 15 分钟正常推进"""
        from tests.snapshot_states import instruct

        constant = game("Script.Core.constant")
        core = game("Script.Kernel.core")
        save_handle = game("Script.Core.save_handle")
        working = game("Script.Modules.gameplay_resolution.working")
        playthrough = game("Script.Modules.domains.playthrough")
        country = game("Script.Modules.domains.country")
        modes = game("Script.Modules.domains.modes")
        needs = game("Script.Modules.domains.needs")
        achievement = game("Script.Modules.domains.achievement")
        history = game("Script.Modules.domains.history")
        plan = game("Script.Modules.domains.plan")

        for _ in range(3):
            instruct(self.world, constant.Instruct.WAIT)
        nation_id = next(iter(country.table(country.REPUTATION)))
        with kernel_data.writing():
            playthrough.set_game_round(2)
            playthrough.set_setting(playthrough.DIFFICULTY, 1, 3)
            country.add_reputation(nation_id, 15)
            achievement.add("field_commission_count", 4)
            history.trigger("ev_round_trip")
            history.trigger_today("ev_round_trip")
            history.add_daily("round_trip_note")
            history.add_inputs(["round_trip_input"])
        keys = (
            playthrough.SETTINGS,
            playthrough.ROUND,
            country.KEY,
            modes.TIME_STOP,
            modes.GROUP_SEX,
            modes.SEX_CLASS,
            needs.NOISE,
            achievement.KEY,
            history.TRIGGERED,
            history.TODAY,
            history.LOG,
            history.INPUTS,
            plan.QUEUE,
            plan.ROUTE,
            plan.SLEEP_SAVE,
        )
        saved = {key: working.get(None, key) for key in keys}
        saved_clock = core.state().clock
        save_handle.establish_save(SAVE_ID)
        try:
            with kernel_data.writing():
                playthrough.set_game_round(9)
                playthrough.set_setting(playthrough.DIFFICULTY, 1, 1)
                country.add_reputation(nation_id, 100)
                achievement.add("field_commission_count", 99)
                history.clear_today()
                history.clear_daily()
                history.add_inputs(["after_save"])
            save_handle.input_load_save(SAVE_ID)
        finally:
            shutil.rmtree(
                save_handle.get_save_dir_path(SAVE_ID), ignore_errors=True
            )
        for key in keys:
            self.assertEqual(working.get(None, key), saved[key], key)
        self.assertEqual(core.state().clock, saved_clock)
        for _ in range(3):
            instruct(self.world, constant.Instruct.WAIT)
        self.assertEqual(core.state().clock, saved_clock + 15)
