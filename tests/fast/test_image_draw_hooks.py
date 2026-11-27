"""
断面图与口上图片界面回调测试
============================
- ImageHookTest：验证 Tk 图片回调登记与绘制、回调按登记顺序执行及未登记时静默。
- CrossSectionTest：验证无交互对象时静默，以及不同身体状态下的断面图选图与回调绘制。
- TalkImageTest：验证口上图片标签按序发出并移除，以及口上绘制先发图片再输出正文。
- ImportBoundaryTest：验证 banned_imports 的检查行为，以及屏蔽 Script.UI 后口上图片正常运行。
"""

import json
import subprocess
import sys
from typing import NamedTuple
from unittest import mock

from Script.Core import constant, io_init
from Script.Design import cross_section_image, talk, talk_image
from Script.Kernel import core
from Script.Modules.domains import activity, dirty, h_state, pregnancy
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.Modules.tk_ui import callbacks
from Script.UI.Moudle import draw
from tests import chara_abilities as ca
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports

TARGET = 1
""" 测试使用的交互对象角色编号（1）。 """
BLOCKED_RUN = """
import importlib.abc
import json
import sys


class BlockUi(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "Script.UI" or fullname.startswith("Script.UI."):
            raise ImportError(fullname)
        return None


sys.meta_path.insert(0, BlockUi())
from Script.Design import talk_image
from Script.Modules.gameplay_resolution import ui_hooks

emitted = []
ui_hooks.on_image(emitted.append)
text = talk_image.draw_image_in_talk("前{img:测试图}后")
ui = sorted(
    name
    for name in sys.modules
    if name == "Script.UI" or name.startswith("Script.UI.")
)
print(json.dumps({"text": text, "emitted": emitted, "ui": ui}))
"""
"""
在屏蔽 Script.UI 的子进程中执行的脚本，运行 draw_image_in_talk
并以 JSON 输出去标签文本、发出的图片名及已加载的 Script.UI 模块列表。
"""

type Drawn = tuple[bool, str, str]
""" 单次绘制或直接输出的记录元组类型，依次为是否处于图片回调内、绘制类或函数名以及图片名或文本。 """


class Body(NamedTuple):
    """交互对象身体状态元组，依次记录阴道与子宫精液量、素质编号、生理期阶段与插入位置。"""

    vagina: int = 0
    womb: int = 0
    talents: tuple[int, ...] = ()
    period: int = 0
    insert: int = -1


CROSS_SECTIONS: tuple[tuple[Body, str], ...] = (
    (Body(), "标准状态"),
    (Body(vagina=1), "标准状态"),
    (Body(vagina=2), "精液少"),
    (Body(vagina=200), "精液少"),
    (Body(womb=201), "精液中"),
    (Body(vagina=1000), "精液中"),
    (Body(vagina=600, womb=401), "精液多"),
    (Body(talents=(20,)), "受精"),
    (Body(talents=(21,)), "妊娠"),
    (Body(talents=(22,)), "临盆"),
    (Body(period=5), "排卵期"),
    (Body(period=4), "危险期"),
    (Body(period=2), "标准状态"),
    (Body(vagina=1001, talents=(21,), period=5), "精液多"),
    (Body(vagina=2, talents=(20,)), "精液少"),
    (Body(talents=(20, 21, 22)), "受精"),
    (Body(talents=(21, 22)), "妊娠"),
    (Body(talents=(22,), period=5), "临盆"),
    (Body(insert=6), "标准状态_插入"),
    (Body(insert=7, vagina=300), "精液中_插入"),
    (Body(insert=7, talents=(21,)), "妊娠_插入"),
    (Body(insert=6, period=4), "危险期_插入"),
    (Body(insert=8), "标准状态"),
)
""" 用于断言断面图选图的（身体状态，预期图片名）用例元组。 """
TALK_TAGS: tuple[tuple[str, str, list[str]], ...] = (
    ("前后", "前后", []),
    ("前{img:}后", "前{img:}后", []),
    ("前{img:甲}后", "前后", ["甲"]),
    ("{img:甲}一{img:乙}二", "一二", ["甲", "乙"]),
    ("{img:甲}一{img:甲}二{img:乙}", "一二", ["甲", "甲", "乙"]),
)
""" 用于断言口上图片标签处理的（原始文本，去标签文本，预期图片名列表）用例元组。 """


