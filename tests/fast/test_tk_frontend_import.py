"""Tk 前端包无副作用导入测试：验证导入 `Script.Frontend.Tk` 下全部子模块不会创建 Tk 根窗口。"""

import json
import subprocess
import sys

from tests.fast.base import FastTestCase
from tests.world import ROOT

IMPORT_ALL = """
import importlib
import json
import pkgutil
import tkinter

created = []
real_init = tkinter.Tk.__init__


def recording_init(self, *args, **kwargs):
    created.append(args)
    real_init(self, *args, **kwargs)


tkinter.Tk.__init__ = recording_init
from Script.Config import normal_config

normal_config.init_normal_config()
import Script.Frontend.Tk as package

names = sorted(
    f"{package.__name__}.{info.name}"
    for info in pkgutil.iter_modules(package.__path__)
)
for name in names:
    importlib.import_module(name)
print(json.dumps({"modules": names, "tk_roots": len(created)}))
"""
"""统计 `tkinter.Tk.__init__` 调用次数并导入 `Script.Frontend.Tk` 全部子模块的子进程脚本。"""


class TkFrontendImportTest(FastTestCase):
    """验证导入 Tk 前端包全部子模块时不产生创建 Tk 根窗口的副作用。"""

    def test_modules_import_without_creating_tk_root(self) -> None:
        """运行子进程脚本 `IMPORT_ALL`，断言已导入 `Script.Frontend.Tk.app` 且创建根窗口次数为 0。"""
        result = subprocess.run(
            [sys.executable, "-c", IMPORT_ALL],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        report = json.loads(result.stdout.splitlines()[-1])
        self.assertIn("Script.Frontend.Tk.app", report["modules"])
        self.assertEqual(report["tk_roots"], 0)
