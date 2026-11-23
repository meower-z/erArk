"""
StateMachine 移动提示界面解耦测试
=================================
- 提示发出（MoveIntentNoticeTest）：玩家与 NPC 同处出发地点且提示开启时，
  general_movement_module 通过 ui_hooks 发出一条默认选项的移动提示。
- 抑制条件（MoveIntentNoticeTest）：关闭 show_info_flag、将绘制设置项 8 设为 0 或将玩家移至其他地点时，
  general_movement_module 不触发提示回调。
- 无回调运行（MoveIntentNoticeTest）：未登记提示回调时，general_movement_module 正常完成寻路且不调用 NormalDraw.draw。
- Tk 回调绘制（TkMoveIntentTest）：经 core.load(load_order.LOAD_ORDER) 加载模块后，
  Tk 提示回调以 NormalDraw 与 standard 样式绘制移动提示文本。
"""

from unittest import mock

from Script.Config import normal_config
from Script.Core import constant, get_text
from Script.Design import map_handle
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.domains import activity
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.StateMachine import default
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase

START = ["宿舍", "1区", "101"]
""" 测试中玩家与 NPC 的初始场景路径（宿舍/1区/101）。 """
TARGET = ["中枢", "博士办公室"]
""" 测试中 NPC 寻路的目标场景路径（中枢/博士办公室）。 """
ELSEWHERE = ["中枢", "会议室"]
""" 用于将玩家移离出发地点的另一场景路径（中枢/会议室）。 """
MOVE_INTENT = 8
""" 绘制设置（draw_setting）中控制 NPC 移动提示的设置编号（8）。 """


class MoveIntentCase(FastTestCase):
    """移动提示测试基类，准备同处出发地点的玩家与 NPC 以及开启的提示设置。"""

    def setUp(self) -> None:
        """准备目标与备用场景、同处 START 的玩家与 NPC、工作集上下文、开启的提示设置以及预期提示文本。"""
        super().setUp()
        self.world.scene(TARGET)
        self.world.scene(ELSEWHERE)
        self.world.chara(0, "博士", position=START)
        self.npc = self.world.chara(1, "干员1", position=START)
        self.enterContext(working.based_on(core.state()))
        self.enterContext(
            mock.patch.dict(
                normal_config.system_setting.draw_setting, {MOVE_INTENT: 1}
            )
        )
        self.expected = get_text._("{0}打算前往{1}\n").format(
            self.npc.name, self.scene_name(TARGET)
        )

    @staticmethod
    def scene_name(path: list[str]) -> str:
        """
        按地图路径列表查询对应场景的显示名称。
        Keyword arguments:
        path -- list[str]，场景在地图系统下的路径段列表
        Return arguments:
        str -- constant.scene_data 中对应的场景名称
        """
        key = map_handle.get_map_system_path_str_for_list(path)
        return constant.scene_data[key].scene_name

    def move(self, show_info_flag: bool = True) -> None:
        """
        调用 general_movement_module 让测试 NPC 寻路前往 TARGET，并断言返回 True 且行为状态为 MOVE。
        Keyword arguments:
        show_info_flag -- bool，是否允许发出移动提示，默认为 True
        Return arguments:
        None -- 无返回值
        """
        self.assertTrue(
            default.general_movement_module(
                self.npc.cid, list(TARGET), show_info_flag
            )
        )
        self.assertEqual(
            activity.behavior(self.npc.cid).behavior_id,
            constant.Behavior.MOVE,
        )


class MoveIntentNoticeTest(MoveIntentCase):
    """验证 general_movement_module 通过 ui_hooks 发出与抑制移动提示的行为。"""

    def setUp(self) -> None:
        """将 ui_hooks 已登记的提示回调列表替换为单个记录用模拟对象。"""
        super().setUp()
        self.notices = mock.Mock()
        self.enterContext(
            mock.patch.object(ui_hooks, "_notices", [self.notices])
        )

    def test_same_place_emits_notice(self) -> None:
        """验证玩家与 NPC 同处出发地点且提示开启时，回调收到一次带默认显示参数的预期提示文本。"""
        self.move()
        self.notices.assert_called_once_with(
            self.expected, wait=False, style=None, use_text_width=False
        )

    def test_no_notice_when_apart_hidden_or_quiet(self) -> None:
        """验证关闭 show_info_flag、关闭绘制设置项 8 或玩家移至其他地点时，提示回调不被调用。"""
        self.move(show_info_flag=False)
        normal_config.system_setting.draw_setting[MOVE_INTENT] = 0
        self.move()
        normal_config.system_setting.draw_setting[MOVE_INTENT] = 1
        self.world.move(0, ELSEWHERE)
        self.move()
        self.notices.assert_not_called()

    def test_without_handlers_moves_silently(self) -> None:
        """验证未登记提示回调时，general_movement_module 正常使 NPC 进入移动状态且不调用 NormalDraw.draw。"""
        drawn = self.enterContext(
            mock.patch.object(draw.NormalDraw, "draw", autospec=True)
        )
        with mock.patch.object(ui_hooks, "_notices", []):
            self.move()
        drawn.assert_not_called()


class TkMoveIntentTest(MoveIntentCase):
    """验证经 load_order 登记的 Tk 回调绘制移动提示的行为。"""

    def test_tk_callbacks_draw_notice_text(self) -> None:
        """
        验证调用 core.load(load_order.LOAD_ORDER) 后，移动会触发一次 NormalDraw.draw，
        且传入对象的类名为 NormalDraw、样式为 standard、文本为预期提示。
        """
        core.load(load_order.LOAD_ORDER)
        drawn = self.enterContext(
            mock.patch.object(draw.NormalDraw, "draw", autospec=True)
        )
        self.move()
        self.assertEqual(
            [
                (type(now).__name__, now.style, now.text)
                for (now,), _kwargs in drawn.call_args_list
            ],
            [("NormalDraw", "standard", self.expected)],
        )
