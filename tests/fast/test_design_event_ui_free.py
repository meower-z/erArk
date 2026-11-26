"""
状态触发事件文本构建与无界面运行测试
====================================
- 触发与显示（HandleEventTest）：验证事件选中、自定义事件切换、短文本不清除标记、离场空文本与逐行绘制。
- 文本与样式（BuildEventTextTest）：验证子事件分段、样式优先级以及 show_event_text 经回调按专属事件样式绘制。
- 状态判定（JudgeStatusTest）：验证 judge_character_status 显示一次开始事件并记录切换后的事件编号。
- 无界面运行（EventUiFreeTest）：验证屏蔽界面、结算与输入输出模块时 event.py 可在子进程中选出并构建事件文本。
- 导入边界（EventImportBoundaryTest）：验证 Script/Design/event.py 源码不导入界面、输入输出与 Tk 模块。
"""

import dataclasses
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import game_type
from Script.Design import character_behavior, event, settle_behavior
from Script.Kernel import core
from Script.Modules.domains import activity, identity
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.UI.Moudle import draw
from tests import kernel_data
from tests.chara_activity import aim, place, stand
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports
from tests.ui_free_subprocess import ChildRun, run_ui_free

BEHAVIOR = "event_text_test_behavior"
""" 测试用的合成行为编号 """
MAIN = "event-text-main"
""" 测试用的普通事件编号（类型 2，含跳过口上效果 10012） """
DIY = "event-text-diy"
""" 测试用的三段自定义事件编号 """
DIY_SHORT = "event-text-diy-short"
""" 测试用的不足三段自定义事件编号 """
SON = "event-text-son"
""" 测试用的子事件编号 """
ADV = "event-text-adv"
""" 测试用的角色专属事件编号 """
NPC = 1
""" 测试中触发事件的非玩家角色编号 """
EVENT = "Script/Design/event.py"
""" 待检查导入边界的 event.py 仓库相对路径 """
EVENTS = {
    MAIN: (2, "", "正文甲", {}, {"10012": 1}),
    DIY: (1, "", "第一段|第二段|第三段", {}, {}),
    DIY_SHORT: (1, "", "第一段|第二段", {}, {}),
    SON: (1, "", "第一段|第二段", {"option_son": 1}, {}),
    ADV: (1, "7", "专属正文", {}, {}),
}
""" 合成测试事件表，键为事件编号，值为 (类型, 角色专属标识, 测试文本, 前提, 效果) 元组 """
UI_FREE_RUN = f"""
from unittest import mock
from Script.Config import game_config, map_config
from Script.Core import game_type
from Script.Design import event
from Script.Kernel import core
from Script.Modules.domains import activity, identity
from Script.Modules.gameplay_resolution import ui_hooks, working
from tests import chara_abilities, chara_data, kernel_data
from tests.chara_activity import aim, place, stand
from tests.world import DEFAULT_SCENE, start_time
map_config.init_map_data()
kernel_data.reset_clock(start_time(), {{}})
for cid in (0, 1):
    kernel_data.put(identity.put, identity.Identity(cid, name=str(cid), sex=1))
    chara_abilities.zero_tables(cid)
    chara_data.seed(cid, {{}})
    place(cid, DEFAULT_SCENE)
aim(1, 0)
stand(1, {BEHAVIOR!r})
table = {{}}
for uid, (kind, adv_id, text, premise, effect) in {EVENTS!r}.items():
    now = game_type.Event()
    now.uid, now.behavior_id, now.type, now.adv_id = uid, {BEHAVIOR!r}, kind, adv_id
    now.text, now.premise, now.effect = text, premise, effect
    table[uid] = now
shown = []
with (
    mock.patch.object(game_config, "config_event", table),
    mock.patch.object(game_config, "config_event_status_data", {{{BEHAVIOR!r}: [{MAIN!r}]}}),
    mock.patch.object(event, "_event_index", {{}}),
    mock.patch.object(ui_hooks, "_line_wait_texts", [lambda text, style: shown.append([text, style])]),
    working.based_on(core.state()),
):
    fired = event.handle_event(1, True)
    event.show_event_text(fired)
    payload["fired"] = [fired.event_id, fired.event_type, fired.text, fired.style]
    payload["skip"] = activity.event(1).skip_instruct_talk
    activity.update_event(1, chara_diy_event_flag=True, event_id={DIY!r})
    kernel_data.put(identity.put, identity.Identity(1, name="1", sex=1, text_color="#ff0000"))
    built = [event.build_event_text(uid, 1, 1) for uid in ({MAIN!r}, {SON!r}, {ADV!r})]
    payload["built"] = [[one.event_id, one.text, one.style] for one in built]
    place(1, ["0", "0"])
    payload["away"] = event.build_event_text({MAIN!r}, 1, 1).text
    payload["shown"] = shown
"""
""" 在无界面子进程中执行事件触发、显示与文本构建的代码片段 """


