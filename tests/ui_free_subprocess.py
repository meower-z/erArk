"""
无界面子进程测试辅助模块
========================
本模块在独立 Python 子进程中安装导入拦截器并执行测试代码片段。
请求经标准输入以纯 ASCII JSON 传入。结果经原始标准输出文件描述符以纯 ASCII JSON 返回。
子进程将标准输出与文件描述符 1 重定向至 UTF-8 编码的标准错误，避免普通输出与终端编码干扰结果。
"""

import importlib.abc
import io
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from types import ModuleType

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
"""由模块路径推导的仓库根目录，用作子进程的工作目录。"""
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
"""默认拦截的 10 个模块根名集合，由 UiImportBlocker 用于拦截各根模块及其子模块。"""
ALLOWED = frozenset({"Script.Modules.tk_ui", "Script.Modules.tk_ui.orders"})
"""默认按精确全名放行的模块集合，仅包含 Script.Modules.tk_ui 与 Script.Modules.tk_ui.orders。"""


@dataclass(frozen=True)
class ChildRun:
    """一次无界面子进程执行的不可变返回结果。"""

    payload: dict[str, object]
    """测试代码片段在子进程中写入的结果字典。"""
    attempted: list[str]
    """子进程中按尝试顺序记录的被拦截导入模块全名列表。"""
    loaded: list[str]
    """子进程结束时位于 sys.modules 中且受拦截规则覆盖的已排序模块全名列表。"""


@dataclass
class UiImportBlocker(importlib.abc.MetaPathFinder):
    """挂在 sys.meta_path 中的模块导入拦截器，记录并拒绝受限模块导入。"""

    blocked: frozenset[str]
    """受拦截的模块根名集合，用于匹配根模块自身及其子模块。"""
    allowed: frozenset[str]
    """按精确模块全名豁免拦截的放行集合。"""
    attempted: list[str] = field(default_factory=list)
    """按触发顺序记录的被拒绝导入模块全名列表。"""

    def covers(self, name: str) -> bool:
        """
        判断模块全名是否处于当前拦截范围内。
        Keyword arguments:
        name -- str，待判定的模块全名
        Return arguments:
        bool -- 不在 allowed 中且匹配 blocked 任一根模块或其子模块时返回 True，否则返回 False
        """
        return name not in self.allowed and any(
            name == root or name.startswith(root + ".") for root in self.blocked
        )

    def find_spec(
        self,
        fullname: str,
        path: Sequence[str] | None,
        target: ModuleType | None = None,
    ) -> None:
        """
        实现 MetaPathFinder 钩子，对受拦截模块记录全名并抛出带 name 属性的 ImportError。
        Keyword arguments:
        fullname -- str，待导入的模块全名
        path -- Sequence[str] | None，父包搜索路径，顶层模块为 None
        target -- ModuleType | None，重载时的目标模块对象，默认 None
        Return arguments:
        None -- 模块不受拦截时返回 None，交由后续查找器处理
        """
        if self.covers(fullname):
            self.attempted.append(fullname)
            raise ImportError(f"UI-free child blocks {fullname}", name=fullname)
        return None


def run_ui_free(
    snippet: str,
    *,
    boot: bool = False,
    blocked: frozenset[str] = BLOCKED,
    allowed: frozenset[str] = ALLOWED,
    timeout: float = 300,
) -> ChildRun:
    """
    在安装导入拦截器的独立 Python 子进程中执行代码片段并返回运行结果。
    子进程非零退出时抛出 RuntimeError，错误消息包含退出码与按 UTF-8 解码的标准错误输出。
    Keyword arguments:
    snippet -- str，在子进程中执行的 Python 代码片段，可通过全局字典 payload 回传结果
    boot -- bool，是否在安装拦截器后调用 boot_backend 初始化配置与空内核状态，默认 False
    blocked -- frozenset[str]，受拦截的模块根名集合，默认 BLOCKED
    allowed -- frozenset[str]，按精确全名放行的模块集合，默认 ALLOWED
    timeout -- float，子进程超时秒数，默认 300
    Return arguments:
    ChildRun -- 包含 payload、attempted 与 loaded 的子进程运行结果
    """
    request = {
        "snippet": snippet,
        "boot": boot,
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


def boot_backend() -> None:
    """依次初始化基础配置与游戏配置数据，并将内核状态重置为时钟为 0 的空 GameState。"""
    from Script.Config import normal_config

    normal_config.init_normal_config()
    from Script.Config import game_config
    from Script.Kernel import core

    game_config.init()
    core.reset_state(core.GameState(0, {}, {}))


def child_main() -> None:
    """
    子进程入口函数。
    函数从标准输入读取纯 ASCII JSON 请求，并将标准错误重包装为 UTF-8。
    函数复制文件描述符 1 作为结果通道，再将文件描述符 1 与标准输出重定向至标准错误。
    函数在 sys.meta_path 首位安装拦截器，按需调用 boot_backend 后执行代码片段。
    执行结束后，函数将包含 payload、attempted 与 loaded 的纯 ASCII JSON 写入结果通道。
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
    if request["boot"]:
        boot_backend()
    payload: dict[str, object] = {}
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
