# -*- coding: UTF-8 -*-
"""
载具表补齐：开新游戏时与读档时
==============================
载具管理面板按 game_config.config_vehicle 的每个载具id读 rhodes_island.vehicles，面板打开时只读。
- 开新游戏后，每个载具id都在载具表里，数量与损坏数都是 0。
- 旧存档的载具表缺一个载具id（存档之后才加的载具）：经 save_handle 真实写盘、读档后，缺的id补成 [0, 0]，
  其余载具的数据不变。
"""

import shutil

from tests.slow.base import SlowTestCase

SAVE_ID = "test_old_save_missing_vehicle"
""" 本测试写入 save/ 的存档id，测试结束时删掉 """
OWNED = [2, 1]
""" 读档前留在载具表里的一辆载具的数据：2 辆，1 辆损坏 """


class TestOldSaveMissingVehicle(SlowTestCase):
    """新游戏与读档后，载具表有每个载具id"""

    def tearDown(self) -> None:
        """
        删掉本测试写入的存档
        Keyword arguments:
        无
        Return arguments:
        无
        """
        from Script.Core import save_handle

        shutil.rmtree(
            save_handle.get_save_dir_path(SAVE_ID), ignore_errors=True
        )
        super().tearDown()

    def test_new_game_and_old_save_fill_every_vehicle(self) -> None:
        """新游戏的载具表有每个载具id且全为 [0, 0]；缺一个id的存档读档后补成 [0, 0]，留着的载具不变"""
        from Script.UI.Moudle import view
        from Script.Config import game_config
        from Script.Core import constant, save_handle

        vehicle_ids = sorted(game_config.config_vehicle)
        self.assertGreater(len(vehicle_ids), 1, "配置里至少两辆载具")
        self.assertEqual(
            self.cache.rhodes_island.vehicles,
            {vehicle_id: [0, 0] for vehicle_id in vehicle_ids},
            "新游戏的载具表",
        )

        missing, kept = vehicle_ids[0], vehicle_ids[1]
        vehicles = self.cache.rhodes_island.vehicles
        del vehicles[missing]
        vehicles[kept] = list(OWNED)
        save_handle.establish_save(SAVE_ID)
        save_handle.input_load_save(SAVE_ID)
        view.now_panel_id = constant.Panel.IN_SCENE

        vehicles = self.cache.rhodes_island.vehicles
        self.assertEqual(sorted(vehicles), vehicle_ids, "读档后的载具id")
        self.assertEqual(vehicles[missing], [0, 0], "缺的载具补成 [0, 0]")
        self.assertEqual(vehicles[kept], OWNED, "留着的载具不变")
