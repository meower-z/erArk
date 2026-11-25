"""
地图查看服务测试
================
覆盖地图格子分类、居中缩进与缺省最大行宽回退、设施提示候选、地图路径校正与上下级切换、
跨区块入口判定、场景名列表、收藏地点读写、地图面板与收藏面板按钮绘制，
以及在拦截界面、结算与 Tk 模块的独立子进程中运行服务。
"""

import json
import os
import subprocess
import sys
from unittest import mock

from Script.Config import game_config
from Script.Core import constant, flow_handle
from Script.Design import map_handle
from Script.Modules.domains import bookmarks, scene_state
from Script.Modules.gameplay_resolution import world_view_service as svc
from Script.UI.Moudle import draw, view
from Script.UI.Panel import see_map_panel
from tests import kernel_data
from tests.fast.base import FastTestCase
from tests.fast.test_backend_ui_boundary_guard import ROOT, banned_imports

SERVICE_PATH = "Script/Modules/gameplay_resolution/world_view_service.py"
""" 地图查看服务模块的仓库相对路径。 """
DORM = ["宿舍", "1区"]
""" 测试用宿舍 1 区地图路径。 """
START = ["宿舍", "1区", "101"]
""" 测试用玩家起始宿舍 101 场景路径。 """
LOCKED = ["宿舍", "1区", "102"]
""" 测试用锁门宿舍 102 场景路径。 """
BUSY = ["宿舍", "1区", "103"]
""" 测试用含在编干员的宿舍 103 场景路径。 """
EMPTY = ["宿舍", "1区", "104"]
""" 测试用空闲宿舍 104 场景路径。 """
BLOCK = ["中枢", "0"]
""" 测试用另一区块入口场景中枢 0 路径。 """


def key(path: list[str]) -> str:
    """
    将场景路径列表转为地图系统路径字符串。
    Keyword arguments:
    path -- list[str]，地图或场景路径列表
    Return arguments:
    str -- 系统路径字符串
    """
    return map_handle.get_map_system_path_str_for_list(path)


def cell(view_data: svc.MapView, text: str) -> svc.MapCell:
    """
    按展示文本查找地图视图中唯一的格子对象。
    Keyword arguments:
    view_data -- svc.MapView，地图查看数据
    text -- str，目标格子文本
    Return arguments:
    svc.MapCell -- 匹配的唯一格子对象
    """
    found = [c for row in view_data.rows for c in row if c.text == text]
    assert len(found) == 1, (text, len(found))
    return found[0]


class WorldViewCase(FastTestCase):
    """地图查看服务测试基类，预置位于宿舍 1 区 101 的博士、位于 103 的在编干员与锁门的 102。"""

    def setUp(self) -> None:
        """初始化测试世界，创建博士与一名在编干员并锁定宿舍 102。"""
        super().setUp()
        self.world.chara(0, "博士", position=START)
        self.world.chara(1, "干员甲", position=BUSY)
        kernel_data.put(scene_state.set_close_flag, key(LOCKED), 1)


