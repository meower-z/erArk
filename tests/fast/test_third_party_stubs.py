# -*- coding: UTF-8 -*-
"""
第三方类型存根测试
==================
本模块包含两项针对 tests/_mypy_stubs 第三方类型存根的快速测试。
StubVersionsTest 核对 requirements-lint.txt 中 openai 与 google-genai 的固定版
本与 STUB_VERSIONS 一致。ThirdPartyStubsTest 在临时目录生成包含 openai 与
google.genai 调用用例的 Python 模块。该测试使用仓库的 pyproject.toml 对该模块
运行 mypy。该测试核对每行报出的错误码集合与预期一致。该测试从 -v 日志核对
mypy 解析了 openai 与 google.genai。该测试还核对每个以 openai 或
google.genai 为前缀的已解析模块都来自 tests/_mypy_stubs。
"""

import importlib.util
import os
import re
import subprocess
import sys
import tempfile
import unittest

from tests.fast.base import FastTestCase
from tests.world import ROOT

HEADER = [
    "from collections.abc import Iterator, Sequence",
    "from pathlib import Path",
    "from typing import assert_type",
    "",
    "import openai",
    "from google import genai",
    "from google.genai import types as genai_types",
    "from openai import Stream",
    "from openai.types import Image, ImageEditStreamEvent, ImagesResponse",
    "from openai.types.chat import ChatCompletion, ChatCompletionChunk",
    "",
    "",
    "def calls(",
    "    client: openai.OpenAI,",
    "    genai_client: genai.Client,",
    "    images: Sequence[Path],",
    "    item: Image,",
    ") -> None:",
]
""" 临时测试模块开头的导入语句与 calls 函数头 """

CASES: list[tuple[str, tuple[str, ...]]] = [
    (
        'assert_type(openai.OpenAI(api_key="k", base_url=None, timeout=60.0),'
        " openai.OpenAI)",
        (),
    ),
    (
        'assert_type(client.with_options(base_url="http://127.0.0.1:8000/v1"),'
        " openai.OpenAI)",
        (),
    ),
    (
        "assert_type(client.with_options(http_client=openai.DefaultHttpxClient("
        'proxy="http://127.0.0.1:8080")), openai.OpenAI)',
        (),
    ),
    (
        'assert_type(client.chat.completions.create(model="m", messages=['
        '{"role": "system", "content": "s"}, {"role": "user", "content": "u"}'
        "]), ChatCompletion)",
        (),
    ),
    (
        'assert_type(client.chat.completions.create(model="m", messages=[],'
        " stream=True), Stream[ChatCompletionChunk])",
        (),
    ),
    (
        'assert_type(client.chat.completions.create(model="m", messages=[])'
        ".choices[0].message.content, str | None)",
        (),
    ),
    (
        'assert_type(next(client.chat.completions.create(model="m", messages=[],'
        " stream=True)).choices[0].delta.content, str | None)",
        (),
    ),
    (
        'assert_type(client.images.generate(prompt="p", size="1024x1024"),'
        " ImagesResponse)",
        (),
    ),
    (
        'assert_type(client.images.generate(prompt="p").data, list[Image] | None)',
        (),
    ),
    ("assert_type(item.b64_json, str | None)", ()),
    ("assert_type(item.url, str | None)", ()),
    (
        'assert_type(client.images.edit(image=list(images), prompt="p",'
        ' input_fidelity="high"), ImagesResponse)',
        (),
    ),
    (
        'assert_type(client.images.edit(image=list(images), prompt="p",'
        " stream=True), Stream[ImageEditStreamEvent])",
        (),
    ),
    (
        "assert_type(openai.DefaultHttpxClient("
        'proxy="http://127.0.0.1:8080").close(), None)',
        (),
    ),
    (
        "assert_type(openai.DefaultHttpxClient().__enter__(),"
        " openai.DefaultHttpxClient)",
        (),
    ),
    (
        'assert_type(genai.Client(api_key="k", http_options=genai.types.'
        'HttpOptions(api_version="v1alpha", base_url=None)), genai.Client)',
        (),
    ),
    (
        'assert_type(genai_client.models.generate_content(model="m", contents="c",'
        ' config=genai_types.GenerateContentConfig(system_instruction="s"))'
        ".text, str | None)",
        (),
    ),
    (
        'assert_type(genai_client.models.generate_content_stream(model="m",'
        ' contents="c"), Iterator[genai_types.GenerateContentResponse])',
        (),
    ),
    ("openai.OpenAI(api_key=1)", ("arg-type",)),
    ('client.with_options(timeout="60")', ("arg-type",)),
    ("openai.DefaultHttpxClient(proxy=8080)", ("arg-type",)),
    (
        "client.chat.completions.create(model=1, messages=[])",
        ("call-overload",),
    ),
    ('client.chat.completions.create(model="m")', ("call-overload",)),
    (
        'client.chat.completions.create(model="m", messages=['
        '{"role": "robot", "content": "x"}])',
        ("list-item", "misc"),
    ),
    ('client.images.generate(prompt="p", quality="ultra")', ("call-overload",)),
    ('client.images.edit(image="a.png", prompt="p")', ("arg-type",)),
    (
        'len(client.chat.completions.create(model="m", messages=[])'
        ".choices[0].message.content)",
        ("arg-type",),
    ),
    ("genai.Client(api_key=1)", ("arg-type",)),
    ("genai.types.HttpOptions(api_version=1)", ("arg-type",)),
    (
        'genai_client.models.generate_content(model="m", contents=1)',
        ("arg-type",),
    ),
    (
        'genai_client.models.generate_content(model="m", contents="c", stream=True)',
        ("call-arg",),
    ),
    ("genai_types.GenerateContentConfig(system_instruction=1)", ("arg-type",)),
    (
        'genai_client.models.generate_content(model="m", contents="c").text.upper()',
        ("union-attr",),
    ),
]
""" 用例列表，每项为一条调用语句和该行预期的 mypy 错误码元组 """