def event_table() -> dict[str, game_type.Event]:
    """
    根据合成事件定义 EVENTS 构造以事件编号为键的事件配置表。
    Return arguments:
    dict[str, game_type.Event] -- 事件编号到 Event 配置对象的映射
    """
    table = {}
    for uid, (kind, adv_id, text, premise, effect) in EVENTS.items():
        now = game_type.Event()
        now.uid = uid
        now.behavior_id = BEHAVIOR
        now.type = kind
        now.adv_id = adv_id
        now.text = text
        now.premise = premise
        now.effect = effect
        table[uid] = now
    return table


class EventTextCase(FastTestCase):
    """事件文本与触发测试的公共基类，准备合成角色、事件配置与输出记录器。"""

    def setUp(self) -> None:
        """
        初始化玩家与测试角色，打补丁替换事件配置表，并挂载回调与绘制记录器。
        Return arguments:
        None -- 无返回值
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(NPC, "干员")
        aim(NPC, 0)
        stand(NPC, BEHAVIOR)
        self.enterContext(working.based_on(core.state()))
        self.enterContext(
            mock.patch.object(game_config, "config_event", event_table())
        )
        self.enterContext(
            mock.patch.object(
                game_config, "config_event_status_data", {BEHAVIOR: [MAIN]}
            )
        )
        self.enterContext(mock.patch.object(event, "_event_index", {}))
        self.shown: list[tuple[str, str]] = []
        self.enterContext(
            mock.patch.object(
                ui_hooks,
                "_line_wait_texts",
                [*ui_hooks._line_wait_texts, self.record],
            )
        )
        self.drawn: list[tuple[str, float, str, str]] = []
        self.enterContext(
            mock.patch.object(
                draw.LineFeedWaitDraw,
                "draw",
                autospec=True,
                side_effect=self.keep,
            )
        )

    def record(self, text: str, style: str) -> None:
        """
        记录经 ui_hooks 逐行等待文本回调收到的文本与样式。
        Keyword arguments:
        text -- str，回调收到的文本
        style -- str，回调收到的样式名
        Return arguments:
        None -- 无返回值
        """
        self.shown.append((text, style))

    def keep(self, now: draw.LineFeedWaitDraw) -> None:
        """
        记录被拦截的 LineFeedWaitDraw 对象的类名、宽度、样式与文本。
        Keyword arguments:
        now -- draw.LineFeedWaitDraw，被拦截的绘制对象
        Return arguments:
        None -- 无返回值
        """
        self.drawn.append((type(now).__name__, now.width, now.style, now.text))

    def color(self, cid: int) -> None:
        """
        为指定测试角色写入固定的文字颜色 "#ff0000"。
        Keyword arguments:
        cid -- int，目标角色编号
        Return arguments:
        None -- 无返回值
        """
        kernel_data.put(
            identity.put,
            dataclasses.replace(identity.of(cid), text_color="#ff0000"),
        )


class HandleEventTest(EventTextCase):
    """验证 handle_event 的选事件规则与 show_event_text 的回调输出。"""

    def test_fired_event_reaches_line_wait_draw(self) -> None:
        """
        验证选中类型 2 事件后会写入跳过口上标记，并经回调按配置宽度调用 LineFeedWaitDraw。
        Return arguments:
        None -- 无返回值
        """
        fired = event.handle_event(NPC)
        assert fired is not None
        self.assertEqual(
            (fired.event_id, fired.event_type, fired.text, fired.style),
            (MAIN, 2, "\n正文甲", "standard"),
        )
        self.assertTrue(activity.event(NPC).skip_instruct_talk)
        event.show_event_text(fired)
        self.assertEqual(self.shown, [("\n正文甲", "standard")])
        width = normal_config.config_normal.text_width
        self.assertEqual(
            self.drawn, [("LineFeedWaitDraw", width, "standard", "\n正文甲")]
        )

    def test_diy_event_swaps_id_and_clears_flag(self) -> None:
        """
        验证启用自定义事件标记时事件编号切换为自定义事件、事件类型不变、取第三段测试文本并清除标记。
        Return arguments:
        None -- 无返回值
        """
        activity.update_event(NPC, chara_diy_event_flag=True, event_id=DIY)
        fired = event.handle_event(NPC)
        assert fired is not None
        self.assertEqual(
            (fired.event_id, fired.event_type, fired.text),
            (DIY, 2, "\n第三段"),
        )
        self.assertFalse(activity.event(NPC).chara_diy_event_flag)

    def test_short_diy_text_keeps_flag_and_shows_nothing(self) -> None:
        """
        验证不足三段的自定义事件测试文本返回空文本、不清除标记且不触发输出。
        Return arguments:
        None -- 无返回值
        """
        activity.update_event(
            NPC, chara_diy_event_flag=True, event_id=DIY_SHORT
        )
        fired = event.handle_event(NPC)
        assert fired is not None
        self.assertEqual((fired.event_id, fired.text), (DIY_SHORT, ""))
        self.assertTrue(activity.event(NPC).chara_diy_event_flag)
        event.show_event_text(fired)
        self.assertEqual((self.shown, self.drawn), ([], []))

    def test_player_elsewhere_gets_empty_text(self) -> None:
        """
        验证玩家不在场时返回原事件编号与空文本、不清除自定义事件标记且不触发输出。
        Return arguments:
        None -- 无返回值
        """
        place(NPC, ["0", "0"])
        activity.update_event(NPC, chara_diy_event_flag=True, event_id=DIY)
        fired = event.handle_event(NPC)
        assert fired is not None
        self.assertEqual((fired.event_id, fired.text), (MAIN, ""))
        self.assertTrue(activity.event(NPC).chara_diy_event_flag)
        event.show_event_text(fired)
        self.assertEqual((self.shown, self.drawn), ([], []))

    def test_before_instruct_skips_type_1(self) -> None:
        """
        验证 event_before_instrust_flag 为真时跳过类型 1 事件，为假时选中该事件。
        Return arguments:
        None -- 无返回值
        """
        with mock.patch.object(
            game_config, "config_event_status_data", {BEHAVIOR: [DIY]}
        ):
            self.assertIsNone(event.handle_event(NPC, True))
            fired = event.handle_event(NPC)
        assert fired is not None
        self.assertEqual((fired.event_id, fired.event_type), (DIY, 1))
        self.assertFalse(activity.event(NPC).skip_instruct_talk)

    def test_no_event_returns_none(self) -> None:
        """
        验证当前行为没有候选事件时 handle_event 返回 None。
        Return arguments:
        None -- 无返回值
        """
        stand(NPC, "event_text_other_behavior")
        self.assertIsNone(event.handle_event(NPC))


class BuildEventTextTest(EventTextCase):
    """验证 build_event_text 的子事件分段与样式优先级，以及 show_event_text 经回调按专属事件样式绘制。"""

    def test_son_event_keeps_second_part(self) -> None:
        """
        验证带 option_son 前提的子事件选取第二段测试文本并在开头添加换行符。
        Return arguments:
        None -- 无返回值
        """
        built = event.build_event_text(SON, NPC, 1)
        self.assertEqual(built.text, "\n第二段")

    def test_adv_style_prefers_own_color(self) -> None:
        """
        验证专属事件样式优先取有文字颜色的角色名，其次取交互对象名，非专属事件取 "standard"。
        Return arguments:
        None -- 无返回值
        """
        self.color(0)
        self.assertEqual(event.build_event_text(ADV, NPC, 1).style, "博士")
        self.color(NPC)
        self.assertEqual(event.build_event_text(ADV, NPC, 1).style, "干员")
        self.assertEqual(event.build_event_text(MAIN, NPC, 1).style, "standard")

    def test_show_draws_adv_style(self) -> None:
        """
        验证角色有文字颜色时，show_event_text 经回调以角色名样式、专属事件正文与配置宽度调用一次 LineFeedWaitDraw。
        Return arguments:
        None -- 无返回值
        """
        self.color(NPC)
        event.show_event_text(event.build_event_text(ADV, NPC, 1))
        width = normal_config.config_normal.text_width
        self.assertEqual(
            self.drawn, [("LineFeedWaitDraw", width, "干员", "\n专属正文")]
        )


class JudgeStatusTest(EventTextCase):
    """验证 judge_character_status 触发并显示开始事件的流程。"""

    def test_start_event_shown_once_with_swapped_id(self) -> None:
        """
        验证 judge_character_status 显示一次开始事件的第三段测试文本，并记录切换后的自定义事件编号。
        Return arguments:
        None -- 无返回值
        """
        activity.update_event(NPC, chara_diy_event_flag=True, event_id=DIY)
        with mock.patch.object(
            settle_behavior, "handle_settle_behavior", return_value=None
        ):
            character_behavior.judge_character_status(NPC)
        self.assertEqual(self.shown, [("\n第三段", "standard")])
        self.assertEqual(activity.event(NPC).event_id, DIY)


class EventUiFreeTest(FastTestCase):
    """验证屏蔽界面、结算与输入输出模块时 event.py 可在独立子进程中完成事件触发与文本构建。"""

    child: ChildRun
    """ 无界面子进程的单次执行结果 """

    @classmethod
    def setUpClass(cls) -> None:
        """
        在启用后端初始化的无界面子进程中执行一次 UI_FREE_RUN 并缓存结果。
        Return arguments:
        None -- 无返回值
        """
        super().setUpClass()
        cls.child = run_ui_free(UI_FREE_RUN, boot=True)

    def test_event_runs_without_ui(self) -> None:
        """
        验证无界面子进程返回预期的触发与构建结果，且未尝试或加载受拦截模块。
        Return arguments:
        None -- 无返回值
        """
        self.assertEqual(
            self.child.payload,
            {
                "fired": [MAIN, 2, "\n正文甲", "standard"],
                "skip": True,
                "built": [
                    [DIY, "\n第三段", "standard"],
                    [SON, "\n第二段", "standard"],
                    [ADV, "\n专属正文", "1"],
                ],
                "away": "",
                "shown": [["\n正文甲", "standard"]],
            },
        )
        self.assertEqual((self.child.attempted, self.child.loaded), ([], []))


class EventImportBoundaryTest(FastTestCase):
    """验证 Script/Design/event.py 源码的导入边界。"""

    def test_event_imports_no_ui(self) -> None:
        """
        验证 banned_imports 在 Script/Design/event.py 源码中不报告界面、输入输出与 Tk 导入。
        Return arguments:
        None -- 无返回值
        """
        self.assertEqual(banned_imports((ROOT / EVENT).read_bytes(), EVENT), [])