class MapViewTest(WorldViewCase):
    """验证地图格子分类、居中缩进、设施提示与上下级切换标记。"""

    def test_cells_by_kind(self) -> None:
        """验证玩家所在为金色、锁门为灰色、有干员为绿色、空房间为普通样式、墙体为纯文本。"""
        data = svc.map_view(DORM, 129)
        here = cell(data, "101")
        self.assertEqual(
            (here.kind, here.style), (svc.CellKind.HERE, "gold_enrod")
        )
        locked = cell(data, "102")
        self.assertEqual(
            (locked.kind, locked.style), (svc.CellKind.CLOSED, "deep_gray")
        )
        self.assertEqual(locked.scene_path, LOCKED)
        busy = cell(data, "103")
        self.assertEqual(
            (busy.kind, busy.style, busy.occupied, busy.scene_path),
            (svc.CellKind.OPEN, "green", True, BUSY),
        )
        empty = cell(data, "104")
        self.assertEqual(
            (empty.kind, empty.style, empty.occupied),
            (svc.CellKind.OPEN, "standard", False),
        )
        wall = data.rows[0][0]
        self.assertEqual((wall.kind, wall.scene_path), (svc.CellKind.TEXT, []))
        self.assertTrue(wall.text.startswith("╔"))

    def test_indent_centres_widest_line(self) -> None:
        """验证缩进为宽度差的一半向零取整，以及缺少 max_width 属性时按各行最大宽度回退。"""
        map_draw = constant.map_data[key(DORM)].map_draw
        widest = max(line.width for line in map_draw.draw_text)
        self.assertEqual(svc.map_view(DORM, widest + 20).indent, 10)
        self.assertEqual(svc.map_view(DORM, widest - 9).indent, -4)
        saved = map_draw.max_width
        del map_draw.max_width
        try:
            self.assertEqual(svc.map_view(DORM, widest + 30).indent, 15)
        finally:
            map_draw.max_width = saved

    def test_tips_of_the_facility_named_like_the_map(self) -> None:
        """验证地图名匹配设施名时返回对应设施的全部提示，无匹配时返回空列表。"""
        data = svc.map_view(["中枢"], 129)
        facility_id = next(
            cid
            for cid, facility in game_config.config_facility.items()
            if facility.name == data.name
        )
        expected = [
            game_config.config_tip_data[tip_id].info
            for tip_id in game_config.config_tip_data_by_facility[facility_id]
        ]
        self.assertGreater(len(expected), 1)
        self.assertEqual(data.tips, expected)
        self.assertEqual(svc.map_view(DORM, 129).tips, [])

    def test_up_and_down_buttons(self) -> None:
        """验证不同层级地图的上下级切换标记，以及场景数与场景条目数一致。"""
        data = svc.map_view(DORM, 129)
        self.assertEqual((data.can_go_up, data.can_go_down), (True, False))
        self.assertEqual(data.scene_count, len(svc.scene_entries(DORM)))
        upper = svc.map_view(["宿舍"], 129)
        self.assertEqual((upper.can_go_up, upper.can_go_down), (True, True))
        root = svc.map_view([], 129)
        self.assertEqual((root.can_go_up, root.can_go_down), (False, True))


class MapPathTest(WorldViewCase):
    """验证地图路径校正、上下级路径计算与跨区块入口判定。"""

    def test_settle_view(self) -> None:
        """验证去掉多段路径末尾入口段 0，以及玩家移动后非空路径跟随玩家所在地图。"""
        self.assertEqual(svc.settle_view([*DORM, "0"], START), DORM)
        self.assertEqual(svc.settle_view(["0"], START), ["0"])
        self.assertEqual(svc.settle_view(["中枢"], START), ["中枢"])
        self.assertEqual(svc.settle_view(["中枢"], LOCKED), DORM)
        self.assertEqual(svc.settle_view([], LOCKED), [])

    def test_parent_and_child(self) -> None:
        """验证上级路径去掉末段，下级路径沿玩家所在方向追加一层。"""
        self.assertEqual(svc.parent_map(START), DORM)
        self.assertEqual(svc.parent_map(DORM), ["宿舍"])
        self.assertEqual(svc.child_map([]), ["宿舍"])
        self.assertEqual(svc.child_map(["宿舍"]), DORM)

    def test_opens_map_only_for_another_block_entrance(self) -> None:
        """验证仅当目标位于另一区块且末段为 0 时保持地图面板开启。"""
        self.assertTrue(svc.opens_map(BLOCK))
        self.assertFalse(svc.opens_map([*DORM, "0"]))
        self.assertFalse(svc.opens_map(["中枢", "博士房间"]))
        self.assertFalse(svc.opens_map(EMPTY))


class SceneListTest(WorldViewCase):
    """验证地图场景名列表查询。"""

    def test_scene_entries(self) -> None:
        """验证场景条目按 path_edge 顺序返回，正确标记玩家所在并携带真实场景路径。"""
        entries = svc.scene_entries(DORM)
        path_edge = constant.map_data[key(DORM)].path_edge
        self.assertEqual([e.scene_id for e in entries], list(path_edge))
        here = [e for e in entries if e.here]
        self.assertEqual(
            [(e.scene_id, e.scene_path) for e in here], [("101", START)]
        )
        locked = next(e for e in entries if e.scene_id == "102")
        self.assertEqual(
            locked.name, constant.scene_data[key(LOCKED)].scene_name
        )
        self.assertEqual(locked.scene_path, LOCKED)


class BookmarkTest(WorldViewCase):
    """验证收藏地点列表查询与收藏开关。"""

    def test_entries_and_toggle(self) -> None:
        """验证收藏列表顺序与当前位置标记，以及取消收藏和加入收藏的读写结果。"""
        kernel_data.put(bookmarks.add, BLOCK)
        kernel_data.put(bookmarks.add, START)
        entries = svc.bookmark_entries()
        self.assertEqual(
            [(e.scene_path, e.label, e.here) for e in entries],
            [
                (BLOCK, os.sep.join(BLOCK), False),
                (START, os.sep.join(START), True),
            ],
        )
        self.assertTrue(svc.here_bookmarked())
        kernel_data.written(svc.bookmark_here, False)
        self.assertEqual(bookmarks.places(), [BLOCK])
        self.assertFalse(svc.here_bookmarked())
        kernel_data.written(svc.bookmark_here, True)
        self.assertEqual(bookmarks.places(), [BLOCK, START])


