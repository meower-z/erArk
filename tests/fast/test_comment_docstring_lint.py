"""
测试 tools/lint_comments.py 的三条检查规则与基线收紧逻辑，并验证当前仓库通过已提交基线检查。
运行命令：pytest tests/fast/test_comment_docstring_lint.py
"""

import json
import subprocess
import tempfile
from pathlib import Path

from tests.fast.base import FastTestCase
from tools import lint_comments

ROOT = Path(__file__).resolve().parents[2]
SUPPRESSIONS = (
    "# type" ": ignore[attr-defined]",
    "# no" "qa: F401",
    "# pragma: no cover",
    "# pyright" ": ignore[reportGeneralTypeIssues]",
    "# pylint" ": disable=unused-import",
    "# fmt" ": off",
    "# no" "sec",
)
LEGACY = (
    "cache_control",
    "game_type.Cache",
    "game_type.Character",
    "game_type.Rhodes_Island",
    "Rhodes_Island",
    "SaveUnpickler",
    "PickledPatient",
    "_reset_keeping_cache",
    "gameplay_resolution.draft",
    "save_load.unsaved",
    "cache.character_data",
    "cache.rhodes_island",
    "Cache.npc_id_got",
    "Character.dormitory",
)
LIVE = (
    "core.Character",
    "Character.data",
    "Character.json",
    "Character.csv",
    "Character_Talk.json",
    "CharacterStatusChange",
    "legacy_pickle.cache",
    "image_cache.get",
)


def docstring(length: int, indent: str = "    ") -> str:
    """
    构造一行带指定缩进与字符数的单行三引号文档字符串源码。
    Keyword arguments:
    length -- 文档字符串正文字符数
    indent -- 行首缩进空格
    Return arguments:
    str -- 以换行结尾的文档字符串源码行
    """
    return f'{indent}"""{"x" * length}"""\n'


def comment_lines(source: str) -> list[int]:
    """
    返回 lint_comments.scan 在给定源码中计入的所有注释行号列表。
    Keyword arguments:
    source -- Python 源码文本
    Return arguments:
    list[int] -- 计入注释的行号列表
    """
    return [line for line, _ in lint_comments.scan(source).comments]


def long_docstrings(source: str) -> dict[str, int]:
    """
    返回 lint_comments.scan 在给定源码中检出的超限文档字符串映射。
    Keyword arguments:
    source -- Python 源码文本
    Return arguments:
    dict[str, int] -- 宿主限定名到清理后字符数的映射
    """
    found = lint_comments.scan(source).docstrings
    return {name: length for name, (length, _) in found.items()}


