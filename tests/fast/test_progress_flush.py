"""
耗时同步工作前刷出进度提示测试
==============================
本模块验证六处耗时同步工作在进入阻塞调用时，对应的进度提示文本已通过协议端口投递为 RenderChunk。
测试覆盖口上文件刷新、五子棋对手思考、文本生成模型调用、过24点跨日结算、入睡结算与读档迁移六个入口。
"""

import sys
import tempfile
from collections.abc import Callable
from types import ModuleType
from unittest import mock

from Script.Config import normal_config
from Script.Core import input_cache, io_init, old_chara_to_new, save_handle
from Script.Design import handle_chat_ai
from Script.Protocol import (
    RenderChunk,
    ScriptedUiPort,
    TextOp,
    default_first_option,
)
from Script.Kernel import core
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import index
from Script.Modules.tk_ui import orders
from Script.Settle import past_day_settle, sleep_settle
from Script.System.Education_System import sex_class_handle
from Script.UI.Moudle import draw
from Script.UI.Panel import chat_ai_panel, debug_panel, play_gomoku_panel
from tests import legacy_save
from tests.chara_activity import aim
from tests.fast.base import FastTestCase

WIDTH = 100
"""传入测试面板的宽度"""
SLOT = "progress_flush"
"""读档迁移用例在临时存档目录中写入与读取的存档槽位标识"""
NEW_DAY_IMPORTS = (
    "Script.System.Cooking_System.cooking",
    "Script.Modules.gameplay_resolution.assistant_service",
    "Script.Modules.gameplay_resolution.diplomacy_service",
    "Script.Modules.gameplay_resolution.navigation_service",
    "Script.System.Pregnancy_System.pregnancy_handle",
    "Script.System.Pregnancy_System.egg_handle",
    "Script.System.Education_System.schedule_template_handle",
    "Script.System.Education_System.semester_handle",
    "Script.System.Education_System.growth_event_handle",
    "Script.System.Official_Event_System.official_event_handle",
)
"""
update_new_day 函数体内延迟导入的十个模块名（不含测试已导入的 sex_class_handle），
供跨日结算用例在 sys.modules 中临时占位以隔离导入期副作用。
"""


def emit_text(self: draw.NormalDraw) -> None:
    """
    将 NormalDraw 的文本与样式通过 io_init.era_print 发往协议端口，用于替代测试环境中被屏蔽的 NormalDraw.draw。
    Keyword arguments:
    self (draw.NormalDraw) -- 待输出的普通文本绘制对象
    Return arguments:
    None -- 无返回值
    """
    io_init.era_print(self.text, self.style)


class Reached(BaseException):
    """探针命中目标阻塞调用时抛出的中断异常。该类继承自 BaseException，可绕过游戏代码中的 except Exception 捕获。"""


