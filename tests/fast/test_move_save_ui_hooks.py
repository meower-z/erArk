"""
角色移动与读档界面回调测试
==========================
- 寻路面板：验证主角寻路选定首段、抵达目标与遇锁时经 ui_hooks 切换面板。
- 开门与私密房间：验证开门提示与私密房间结算提示经 ui_hooks 发出并由 Tk 回调绘制。
- 读档提示：验证读档检测、地图更新与设置补全提示经 ui_hooks 发出并由 Tk 回调绘制。
- 导入边界：验证角色移动与读档模块源码不导入 Script.UI 下的模块。
"""

import ast
import re
from importlib.util import resolve_name
from pathlib import PurePosixPath
from unittest import mock

from Script.Config import normal_config
from Script.Core import constant, get_text, io_init, save_handle
from Script.Design import character_move, map_handle
from Script.Modules.domains import activity, country, flags, identity
from Script.Modules.domains import inventory, physical_exam, scene_state
from Script.Modules.gameplay_resolution import ui_hooks
from Script.Modules.save_load.legacy_pickle import LegacyObject
from Script.Modules.tk_ui import player_pick
from Script.UI.Moudle import draw, view
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT

CORRIDOR = ["宿舍", "1区", "外走廊"]
""" 1 区宿舍外走廊的场景路径，与 102 号宿舍相邻。 """
DORM = ["宿舍", "1区", "102"]
""" 1 区 102 号宿舍的场景路径，非玩家所属宿舍。 """
OFFICE = ["中枢", "博士办公室"]
""" 中枢博士办公室的场景路径，与外走廊相距多段路程。 """
GONE = ["中枢", "拆除的房间"]
""" 当前地图 constant.scene_data 中不存在的测试房间路径。 """
COPY_KEY = 301
""" 1 层宿舍复制钥匙的道具编号（301）。 """
MASTER_KEY = 152
""" 一次性宿舍万能钥匙的道具编号（152）。 """
SLOT = "move_save_ui_hooks"
""" 读档测试传入 save_handle.install_save 的模拟存档编号。 """
SOURCES = ("Script/Design/character_move.py", "Script/Core/save_handle.py")
""" 接受 Script.UI 导入边界检查的两个模块仓库相对路径元组。 """

type Drawn = tuple[str, float, str, str]
""" 一次绘制或直接输出的记录元组类型，依次为来源名、宽度、样式名与文本。 """
type Notice = tuple[str, bool, str | None, bool]
""" 一条提示的参数元组类型，依次为文本、是否等待确认、样式名与是否按文本宽度排版。 """

_ = get_text._