class ScanTest(FastTestCase):
    """验证 scan 对单个源码文本的注释识别、文档字符串长度计算与限定名提取规则。"""

    def test_every_suppression_directive_is_a_comment(self) -> None:
        """验证 SUPPRESSIONS 中的每类静态检查抑制注释都会被计入注释数。"""
        for directive in SUPPRESSIONS:
            with self.subTest(directive=directive):
                self.assertEqual(
                    comment_lines(f"import os  {directive}\n"), [1]
                )

    def test_only_shebang_and_coding_headers_are_exempt(self) -> None:
        """验证 shebang 与编码声明仅在合法文件头位置豁免，其他位置及普通注释均计入。"""
        header = "#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\nx = 1\n"
        self.assertEqual(comment_lines(header), [])
        self.assertEqual(comment_lines("# coding: utf-8\nx = 1\n"), [])
        self.assertEqual(comment_lines("x = 1\n# -*- coding: utf-8 -*-\n"), [2])
        self.assertEqual(comment_lines("\n\n# -*- coding: utf-8 -*-\n"), [3])
        self.assertEqual(comment_lines("x = 1\n#!/usr/bin/env python3\n"), [2])
        self.assertEqual(comment_lines("# a note\n# second note\n"), [1, 2])

    def test_hash_inside_strings_is_not_a_comment(self) -> None:
        """验证普通字符串、f-string 与三引号字符串内部的 # 字符不会被计作注释。"""
        source = (
            's = "# no"\n'
            "t = f\"{s} # no {'#'}\"\n"
            'u = """\n# no\n"""\n'
            "v = 1  # yes\n"
        )
        self.assertEqual(comment_lines(source), [6])

    def test_docstring_cap_counts_cleaned_characters(self) -> None:
        """验证文档字符串上限按去除公共缩进后的字符数计算：500 字符通过，501 字符超限。"""
        at_cap = "def f():\n" + docstring(500)
        over = "def f():\n" + docstring(501)
        self.assertEqual(long_docstrings(at_cap), {})
        self.assertEqual(long_docstrings(over), {"f": 501})
        for last, expected in ((50, {}), (51, {"g": 501})):
            lines = ["        " + "y" * 49] * 9 + ["        " + "y" * last]
            body = "\n".join(lines)
            indented = f'def g():\n    """\n{body}\n    """\n'
            with self.subTest(last=last):
                self.assertEqual(long_docstrings(indented), expected)

    def test_docstring_owners_get_qualified_names(self) -> None:
        """验证模块、嵌套类方法、if 块内函数、单行函数及括号拼接字符串均获得正确的限定名与长度。"""
        source = (
            docstring(510, "")
            + "class Outer:\n"
            + "    class Inner:\n"
            + "        async def method(self):\n"
            + docstring(520, "            ")
            + "    if True:\n"
            + "        def guarded(self, x=lambda: 1) -> dict[str, int]:\n"
            + docstring(530, "            ")
            + f'def one_line(): "{"z" * 540}"\n'
            + "def joined():\n"
            + f'    ("{"a" * 300}"\n     "{"b" * 250}")\n'
        )
        self.assertEqual(
            long_docstrings(source),
            {
                "<module>": 510,
                "Outer.Inner.method": 520,
                "Outer.guarded": 530,
                "one_line": 540,
                "joined": 550,
            },
        )

    def test_non_str_first_statements_are_not_docstrings(self) -> None:
        """验证 f-string、字节串、非首条语句的字符串以及对字符串调用方法的语句均不视为文档字符串。"""
        body = "z" * 600
        source = (
            f'def fstring():\n    f"{body}"\n'
            f'def data():\n    b"{body}"\n'
            f'def later():\n    x = 1\n    "{body}"\n'
            f'def call():\n    "{body}".strip()\n'
        )
        self.assertEqual(long_docstrings(source), {})


