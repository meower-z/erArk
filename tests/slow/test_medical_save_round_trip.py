# -*- coding: UTF-8 -*-
"""
医疗部数据随存档存下、读档时原样换回
====================================
新游戏里等待三次，再跑一次医疗部的每日结算（有了经营日志与收入），经 save_handle 写盘存档。
存档后改掉医疗部的收入，读档。读档后三个键（base.medical、base.medical_clinic、base.medical_ward）
与存档时相同（键的顺序与数值类型也相同），读出的各项值与类型也相同。门诊病人表不空。
"""

import importlib
import shutil
from types import ModuleType

from tests.slow.base import SlowTestCase

SAVE_ID = "test_medical_save_round_trip"
""" 本测试写入 save/ 的存档id，测试结束时删掉 """


def game(name: str) -> ModuleType:
    """按模块全名 name 导入游戏模块，返回模块"""
    return importlib.import_module(name)


def typed(value: object) -> object:
    """
    值连同各层的类型（病人取各字段），用来比较值与类型都相同
    Keyword arguments:
    value -- 医疗部的值
    Return arguments:
    object -- 可比较的形式
    """
    if hasattr(value, "as_dict"):
        return typed(value.as_dict())
    if isinstance(value, dict):
        return ("dict", [(typed(k), typed(v)) for k, v in value.items()])
    if isinstance(value, list):
        return ("list", [typed(v) for v in value])
    if hasattr(value, "__dataclass_fields__"):
        return (type(value).__name__, typed(dict(vars(value))))
    return (type(value).__name__, value)


class MedicalSaveRoundTripTest(SlowTestCase):
    """医疗部的三个键随存档存下，读档后与存档时相同"""

    def test_medical_keys_survive_save_and_load(self) -> None:
        """存档后改掉的收入在读档后回到存档时的值，三个键与读出的值都和存档时相同"""
        from tests import kernel_data
        from tests.snapshot_states import instruct

        constant = game("Script.Core.constant")
        save_handle = game("Script.Core.save_handle")
        working = game("Script.Modules.gameplay_resolution.working")
        medical = game("Script.Modules.domains.medical")
        medical_patient = game("Script.Modules.domains.medical_patient")
        medical_service = game("Script.System.Medical_System.medical_service")
        for _ in range(3):
            instruct(self.world, constant.Instruct.WAIT)
        kernel_data.written(
            medical_service.settle_medical_department, draw_flag=False
        )
        keys = (medical.KEY, medical.CLINIC, medical.WARD)
        saved = {key: working.get(None, key) for key in keys}
        saved_fields = typed(medical.state().as_fields())
        self.assertTrue(medical.state().today, "开局后有门诊病人")
        self.assertTrue(medical.state().recent_reports, "结算后有经营日志")
        save_handle.establish_save(SAVE_ID)
        try:
            with kernel_data.writing(), medical.editing() as m:
                m.income_total += 1000
            save_handle.input_load_save(SAVE_ID)
        finally:
            shutil.rmtree(
                save_handle.get_save_dir_path(SAVE_ID), ignore_errors=True
            )
        for key in keys:
            self.assertTrue(
                medical_patient.same(working.get(None, key), saved[key]), key
            )
        self.assertEqual(typed(medical.state().as_fields()), saved_fields)
