"""
地图与口上界面回调测试
======================
- DividerAndRichTalkHookTest：分隔线与富文本口上回调的登记、派发顺序、默认参数与未登记静默。
- TkMapTalkCallbacksTest：正常启动流程登记 Tk 回调以及分隔线与富文本口上绘制序列。
- MapAccessibleHookTest：judge_scene_accessible 经分隔线与提示回调派发未开放与锁门提醒。
- TalkHookTest：handle_talk_draw 与 second_behavior_info_text 经富文本口上和提示回调派发。
- ImportBoundaryTest：三模块的后端界面导入边界以及屏蔽界面模块时的独立加载。
"""

import json
import subprocess
import sys
from typing import Any
from unittest import mock

from Script.Config import game_config, normal_config
from Script.Core import constant, game_type, get_text
from Script.Design import map_handle, talk
from Script.Kernel import core
from Script.Modules.domains import activity, facility, identity, scene_state
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.Modules.tk_ui import callbacks
from Script.UI.Moudle import draw, rich_text_draw
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports

TARGET = 1
""" 测试使用的目标角色编号（1）。 """
EXTRA = 2
""" 测试使用的第三名角色编号（2），用于覆盖口上归属角色颜色优先级。 """
DORM = ["宿舍", "1区", "102"]
""" 1 区 102 号宿舍的场景路径列表。 """
BLANK = constant.Behavior.SHARE_BLANKLY
""" 测试口上派发时使用的基础行为编号。 """
SOURCES = (
    "Script/Design/map_handle.py",
    "Script/Design/talk.py",
    "Script/Modules/gameplay_resolution/ui_hooks.py",
)
""" 接受后端界面边界导入检查的三个模块仓库相对路径元组。 """
STARTUP_CHECK = """
import json, sys
from Script.Config import normal_config
normal_config.init_normal_config()
from Script.Modules.gameplay_resolution import ui_hooks
before = [
    bool(ui_hooks._dividers),
    bool(ui_hooks._rich_talks),
    "Script.Modules.tk_ui.callbacks" in sys.modules,
]
from Script.Kernel import core
from Script.Modules import load_order
core.load(load_order.LOAD_ORDER)
fmt = lambda fns: [[f.__module__, f.__name__] for f in fns]
out = {"before": before, "dividers": fmt(ui_hooks._dividers), "rich_talks": fmt(ui_hooks._rich_talks)}
print(json.dumps(out))
"""
""" 子进程脚本：不直接导入 callbacks，执行正常启动加载顺序并输出两类回调的登记结果。 """
BLOCKED_RUN = """
import importlib.abc, json, sys
BLOCKED = ("Script.UI", "Script.Modules.tk_ui.callbacks", "tkinter", "_tkinter")
def is_blocked(n): return any(n == r or n.startswith(r + ".") for r in BLOCKED)
class BlockUi(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if is_blocked(fullname): raise ImportError(fullname)
        return None
sys.meta_path.insert(0, BlockUi())
from Script.Config import normal_config
normal_config.init_normal_config()
from Script.Design import map_handle, talk
from Script.Modules.gameplay_resolution import ui_hooks
dividers, talks = [], []
ui_hooks.on_divider(dividers.append)
ui_hooks.on_rich_talk(lambda t, **kw: talks.append([t, kw["base_style"], kw["wait_flag"], kw["trailing_wait"]]))
ui_hooks.emit_divider("=")
ui_hooks.emit_rich_talk("口上", trailing_wait=True)
print(json.dumps({"dividers": dividers, "talks": talks, "loaded": sorted(n for n in sys.modules if is_blocked(n))}))
"""
""" 子进程脚本：屏蔽界面、callbacks 与 Tk 模块后导入三模块，验证回调派发且零误加载。 """

type Drawn = tuple[str, object, object, object]
""" 一次绘制的记录元组类型，依次为绘制类名、文本、宽度与样式名。 """
type Notice = tuple[str, bool, str | None, bool]
""" 一条提示回调的参数元组类型，依次为文本、是否等待确认、样式名与是否按配置文本宽度排版。 """
type RichCall = tuple[str, str, bool, bool]
""" 一次富文本口上回调的参数元组类型，依次为文本、基础样式、行尾等待标记与结尾追加等待标记。 """

_ = get_text._


