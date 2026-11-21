# -*- coding: UTF-8 -*-
"""
载具表补齐：开新游戏时与读档时
==============================
- 开新游戏后，载具表有每个配置载具id，各为 (0, 0)。
- 存档的载具表缺一个载具id时（例如存档之后配置里加了载具），经 save_handle 真实写盘、读档后，缺的id补成 (0, 0)。
  其余载具的数据不变。
"""

import shutil

from tests.slow.base import SlowTestCase

SAVE_ID = "test_old_save_missing_vehicle"
""" 本测试写入 save/ 的存档id，测试结束时删掉 """
OWNED = (2, 1)
""" 读档前留在载具表里的一种载具的 (拥有数, 外勤中数) """


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
        """新游戏的载具表每个载具id一行 (0, 0)。缺一个id的存档读档后，缺的id补成 (0, 0)，留着的载具不变"""
        from Script.UI.Moudle import view
        from Script.Config import game_config
        from Script.Core import constant, save_handle
        from Script.Modules.domains import commission
        from Script.Modules.gameplay_resolution import working
        from tests import kernel_data

        vehicle_ids = sorted(game_config.config_vehicle)
        self.assertGreater(len(vehicle_ids), 1, "配置里至少两辆载具")
        self.assertEqual(
            commission.vehicles(),
            {vehicle_id: (0, 0) for vehicle_id in vehicle_ids},
            "新游戏的载具表",
        )

        missing, kept = vehicle_ids[0], vehicle_ids[1]
        table = {str(vid): (0, 0) for vid in vehicle_ids if vid != missing}
        table[str(kept)] = OWNED
        with kernel_data.writing():
            working.put(None, commission.VEHICLES, table)
        save_handle.establish_save(SAVE_ID)
        save_handle.input_load_save(SAVE_ID)
        view.now_panel_id = constant.Panel.IN_SCENE

        vehicles = commission.vehicles()
        self.assertEqual(sorted(vehicles), vehicle_ids, "读档后的载具id")
        self.assertEqual(vehicles[missing], (0, 0), "缺的载具补成 (0, 0)")
        self.assertEqual(vehicles[kept], OWNED, "留着的载具不变")
