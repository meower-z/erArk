# -*- coding: UTF-8 -*-
"""
读档时重定玩家交互对象的测试
============================
- 交互对象不在场且场内有别的角色时，save.json 槽位读档把交互对象设为编号最小的在场角色。
- 同样情形下，旧格式槽位读档把交互对象设为编号最小的在场角色。
- 交互对象不在场且场内没有别的角色时，读档把交互对象设为玩家自己（0）。
- 交互对象已在当前场景时，读档保留原交互对象。
- 每个用例在读档后校验 check_observable_05 返回空列表。
- 测试存档写入临时目录（index.SAVE_DIR 指向临时目录）。
"""

import tempfile
from unittest import mock

from Script.Core import save_handle
from Script.Kernel import core
from Script.Modules.domains import activity, country, roster
from Script.Modules.save_load import index
from Script.Test.Static_Check.checks.check_observable import (
    check_observable_05,
)
from tests import kernel_data, legacy_save
from tests.fast.base import FastTestCase
from tests.world import DEFAULT_SCENE

SLOT = "settle_target"
""" 测试读写的存档槽位 id """
ELSEWHERE = ["中枢", "博士房间"]
""" 放置不在场角色的场景坐标（与玩家所在的 DEFAULT_SCENE 不同） """


class LoadSettlesPlayerTargetTest(FastTestCase):
    """读档后重定玩家交互对象的测试"""

    def setUp(self) -> None:
        """
        复原测试世界，将存档目录指向临时目录并置空事件表。
        创建玩家 0，将其写入在编名册并填充国家数据。
        """
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))
        self.enterContext(mock.patch.object(core, "_events", []))
        self.world.chara(0, "博士")
        kernel_data.put(roster.set_active, {0})
        kernel_data.written(country.fill)

    def load_with_target(
        self, present: list[int], absent: list[int], target: int, legacy: bool
    ) -> int:
        """
        按给定角色分布与交互对象写入存档，将交互对象置为 0 后经 input_load_save 读档，
        返回读档后的玩家交互对象 id。
        Keyword arguments:
        present -- 放在玩家默认场景（DEFAULT_SCENE）的角色 id 列表
        absent -- 放在其他场景（ELSEWHERE）的角色 id 列表
        target -- 存档前设置的玩家交互对象 id
        legacy -- 为真时经 legacy_save.to_legacy 转为旧格式槽位再读档，为假时读 save.json 槽位
        Return arguments:
        int -- 读档后 activity.target(0) 返回的交互对象 id
        """
        for cid in present:
            self.world.chara(cid, f"在场{cid}", DEFAULT_SCENE)
        for cid in absent:
            self.world.chara(cid, f"别处{cid}", ELSEWHERE)
        kernel_data.put(activity.set_target, 0, target)
        save_handle.establish_save(SLOT)
        if legacy:
            legacy_save.to_legacy(SLOT, legacy_save.old("Cache"))
            self.assertFalse(index.is_json(SLOT))
        kernel_data.put(activity.set_target, 0, 0)
        save_handle.input_load_save(SLOT)
        return activity.target(0)

    def test_absent_target_moves_to_first_present(self) -> None:
        """
        save.json 槽位中交互对象不在场且场内有别的角色时，读档将其定为编号最小的在场角色。
        读档后 check_observable_05 返回空列表。
        """
        self.assertEqual(self.load_with_target([3, 1], [2], 2, False), 1)
        self.assertEqual(check_observable_05(), [])

    def test_legacy_absent_target_moves_to_first_present(self) -> None:
        """
        旧格式槽位中交互对象不在场且场内有别的角色时，读档将其定为编号最小的在场角色。
        读档后 check_observable_05 返回空列表。
        """
        self.assertEqual(self.load_with_target([3, 1], [2], 2, True), 1)
        self.assertEqual(check_observable_05(), [])

    def test_absent_target_with_nobody_present_falls_back_to_self(
        self,
    ) -> None:
        """
        交互对象不在场且场内没有别的角色时，读档将交互对象定为玩家自己（0）。
        读档后 check_observable_05 返回空列表。
        """
        self.assertEqual(self.load_with_target([], [2], 2, False), 0)
        self.assertEqual(check_observable_05(), [])

    def test_present_target_is_kept(self) -> None:
        """
        交互对象已在玩家当前场景时，读档保留原交互对象。
        读档后 check_observable_05 返回空列表。
        """
        self.assertEqual(self.load_with_target([1, 3], [2], 3, False), 3)
        self.assertEqual(check_observable_05(), [])