def run_json(script: str) -> dict[str, Any]:
    """在独立子进程运行脚本并解析末行 JSON 输出。"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr[-2000:])
    return json.loads(result.stdout.splitlines()[-1])


def expected_rich(
    text: str, base_style: str = "standard", wait_flag: bool = True
) -> list[Drawn]:
    """按当前配置文本宽度构造富文本绘制对象的预期记录列表。"""
    width = normal_config.config_normal.text_width
    return [
        (type(item).__name__, item.text, width, item.style)
        for item in rich_text_draw.get_rich_text_draw_list(
            text, base_style=base_style, wait_flag=wait_flag
        )
    ]


class DrawCase(FastTestCase):
    """初始化测试角色、打开工作集并接管 draw 模块中全部绘制类 draw 方法的测试基类。"""

    def setUp(self) -> None:
        """初始化玩家与目标角色，打开工作集，并将全部 draw 绘制类的 draw 调用记入 self.drawn。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(TARGET, "测试干员")
        self.enterContext(working.based_on(core.state()))
        self.drawn: list[Drawn] = []
        self.notices: list[Notice] = []
        for cls in vars(draw).values():
            if isinstance(cls, type) and hasattr(cls, "draw"):
                self.enterContext(
                    mock.patch.object(
                        cls, "draw", autospec=True, side_effect=self.keep
                    )
                )

    def keep(self, now: object) -> None:
        """记录单次绘制对象的类名、文本、宽度与样式名。"""
        self.drawn.append(
            (
                type(now).__name__,
                getattr(now, "text", None),
                getattr(now, "width", None),
                getattr(now, "style", None),
            )
        )

    def record_notice(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """记录单次提示回调的参数元组。"""
        self.notices.append((text, wait, style, use_text_width))


class DividerAndRichTalkHookTest(FastTestCase):
    """分隔线与富文本口上回调的登记、顺序、默认参数与未登记行为测试。"""

    def setUp(self) -> None:
        """将 ui_hooks 的分隔线与富文本口上回调列表暂时替换为空列表。"""
        super().setUp()
        self.enterContext(mock.patch.object(ui_hooks, "_dividers", []))
        self.enterContext(mock.patch.object(ui_hooks, "_rich_talks", []))

    def test_unregistered_hooks_are_noops(self) -> None:
        """验证未登记回调时 emit_divider 与 emit_rich_talk 均静默返回 None。"""
        self.assertIsNone(ui_hooks.emit_divider())
        self.assertIsNone(ui_hooks.emit_divider("="))
        self.assertIsNone(ui_hooks.emit_rich_talk("口上"))

    def test_divider_registration_order_and_default(self) -> None:
        """验证 on_divider 原样返回回调，emit_divider 按登记顺序传递默认与自定义分隔字符。"""
        calls = mock.Mock()
        self.assertIs(ui_hooks.on_divider(calls.first), calls.first)
        self.assertIs(ui_hooks.on_divider(calls.second), calls.second)
        ui_hooks.emit_divider()
        ui_hooks.emit_divider("=")
        self.assertEqual(
            calls.mock_calls,
            [
                mock.call.first("-"),
                mock.call.second("-"),
                mock.call.first("="),
                mock.call.second("="),
            ],
        )

    def test_rich_talk_registration_order_and_defaults(self) -> None:
        """验证 on_rich_talk 原样返回回调，emit_rich_talk 按登记顺序转发默认与自定义参数。"""
        calls = mock.Mock()
        self.assertIs(ui_hooks.on_rich_talk(calls.first), calls.first)
        self.assertIs(ui_hooks.on_rich_talk(calls.second), calls.second)
        ui_hooks.emit_rich_talk("甲")
        ui_hooks.emit_rich_talk(
            "乙", base_style="测试干员", wait_flag=False, trailing_wait=True
        )
        kw1 = {
            "base_style": "standard",
            "wait_flag": True,
            "trailing_wait": False,
        }
        kw2 = {
            "base_style": "测试干员",
            "wait_flag": False,
            "trailing_wait": True,
        }
        self.assertEqual(
            calls.mock_calls,
            [
                mock.call.first("甲", **kw1),
                mock.call.second("甲", **kw1),
                mock.call.first("乙", **kw2),
                mock.call.second("乙", **kw2),
            ],
        )


class TkMapTalkCallbacksTest(DrawCase):
    """正常启动登记与 Tk 分隔线、富文本口上回调的绘制顺序测试。"""

    def test_startup_registers_tk_callbacks(self) -> None:
        """验证独立子进程不直接导入 callbacks 时，执行正常启动加载顺序后自动登记两类 Tk 回调。"""
        report = run_json(STARTUP_CHECK)
        self.assertEqual(report["before"], [False, False, False])
        mod = "Script.Modules.tk_ui.callbacks"
        self.assertIn([mod, "draw_divider"], report["dividers"])
        self.assertIn([mod, "draw_rich_talk"], report["rich_talks"])

    def test_draw_divider_uses_configured_text_width(self) -> None:
        """验证 callbacks.draw_divider 按当前配置文本宽度绘制 "-" 与 "=" 字符的 LineDraw。"""
        width = normal_config.config_normal.text_width
        callbacks.draw_divider("-")
        callbacks.draw_divider("=")
        self.assertEqual(
            self.drawn,
            [
                ("LineDraw", "-", width, "standard"),
                ("LineDraw", "=", width, "standard"),
            ],
        )

    def test_draw_rich_talk_sequence_and_trailing_wait(self) -> None:
        """验证 draw_rich_talk 先绘零宽换行、再按配置宽度逐项绘制富文本，并按需追加尾等待。"""
        sample = "甲<color:red>乙</color>\n"
        cases = (
            ("standard", True, False),
            ("standard", True, True),
            ("gold_enrod", False, False),
        )
        for style, wait_flag, trailing_wait in cases:
            with self.subTest(
                style=style, wait_flag=wait_flag, trailing_wait=trailing_wait
            ):
                self.drawn.clear()
                callbacks.draw_rich_talk(
                    sample,
                    base_style=style,
                    wait_flag=wait_flag,
                    trailing_wait=trailing_wait,
                )
                expected: list[Drawn] = [
                    ("NormalDraw", "\n", 0, "standard"),
                    *expected_rich(sample, style, wait_flag),
                ]
                if trailing_wait:
                    expected.append(("LineFeedWaitDraw", " \n", 0, "standard"))
                self.assertEqual(self.drawn, expected)


class MapAccessibleHookTest(DrawCase):
    """map_handle.judge_scene_accessible 经分隔线与提示回调派发未开放与锁门提醒的测试。"""

    def setUp(self) -> None:
        """接管 ui_hooks 的分隔线与提示回调列表，将派发参数分别记入 self.dividers 与 self.notices。"""
        super().setUp()
        self.dividers: list[str] = []
        self.enterContext(
            mock.patch.object(ui_hooks, "_dividers", [self.dividers.append])
        )
        self.enterContext(
            mock.patch.object(ui_hooks, "_notices", [self.record_notice])
        )

    def lock_dorm(self) -> tuple[str, str]:
        """锁定 102 号宿舍并返回其场景路径键与预期锁门提示文本。"""
        dorm_str = map_handle.get_map_system_path_str_for_list(DORM)
        scene_state.set_close_flag(dorm_str, 1)
        name = constant.scene_data[dorm_str].scene_name
        text = _(
            "\n  ●目标移动房间——{0}，当前门是锁着的，需要钥匙或其他方法进入\n"
        ).format(name)
        return dorm_str, text

    def test_wait_open_emits_divider_and_notice_for_player(self) -> None:
        """验证设施未开放时玩家进门返回 wait_open，并发出分隔线与按配置宽度排版的等待提示。"""
        build_scene, forge_scene = game_type.Scene(), game_type.Scene()
        build_scene.scene_name, forge_scene.scene_name = "龙门食坊", "铁匠铺"
        self.world.chara(EXTRA, "铁匠干员", adv=163)
        facility.set_open(160, False)
        facility.set_open(13, False)
        eff = game_config.config_facility_effect
        op = game_config.config_facility_open
        z_build, z_forge = eff[op[160].zone_cid], eff[op[13].zone_cid]
        build_msg = _(
            "\n  ●目标移动房间——{0}，当前尚未建设，需要在基建-{1}中建设该地点\n"
        ).format("龙门食坊", z_build.name)
        forge_msg = _(
            "\n  ●目标移动房间——{0}，当前尚未解锁，解锁需要将{1}升到{2}级\n"
        ).format("铁匠铺", z_forge.name, str(z_forge.level)) + _(
            "\n  ●目标移动房间——{0}，当前尚未解锁，解锁需要获得干员{1}\n"
        ).format(
            "铁匠铺", "铁匠干员"
        )
        scenes = {"测试/龙门食坊": build_scene, "测试/铁匠铺": forge_scene}
        with mock.patch.dict(constant.scene_data, scenes):
            for key, msg in (
                ("测试/龙门食坊", build_msg),
                ("测试/铁匠铺", forge_msg),
            ):
                self.dividers.clear()
                self.notices.clear()
                ret = map_handle.judge_scene_accessible(key, 0, True)
                self.assertEqual(
                    (ret, self.dividers, self.notices, self.drawn),
                    ("wait_open", ["-"], [(msg, True, None, True)], []),
                )
            self.dividers.clear()
            self.notices.clear()
            for actor, flag in ((0, False), (TARGET, True)):
                ret = map_handle.judge_scene_accessible(
                    "测试/龙门食坊", actor, flag
                )
                self.assertEqual(ret, "wait_open")
            self.assertEqual(
                (self.dividers, self.notices, self.drawn), ([], [], [])
            )

    def test_door_lock_respects_draw_flag_and_actor(self) -> None:
        """验证锁门房间在玩家且 draw_flag 为真时派发分隔线与等待提示，否则静默返回 door_lock。"""
        dorm_str, expected = self.lock_dorm()
        ret = map_handle.judge_scene_accessible(dorm_str, 0, True)
        self.assertEqual(
            (ret, self.dividers, self.notices, self.drawn),
            ("door_lock", ["-"], [(expected, True, None, True)], []),
        )
        self.dividers.clear()
        self.notices.clear()
        for actor, flag in ((0, False), (TARGET, True)):
            ret = map_handle.judge_scene_accessible(dorm_str, actor, flag)
            self.assertEqual(ret, "door_lock")
        self.assertEqual(
            (self.dividers, self.notices, self.drawn), ([], [], [])
        )

    def test_door_lock_with_tk_callbacks_draws_line_and_wait(self) -> None:
        """验证经 Tk 回调派发锁门提醒时，按配置文本宽度依次绘制 LineDraw 与 WaitDraw。"""
        dorm_str, expected = self.lock_dorm()
        w = normal_config.config_normal.text_width
        ui_hooks._dividers[:] = [callbacks.draw_divider]
        ui_hooks._notices[:] = [callbacks.draw_notice]
        ret = map_handle.judge_scene_accessible(dorm_str, 0, True)
        self.assertEqual(ret, "door_lock")
        self.assertEqual(
            self.drawn,
            [
                ("LineDraw", "-", w, "standard"),
                ("WaitDraw", expected, w, "standard"),
            ],
        )


class TalkHookTest(DrawCase):
    """talk.handle_talk_draw 与 talk.second_behavior_info_text 的回调派发与样式测试。"""

    def setUp(self) -> None:
        """接管 ui_hooks 的富文本口上与提示回调列表，分别记入 self.rich_calls 与 self.notices。"""
        super().setUp()
        self.rich_calls: list[RichCall] = []
        self.enterContext(
            mock.patch.object(ui_hooks, "_rich_talks", [self.record_rich])
        )
        self.enterContext(
            mock.patch.object(ui_hooks, "_notices", [self.record_notice])
        )

    def record_rich(
        self,
        text: str,
        *,
        base_style: str,
        wait_flag: bool,
        trailing_wait: bool,
    ) -> None:
        """记录单次富文本口上回调的参数元组。"""
        self.rich_calls.append((text, base_style, wait_flag, trailing_wait))

    def test_handle_talk_draw_normal_and_jump_trailing_wait(self) -> None:
        """验证地文口上经 emit_rich_talk 派发，含 <jump> 时 trailing_wait 为 True，否则为 False。"""
        for text in ("普通地文", "<jump>快进地文"):
            talk.handle_talk_draw(0, text, "", common_behavior_id=BLANK)
        self.assertEqual(
            self.rich_calls,
            [
                ("普通地文", "standard", True, False),
                ("快进地文", "standard", True, True),
            ],
        )
        self.assertEqual(self.drawn, [])

    def test_handle_talk_draw_selects_character_style_priority(self) -> None:
        """验证角色口上按口上归属角色、触发者、交互对象、standard 的优先级选择 base_style。"""
        self.world.chara(EXTRA, "归属干员")
        activity.set_target(0, TARGET)
        cfg = type("SampleTalk", (), {"behavior_id": BLANK, "adv_id": EXTRA})()
        with mock.patch.dict(game_config.config_talk, {"test_style": cfg}):
            for colors, label in (
                (("#112233", "#445566", "#778899"), "一"),
                (("", "#445566", "#778899"), "二"),
                (("", "", "#778899"), "三"),
                (("", "", ""), "四"),
            ):
                identity.update(EXTRA, text_color=colors[0])
                identity.update(0, text_color=colors[1])
                identity.update(TARGET, text_color=colors[2])
                talk.handle_talk_draw(0, label, "test_style")
        self.assertEqual(
            [style for _t, style, _w, _tr in self.rich_calls],
            ["归属干员", "博士", "测试干员", "standard"],
        )
        self.assertEqual(self.drawn, [])

    def test_handle_talk_draw_with_tk_callback_draws_rich_sequence(
        self,
    ) -> None:
        """验证经 Tk 富文本口上回调派发带标签与 <jump> 的口上时绘制序列完整一致。"""
        ui_hooks._rich_talks[:] = [callbacks.draw_rich_talk]
        body = "甲<color:red>乙</color>"
        talk.handle_talk_draw(0, f"<jump>{body}", "", common_behavior_id=BLANK)
        self.assertEqual(
            self.drawn,
            [
                ("NormalDraw", "\n", 0, "standard"),
                *expected_rich(body, "standard", True),
                ("LineFeedWaitDraw", " \n", 0, "standard"),
            ],
        )

    def test_second_behavior_info_text_styles_and_return(self) -> None:
        """验证 second_behavior_info_text 按二段行为种类选择样式并经零宽等待提示派发且保留返回值。"""
        cases = (
            (0, "p_orgasm_normal", "semen"),
            (TARGET, "v_orgasm_strong", "gold_enrod"),
            (TARGET, "plural_orgasm_2", "gold_enrod"),
            (TARGET, "terror_mark_1", "crimson"),
            (TARGET, "hate_mark_2", "crimson"),
            (TARGET, "happy_mark_1", "gold_enrod"),
            (TARGET, "semen_drinking_climax", "gold_enrod"),
            (TARGET, "first_sex", "gold_enrod"),
            (TARGET, "first_kiss", "gold_enrod"),
        )
        for chara_id, behavior_id, style in cases:
            with self.subTest(chara_id=chara_id, behavior_id=behavior_id):
                self.notices.clear()
                ret = talk.second_behavior_info_text(chara_id, behavior_id)
                self.assertTrue(ret.endswith("\n\n"), ret)
                self.assertEqual(self.notices, [(ret, True, style, False)])
        self.notices.clear()
        self.assertEqual(
            talk.second_behavior_info_text(TARGET, "unknown_behavior"), ""
        )
        self.assertEqual((self.notices, self.drawn), ([], []))

    def test_second_behavior_info_text_with_tk_callback(self) -> None:
        """验证经 Tk 提示回调派发恐怖刻印横幅时绘出零宽 crimson 样式 WaitDraw。"""
        ui_hooks._notices[:] = [callbacks.draw_notice]
        ret = talk.second_behavior_info_text(TARGET, "terror_mark_1")
        self.assertEqual(self.drawn, [("WaitDraw", ret, 0, "crimson")])


class ImportBoundaryTest(FastTestCase):
    """map_handle、talk 与 ui_hooks 的导入边界及屏蔽界面加载测试。"""

    def test_sources_import_no_ui(self) -> None:
        """验证 SOURCES 中三个模块经 banned_imports 检查均不含禁用导入。"""
        for path in SOURCES:
            with self.subTest(path=path):
                self.assertEqual(
                    banned_imports((ROOT / path).read_bytes(), path), []
                )

    def test_modules_load_without_ui_in_subprocess(self) -> None:
        """验证独立子进程屏蔽界面、callbacks 与 Tk 模块后可导入三模块并派发回调且零误加载。"""
        expected = {
            "dividers": ["="],
            "talks": [["口上", "standard", True, True]],
            "loaded": [],
        }
        self.assertEqual(run_json(BLOCKED_RUN), expected)