class ImageCase(FastTestCase):
    """图片回调测试基类，记录发出的图片名以及图片回调内外的绘制与直接输出。"""

    def setUp(self) -> None:
        """初始化主角与测试交互对象，接管图片回调、draw 中全部带 draw 方法的类、era_print 与 image_print。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(TARGET, "测试干员")
        self.emitted: list[str] = []
        self.log: list[Drawn] = []
        self.inside = False
        self.hooks = list(ui_hooks._images)
        self.enterContext(
            mock.patch.object(ui_hooks, "_images", [self.forward])
        )
        for cls in vars(draw).values():
            if isinstance(cls, type) and hasattr(cls, "draw"):
                self.enterContext(
                    mock.patch.object(
                        cls, "draw", autospec=True, side_effect=self.keep
                    )
                )
        self.enterContext(
            mock.patch.object(io_init, "era_print", side_effect=self.printed)
        )
        self.enterContext(
            mock.patch.object(io_init, "image_print", side_effect=self.image)
        )

    def forward(self, img_name: str) -> None:
        """记录图片名，并在回调标记开启期间按原顺序调用测试前已登记的图片回调。"""
        self.emitted.append(img_name)
        self.inside = True
        try:
            for fn in self.hooks:
                fn(img_name)
        finally:
            self.inside = False

    def keep(self, now: object) -> None:
        """记录绘制对象是否处于图片回调内、其类名，以及图片名或文本属性。"""
        name = getattr(now, "image_name", None)
        text = name if isinstance(name, str) else str(getattr(now, "text", ""))
        self.log.append((self.inside, type(now).__name__, text))

    def printed(
        self,
        string: str,
        style: str | tuple[str, ...] = "standard",
        tooltip: str = "",
    ) -> None:
        """记录 io_init.era_print 调用时是否处于图片回调内以及输出文本。"""
        self.log.append((self.inside, "era_print", string))

    def image(self, image_name: str) -> None:
        """记录 io_init.image_print 调用时是否处于图片回调内以及图片名。"""
        self.log.append((self.inside, "image_print", image_name))

    def drawn(self) -> list[Drawn]:
        """返回处于图片回调内的绘制记录列表。"""
        return [entry for entry in self.log if entry[0]]

    def direct(self) -> list[Drawn]:
        """返回处于图片回调外的绘制或输出记录列表。"""
        return [entry for entry in self.log if not entry[0]]

    def clear(self) -> None:
        """清空已记录的图片名列表与绘制记录列表。"""
        self.emitted.clear()
        self.log.clear()


class ImageHookTest(ImageCase):
    """图片回调登记、派发与未登记行为的测试。"""

    def test_tk_callback_registered(self) -> None:
        """验证 Tk 图片绘制回调 callbacks.draw_image 已登记到 ui_hooks。"""
        self.assertIn(callbacks.draw_image, self.hooks)

    def test_tk_callback_draws_image(self) -> None:
        """验证 emit_image 发出图片名后，Tk 回调在回调内通过 ImageDraw 绘制同名图片。"""
        ui_hooks.emit_image("测试图")
        self.assertEqual(self.emitted, ["测试图"])
        self.assertEqual(self.log, [(True, "ImageDraw", "测试图")])

    def test_emit_calls_in_registration_order(self) -> None:
        """验证未登记回调时 emit_image 静默、on_image 原样返回回调，以及多个回调按登记顺序执行。"""
        calls: list[tuple[str, str]] = []

        def first(img_name: str) -> None:
            """记录第一个测试回调收到的图片名。"""
            calls.append(("一", img_name))

        def second(img_name: str) -> None:
            """记录第二个测试回调收到的图片名。"""
            calls.append(("二", img_name))

        self.enterContext(mock.patch.object(ui_hooks, "_images", []))
        ui_hooks.emit_image("甲")
        self.assertIs(ui_hooks.on_image(first), first)
        self.assertIs(ui_hooks.on_image(second), second)
        ui_hooks.emit_image("乙")
        self.assertEqual(calls, [("一", "乙"), ("二", "乙")])

    def test_unregistered_hook_draws_nothing(self) -> None:
        """验证未登记图片回调时断面图与口上图片函数均不绘制，且口上文本仍会去掉图片标签。"""
        self.enterContext(mock.patch.object(ui_hooks, "_images", []))
        with working.based_on(core.state()):
            activity.set_target(0, TARGET)
            cross_section_image.draw_cross_section_image()
        text = talk_image.draw_image_in_talk("前{img:甲}后")
        self.assertEqual(text, "前后")
        self.assertEqual((self.emitted, self.log), ([], []))


class CrossSectionTest(ImageCase):
    """断面图选图与回调绘制的测试。"""

    def test_no_target_draws_nothing(self) -> None:
        """验证没有交互对象时 draw_cross_section_image 不发出图片名且不产生绘制记录。"""
        with working.based_on(core.state()):
            activity.set_target(0, 0)
            cross_section_image.draw_cross_section_image()
        self.assertEqual((self.emitted, self.log), ([], []))

    def test_body_state_picks_image(self) -> None:
        """验证 CROSS_SECTIONS 中每组身体状态均选出预期断面图名，且仅在图片回调内由 ImageDraw 绘制。"""
        for body, name in CROSS_SECTIONS:
            with self.subTest(body=body), working.based_on(core.state()):
                self.clear()
                put_body(body)
                cross_section_image.draw_cross_section_image()
                self.assertEqual(self.emitted, [name])
                self.assertEqual(self.log, [(True, "ImageDraw", name)])


class TalkImageTest(ImageCase):
    """口上图片标签解析、移除与口上绘制顺序的测试。"""

    def test_tags_emit_in_order_and_are_stripped(self) -> None:
        """验证 TALK_TAGS 中每条文本均按标签顺序发出图片名、在回调内经 ImageDraw 绘制并返回去标签文本。"""
        for text, cleaned, names in TALK_TAGS:
            with self.subTest(text=text):
                self.clear()
                self.assertEqual(talk_image.draw_image_in_talk(text), cleaned)
                self.assertEqual(self.emitted, names)
                self.assertEqual(
                    self.log, [(True, "ImageDraw", name) for name in names]
                )

    def test_talk_draw_shows_image_before_text(self) -> None:
        """验证 talk.handle_talk_draw 先在回调内经 ImageDraw 绘制口上图片，再在回调外输出不含图片标签的口上文本。"""
        talk.handle_talk_draw(
            0,
            "前{img:甲}后",
            "",
            common_behavior_id=constant.Behavior.SHARE_BLANKLY,
        )
        self.assertEqual(self.emitted, ["甲"])
        self.assertEqual(self.log[0], (True, "ImageDraw", "甲"))
        self.assertEqual(self.drawn(), [(True, "ImageDraw", "甲")])
        shown = "".join(text for _, _, text in self.direct())
        self.assertIn("前", shown)
        self.assertNotIn("{img:", shown)


class ImportBoundaryTest(FastTestCase):
    """断面图、口上图片与 ui_hooks 导入边界的测试。"""

    def test_checker_reports_relative_and_multi_name_imports(self) -> None:
        """验证 banned_imports 能检出相对导入与单条语句中的后续禁用导入名。"""
        source = "from ..UI.Moudle import draw\nfrom Script import Core, UI\n"
        self.assertEqual(
            banned_imports(source, "Script/Design/sample.py"),
            [(1, "Script.UI.Moudle.draw"), (2, "Script.UI")],
        )

    def test_talk_image_runs_without_ui(self) -> None:
        """
        验证在屏蔽 Script.UI 的子进程中，draw_image_in_talk 能经回调发出图片名、
        返回去标签文本且进程未加载 Script.UI。
        """
        result = subprocess.run(
            [sys.executable, "-c", BLOCKED_RUN],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        report = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(
            report, {"text": "前后", "emitted": ["测试图"], "ui": []}
        )


def put_body(body: Body) -> None:
    """
    将主角交互对象设为 TARGET，并把 body 中的精液量、素质、生理期与插入位置写入当前工作状态。
    Keyword arguments:
    body -- Body，要写入测试交互对象的身体状态元组
    Return arguments:
    None -- 无返回值
    """
    activity.set_target(0, TARGET)
    with dirty.editing(TARGET) as now:
        now.body_semen[6][1] = body.vagina
        now.body_semen[7][1] = body.womb
    for talent_id in body.talents:
        ca.talent(TARGET)[talent_id] = 1
    pregnancy.update(TARGET, reproduction_period=body.period)
    h_state.set(TARGET, insert_position=body.insert)
