"""
无界面隔离测试子进程辅助模块

在独立 Python 子进程中安装 sys.meta_path 导入拦截器、隔离地图缓存与标准流后执行代码片段，
将载荷、被拒导入尝试与已加载受限模块以纯 ASCII JSON 返回父进程。
"""

import contextlib
import importlib.abc
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from types import ModuleType

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
"""erArk 仓库根目录，用作子进程工作目录。"""
BLOCKED = frozenset(
    {
        "Script.UI",
        "Script.Settle",
        "Script.System.Instruct_System.handle_instruct",
        "Script.Core.flow_handle",
        "Script.Core.io_init",
        "Script.Frontend",
        "Script.Modules.tk_ui",
        "tkinter",
        "_tkinter",
        "PIL.ImageTk",
    }
)
"""默认拦截的界面、结算、指令入口、前端与 Tk 相关模块根名称集合。"""
ALLOWED = frozenset({"Script.Modules.tk_ui", "Script.Modules.tk_ui.orders"})
"""默认按精确模块名放行的模块集合，仅放行 tk_ui 包壳与 orders。"""


@dataclass(frozen=True)
class ChildRun:
    """无界面子进程单次运行返回给父进程的不可变结果记录。"""

    payload: dict[str, object]
    """代码片段在子进程中写入的结果字典。"""
    attempted: list[str]
    """子进程运行期间按尝试顺序记录的被拒导入模块全名列表。"""
    loaded: list[str]
    """代码片段执行完毕后 sys.modules 中仍被拦截规则覆盖的有序模块名列表。"""


@dataclass
class UiImportBlocker(importlib.abc.MetaPathFinder):
    """拦截受限模块导入并记录每次尝试的 sys.meta_path 查找器。"""

    blocked: frozenset[str]
    """需按模块名或子模块前缀拦截的根模块名集合"""
    allowed: frozenset[str]
    """按精确模块名放行的模块名集合"""
    attempted: list[str] = field(default_factory=list)
    """子进程运行期间按尝试顺序记录的被拒导入模块全名列表。"""

    def covers(self, name: str) -> bool:
        """判断模块名是否落在拦截范围内且未被精确放行。"""
        return name not in self.allowed and any(
            name == root or name.startswith(root + ".") for root in self.blocked
        )

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None = None,
    ) -> None:
        """在导入查找阶段拦截受限模块，记录尝试并抛出带模块名的 ImportError。"""
        if self.covers(fullname):
            self.attempted.append(fullname)
            raise ImportError(f"UI-free child blocks {fullname}", name=fullname)
        return None


def run_ui_free(
    snippet: str,
    *,
    boot: bool = False,
    map_data: bool = False,
    blocked: frozenset[str] = BLOCKED,
    allowed: frozenset[str] = ALLOWED,
    timeout: float = 300,
) -> ChildRun:
    """
    在安装导入拦截器的子进程中执行代码片段并返回运行结果。
    Keyword arguments:
    snippet -- 在子进程中执行的 Python 代码片段，可通过 payload 字典回传数据
    boot -- 为 True 时在执行片段前启动无界面后端配置与空内核状态
    map_data -- boot 为 True 时是否在临时缓存目录中载入地图数据；单独为 True 时抛出 ValueError
    blocked -- 需按模块名及前缀拦截的模块根集合
    allowed -- 按精确模块名放行的模块集合
    timeout -- 子进程等待超时秒数
    Return arguments:
    ChildRun -- 含 payload、attempted 与 loaded 的结果对象；非零退出时抛出 RuntimeError
    """
    if map_data and not boot:
        raise ValueError("map_data needs boot=True")
    request = {
        "snippet": snippet,
        "boot": boot,
        "map_data": map_data,
        "blocked": sorted(blocked),
        "allowed": sorted(allowed),
    }
    result = subprocess.run(
        [sys.executable, "-m", "tests.ui_free_subprocess"],
        cwd=ROOT,
        input=json.dumps(request).encode("ascii"),
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace")
        raise RuntimeError(
            f"UI-free child exited {result.returncode}:\n{stderr}"
        )
    report = json.loads(result.stdout.decode("ascii"))
    return ChildRun(report["payload"], report["attempted"], report["loaded"])


MAP_CACHES = (
    "all_scene_data_path",
    "all_map_data_path",
    "all_place_data_path",
    "scene_path_edge_path",
)
"""map_config 中记录四个地图缓存文件路径的属性名称元组。"""


def load_map_data(source: str, cache: str) -> None:
    """
    重置全局地图表、将地图缓存路径指向临时目录并载入地图数据，使读取与重建均限于临时目录且可重复调用。
    Keyword arguments:
    source -- 源缓存目录路径，已有缓存文件会先复制到 cache
    cache -- 临时缓存目录路径，用于承接地图缓存读取与缺失或跨语言时的重建写入
    Return arguments:
    None -- 将地图表重绑为空字典、重定向缓存路径并调用 map_config.init_map_data 完成载入
    """
    from Script.Config import map_config
    from Script.Core import constant
    from Script.Design import map_handle

    constant.scene_data, constant.map_data, constant.place_data = {}, {}, {}
    for name in MAP_CACHES:
        file_name = os.path.basename(getattr(map_config, name))
        if os.path.exists(os.path.join(source, file_name)):
            shutil.copyfile(
                os.path.join(source, file_name), os.path.join(cache, file_name)
            )
        setattr(map_config, name, os.path.join(cache, file_name))
    map_handle.scene_path_edge_path = map_config.scene_path_edge_path
    map_config.init_map_data()


def boot_backend(map_cache: str | None) -> None:
    """
    在拦截器生效后按顺序初始化通用配置、游戏配置、可选地图数据与空内核状态。
    Keyword arguments:
    map_cache -- 地图临时缓存目录路径；为 None 时跳过地图载入，否则经 load_map_data 载入
    Return arguments:
    None -- 完成配置加载并将内核重置为空状态
    """
    from Script.Config import normal_config

    normal_config.init_normal_config()
    from Script.Config import game_config
    from Script.Kernel import core

    game_config.init()
    if map_cache is not None:
        load_map_data("data", map_cache)
    core.reset_state(core.GameState(0, {}, {}))


def child_main() -> None:
    """
    子进程入口：从二进制标准输入读取请求、配置 UTF-8 标准错误并将文件描述符 1 重定向至标准错误，
    安装拦截器并仅在请求地图数据时创建临时缓存目录后执行片段，
    最终向保留的描述符写出包含载荷、被拒尝试与已加载受限模块的纯 ASCII JSON 报告。
    """
    request = json.loads(sys.stdin.buffer.read().decode("ascii"))
    sys.stderr = io.TextIOWrapper(
        sys.stderr.buffer, "utf-8", "backslashreplace", write_through=True
    )
    report_fd = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    blocker = UiImportBlocker(
        frozenset(request["blocked"]), frozenset(request["allowed"])
    )
    sys.meta_path.insert(0, blocker)
    payload: dict[str, object] = {}
    map_cache = (
        tempfile.TemporaryDirectory()
        if request["map_data"]
        else contextlib.nullcontext()
    )
    with map_cache as map_dir:
        if request["boot"]:
            boot_backend(map_dir)
        exec(
            compile(request["snippet"], "<ui-free snippet>", "exec"),
            {"payload": payload},
        )
    loaded = sorted(name for name in sys.modules if blocker.covers(name))
    report = {
        "payload": payload,
        "attempted": blocker.attempted,
        "loaded": loaded,
    }
    with os.fdopen(report_fd, "wb") as report_file:
        report_file.write(json.dumps(report).encode("ascii"))


if __name__ == "__main__":
    child_main()
