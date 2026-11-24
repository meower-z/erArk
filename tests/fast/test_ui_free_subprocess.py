"""
无界面隔离测试子进程辅助模块的单元测试

覆盖后端无界面启动与数据目录只读、多编码标准流与中文报错透传、临时目录地图重建、
参数校验、延迟导入拦截、tk_ui.orders 精确放行与同包兄弟拦截。
"""

import os
import tempfile
from unittest import mock

from tests.fast.base import FastTestCase
from tests.ui_free_subprocess import ROOT, run_ui_free

BOOTED_RUN = """
from Script.Config import game_config
from Script.Core import constant
from Script.Kernel import core
payload["behaviors"] = len(game_config.config_behavior_must_settle_cid_list) > 0
payload["scenes"] = len(constant.scene_data) > 0
payload["characters"] = len(core.state().characters)
"""
"""在已启动无界面后端的子进程中检查行为配置、场景数据与空角色表的代码片段。"""
CHINESE_RUN = """
import os
import sys
os.write(1, b"native write to fd 1\\n")
print("博士与干员")
payload["text"] = "博士与干员"
payload["encoding"] = sys.__stdout__.encoding
"""
"""在子进程中向文件描述符 1 执行原生写入、打印中文文本并回传文本与原始标准输出编码的代码片段。"""
MAP_REBUILD_RUN = """
import os
import pickle
import tempfile
from Script.Core import constant
from tests.ui_free_subprocess import load_map_data
def stale_caches(folder):
    for name in ("SceneData", "MapData", "PlaceData"):
        with open(os.path.join(folder, name), "wb") as cache_file:
            pickle.dump({}, cache_file)
            pickle.dump("other_language", cache_file)
    with open(os.path.join(folder, "ScenePath"), "w") as cache_file:
        cache_file.write("{}")
def load(case):
    with tempfile.TemporaryDirectory() as source:
        with tempfile.TemporaryDirectory() as cache:
            if case == "other_language":
                stale_caches(source)
            load_map_data("data" if case == "valid" else source, cache)
            files = sorted(os.listdir(cache))
    places = {tag: list(paths) for tag, paths in constant.place_data.items()}
    repeats = sum(len(paths) - len(set(paths)) for paths in places.values())
    return files, places, sorted(constant.scene_data), repeats
_, base_places, base_scenes, base_repeats = load("valid")
payload["base"] = [len(base_places) > 0, len(base_scenes) > 0, base_repeats]
for case in ("missing", "other_language", "valid"):
    files, places, scenes, repeats = load(case)
    payload[case] = [files, places == base_places, scenes == base_scenes, repeats]
"""
"""
在子进程中依次以有效缓存、空目录、异语言陈旧缓存与二次有效缓存调用 load_map_data，
回传临时缓存文件列表、地点与场景表一致性及重复路径数的代码片段。
"""
LAZY_IMPORT_RUN = """
import importlib
def load_later(name):
    importlib.import_module(name)
try:
    load_later({name!r})
except ImportError as error:
    payload["refused"] = error.name
"""
"""通过函数内延迟调用 importlib.import_module 验证受限导入被拒绝的模板片段。"""
TEMP_RUN = """
import os
payload["entries"] = len(os.listdir(os.environ["TMPDIR"]))
"""
"""统计子进程环境中 TMPDIR 目录内条目数量并写入 payload 的代码片段。"""
TK_ORDERS_RUN = """
import sys
from Script.Modules.tk_ui import orders
payload["accept"] = callable(orders.accept)
try:
    from Script.Modules.tk_ui import callbacks
except ImportError as error:
    payload["refused"] = error.name
payload["orders_loaded"] = "Script.Modules.tk_ui.orders" in sys.modules
"""
"""验证 tk_ui.orders 可正常导入而同包 callbacks 被拦截的代码片段。"""


def data_files() -> dict[str, tuple[int, int]]:
    """遍历仓库 data 目录下全部文件，返回路径到文件大小与纳秒修改时间的映射。"""
    found = {}
    for folder, _, names in os.walk(os.path.join(ROOT, "data")):
        for name in names:
            path = os.path.join(folder, name)
            stat = os.stat(path)
            found[path] = (stat.st_size, stat.st_mtime_ns)
    return found