class PanelTest(WorldViewCase):
    """验证地图主面板与收藏面板的按钮绘制和交互回调。"""

    def record(self) -> list:
        """
        将五种基础绘制类的 draw 方法替换为记录器。
        Return arguments:
        list -- 由 (类名, 绘制对象) 组成的绘制记录列表
        """
        drawn: list = []
        for name in (
            "Button",
            "CenterButton",
            "LeftButton",
            "LeftDraw",
            "NormalDraw",
        ):
            cls = getattr(draw, name)
            patcher = mock.patch.object(
                cls, "draw", lambda obj, _name=name: drawn.append((_name, obj))
            )
            patcher.start()
            self.addCleanup(patcher.stop)
        return drawn

    def test_map_buttons_and_bottom_row(self) -> None:
        """验证地图主面板按格子类别绘制按钮与金色文本，并按序绘制底部按钮及响应返回。"""
        drawn = self.record()
        offered: list = []

        def back(return_list: list) -> str:
            if offered:
                raise AssertionError("返回 did not close the panel")
            offered.extend(return_list)
            texts = {
                obj.return_text: obj.text
                for _, obj in drawn
                if hasattr(obj, "return_text")
            }
            return next(
                r for r in return_list if texts.get(r, "").endswith("返回")
            )

        view.now_panel_id = constant.Panel.SEE_MAP
        with mock.patch.object(flow_handle, "askfor_all", back):
            see_map_panel.SeeMapPanel(129).draw()
        self.assertEqual(view.now_panel_id, constant.Panel.IN_SCENE)
        styles = {
            obj.text: obj.normal_style
            for name, obj in drawn
            if name == "Button"
        }
        self.assertEqual(
            (styles["102"], styles["103"], styles["104"]),
            ("deep_gray", "green", "standard"),
        )
        self.assertNotIn("101", styles)
        gold = [
            obj.text
            for name, obj in drawn
            if name == "NormalDraw" and obj.style == "gold_enrod"
        ]
        self.assertEqual(gold, ["101"])
        bottom = [
            obj.text
            for name, obj in drawn
            if name == "CenterButton" and obj.return_text.isdigit()
        ]
        self.assertEqual(len(bottom), 3)
        self.assertTrue(bottom[0].endswith("查看上级地图"))
        self.assertTrue(bottom[1].endswith("返回"))
        self.assertTrue(bottom[2].endswith("干员位置一览"))
        self.assertIn("102", offered)
        self.assertNotIn("101", offered)

    def test_bookmark_button_toggles_here(self) -> None:
        """验证当前位置已收藏时显示取消收藏按钮，触发回调后将其从收藏列表中删除。"""
        kernel_data.put(bookmarks.add, BLOCK)
        kernel_data.put(bookmarks.add, START)
        drawn = self.record()
        panel = see_map_panel.CollectionSceneNamePanel(DORM, 129)
        panel.draw()
        button = [obj for name, obj in drawn if name == "CenterButton"][-1]
        self.assertEqual(button.text.strip(), "[取消收藏当前地点]")
        self.assertEqual(panel.end_index, 1)
        self.assertIn(button.return_text, panel.return_list)
        kernel_data.written(button.cmd_func, *button.args)
        self.assertEqual(bookmarks.places(), [BLOCK])


