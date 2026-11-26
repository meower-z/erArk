"""
存档读档无界面与样式回调测试
============================
LoadUiFreeTest 在放行 Script.Settle 的无界面子进程中执行 save_handle.install_save。
该测试类验证读档不触碰其余受拦截模块，并核对进度提示刷出与口上颜色更新时的样式回调顺序。
LoadStyleTest 在本进程接入 ScriptedUiPort 并执行读档，验证新增的角色口上颜色定义会发往协议端口。
"""

import copy
import tempfile
from unittest import mock

from Script.Config import character_config, game_config
from Script.Core import io_init, save_handle
from Script.Kernel import core
from Script.Modules.domains import country
from Script.Modules.gameplay_resolution import working
from Script.Modules.save_load import index
from Script.Protocol import (
    RenderChunk,
    ScriptedUiPort,
    StyleDefOp,
    default_first_option,
)
from tests import legacy_save
from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import BLOCKED, ChildRun, run_ui_free

SLOT = "save_handle_ui_free"
""" LoadStyleTest 写入与读入旧格式测试存档时使用的存档位名称。 """
NAME = "测试干员"
""" LoadStyleTest 中用于核对口上颜色样式名的测试角色名称。 """
LOADS = """
import os
import tempfile
from unittest import mock

payload["error"] = None
try:
    from Script.Core import save_handle
    from Script.Modules.save_load import style_hooks
except ImportError as error:
    payload["error"] = repr(error)
if payload["error"] is None:
    from Script.Config import character_config, map_config
    from Script.Kernel import core
    from Script.Modules.domains import country
    from Script.Modules.gameplay_resolution import ui_hooks, working
    from Script.Modules.save_load import index, settings
    from tests import kernel_data, legacy_save
    from tests.world import start_time

    character_config.init_character_tem_data()
    map_config.init_map_data()
    kernel_data.reset_clock(start_time(), {})
    calls = []
    ui_hooks.on_notice(lambda text, **options: calls.append(text.strip()))
    ui_hooks.on_flush(lambda: calls.append("flush"))
    style_hooks.on_styles_changed(lambda: calls.append("styles"))
    templates = character_config.character_tem_list
    npc = min(cid for cid, tem in templates.items() if cid and tem.TextColor)
    old = legacy_save.old
    caches = {
        "plain": {},
        "old_ids": {"npc_tem_data": []},
        "replace": {"character_data": {891: old("Character")}},
        "color": {
            "character_data": {0: old("Character"), npc: old("Character", adv=npc)},
            "npc_tem_data": {npc: None},
        },
    }
    with (
        tempfile.TemporaryDirectory() as folder,
        mock.patch.object(index, "SAVE_DIR", folder),
        mock.patch.object(settings, "path", os.path.join(folder, "settings.json")),
        mock.patch.object(country, "fill", lambda: None),
    ):
        for name, attrs in caches.items():
            calls.clear()
            legacy_save.write_cache("child", old("Cache", **attrs))
            with working.based_on(core.state()):
                save_handle.install_save("child", 1)
            payload[name] = list(calls)
"""
""" 在无界面子进程中导入 save_handle 与 style_hooks，记录导入错误及四组旧存档读档的回调事件。 """
DETECT = "开始检测存档的数据结构是否需要跨版本更新"
""" 读档开始检测跨版本数据结构更新时的预期提示文本。 """
OLD_IDS = "检测到旧版存档，开始迁移角色ID系统..."
""" 读档触发旧存档角色 ID 系统迁移时的预期提示文本。 """
REPLACE = "检测到需要进行角色替换迁移..."
""" 读档触发角色替换迁移时的预期提示文本。 """
COLOR = "共有1个角色的口上颜色已更新"
""" 单个角色口上颜色更新完成后的预期提示文本。 """
MARKS = frozenset({"flush", "styles", DETECT, OLD_IDS, REPLACE, COLOR})
""" LoadUiFreeTest.marks 保留的刷出、样式变更与四条预期提示标记集合。 """