ERROR_LINE = re.compile(r"^.+:(\d+): error: .*  \[([a-z-]+)\]$")
""" 匹配单行 mypy 报错输出并提取行号与错误码的正则表达式 """
PARSING_LINE = re.compile(r"Parsing (.+) \(([\w.]+)\)$", re.MULTILINE)
""" 匹配 mypy -v 日志中 Parsing 行并提取文件路径与模块名的正则表达式 """
STUBBED = ("openai", "google.genai")
""" 必须由 tests/_mypy_stubs 提供的模块名前缀 """
STUB_VERSIONS = {"openai": "3.31.0", "google-genai": "2.31.0"}
""" tests/_mypy_stubs 中第三方包存根对应的包名与版本号 """


class StubVersionsTest(FastTestCase):
    """验证 requirements-lint.txt 中 openai 与 google-genai 的固定版本与存根一致"""

    def test_lint_pins_match_stubs(self) -> None:
        """
        核对 requirements-lint.txt 中 STUB_VERSIONS 各包对应的固定版本
        Keyword arguments:
        无
        Return arguments:
        无
        """
        pins: dict[str, str] = {}
        path = os.path.join(ROOT, "requirements-lint.txt")
        with open(path, encoding="utf-8") as f:
            for line in f:
                name, sep, version = line.strip().partition("==")
                if sep:
                    pins[name] = version
        for name, version in STUB_VERSIONS.items():
            self.assertEqual(version, pins.get(name), name)


@unittest.skipUnless(importlib.util.find_spec("mypy"), "本测试需要 mypy")
class ThirdPartyStubsTest(FastTestCase):
    """验证 mypy 通过 tests/_mypy_stubs 检查 openai 与 google.genai 调用"""

    def test_stubs_check_callers(self) -> None:
        """
        核对 mypy 检查临时调用模块时的每行错误码与模块解析路径
        Keyword arguments:
        无
        Return arguments:
        无
        """
        source = "\n".join(HEADER + ["    " + line for line, _ in CASES]) + "\n"
        first = len(HEADER) + 1
        expected = {
            first + i: set(codes) for i, (_, codes) in enumerate(CASES) if codes
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "calls.py")
            with open(path, "w", encoding="utf-8") as f:
                f.write(source)
            proc = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mypy",
                    "--config-file",
                    os.path.join(ROOT, "pyproject.toml"),
                    "--cache-dir",
                    os.path.join(tmp, "cache"),
                    "--show-error-codes",
                    "--no-pretty",
                    "--no-error-summary",
                    "--hide-error-context",
                    "-v",
                    path,
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
        found: dict[int, set[str]] = {}
        for line in proc.stdout.splitlines():
            if ": note: " in line:
                continue
            match = ERROR_LINE.match(line)
            if match is None:
                self.fail(line)
            found.setdefault(int(match.group(1)), set()).add(match.group(2))
        self.assertEqual(expected, found)
        stubs = os.path.join(ROOT, "tests", "_mypy_stubs")
        parsed = {
            module: file
            for file, module in PARSING_LINE.findall(proc.stderr)
            if module.startswith(STUBBED)
        }
        self.assertIn("openai", parsed)
        self.assertIn("google.genai", parsed)
        for module, file in parsed.items():
            self.assertTrue(
                os.path.normcase(os.path.abspath(file)).startswith(
                    os.path.normcase(stubs + os.sep)
                ),
                f"{module} {file}",
            )
