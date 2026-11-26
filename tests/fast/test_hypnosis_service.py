"""
催眠服务（hypnosis_service）测试
================================
- 催眠服务计算与模块边界：验证催眠面板与五个调用方的导入关系、无意识状态名称、理智消耗、深度上限、深度增长与颜色分段。
- 催眠完成判定：验证催眠类型 2 在不可锁门场景、可锁门场景及深度不足分支的返回值、状态写入与 ui_hooks 提示参数。
- Tk 提示绘制：验证经 load_order 登记的提示回调按分支绘制对应类型的绘制对象及默认宽度与样式。
"""

import os
from unittest import mock

from Script.Config import game_config
from Script.Core import get_text
from Script.Design import handle_ability, handle_talent, settle_behavior
from Script.Kernel import core
from Script.Modules import load_order
from Script.Modules.domains import abilities, activity, flags, hypnosis
from Script.Modules.domains import identity, player_ability, scene_state
from Script.Modules.gameplay_resolution import first_record_text
from Script.Modules.gameplay_resolution import hypnosis_service, ui_hooks
from Script.Modules.gameplay_resolution import status_tag_service, working
from Script.Settle import default as settle_default
from Script.System.Sex_System import h_mode_common
from Script.UI.Moudle import draw
from Script.UI.Panel import hypnosis_panel
from tests import chara_abilities as ca
from tests.fast.base import FastTestCase

TARGET = 1
""" 测试用的目标角色编号（1） """
LOCKABLE = ["宿舍", "1区", "101"]
""" 测试用的可锁门场景路径（close_type 为 1） """
UNLOCKABLE = (["中枢", "走廊"], ["中枢", "休息室"])
""" 测试用的不可锁门场景路径元组（close_type 不为 1） """
AIR = 2
""" 催眠类型 2 的配置编号 """
REFUSED = "\n当前地点不能锁门，无法进行空气催眠\n"
""" 场景不可锁门时用于比对的「不能锁门」提示原文 """
LOCKED = "\n为了防止有人打扰，将门锁上了\n"
""" 场景首次锁门时用于比对的「已锁门」提示原文 """
MOVED = (
    "unconscious_list",
    "calculate_hypnosis_sanity_cost",
    "hypnosis_degree_calculation",
    "hypnosis_degree_limit_calculation",
    "evaluate_hypnosis_completion",
    "get_hypnosis_degree_color",
)
""" 由 hypnosis_service 提供且 hypnosis_panel 中不定义的属性名称元组 """
CALLERS = (
    settle_behavior,
    settle_default,
    first_record_text,
    h_mode_common,
    status_tag_service,
)
""" 调用 hypnosis_service 的五个模块元组 """