class ProgressShownBeforeWork(FastTestCase):
    """验证六处耗时同步工作在进入阻塞调用前已向协议端口刷出进度提示文本。"""

    def setUp(self) -> None:
        """
        准备测试角色与协议端口环境。该方法创建角色 0「博士」与角色 1「干员」，将干员设为博士的交互对象。
        该方法通过 enterContext 临时将待写输入队列 orders._unsettled 与输入历史 input_cache.input_cache 替换为空
        列表，并将 NormalDraw.draw 替换为 emit_text，在用例结束后还原它们与 io_init._port。
        该方法最后将 io_init 接入默认选首项且文本输入返回「1」的 ScriptedUiPort。
        Keyword arguments:
        无
        Return arguments:
        None -- 无返回值
        """
        super().setUp()
        self.world.chara(0, "博士")
        self.world.chara(1, "干员")
        aim(0, 1)
        self.enterContext(mock.patch.object(io_init, "_port", io_init._port))
        self.enterContext(mock.patch.object(orders, "_unsettled", []))
        self.enterContext(mock.patch.object(input_cache, "input_cache", []))
        self.enterContext(mock.patch.object(draw.NormalDraw, "draw", emit_text))
        self.port = ScriptedUiPort(default_first_option("1"))
        io_init.configure(self.port)

    def shown_at(
        self, owner: object, name: str, start: Callable[[], object]
    ) -> str:
        """
        在目标阻塞调用触发时记录协议端口已收到的文本并中断执行。该方法将 owner 的 name 属性替换为探针，
        调用 start 并断言探针抛出 Reached。
        Keyword arguments:
        owner (object) -- 持有待替换目标属性的对象或模块
        name (str) -- 待替换为探针的属性名
        start (Callable[[], object]) -- 触发目标流程的无参可调用对象
        Return arguments:
        str -- 探针命中时，self.port.events 中各 RenderChunk 里全部 TextOp 的文本拼接结果
        """
        seen: list[str] = []

        def probe(*_args: object, **_kwargs: object) -> None:
            seen.append(
                "".join(
                    op.text
                    for event in self.port.events
                    if isinstance(event, RenderChunk)
                    for op in event.ops
                    if isinstance(op, TextOp)
                )
            )
            raise Reached

        with mock.patch.object(owner, name, probe), self.assertRaises(Reached):
            start()
        return seen[0]

    def test_talk_refresh(self) -> None:
        """刷新口上文件时，在调用 build_chara_talk 前已刷出「开始刷新口上文件」提示"""
        panel = debug_panel.TALK_QUICK_TEST(WIDTH)
        shown = self.shown_at(
            debug_panel, "build_chara_talk", panel.refresh_talk_file
        )
        self.assertIn("开始刷新口上文件", shown)

    def test_gomoku_ai_turn(self) -> None:
        """五子棋玩家落子后，在调用 ai_move 前已刷出「思考中」提示"""
        panel = play_gomoku_panel.GomokuPanel(WIDTH)
        panel.select_row(7)
        panel.select_col(7)
        shown = self.shown_at(panel, "ai_move", panel.place_piece)
        self.assertIn("思考中", shown)

    def test_text_ai_call(self) -> None:
        """调用文本生成模型时，在执行 text_ai 前已刷出「正在调用test-model」提示"""
        ai = normal_config.ai_setting
        self.enterContext(
            mock.patch.dict(ai.ai_chat_setting, {1: 1, 5: "test-model", 8: 0})
        )
        self.enterContext(mock.patch.dict(ai.ai_chat_api_key, {"KEY": "k"}))
        self.enterContext(
            mock.patch.object(
                handle_chat_ai, "get_key_type", return_value="KEY"
            )
        )
        shown = self.shown_at(
            handle_chat_ai,
            "text_ai",
            lambda: handle_chat_ai.judge_use_text_ai(
                0,
                "",
                "",
                chat_ai_panel.OUTPUT,
                settle=chat_ai_panel.settle_direct_instruct,
            ),
        )
        self.assertIn("正在调用test-model", shown)

    def test_new_day_settle(self) -> None:
        """
        过24点跨日结算时，在调用 clean_expired_temp_class 前已刷出「已过24点，开始结算各种数据」提示。
        用例在 sys.modules 中为 NEW_DAY_IMPORTS 里尚未加载的模块临时放入空 ModuleType 替身，
        避免 update_new_day 内部导入触发读档修补注册等副作用。
        """
        stubs = {
            name: ModuleType(name)
            for name in NEW_DAY_IMPORTS
            if name not in sys.modules
        }
        self.enterContext(mock.patch.dict(sys.modules, stubs))
        shown = self.shown_at(
            sex_class_handle,
            "clean_expired_temp_class",
            past_day_settle.update_new_day,
        )
        self.assertIn("已过24点，开始结算各种数据", shown)

    def test_sleep_settle(self) -> None:
        """博士入睡结算时，在调用 settle_character_juel 前已刷出「博士入睡，开始结算各种数据」提示"""
        shown = self.shown_at(
            sleep_settle, "settle_character_juel", sleep_settle.update_sleep
        )
        self.assertIn("博士入睡，开始结算各种数据", shown)

    def test_save_migration(self) -> None:
        """
        验证读档三项子用例在进入目标调用前均已刷出对应进度提示。无迁移子用例在 update_tem_character 前检查跨版本检测
        提示。角色ID迁移与角色替换迁移子用例分别在 migrate_old_save_data 与 migrate_character_replacement 前检查检测
        提示与各自迁移提示。用例将 draw.LeftDraw.draw 替换为 emit_text，在临时目录经 legacy_save.write_cache 写出槽
        位缓存文件，用 working.based_on 隔离写入，并在每项子用例前清空 self.port.events。
        """
        self.enterContext(mock.patch.object(draw.LeftDraw, "draw", emit_text))
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))
        self.enterContext(working.based_on(core.state()))
        detecting = "开始检测存档的数据结构是否需要跨版本更新"
        cases = (
            ({}, "update_tem_character", (detecting,)),
            (
                {"npc_tem_data": []},
                "migrate_old_save_data",
                (detecting, "检测到旧版存档，开始迁移角色ID系统"),
            ),
            (
                {"character_data": {891: legacy_save.old("Character")}},
                "migrate_character_replacement",
                (detecting, "检测到需要进行角色替换迁移"),
            ),
        )
        for attrs, name, notices in cases:
            with self.subTest(name):
                self.port.events.clear()
                legacy_save.write_cache(SLOT, legacy_save.old("Cache", **attrs))
                shown = self.shown_at(
                    old_chara_to_new,
                    name,
                    lambda: save_handle.install_save(SLOT, 1),
                )
                for notice in notices:
                    self.assertIn(notice, shown)