class HookCase(FastTestCase):
    """界面回调测试基类，记录提示、面板切换以及回调内外的绘制与直接输出。"""

    def setUp(self) -> None:
        """初始化无钥匙玩家与地图面板，接管提示、面板切换、全部绘制类与 era_print。"""
        super().setUp()
        self.world.chara(0, "博士", position=CORRIDOR)
        for item_id in (COPY_KEY, MASTER_KEY):
            kernel_data.put(inventory.set_item, 0, item_id, 0)
        self.notices: list[Notice] = []
        self.drawn: list[Drawn] = []
        self.direct: list[Drawn] = []
        self.panels: list[int] = []
        self.inside = False
        self.hooks = list(ui_hooks._notices)
        self.enterContext(
            mock.patch.object(ui_hooks, "_notices", [self.forward])
        )
        self.enterContext(
            mock.patch.object(
                ui_hooks,
                "_panel_switches",
                [*ui_hooks._panel_switches, self.panels.append],
            )
        )
        self.enterContext(
            mock.patch.object(view, "now_panel_id", constant.Panel.SEE_MAP)
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

    def forward(
        self, text: str, *, wait: bool, style: str | None, use_text_width: bool
    ) -> None:
        """记录提示参数，再于回调标记开启期间依次调用测试前已登记的提示回调。"""
        self.notices.append((text, wait, style, use_text_width))
        self.inside = True
        try:
            for fn in self.hooks:
                fn(
                    text,
                    wait=wait,
                    style=style,
                    use_text_width=use_text_width,
                )
        finally:
            self.inside = False

    def keep(self, now: object) -> None:
        """按是否处于提示回调内，将绘制对象的类名、宽度、样式与文本记入对应列表。"""
        drawn = (
            type(now).__name__,
            getattr(now, "width", 0),
            getattr(now, "style", ""),
            getattr(now, "text", ""),
        )
        (self.drawn if self.inside else self.direct).append(drawn)

    def printed(
        self,
        string: str,
        style: str | tuple[str, ...] = "standard",
        tooltip: str = "",
    ) -> None:
        """在提示回调外直接调用 io_init.era_print 时将样式与文本记入直接输出列表。"""
        if not self.inside:
            self.direct.append(("era_print", 0, str(style), string))

    def assert_notices(
        self, *expected: Notice, direct: tuple[Drawn, ...] = ()
    ) -> None:
        """
        依次核对 ui_hooks 记录的提示、回调外直接绘制与 Tk 回调绘出的绘制对象。
        Keyword arguments:
        expected -- Notice，按顺序预期的提示参数元组
        direct -- tuple[Drawn, ...]，按顺序预期的提示回调之外的直接绘制记录
        Return arguments:
        None -- 无返回值
        """
        width = normal_config.config_normal.text_width
        self.assertEqual(self.notices, list(expected))
        self.assertEqual(self.direct, list(direct))
        self.assertEqual(
            self.drawn,
            [
                (
                    "WaitDraw" if wait else "NormalDraw",
                    width if use_text_width else 0,
                    style or draw.NormalDraw.style,
                    text,
                )
                for text, wait, style, use_text_width in expected
            ],
        )

    def assert_panel(self, panel_id: int) -> None:
        """核对面板切换记录为单元素列表 [panel_id]，且 view.now_panel_id 等于 panel_id。"""
        self.assertEqual(self.panels, [panel_id])
        self.assertEqual(view.now_panel_id, panel_id)


class RoutePanelTest(HookCase):
    """主角寻路触发面板切换的测试。"""

    def test_first_leg_is_chosen_from_scene_panel(self) -> None:
        """验证寻路可走第一段时抛出 player_pick.Chosen，并经回调切至场景面板。"""
        with self.assertRaises(player_pick.Chosen):
            kernel_data.written(character_move.own_charcter_move, list(OFFICE))
        self.assert_panel(constant.Panel.IN_SCENE)

    def test_arrived_route_returns_to_scene_panel(self) -> None:
        """验证玩家已在目标位置时切至场景面板，并将已设定的交互目标清零。"""
        self.world.chara(1, "干员", position=CORRIDOR)
        kernel_data.put(activity.set_target, 0, 1)
        self.assertEqual(activity.target(0), 1)
        kernel_data.written(character_move.own_charcter_move, list(CORRIDOR))
        self.assert_panel(constant.Panel.IN_SCENE)
        self.assertEqual(activity.target(0), 0)

    def test_locked_door_keeps_map_panel(self) -> None:
        """验证目标宿舍上锁且玩家无钥匙时切至地图面板。"""
        lock(DORM)
        kernel_data.written(character_move.own_charcter_move, list(DORM))
        self.assert_panel(constant.Panel.SEE_MAP)


class DoorNoticeTest(HookCase):
    """玩家用钥匙开宿舍门发出开门提示的测试。"""

    def setUp(self) -> None:
        """执行基类初始化并将 102 号宿舍的门锁标记设为 1。"""
        super().setUp()
        lock(DORM)

    def walk(self) -> str:
        """
        让玩家从外走廊走向 102 号宿舍并返回进门判定结果。
        Return arguments:
        str -- character_move.character_move 返回的进门判定结果
        """
        return kernel_data.written(character_move.character_move, 0, DORM)[0]

    def test_copy_key_opens_door(self) -> None:
        """验证持 1 层复制钥匙时返回 open、除直接门锁提醒外发出等待型开门提示并解锁房门。"""
        kernel_data.put(inventory.set_item, 0, COPY_KEY, 1)
        self.assertEqual(self.walk(), "open")
        text = _("\n  ●你拿出了该楼层的复制钥匙，悄悄打开了门\n\n")
        self.assert_notices((text, True, None, False), direct=lock_warning())
        self.assertEqual(scene_state.close_flag(path_str(DORM)), 0)

    def test_master_key_is_spent(self) -> None:
        """验证持一次性万能钥匙时返回 open、除直接门锁提醒外发出等待型开门提示、消耗钥匙并解锁。"""
        kernel_data.put(inventory.set_item, 0, MASTER_KEY, 1)
        self.assertEqual(self.walk(), "open")
        text = _("\n  ●你拿出了一次性万能钥匙，悄悄打开了门\n\n")
        self.assert_notices((text, True, None, False), direct=lock_warning())
        self.assertEqual(inventory.items(0)[MASTER_KEY], 0)
        self.assertEqual(scene_state.close_flag(path_str(DORM)), 0)

    def test_no_key_leaves_door_locked(self) -> None:
        """验证无钥匙时返回 door_lock、仅产生直接门锁提醒、不发回调提示且门锁标记为 1。"""
        self.assertEqual(self.walk(), "door_lock")
        self.assert_notices(direct=lock_warning())
        self.assertEqual(scene_state.close_flag(path_str(DORM)), 1)


class PrivateMoveNoticeTest(HookCase):
    """私密房间前移动结算发出提示的测试。"""

    def test_stop_follow_notice(self) -> None:
        """验证 stop_follow 结算清除角色跟随标记，并发出默认样式的非等待型取消跟随提示。"""
        self.world.chara(1, "干员", position=CORRIDOR)
        kernel_data.put(flags.set, 1, is_follow=1)
        kernel_data.written(
            character_move.settle_private_move, 1, "stop_follow"
        )
        text = _("因为等待时间过长，所以{0}不再继续跟随\n").format(
            identity.of(1).name
        )
        self.assert_notices((text, False, None, False))
        self.assertEqual(flags.get(1, "is_follow"), 0)

    def test_unknown_outcome_is_silent(self) -> None:
        """验证传入空结果字符串时 settle_private_move 不发回调提示且无直接绘制。"""
        self.world.chara(1, "干员", position=CORRIDOR)
        kernel_data.written(character_move.settle_private_move, 1, "")
        self.assert_notices()


class LoadNoticeTest(HookCase):
    """读档检测、地图更新与设置补全提示的测试。"""

    def test_install_save_reports_start_and_finish(self) -> None:
        """验证 install_save 依次发出开始检测提示与检测完毕提示并按默认样式零宽绘制。"""
        saved = {"rhodes_island": LegacyObject()}
        with (
            mock.patch.object(save_handle, "load_save", lambda _id: saved),
            mock.patch.object(country, "fill", lambda: None),
        ):
            kernel_data.written(save_handle.install_save, SLOT, 13)
        start = _("\n开始检测存档的数据结构是否需要跨版本更新\n")
        head, tail = _("\n检测完毕，共有{0}条数据完成了更新\n").split("{0}")
        finish = self.notices[-1][0]
        self.assertRegex(finish, f"^{re.escape(head)}[0-9]+{re.escape(tail)}$")
        self.assertEqual(self.notices[0], (start, False, None, False))
        self.assertEqual(self.notices[-1], (finish, False, None, False))
        self.assertEqual(self.drawn[0], ("NormalDraw", 0, "standard", start))
        self.assertEqual(self.drawn[-1], ("NormalDraw", 0, "standard", finish))

    def test_removed_scene_reports_map_update(self) -> None:
        """验证存档场景表与当前地图不同时 update_map 计入差异并发出默认样式地图更新提示。"""
        loaded = {
            "scene_data": {path_str(GONE): object()},
            "character_data": {0: None},
        }
        count = kernel_data.written(save_handle.update_map, loaded)
        self.assertEqual(count, len(constant.scene_data) + 1)
        self.assert_notices((_("\n游戏地图已更新\n"), False, None, False))

    def test_character_in_removed_room_moves_back(self) -> None:
        """验证角色位于地图外房间时 update_map 将其移回区块入口并发出金色角色移回提示。"""
        self.world.chara(1, "干员", position=CORRIDOR)
        kernel_data.put(activity.set_position, 1, list(GONE))
        loaded = {"character_data": {0: None, 1: None}}
        self.assertEqual(kernel_data.written(save_handle.update_map, loaded), 1)
        text = _(
            "\n有{0}名角色所在的房间已不存在（地图改建），已将她们移动到所属区块的入口\n"
        ).format(1)
        self.assert_notices((text, False, "gold_enrod", False))
        self.assertEqual(activity.position(1), [GONE[0], "0"])

    def test_missing_settings_are_reported(self) -> None:
        """验证缺失口上选择与体检设置时发出两条金色设置补全提示，补全后再次调用静默。"""
        kernel_data.put(physical_exam.set_settings, {})
        versions = normal_config.system_setting.character_text_version
        with mock.patch.dict(versions, clear=True):
            kernel_data.written(save_handle.update_settings, {})
            kernel_data.written(save_handle.update_settings, {})
        self.assert_notices(
            (
                _("\n角色口上选择设置已更新，如有需要请手动修改\n"),
                False,
                "gold_enrod",
                False,
            ),
            (
                _("\n体检设置已更新，如有需要请手动修改\n"),
                False,
                "gold_enrod",
                False,
            ),
        )


class ImportBoundaryTest(FastTestCase):
    """角色移动与读档模块的 Script.UI 导入边界语法树测试。"""

    def test_sources_import_no_ui(self) -> None:
        """验证 SOURCES 中两个模块经 ui_imports 检查均不含 Script.UI 下的导入。"""
        for path in SOURCES:
            with self.subTest(path=path):
                source = (ROOT / path).read_bytes()
                self.assertEqual(ui_imports(source, path), [])

    def test_checker_reads_every_imported_name(self) -> None:
        """验证 ui_imports 检出同语句后续与相对导入的 Script.UI，并放行前缀相近模块。"""
        source = (
            "from Script import Frontend, UI\n"
            "from ..UI.Moudle import draw\n"
            "import Script.UIX\n"
        )
        self.assertEqual(
            ui_imports(source, "Script/Design/sample.py"),
            [(1, "Script.UI"), (2, "Script.UI.Moudle.draw")],
        )


def ui_imports(source: str | bytes, path: str) -> list[tuple[int, str]]:
    """
    解析源码语法树，检查每条导入语句的全部导入名并找出 Script.UI 及其子模块。
    Keyword arguments:
    source -- str | bytes，待检查的 Python 源码
    path -- str，文件的仓库相对路径，用于解析相对导入
    Return arguments:
    list[tuple[int, str]] -- 排序后的（行号，解析后导入全名）列表
    """
    package = ".".join(PurePosixPath(path).parent.parts)
    found: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = resolve_name("." * node.level + (node.module or ""), package)
            names = [f"{base}.{alias.name}" for alias in node.names]
        else:
            continue
        found.extend(
            (node.lineno, name)
            for name in names
            if name == "Script.UI" or name.startswith("Script.UI.")
        )
    return sorted(found)


def lock_warning() -> tuple[Drawn, ...]:
    """
    构造玩家走向锁着的 102 号宿舍门前时，进门判定在回调外直接绘制的门锁提醒记录。
    Return arguments:
    tuple[Drawn, ...] -- 分隔线的 LineDraw 记录与等待型 WaitDraw 门锁提醒记录
    """
    width = normal_config.config_normal.text_width
    name = constant.scene_data[path_str(DORM)].scene_name
    text = _(
        "\n  ●目标移动房间——{0}，当前门是锁着的，需要钥匙或其他方法进入\n"
    ).format(name)
    return (
        ("LineDraw", width, "standard", "-"),
        ("WaitDraw", width, "standard", text),
    )


def path_str(path: list[str]) -> str:
    """
    将场景路径列表转为场景表的路径键。
    Keyword arguments:
    path -- list[str]，场景路径列表
    Return arguments:
    str -- 场景表中的场景路径键
    """
    return map_handle.get_map_system_path_str_for_list(path)


def lock(path: list[str]) -> None:
    """
    将指定房间的门锁标记设为 1。
    Keyword arguments:
    path -- list[str]，房间的场景路径列表
    Return arguments:
    None -- 无返回值
    """
    kernel_data.put(scene_state.set_close_flag, path_str(path), 1)
