"""
测试 tools/pyrefly_baseline_check.py 的基线放行、同文件报错增长拦截、新文件报错拦截，
以及不可解析 ERROR 行的异常拦截。
运行命令：python -m unittest tests.fast.test_pyrefly_baseline_check
"""

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from tests.fast.base import FastTestCase
from tools import pyrefly_baseline_check

ROOT = Path(__file__).resolve().parents[2]
""" 仓库根目录路径 """
BAD = 'def {name}() -> int:\n    return "x"{tail}\n'
""" 触发 bad-return 的测试函数源码模板，含函数名与行尾占位符 """
IGNORE = "  # type" ": ignore"
""" 附加在返回语句行尾的忽略注释片段 """
MIXED = (
    "print('ERROR a.py:1:12-15: msg [bad-return]');"
    "print('ERROR a.py: msg');"
    "raise SystemExit(1)"
)
""" 输出一条可读 ERROR 行与一条缺少位置和规则的 ERROR 行后以退出码 1 退出的代码片段 """


@unittest.skipUnless(importlib.util.find_spec("pyrefly"), "本测试需要 pyrefly")
class PyreflyBaselineCheckTest(FastTestCase):
    """在临时 git 仓库上验证 pyrefly_baseline_check.check 的基线检查行为。"""

    def repo(self, files: dict[str, str]) -> Path:
        """
        构造包含真实 pyproject.toml、单行基线与给定源码文件的临时 git 仓库，并在清理时删除。
        Keyword arguments:
        files -- 相对路径到文件源码文本的映射
        Return arguments:
        Path -- 临时仓库根目录路径
        """
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        shutil.copy(ROOT / "pyproject.toml", tmp / "pyproject.toml")
        (tmp / ".lint-baseline.tsv").write_text(
            "# lint-baseline v2\na.py\tf\tpyrefly:bad-return\tcount=1\n",
            encoding="utf-8",
        )
        for rel, text in files.items():
            (tmp / rel).write_text(text, encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=tmp, check=True)
        subprocess.run(["git", "add", "."], cwd=tmp, check=True)
        return tmp

    def test_baselined_error_passes(self) -> None:
        """
        验证文件报错数未超过基线上限时检查报告为空。
        Keyword arguments:
        无
        Return arguments:
        无
        """
        tmp = self.repo({"a.py": BAD.format(name="f", tail="")})
        self.assertEqual([], pyrefly_baseline_check.check(tmp))

    def test_rise_in_file_fails(self) -> None:
        """
        验证已有文件新增带忽略注释的报错时报错数上升被拦截，报告首行与原始报错行数符合预期。
        Keyword arguments:
        无
        Return arguments:
        无
        """
        text = BAD.format(name="f", tail="") + BAD.format(name="g", tail=IGNORE)
        report = pyrefly_baseline_check.check(self.repo({"a.py": text}))
        self.assertEqual("a.py pyrefly:bad-return: 2 > 1", report[0])
        self.assertEqual(3, len(report))

    def test_new_file_fails(self) -> None:
        """
        验证不在基线中的新文件出现报错时被拦截，报告首行与原始报错行数符合预期。
        Keyword arguments:
        无
        Return arguments:
        无
        """
        tmp = self.repo(
            {
                "a.py": BAD.format(name="f", tail=""),
                "b.py": BAD.format(name="h", tail=""),
            }
        )
        report = pyrefly_baseline_check.check(tmp)
        self.assertEqual("b.py pyrefly:bad-return: 1 > 0", report[0])
        self.assertEqual(2, len(report))

    def test_unreadable_error_line_fails(self) -> None:
        """
        验证输出同时含可读 ERROR 行与不可解析 ERROR 行时 run_checker 抛出 RuntimeError。
        Keyword arguments:
        无
        Return arguments:
        无
        """
        with open(ROOT / "pyproject.toml", "rb") as f:
            checkers = tomllib.load(f)["tool"]["lint-ratchet"]["checkers"]
        argv = [sys.executable, "-c", MIXED, "{files}"]
        table = dict(checkers["pyrefly"], argv=argv)
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        with self.assertRaises(RuntimeError):
            pyrefly_baseline_check.run_checker(tmp, table, ["a.py"])
