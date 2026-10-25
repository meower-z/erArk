# -*- coding: UTF-8 -*-
"""
PRTS 立绘下载器 MCP 服务器各启动方式的导入
==========================================
tools/MCP/prts_character_downloader 有三种启动方式，载入 server 模块的方式各不相同：
- 在包目录运行 python start_server.py：按顶层模块名执行 from server import main；
- 在包目录运行 python server.py：server.py 本身作为脚本运行；
- 在 tools/MCP 运行 python -m prts_character_downloader：server 作为包成员载入。
每种方式都在子进程里只做导入（不启动服务器、不联网），检查 server 能载入，
且 server 用的 PRTSCharacterDownloader 就是同一种方式下导入 downloader 得到的类。
测试依赖里没有 mcp，子进程的 PYTHONPATH 指向临时目录里的 mcp 替身，只提供 server.py 在模块顶层导入的名字。
"""

import os
import subprocess
import sys
import tempfile

from tests.fast.base import FastTestCase
from tests.world import ROOT

MCP_DIR = os.path.join(ROOT, "tools", "MCP")
""" 包的上级目录，python -m 的工作目录 """
PACKAGE_DIR = os.path.join(MCP_DIR, "prts_character_downloader")
""" 包目录，start_server.py 与 server.py 的工作目录 """
MCP_STUB_FILES = {
    "mcp/__init__.py": "",
    "mcp/types.py": "",
    "mcp/server/__init__.py": (
        "class NotificationOptions:\n  pass\n\n\nclass Server:\n  pass\n"
    ),
    "mcp/server/models.py": "class InitializationOptions:\n  pass\n",
}
""" mcp 替身的文件：相对路径 -> 内容 """
START_WAYS = (
    (
        "start_server.py",
        PACKAGE_DIR,
        "from server import main\n"
        "import server, downloader\n"
        "assert server.PRTSCharacterDownloader is"
        " downloader.PRTSCharacterDownloader\n",
    ),
    (
        "server.py",
        PACKAGE_DIR,
        "import runpy\n"
        "server_globals = runpy.run_path('server.py', run_name='probe')\n"
        "import downloader\n"
        "assert server_globals['PRTSCharacterDownloader'] is"
        " downloader.PRTSCharacterDownloader\n",
    ),
    (
        "python -m prts_character_downloader",
        MCP_DIR,
        "import prts_character_downloader.server as server\n"
        "import prts_character_downloader.downloader as downloader\n"
        "assert server.PRTSCharacterDownloader is"
        " downloader.PRTSCharacterDownloader\n",
    ),
)
"""
启动方式：(名称, 工作目录, 子进程执行的导入代码)
server.py 以 run_name='probe' 运行，不进入 __main__ 分支
"""


def write_mcp_stub(root: str) -> None:
  """
  在目录里写出 mcp 替身包
  Keyword arguments:
  root -- 目录，写完后加进子进程的 PYTHONPATH
  Return arguments:
  无
  """
  for relative_path, content in MCP_STUB_FILES.items():
    path = os.path.join(root, relative_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
      f.write(content)


class PrtsDownloaderStartImportsTest(FastTestCase):
  """PRTS 立绘下载器的每种启动方式都能载入 server，且 server 用的下载器类就是同一方式下导入的 downloader 里的类"""

  def test_every_start_way_imports_server(self) -> None:
    """
    在各启动方式的工作目录里用子进程执行导入代码，检查退出码为 0
    Keyword arguments:
    无
    Return arguments:
    无
    """
    with tempfile.TemporaryDirectory() as stub_root:
      write_mcp_stub(stub_root)
      env = dict(os.environ, PYTHONPATH=stub_root, PYTHONDONTWRITEBYTECODE="1")
      for name, cwd, code in START_WAYS:
        with self.subTest(way=name):
          result = subprocess.run(
              [sys.executable, "-c", code],
              cwd=cwd,
              env=env,
              stdin=subprocess.DEVNULL,
              capture_output=True,
              text=True,
              encoding="utf-8",
              errors="replace",
              timeout=60,
              check=False,
          )
          self.assertEqual(result.returncode, 0, result.stderr)