class UiFreeSubprocessTest(FastTestCase):
    """测试无界面子进程辅助模块的拦截规则、编码安全、后端启动与错误透传。"""

    def test_booted_backend_loads_no_ui_and_writes_no_data(self) -> None:
        """验证启动无界面后端并载入地图后不加载受限模块、角色为空且 data 目录无修改。"""
        before = data_files()
        run = run_ui_free(BOOTED_RUN, boot=True, map_data=True)
        self.assertEqual((run.loaded, run.attempted), ([], []))
        self.assertEqual(
            run.payload, {"behaviors": True, "scenes": True, "characters": 0}
        )
        self.assertEqual(data_files(), before)

    def test_chinese_payload_survives_child_stdio_encodings(self) -> None:
        """验证 PYTHONIOENCODING 为 cp1252、gbk 或 utf-16 时原生 fd 1 写入与中文载荷均能完整往返。"""
        for encoding in ("cp1252", "gbk", "utf-16"):
            with (
                self.subTest(encoding),
                mock.patch.dict(os.environ, {"PYTHONIOENCODING": encoding}),
            ):
                run = run_ui_free(CHINESE_RUN)
                self.assertEqual(
                    run.payload, {"text": "博士与干员", "encoding": encoding}
                )

    def test_chinese_error_survives_child_stdio_encodings(self) -> None:
        """验证 PYTHONIOENCODING 为 gbk 或 utf-16 时子进程抛出的中文异常信息以 UTF-8 透传至父进程。"""
        for encoding in ("gbk", "utf-16"):
            with self.subTest(encoding):
                with (
                    mock.patch.dict(os.environ, {"PYTHONIOENCODING": encoding}),
                    self.assertRaises(RuntimeError) as caught,
                ):
                    run_ui_free('raise RuntimeError("干员诊断信息")')
                self.assertIn(
                    "RuntimeError: 干员诊断信息", str(caught.exception)
                )

    def test_map_rebuild_stays_in_child_cache(self) -> None:
        """
        验证缺失、异语言与重复有效载入均将缓存限于子进程临时目录，
        所得地点与场景表与基线一致且无重复路径，仓库 data 目录保持不变。
        """
        before = data_files()
        run = run_ui_free(MAP_REBUILD_RUN, boot=True)
        caches = ["MapData", "PlaceData", "SceneData", "ScenePath"]
        self.assertEqual(
            run.payload,
            {
                "base": [True, True, 0],
                "missing": [caches, True, True, 0],
                "other_language": [caches, True, True, 0],
                "valid": [caches, True, True, 0],
            },
        )
        self.assertEqual(data_files(), before)

    def test_temporary_directory_only_for_map_data(self) -> None:
        """验证仅在请求地图数据时创建子进程临时目录，纯导入与无地图启动均不创建。"""
        for boot, map_data, entries in (
            (False, False, 0),
            (True, False, 0),
            (True, True, 1),
        ):
            with (
                self.subTest(boot=boot, map_data=map_data),
                tempfile.TemporaryDirectory() as scratch,
                mock.patch.dict(os.environ, {"TMPDIR": scratch}),
            ):
                run = run_ui_free(TEMP_RUN, boot=boot, map_data=map_data)
                self.assertEqual(run.payload, {"entries": entries})

    def test_already_loaded_blocked_module_is_reported(self) -> None:
        """验证拦截器安装前已导入的受限模块会被记入 loaded，片段仍可导入且 attempted 为空。"""
        run = run_ui_free(
            'import io\npayload["name"] = io.__name__',
            blocked=frozenset({"io"}),
        )
        self.assertEqual(
            (run.payload, run.loaded, run.attempted),
            ({"name": "io"}, ["io"], []),
        )

    def test_map_data_without_boot_is_rejected(self) -> None:
        """验证 boot 为 False 且 map_data 为 True 时 run_ui_free 直接抛出 ValueError。"""
        with self.assertRaises(ValueError):
            run_ui_free("", map_data=True)

    def test_lazy_ui_and_settle_imports_are_refused(self) -> None:
        """验证函数内延迟导入 Script.UI 子模块与 Script.Settle 均被拦截并记入 attempted。"""
        for name, root in (
            ("Script.UI.Moudle.draw", "Script.UI"),
            ("Script.Settle", "Script.Settle"),
        ):
            with self.subTest(name):
                run = run_ui_free(LAZY_IMPORT_RUN.format(name=name))
                self.assertEqual(run.payload["refused"], root)
                self.assertIn(root, run.attempted)
                self.assertEqual(run.loaded, [])

    def test_tk_ui_orders_imports_but_its_siblings_stay_blocked(self) -> None:
        """验证 tk_ui.orders 按精确放行正常加载，同包 callbacks 仍被拦截。"""
        run = run_ui_free(TK_ORDERS_RUN)
        self.assertEqual(
            run.payload,
            {
                "accept": True,
                "refused": "Script.Modules.tk_ui.callbacks",
                "orders_loaded": True,
            },
        )
        self.assertEqual(run.attempted, ["Script.Modules.tk_ui.callbacks"])
        self.assertEqual(run.loaded, [])

    def test_uncaught_blocked_import_reports_child_stderr(self) -> None:
        """验证片段未捕获受限导入时抛出包含子进程 ImportError 与模块名的 RuntimeError。"""
        with self.assertRaises(RuntimeError) as caught:
            run_ui_free("import Script.Settle")
        self.assertIn("ImportError", str(caught.exception))
        self.assertIn("Script.Settle", str(caught.exception))