UI_FREE_RUN = """
import contextlib, importlib.abc, io, json, sys
from types import MappingProxyType
BLOCKED = ("Script.UI", "Script.Settle", "Script.Modules.tk_ui",
    "Script.System.Instruct_System.handle_instruct", "Script.Core.flow_handle",
    "Script.Core.py_cmd", "Script.Core.io_init", "Script.Frontend",
    "tkinter", "_tkinter", "PIL.ImageTk")
attempted = []
def blocked(name):
    return any(name == root or name.startswith(root + ".") for root in BLOCKED)
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if blocked(fullname):
            attempted.append(fullname)
            raise ImportError(fullname)
        return None
sys.meta_path.insert(0, Blocker())
from Script.Config import game_config, map_config, normal_config
with contextlib.redirect_stdout(io.StringIO()):
    normal_config.init_normal_config()
    game_config.init()
    map_config.init_map_data()
from Script.Core import constant
from Script.Design import map_handle
from Script.Kernel import core
from Script.Modules.domains import activity, bookmarks, chara_life, identity
from Script.Modules.domains import roster, scene_state
from Script.Modules.gameplay_resolution import working
from Script.Modules.gameplay_resolution import world_view_service as svc
dorm = ["宿舍", "1区"]
start = dorm + ["101"]
key = map_handle.get_map_system_path_str_for_list
facility = next(s for s in sorted(constant.scene_data, key=str)
    if constant.scene_data[s].scene_name in game_config.config_facility_open_name_set)
facility_path = map_handle.get_map_system_path_for_str(facility)
facility_map = map_handle.get_map_for_path(facility_path)
core.reset_state(core.GameState(0, MappingProxyType({}), MappingProxyType({})))
with working.based_on(core.state()):
    for cid, name in ((0, "doctor"), (1, "npc")):
        identity.put(identity.Identity(cid, name=name))
        chara_life.dormitory.set(cid, key(start))
    roster.add(1)
    activity.set_position(0, start)
    activity.set_position(1, dorm + ["103"])
    scene_state.set_close_flag(key(dorm + ["102"]), 1)
    bookmarks.add(["中枢", "0"])
    view = svc.map_view(dorm, 129)
    kinds = {c.text: [c.kind.value, c.style] for row in view.rows for c in row
        if c.text in ("101", "102", "103", "104")}
    gated = svc.map_view(facility_map, 129)
    gated_kind = [c.kind.value for row in gated.rows for c in row
        if c.text == facility_path[len(facility_map)]]
    map_draw = constant.map_data[key(dorm)].map_draw
    saved = map_draw.max_width
    del map_draw.max_width
    legacy = svc.map_view(dorm, 139).indent
    map_draw.max_width = saved
    out = {
        "kinds": kinds,
        "gated": gated_kind,
        "indent": [view.indent, legacy],
        "tips": len(svc.map_view(["中枢"], 129).tips),
        "settle": svc.settle_view(dorm + ["0"], start),
        "moved": svc.settle_view(["中枢"], dorm + ["102"]),
        "up": svc.parent_map(dorm),
        "down": svc.child_map(["宿舍"]),
        "opens": [svc.opens_map(["中枢", "0"]), svc.opens_map(dorm + ["104"])],
        "scenes": [e.scene_id for e in svc.scene_entries(dorm) if e.here],
    }
    svc.bookmark_here(True)
    out["marked"] = [svc.here_bookmarked(), [b.here for b in svc.bookmark_entries()]]
    svc.bookmark_here(False)
    out["unmarked"] = [svc.here_bookmarked(), bookmarks.places()]
out["attempted"] = attempted
out["loaded"] = sorted(n for n in sys.modules if blocked(n))
print(json.dumps(out))
"""
"""在拦截界面、结算与 Tk 模块的独立子进程中初始化配置与地图，并运行地图查看服务各公开函数的脚本。"""


class ImportBoundaryTest(FastTestCase):
    """验证地图查看服务的无界面与无结算导入边界。"""

    def test_service_imports_no_ui(self) -> None:
        """验证服务源码通过后端界面边界守卫检查。"""
        source = (ROOT / SERVICE_PATH).read_bytes()
        self.assertEqual(banned_imports(source, SERVICE_PATH), [])

    def test_fresh_process_runs_without_ui_or_settle(self) -> None:
        """验证拦截界面、结算与 Tk 模块时独立子进程能跑通全部服务公开函数且零受限模块被尝试导入。"""
        result = subprocess.run(
            [sys.executable, "-c", UI_FREE_RUN],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        out = json.loads(result.stdout.splitlines()[-1])
        self.assertEqual(out["attempted"], [])
        self.assertEqual(out["loaded"], [])
        self.assertEqual(
            out["kinds"],
            {
                "101": ["here", "gold_enrod"],
                "102": ["closed", "deep_gray"],
                "103": ["open", "green"],
                "104": ["open", "standard"],
            },
        )
        self.assertEqual(out["gated"], ["closed"])
        self.assertEqual(out["indent"], [10, 15])
        self.assertGreater(out["tips"], 1)
        self.assertEqual(out["settle"], DORM)
        self.assertEqual(out["moved"], DORM)
        self.assertEqual(out["up"], ["宿舍"])
        self.assertEqual(out["down"], DORM)
        self.assertEqual(out["opens"], [True, False])
        self.assertEqual(out["scenes"], ["101"])
        self.assertEqual(out["marked"], [True, [False, True]])
        self.assertEqual(out["unmarked"], [False, [BLOCK]])