class HypnosisServiceTest(FastTestCase):
    """催眠服务（hypnosis_service）的模块边界、状态名称、数值计算与颜色分段测试"""

    def setUp(self) -> None:
        """创建玩家与测试目标角色并打开基于当前状态的工作集上下文"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(TARGET, "测试干员")
        self.enterContext(working.based_on(core.state()))

    def test_panel_and_callers_use_service(self) -> None:
        """验证 hypnosis_panel 不含催眠服务属性，且五个调用方模块均导入 hypnosis_service 而不导入 hypnosis_panel"""
        for name in MOVED:
            self.assertFalse(hasattr(hypnosis_panel, name), name)
        for module in CALLERS:
            values = list(vars(module).values())
            self.assertIn(hypnosis_service, values, module.__name__)
            self.assertNotIn(hypnosis_panel, values, module.__name__)

    def test_unconscious_names_follow_hypnosis_types(self) -> None:
        """验证 unconscious_list 长度为 8 且索引 4 至 7 与催眠类型 1 至 4 的配置名称对应"""
        names = hypnosis_service.unconscious_list
        self.assertEqual(len(names), 8)
        for cid in (1, 2, 3, 4):
            type_name = game_config.config_hypnosis_type[cid].name.strip()
            self.assertEqual(names[cid + 3], get_text._(type_name + "催眠"))

    def test_sanity_cost_by_target_talent(self) -> None:
        """验证理智消耗在无素质及依次添加素质 71、72、73 时分别返回 20、25、30 与 1"""
        cost = hypnosis_service.calculate_hypnosis_sanity_cost
        self.assertEqual(cost(TARGET), 20)
        for talent_id, expected in ((71, 25), (72, 30), (73, 1)):
            ca.talent(TARGET)[talent_id] = 1
            self.assertEqual(cost(TARGET), expected, talent_id)

    def test_degree_limit_follows_player_talents(self) -> None:
        """验证催眠深度上限在玩家无素质时为 0，获得素质 331 与 334 后依次取对应配置上限"""
        limit = hypnosis_service.hypnosis_degree_limit_calculation
        self.assertEqual(limit(), 0)
        table = game_config.config_hypnosis_talent_of_pl
        for cid in (331, 334):
            ca.talent(0)[table[cid].hypnosis_talent_id] = 1
            self.assertEqual(limit(), table[cid].max_hypnosis_degree)

    def test_degree_gain_uses_talent_aroma_and_random_factor(self) -> None:
        """验证深度增长在目标为玩家或达到上限时返回 0，并按素质、aromatherapy 标志、能力 19 与随机系数计算"""
        gain = hypnosis_service.hypnosis_degree_calculation
        self.assertEqual(gain(TARGET), 0)
        ca.talent(0)[331] = 1
        self.assertEqual(gain(0), 0)
        adjust = handle_ability.get_ability_adjust(
            abilities.ability(TARGET)[19]
        )
        with mock.patch("random.uniform", return_value=1.5) as uniform:
            self.assertEqual(gain(TARGET), round(2 * adjust * 1.5, 1))
            ca.talent(0)[334] = 1
            flags.set(TARGET, aromatherapy=6)
            self.assertEqual(gain(TARGET), round(11 * adjust * 1.5, 1))
        uniform.assert_called_with(0.5, 1.5)
        hypnosis.set(TARGET, hypnosis_degree=50)
        ca.talent(0)[334] = 0
        self.assertEqual(gain(TARGET), 0)

    def test_degree_color_bands(self) -> None:
        """验证催眠深度在各边界值与区间内返回对应的文本样式名称"""
        bands = (
            (0, "standard"),
            (0.1, "pink"),
            (49.9, "pink"),
            (50, "hot_pink"),
            (99.9, "hot_pink"),
            (100, "deep_pink"),
            (199.9, "deep_pink"),
            (200, "purple"),
            (999, "purple"),
        )
        for degree, color in bands:
            self.assertEqual(
                hypnosis_service.get_hypnosis_degree_color(degree), color
            )


class EvaluateHypnosisCompletionTest(FastTestCase):
    """催眠完成判定（evaluate_hypnosis_completion）在锁门条件与深度不足分支的行为测试"""

    def setUp(self) -> None:
        """将 ui_hooks 提示回调替换为记录函数、打桩催眠素质检测并读取催眠类型 2 所需深度"""
        super().setUp()
        self.notices: list[tuple[str, bool, str | None, bool]] = []
        self.enterContext(
            mock.patch.object(ui_hooks, "_notices", [self.record])
        )
        self.gain = self.enterContext(
            mock.patch.object(handle_talent, "npc_gain_hypnosis_talent")
        )
        self.need = game_config.config_hypnosis_type[AIR].hypnosis_degree

    def record(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """
        记录经 ui_hooks.emit_notice 传入的提示参数。
        Keyword arguments:
        text -- str，提示文本
        wait -- bool，是否等待玩家确认
        style -- str | None，文本样式名
        use_text_width -- bool，是否按配置文本宽度排版
        Return arguments:
        None -- 无返回值
        """
        self.notices.append((text, wait, style, use_text_width))

    def start(self, position: list[str], degree: float) -> None:
        """
        在指定场景创建玩家与目标角色，打开工作集上下文并设置催眠类型 2 与目标催眠深度。
        Keyword arguments:
        position -- list[str]，角色初始所在场景路径
        degree -- float，目标角色的初始催眠深度
        Return arguments:
        None -- 无返回值
        """
        self.world.chara(0, "博士", position)
        self.world.chara(TARGET, "测试干员", position)
        self.enterContext(working.based_on(core.state()))
        player_ability.set(0, hypnosis_type=AIR)
        hypnosis.set(TARGET, hypnosis_degree=degree)

    def test_air_hypnosis_needs_a_lockable_room(self) -> None:
        """验证催眠类型 2 在不可锁门场景返回 0、发出等待确认的「不能锁门」提示、不写入状态并调用素质检测"""
        self.start(UNLOCKABLE[0], self.need)
        refused = (get_text._(REFUSED), True, None, False)
        for position in UNLOCKABLE:
            activity.set_position(0, position)
            self.assertNotEqual(self.world.scene(position).close_type, 1)
            self.assertEqual(
                hypnosis_service.evaluate_hypnosis_completion(TARGET), 0
            )
            self.assertEqual(scene_state.close_flag(os.sep.join(position)), 0)
        self.assertEqual(self.notices, [refused, refused])
        self.assertEqual(flags.get(TARGET, "unconscious_h"), 0)
        self.assertEqual(player_ability.get(0, "air_hypnosis_position"), "")
        self.assertEqual(self.gain.call_args_list, [mock.call(TARGET)] * 2)

    def test_air_hypnosis_locks_the_door_once(self) -> None:
        """验证催眠类型 2 在可锁门场景两次调用均返回 1、首次锁门并发出「已锁门」提示，且写入位置与 unconscious_h"""
        self.start(LOCKABLE, self.need)
        self.assertEqual(self.world.scene(LOCKABLE).close_type, 1)
        evaluate = hypnosis_service.evaluate_hypnosis_completion
        self.assertEqual(evaluate(TARGET), 1)
        self.assertEqual(evaluate(TARGET), 1)
        locked = (get_text._(LOCKED), True, None, False)
        self.assertEqual(self.notices, [locked])
        self.assertEqual(scene_state.close_flag(os.sep.join(LOCKABLE)), 1)
        self.assertEqual(
            player_ability.get(0, "air_hypnosis_position"), LOCKABLE
        )
        self.assertEqual(flags.get(TARGET, "unconscious_h"), AIR + 3)

    def test_low_degree_reports_the_needed_degree(self) -> None:
        """验证目标催眠深度不足时返回 0、发出不等待确认的深度不足提示，且不锁门也不写入 unconscious_h"""
        self.start(LOCKABLE, self.need - 1)
        self.assertEqual(
            hypnosis_service.evaluate_hypnosis_completion(TARGET), 0
        )
        self.assertEqual(
            self.notices, [(low_text(self.need), False, None, False)]
        )
        self.assertEqual(flags.get(TARGET, "unconscious_h"), 0)
        self.assertEqual(scene_state.close_flag(os.sep.join(LOCKABLE)), 0)


class TkNoticeTest(FastTestCase):
    """经 load_order 登记的 Tk 提示回调与催眠完成判定的联动绘制测试"""

    def setUp(self) -> None:
        """按 load_order 加载模块以登记 Tk 提示回调，打桩催眠素质检测并记录 NormalDraw 与 WaitDraw 的绘制调用"""
        super().setUp()
        core.load(load_order.LOAD_ORDER)
        self.enterContext(
            mock.patch.object(handle_talent, "npc_gain_hypnosis_talent")
        )
        self.drawn: list[tuple[str, float, str, str]] = []
        for cls in (draw.NormalDraw, draw.WaitDraw):
            self.enterContext(
                mock.patch.object(
                    cls, "draw", autospec=True, side_effect=self.keep
                )
            )

    def keep(self, now: draw.NormalDraw) -> None:
        """
        记录绘制对象的类名、宽度、样式与文本。
        Keyword arguments:
        now -- draw.NormalDraw，当前调用绘制方法的对象
        Return arguments:
        None -- 无返回值
        """
        self.drawn.append((type(now).__name__, now.width, now.style, now.text))

    def test_notices_draw_like_fresh_draw_objects(self) -> None:
        """验证深度不足、不可锁门与首次锁门三个分支依次绘制 NormalDraw、WaitDraw 与 WaitDraw，且宽度、样式与文本一致"""
        need = game_config.config_hypnosis_type[AIR].hypnosis_degree
        self.world.chara(0, "博士", UNLOCKABLE[0])
        self.world.chara(TARGET, "测试干员", UNLOCKABLE[0])
        self.enterContext(working.based_on(core.state()))
        player_ability.set(0, hypnosis_type=AIR)
        evaluate = hypnosis_service.evaluate_hypnosis_completion
        hypnosis.set(TARGET, hypnosis_degree=need - 1)
        evaluate(TARGET)
        hypnosis.set(TARGET, hypnosis_degree=need)
        evaluate(TARGET)
        activity.set_position(0, LOCKABLE)
        evaluate(TARGET)
        wait, normal = draw.WaitDraw(), draw.NormalDraw()
        self.assertEqual(
            self.drawn,
            [
                ("NormalDraw", normal.width, normal.style, low_text(need)),
                ("WaitDraw", wait.width, wait.style, get_text._(REFUSED)),
                ("WaitDraw", wait.width, wait.style, get_text._(LOCKED)),
            ],
        )


def low_text(need: int) -> str:
    """
    构造测试目标在催眠类型 2 下深度不足时的预期提示文本。
    Keyword arguments:
    need -- int，当前催眠类型所需的催眠深度
    Return arguments:
    str -- 格式化后的预期提示文本
    """
    return get_text._(
        "\n{0}的催眠深度未达到{1}%，无法进入{2}催眠状态，需要切换更低的催眠模式或加深催眠程度\n"
    ).format(
        identity.of(TARGET).name,
        need,
        game_config.config_hypnosis_type[AIR].name,
    )