class LoadUiFreeTest(FastTestCase):
    """无界面子进程中的 save_handle.install_save 隔离与回调顺序测试。"""

    child: ChildRun
    """ setUpClass 执行 LOADS 得到的无界面子进程运行结果。 """

    @classmethod
    def setUpClass(cls) -> None:
        """
        调用父类类级准备并经 run_ui_free 执行 LOADS，将结果保存到 cls.child。
        子进程以 boot=True 启动，并采用 BLOCKED - {"Script.Settle"} 作为拦截集合。
        Return arguments:
        None -- 无返回值
        """
        super().setUpClass()
        cls.child = run_ui_free(
            LOADS, boot=True, blocked=BLOCKED - {"Script.Settle"}
        )

    def marks(self, case: str) -> list[str]:
        """
        从子进程结果中取出指定用例的回调记录，并按原顺序筛选属于 MARKS 的项。
        Keyword arguments:
        case -- str，子进程 payload 中的用例键名
        Return arguments:
        list[str] -- 该用例记录中属于 MARKS 的项列表，缺少该用例时返回空列表
        """
        calls = self.child.payload.get(case, [])
        assert isinstance(calls, list)
        return [call for call in calls if call in MARKS]

    def test_load_touches_no_ui_module(self) -> None:
        """
        验证无界面子进程未记录导入错误，且未尝试导入或加载受拦截模块。
        Return arguments:
        None -- 无返回值
        """
        self.assertIsNone(self.child.payload["error"])
        self.assertEqual((self.child.attempted, self.child.loaded), ([], []))

    def test_progress_notices_are_flushed(self) -> None:
        """
        验证 plain、old_ids 与 replace 三组用例在对应进度提示后紧跟刷出回调。
        Return arguments:
        None -- 无返回值
        """
        self.assertEqual(self.marks("plain"), [DETECT, "flush"])
        self.assertEqual(
            self.marks("old_ids"), [DETECT, "flush", OLD_IDS, "flush"]
        )
        self.assertEqual(
            self.marks("replace"), [DETECT, "flush", REPLACE, "flush"]
        )

    def test_text_color_update_changes_styles(self) -> None:
        """
        验证 color 用例在检测提示与刷出之后、颜色更新提示之前触发样式变更回调。
        Return arguments:
        None -- 无返回值
        """
        self.assertEqual(
            self.marks("color"), [DETECT, "flush", "styles", COLOR]
        )


class LoadStyleTest(FastTestCase):
    """已登记 Tk 样式回调时的读档口上颜色端口输出测试。"""

    def setUp(self) -> None:
        """
        准备临时存档目录并打桩 country.fill。
        通过 enterContext 隔离 config_font、config_font_data、io_init.style_def 与 io_init._port。
        创建默认选首项且文本输入返回 "1" 的 ScriptedUiPort 存入 self.port，并经 io_init.configure 接入。
        Return arguments:
        None -- 无返回值
        """
        super().setUp()
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(mock.patch.object(index, "SAVE_DIR", folder))
        self.enterContext(mock.patch.object(country, "fill", lambda: None))
        fonts = copy.deepcopy(game_config.config_font)
        self.enterContext(mock.patch.object(game_config, "config_font", fonts))
        self.enterContext(mock.patch.dict(game_config.config_font_data))
        self.enterContext(
            mock.patch.object(io_init, "style_def", io_init.style_def)
        )
        self.enterContext(mock.patch.object(io_init, "_port", io_init._port))
        self.port = ScriptedUiPort(default_first_option("1"))
        io_init.configure(self.port)

    def test_new_text_color_reaches_port(self) -> None:
        """
        选取编号最小且含非空 TextColor 的非零模板，将主角与该测试角色写入旧格式存档。
        在临时缓冲区执行 install_save 并调用 io_init.flush 刷出端口。
        断言协议端口收到的 StyleDefOp 中，以 NAME 为名的样式前景色等于该模板的 TextColor。
        Return arguments:
        None -- 无返回值
        """
        templates = character_config.character_tem_list
        npc = min(
            cid for cid, tem in templates.items() if cid and tem.TextColor
        )
        cache = legacy_save.old(
            "Cache",
            character_data={
                0: legacy_save.old("Character"),
                npc: legacy_save.old("Character", adv=npc, name=NAME),
            },
            npc_tem_data={npc: None},
        )
        legacy_save.write_cache(SLOT, cache)
        with working.based_on(core.state()):
            save_handle.install_save(SLOT, 1)
        io_init.flush()
        styles = {
            op.name: op.fg
            for event in self.port.events
            if isinstance(event, RenderChunk)
            for op in event.ops
            if isinstance(op, StyleDefOp)
        }
        self.assertEqual(styles.get(NAME), templates[npc].TextColor)
