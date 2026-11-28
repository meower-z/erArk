"""
公务事件结果提示测试
====================
本模块测试 instruct_hooks.show_official_result 经 ui_hooks.emit_notice 输出公务事件结算结果提示。
OfficialResultNoticeTest 验证无界面子进程中的提示发射、界面模块隔离，以及载入 Tk 回调后的 WaitDraw 绘制行为。
"""

from unittest import mock

from Script.Config import game_config, normal_config
from Script.Modules.gameplay_resolution import instruct_hooks
from Script.UI.Moudle import draw
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import run_ui_free

UID = "测试公务丙"
""" 测试用公务事件的 uid。 """
EVENTS = {
    UID: {
        "cid": UID,
        "department": 15,
        "text": "正文",
        "option_1": "选项一",
        "option_1_tip": "{Name}向{TargetName}低头",
        "option_2": "选项二",
    }
}
""" 测试用公务事件配置表，含带结果提示的选项一与无结果提示的选项二。 """
UI_FREE_RUN = f"""
from Script.Config import game_config
from Script.Modules.gameplay_resolution import instruct_hooks, ui_hooks
game_config.config_official_event = {EVENTS!r}
notices = []
ui_hooks.on_notice(lambda text, **options: notices.append([text, options]))
for args in (({UID!r}, 0, 0, 1), ({UID!r}, 0, 0, 2), ({UID!r}, 0, 0, 9)):
    instruct_hooks.show_official_result(*args)
instruct_hooks.show_official_result("缺失", 0, 0, 1)
payload["notices"] = notices
"""
""" 无界面子进程脚本，登记提示回调后按多个选项序号与缺失 uid 调用 instruct_hooks.show_official_result，
    并记录发出的提示。 """


class OfficialResultNoticeTest(FastTestCase):
    """公务事件结算结果经 ui_hooks.emit_notice 发送与经 Tk 回调绘制的测试。"""

    def test_one_wait_notice_without_ui(self) -> None:
        """
        在无界面子进程中登记提示回调，以选项一、选项二、不存在的选项序号与缺失 uid 调用 show_official_result。
        验证仅对带结果提示的选项一发出一条等待提示，参数为 wait=True、style=None 与 use_text_width=True。
        验证子进程中不存在角色时文本中的口上代码原样保留。
        验证子进程未尝试导入也未载入受拦截模块。
        """
        child = run_ui_free(UI_FREE_RUN)
        self.assertEqual(
            child.payload["notices"],
            [
                [
                    "\n  你选择了「选项一」\n  结果：{Name}向{TargetName}低头\n",
                    {"wait": True, "style": None, "use_text_width": True},
                ]
            ],
        )
        self.assertEqual(child.attempted, [])
        self.assertEqual(child.loaded, [])

    def test_tk_draws_one_wait_text(self) -> None:
        """
        创建主体角色干员与互动对象博士，并拦截 NormalDraw.draw 与 WaitDraw.draw。
        以选项一、选项二与不存在的选项序号调用 show_official_result。
        验证仅对选项一绘制一条 WaitDraw。
        验证该 WaitDraw 的文本包含替换后的角色名与互动对象名。
        验证该 WaitDraw 采用配置的文本宽度与默认样式。
        """
        self.world.chara(0, "博士")
        self.world.chara(1, "干员")
        self.enterContext(
            mock.patch.object(game_config, "config_official_event", EVENTS)
        )
        drawn: list[tuple[str, str, float, str]] = []
        for cls in (draw.NormalDraw, draw.WaitDraw):
            self.enterContext(
                mock.patch.object(
                    cls,
                    "draw",
                    autospec=True,
                    side_effect=lambda one: drawn.append(
                        (type(one).__name__, one.text, one.width, one.style)
                    ),
                )
            )
        for index in (1, 2, 9):
            instruct_hooks.show_official_result(UID, 1, 0, index)
        self.assertEqual(
            drawn,
            [
                (
                    "WaitDraw",
                    "\n  你选择了「选项一」\n  结果：干员向博士低头\n",
                    normal_config.config_normal.text_width,
                    draw.NormalDraw.style,
                )
            ],
        )