class RepositoryTest(FastTestCase):
    """在 setUpClass 构造的临时 git 仓库上，验证 measure、violations 与 lowered 的端到端行为。"""

    problems: list[str]
    measured: lint_comments.Measure
    baseline: dict[str, dict[str, int]] = {
        "comments": {"kept.py": 2, "fewer.py": 3, "more.py": 1, "gone.py": 4},
        "docstrings": {
            "grow.py::Grow.method": 600,
            "shrink.py::Shrink.method": 600,
            "gone.py::f": 700,
        },
    }

    @classmethod
    def setUpClass(cls) -> None:
        """用预设测试文件构造临时 git 仓库并暂存，执行一次 measure 与 violations 供各测试方法复用。"""
        stale = "\n".join(LEGACY)
        live = "\n".join(LIVE)
        files = {
            "pyproject.toml": '[tool.lint-ratchet]\nexclude = ["gen/*.py"]\n',
            "new.py": "x = 1  # note\n",
            "kept.py": "# a\n# b\n",
            "fewer.py": "x = 1  # a\n",
            "more.py": "# a\n# b\n",
            "gen/made.py": "# generated\n",
            "header.py": '#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\ns = "#"\n',
            "cap.py": "def f():\n" + docstring(500),
            "over.py": "def f():\n" + docstring(501),
            "grow.py": "class Grow:\n    def method(self):\n"
            + docstring(601, " " * 8),
            "shrink.py": "class Shrink:\n    def method(self):\n"
            + docstring(550, " " * 8),
            "Script/stale.py": f'"""\n{stale}\n"""\n',
            "Script/stale_comment.py": "x = 1  # cache.npc_id_got\n",
            "Script/cjk.py": '"""读Character.dormitory的值"""\n',
            "Script/live.py": f'"""\n{live}\n"""\n',
            "Script/code.py": 'PATH = "game_type.Character"\n',
            "Script/notes.md": "uses `cache.game_time`\n",
            "tests/old.py": '"""cache_control"""\n',
            "docs/flow.md": "reads `cache.debug_mode`\n",
            "docs/live.md": live,
            "README_en.md": "Rhodes_Island\n",
            "plan/old.md": "Rhodes_Island\n",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for path, text in files.items():
                (root / path).parent.mkdir(parents=True, exist_ok=True)
                (root / path).write_text(text, encoding="utf-8")
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            subprocess.run(["git", "add", "-A"], cwd=root, check=True)
            cls.measured = lint_comments.measure(root)
        cls.problems = lint_comments.violations(cls.measured, cls.baseline)

    def flagged(self, prefix: str) -> list[str]:
        """
        筛选 self.problems 中以给定路径前缀开头的违规信息。
        Keyword arguments:
        prefix -- 路径前缀字符串
        Return arguments:
        list[str] -- 匹配的违规信息列表
        """
        return [p for p in self.problems if p.startswith(prefix)]

    def test_comment_counts_may_not_rise(self) -> None:
        """验证新增带注释文件及注释数高于基线的文件报错，持平、减少、排除文件与文件头均通过。"""
        self.assertEqual(len(self.flagged("new.py:")), 1)
        self.assertEqual(len(self.flagged("more.py:")), 1)
        for path in ("kept.py", "fewer.py", "gen/made.py", "header.py"):
            with self.subTest(path=path):
                self.assertEqual(self.flagged(path), [])

    def test_docstrings_may_not_pass_cap_or_grow(self) -> None:
        """验证新增 501 字符文档字符串与基线条目增长 1 字符均报错，500 字符及缩短的基线条目通过。"""
        self.assertEqual(self.flagged("cap.py"), [])
        self.assertEqual(len(self.flagged("over.py:")), 1)
        self.assertEqual(len(self.flagged("grow.py:")), 1)
        self.assertEqual(self.flagged("shrink.py"), [])

    def legacy(self, prefix: str) -> list[str]:
        """
        从给定路径前缀对应的禁用名称违规信息中提取命中的名称列表。
        Keyword arguments:
        prefix -- 路径前缀字符串
        Return arguments:
        list[str] -- 提取出的禁用名称列表
        """
        suffix = " is a deleted legacy name"
        return [
            p.rsplit(": ", 1)[1].removesuffix(suffix)
            for p in self.flagged(prefix)
            if p.endswith(suffix)
        ]

    def test_legacy_names_fail_in_script_text_and_docs(self) -> None:
        """
        验证 LEGACY 全部名称在 Script/ 文档字符串中被检出，且 Script/ 注释、Script/ 与 docs/ 文档、
        README_en.md 及紧邻中文字符处的命中均被报告。
        """
        self.assertEqual(
            sorted(self.legacy("Script/stale.py:")), sorted(LEGACY)
        )
        for path, name in (
            ("Script/stale_comment.py:", "cache.npc_id_got"),
            ("Script/cjk.py:", "Character.dormitory"),
            ("Script/notes.md:", "cache.game_time"),
            ("docs/flow.md:", "cache.debug_mode"),
            ("README_en.md:", "Rhodes_Island"),
        ):
            with self.subTest(path=path):
                self.assertEqual(self.legacy(path), [name])

    def test_live_names_code_literals_and_out_of_scope_files_pass(self) -> None:
        """验证 LIVE 中的现用名称、代码中的字符串字面量以及 plan/ 与 tests/ 下的文件不报错。"""
        for path in (
            "Script/live.py",
            "Script/code.py",
            "docs/live.md",
            "plan/",
            "tests/",
        ):
            with self.subTest(path=path):
                self.assertEqual(self.flagged(path), [])

    def test_lowered_baseline_only_shrinks(self) -> None:
        """验证 lowered 仅将基线收紧至当前值、永不抬高，并移除消失或回到限额内的条目。"""
        self.assertEqual(
            lint_comments.lowered(self.measured, self.baseline),
            {
                "comments": {"fewer.py": 1, "kept.py": 2, "more.py": 1},
                "docstrings": {
                    "grow.py::Grow.method": 600,
                    "shrink.py::Shrink.method": 550,
                },
            },
        )

    def test_repository_passes_against_its_baseline(self) -> None:
        """验证当前仓库针对 tools/lint_comments_baseline.json 的检查结果为零违规。"""
        path = ROOT / lint_comments.BASELINE
        baseline = json.loads(path.read_text(encoding="utf-8"))
        problems = lint_comments.violations(
            lint_comments.measure(ROOT), baseline
        )
        self.assertEqual(problems, [])
