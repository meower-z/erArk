"""
宿舍管理面板绘制与返回流程测试
==============================
本测试验证 Script.UI.Panel.manage_dormitory_panel 绘制宿舍总览页，并用 _back 模拟按下「返回」。
用例断言总览页给出的按钮返回值列表，并断言返回后 view.now_panel_id 变为 constant.Panel.IN_SCENE。
用例同时断言未分配楼层的管理员重置为无岗位，而已分配楼层的管理员保留宿舍管理员岗位。
"""

from unittest import mock

from Script.Core import constant, flow_handle
from Script.Design import basement
from Script.Modules.domains import chara_life, dormitory
from Script.Modules.gameplay_resolution import (
    dormitory_manager_service as managers,
)
from Script.UI.Moudle import view
from Script.UI.Panel import manage_dormitory_panel
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.kernel_data import put

WIDTH = 100
""" 传给 Manage_Dormitory_Panel 的面板宽度。 """


class ManageDormitoryPanelTest(FastTestCase):
    """宿舍管理面板绘制总览页与返回处理的测试。"""

    def setUp(self) -> None:
        """创建博士与甲乙两名宿舍管理员，设 3 级宿舍区并刷新基地、任命乙管理 2 层，替换 askfor_all 与面板编号。"""
        super().setUp()
        self.world.chara(0, "博士")
        for cid, name in ((1, "甲"), (2, "乙")):
            self.world.chara(cid, name)
            put(chara_life.work_type.set, cid, managers.MANAGER_WORK)
        kernel_data.set_facility_level(4, 3)
        kernel_data.written(basement.get_base_updata)
        put(dormitory.set_manager, 2, 2)
        self.seen: list[list[str]] = []
        """ 记录 _back 每次收到的按钮返回值列表副本。 """
        self.enterContext(
            mock.patch.object(flow_handle, "askfor_all", self._back)
        )
        self.enterContext(
            mock.patch.object(
                view, "now_panel_id", constant.Panel.MANAGE_DORMITORY
            )
        )

    def _back(self, return_list: list[str], *args: object) -> str:
        """
        断言 self.seen 为空且 return_list 包含「返回」。随后将 return_list 副本追加到 self.seen 并返回「返回」。
        Keyword arguments:
        return_list -- list[str]，面板本次给出的按钮返回值列表
        args -- tuple[object, ...]，其余位置参数，本方法不使用
        Return arguments:
        str -- 断言通过后返回字符串「返回」
        """
        self.assertEqual(self.seen, [])
        self.assertIn("返回", return_list)
        self.seen.append(list(return_list))
        return "返回"

    def test_back_resets_unassigned_managers_and_returns_to_scene(
        self,
    ) -> None:
        """绘制面板并触发返回，断言总览页按钮返回值列表、甲重置为无岗位、乙保留管理员岗位及面板编号变为 IN_SCENE。"""
        with kernel_data.writing():
            manage_dormitory_panel.Manage_Dormitory_Panel(WIDTH).draw()
        self.assertEqual(
            self.seen,
            [
                [
                    "\n调整宿舍管理员",
                    "显示具体居住情况",
                    "\n打开宿舍调整干员选择",
                    "返回",
                ]
            ],
        )
        self.assertEqual(chara_life.work_type(1), 0)
        self.assertEqual(chara_life.work_type(2), managers.MANAGER_WORK)
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
