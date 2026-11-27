"""
二段结算提示回调与依赖测试
==========================
- 提示回调（SecondEffectNoticeTest）：覆盖 handle_milking_machine、handle_urine_collector、handle_b_orgasm_to_milk、
handle_u_orgasm_to_pee 与 handle_extra_orgasm 的状态写入、ui_hooks 提示参数及零值无提示分支。
- Tk 绘制（TkSecondEffectNoticeTest）：保留启动登记回调，验证这五个函数按顺序以 NormalDraw、
配置文本宽度与默认样式绘制五条提示。
- 模块依赖（SecondEffectBoundaryTest）：验证 Script/Settle/Second_effect.py 导入 ui_hooks。
"""

import os
from collections.abc import Generator
from contextlib import contextmanager
from unittest import mock

from Script.Config import normal_config
from Script.Core import game_type, get_text
from Script.Kernel import core
from Script.Modules.domains import activity, fridge, h_state, identity, needs
from Script.Modules.domains import player_collection, status
from Script.Modules.gameplay_resolution import ui_hooks, working
from Script.Settle import Second_effect
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase
from tests.fast.test_ejaculation_services import imports_in
from tests.world import ROOT

_ = get_text._
""" 文本翻译函数 """
CHARA = 1
""" 测试用角色编号 """
MILKER = 4
""" h_state 身体道具编号 4 """
COLLECTOR = 5
""" h_state 身体道具编号 5 """
MILKED = "\n{0}被搾乳机榨出了{1}ml的乳汁\n"
""" handle_milking_machine 提示文本的 msgid """
COLLECTED = "\n{0}被采尿器吸出了{1}ml的圣水\n"
""" handle_urine_collector 提示文本的 msgid """
MILK_KEPT = "\n{0}在绝顶的同时喷出了{1}ml的乳汁，喷出的乳汁被收集到搾乳机中\n"
""" handle_b_orgasm_to_milk 在身体道具 4 开启时提示文本的 msgid """
MILK_SPILT = "\n{0}在绝顶的同时喷出了{1}ml的乳汁，喷出的乳汁散落的到处都是\n"
""" handle_b_orgasm_to_milk 在身体道具 4 关闭时提示文本的 msgid """
URINE_KEPT = "\n{0}在绝顶的同时漏出了{1}ml的尿液，漏出的尿液被收集到采尿器中\n"
""" handle_u_orgasm_to_pee 在身体道具 5 开启时提示文本的 msgid """
URINE_SPILT = "\n{0}在绝顶的同时漏出了{1}ml的尿液，漏出的尿液在地上汇成一滩\n"
""" handle_u_orgasm_to_pee 在身体道具 5 关闭时提示文本的 msgid """
EXTRA = "\n{0}因为第{1}次的连续额外绝顶而被迫感受到了更多的苦痛和恐怖\n"
""" handle_extra_orgasm 提示文本的 msgid """


def text(msgid: str, amount: int) -> str:
    """将翻译后的 msgid 按测试角色名与数值 amount 格式化为提示文本。"""
    return _(msgid).format(identity.of(CHARA).name, amount)


class NoticeCase(FastTestCase):
    """二段结算提示测试基类，准备测试角色、状态变更对象与独立工作集上下文。"""

    def setUp(self) -> None:
        """创建角色 0 与测试角色 CHARA，并初始化状态变更记录对象 self.change。"""
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(CHARA, "测试干员")
        self.change = game_type.CharacterStatusChange()

    @contextmanager
    def fresh(self) -> Generator[None]:
        """基于当前内核状态开启新的工作集缓冲区，并重置 self.change。"""
        with working.based_on(core.state()):
            self.change = game_type.CharacterStatusChange()
            yield


class SecondEffectNoticeTest(NoticeCase):
    """拦截 ui_hooks 提示回调，测试五个二段结算函数的状态写入与提示参数。"""

    def setUp(self) -> None:
        """初始化提示记录列表，并将 ui_hooks._notices 替换为记录回调 self.note。"""
        super().setUp()
        self.notices: list[tuple[str, bool, str | None, bool]] = []
        self.enterContext(mock.patch.object(ui_hooks, "_notices", [self.note]))

    def note(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """记录一次 ui_hooks 提示回调收到的文本与显示参数元组。"""
        self.notices.append((text, wait, style, use_text_width))

    def test_milking_machine_moves_milk_and_notifies(self) -> None:
        """
        验证 handle_milking_machine 在身体道具 4 开启时更新 fridge.MILK、milk_total、milk 与 milk_ml，并发出对应提示。
        """
        with self.fresh():
            h_state.set_body_item(CHARA, MILKER, True)
            needs.set(CHARA, milk=50)
            activity.update_behavior(CHARA, duration=4, milk_ml=3)
            Second_effect.handle_milking_machine(CHARA, self.change)
            self.assertEqual(fridge.table(fridge.MILK), {CHARA: 20})
            self.assertEqual(player_collection.get("milk_total"), {CHARA: 20})
            self.assertEqual(needs.of(CHARA)["milk"], 30)
            self.assertEqual(activity.behavior(CHARA).milk_ml, 23)
            self.assertEqual(
                self.notices, [(text(MILKED, 20), False, None, True)]
            )

    def test_urine_collector_moves_urine_and_notifies(self) -> None:
        """
        验证 handle_urine_collector 在身体道具 5 开启时更新 fridge.URINE、urine_total、urine 与 urine_ml，
        并发出对应提示。
        """
        with self.fresh():
            h_state.set_body_item(CHARA, COLLECTOR, True)
            needs.set(CHARA, urine=50)
            activity.update_behavior(CHARA, duration=4, urine_ml=3)
            Second_effect.handle_urine_collector(CHARA, self.change)
            self.assertEqual(fridge.table(fridge.URINE), {CHARA: 20})
            self.assertEqual(player_collection.get("urine_total"), {CHARA: 20})
            self.assertEqual(needs.of(CHARA)["urine"], 30)
            self.assertEqual(activity.behavior(CHARA).urine_ml, 23)
            self.assertEqual(
                self.notices, [(text(COLLECTED, 20), False, None, True)]
            )

    def test_b_orgasm_ejects_milk_and_notifies(self) -> None:
        """验证 handle_b_orgasm_to_milk 在身体道具 4 开关两分支下更新 milk、milk_ml 与入库记录，并发出对应提示。"""
        for kept, msgid in ((True, MILK_KEPT), (False, MILK_SPILT)):
            with self.subTest(kept=kept), self.fresh():
                self.notices.clear()
                h_state.set_body_item(CHARA, MILKER, kept)
                needs.set(CHARA, milk=100)
                Second_effect.handle_b_orgasm_to_milk(CHARA, self.change)
                self.assertEqual(needs.of(CHARA)["milk"], 80)
                self.assertEqual(activity.behavior(CHARA).milk_ml, 60)
                stored = {CHARA: 60} if kept else {}
                self.assertEqual(fridge.table(fridge.MILK), stored)
                self.assertEqual(player_collection.get("milk_total"), stored)
                self.assertEqual(
                    self.notices, [(text(msgid, 60), False, None, True)]
                )

    def test_u_orgasm_ejects_urine_and_notifies(self) -> None:
        """验证 handle_u_orgasm_to_pee 在身体道具 5 开关两分支下更新 urine 与入库记录，并发出对应提示。"""
        for kept, msgid in ((True, URINE_KEPT), (False, URINE_SPILT)):
            with self.subTest(kept=kept), self.fresh():
                self.notices.clear()
                h_state.set_body_item(CHARA, COLLECTOR, kept)
                needs.set(CHARA, urine=100)
                Second_effect.handle_u_orgasm_to_pee(CHARA, self.change)
                self.assertEqual(needs.of(CHARA)["urine"], 96)
                stored = {CHARA: 52} if kept else {}
                self.assertEqual(fridge.table(fridge.URINE), stored)
                self.assertEqual(player_collection.get("urine_total"), stored)
                self.assertEqual(
                    self.notices, [(text(msgid, 52), False, None, True)]
                )

    def test_extra_orgasm_settles_pain_terror_and_notifies(self) -> None:
        """验证 handle_extra_orgasm 提升状态 17 与状态 18、清零 extra_orgasm_count，并发出对应提示。"""
        with self.fresh():
            h_state.set(CHARA, extra_orgasm_count=2)
            before = (status.of(CHARA)[17], status.of(CHARA)[18])
            Second_effect.handle_extra_orgasm(CHARA, self.change)
            self.assertGreater(status.of(CHARA)[17], before[0])
            self.assertGreater(status.of(CHARA)[18], before[1])
            self.assertEqual(h_state.get(CHARA, "extra_orgasm_count"), 0)
            self.assertEqual(
                self.notices, [(text(EXTRA, 2), False, None, True)]
            )

    def test_nothing_to_settle_emits_no_notice(self) -> None:
        """验证五个二段结算函数在 milk、urine 与 extra_orgasm_count 均为 0 时不发出提示。"""
        handlers = (
            Second_effect.handle_milking_machine,
            Second_effect.handle_urine_collector,
            Second_effect.handle_b_orgasm_to_milk,
            Second_effect.handle_u_orgasm_to_pee,
            Second_effect.handle_extra_orgasm,
        )
        for handler in handlers:
            with self.subTest(handler=handler.__name__), self.fresh():
                h_state.set_body_item(CHARA, MILKER, True)
                h_state.set_body_item(CHARA, COLLECTOR, True)
                needs.set(CHARA, milk=0, urine=0)
                activity.update_behavior(CHARA, duration=4)
                handler(CHARA, self.change)
        self.assertEqual(self.notices, [])


class TkSecondEffectNoticeTest(NoticeCase):
    """保留启动阶段登记的 Tk 提示回调，测试五个二段结算函数的 NormalDraw 绘制结果。"""

    def setUp(self) -> None:
        """打桩 draw.NormalDraw.draw 以记录绘制调用对象。"""
        super().setUp()
        self.drawn = self.enterContext(
            mock.patch.object(draw.NormalDraw, "draw", autospec=True)
        )

    def test_tk_draws_each_notice_as_normal_draw(self) -> None:
        """验证五个二段结算函数经启动登记回调按顺序以 NormalDraw、配置文本宽度与默认样式绘制五条提示。"""
        with self.fresh():
            h_state.set_body_item(CHARA, MILKER, True)
            h_state.set_body_item(CHARA, COLLECTOR, True)
            needs.set(CHARA, milk=50, urine=50)
            activity.update_behavior(CHARA, duration=4)
            Second_effect.handle_milking_machine(CHARA, self.change)
            Second_effect.handle_urine_collector(CHARA, self.change)
            needs.set(CHARA, milk=100, urine=100)
            Second_effect.handle_b_orgasm_to_milk(CHARA, self.change)
            Second_effect.handle_u_orgasm_to_pee(CHARA, self.change)
            h_state.set(CHARA, extra_orgasm_count=2)
            Second_effect.handle_extra_orgasm(CHARA, self.change)
            expected = [
                text(MILKED, 20),
                text(COLLECTED, 20),
                text(MILK_KEPT, 60),
                text(URINE_KEPT, 52),
                text(EXTRA, 2),
            ]
        width = normal_config.config_normal.text_width
        style = draw.NormalDraw().style
        self.assertEqual(
            [
                (type(now).__name__, now.width, now.style, now.text)
                for (now,), _kw in self.drawn.call_args_list
            ],
            [("NormalDraw", width, style, t) for t in expected],
        )


class SecondEffectBoundaryTest(FastTestCase):
    """检查 Script/Settle/Second_effect.py 模块导入边界的测试类。"""

    def test_imports_ui_hooks(self) -> None:
        """验证 Script/Settle/Second_effect.py 导入 ui_hooks。"""
        path = os.path.join(ROOT, "Script", "Settle", "Second_effect.py")
        with open(path, encoding="utf-8") as source:
            names = imports_in(source.read(), Second_effect.__package__ or "")
        self.assertIn(ui_hooks.__name__, names)
