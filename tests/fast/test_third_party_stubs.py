# -*- coding: UTF-8 -*-
"""
第三方类型存根测试
==================
本模块包含两项针对 tests/_mypy_stubs 第三方类型存根的快速测试。
StubVersionsTest 核对 requirements-lint.txt 中 openai 与 google-genai 的固定版
本与 STUB_VERSIONS 一致。ThirdPartyStubsTest 在临时目录生成包含 openai 与
google.genai 调用用例的 Python 模块，用仓库的 pyproject.toml 对其运行两次
pyrefly：一次指定当前解释器路径，核对每行输出均为 ERROR 且错误码集合与预期一
致；另一次跳过解释器查询并指向空 site-packages 目录，核对两次输出完全一致，以
验证两个包均从 search-path 解析。
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
    ("openai.OpenAI(api_key=1)", ("bad-argument-type",)),
    ('client.with_options(timeout="60")', ("bad-argument-type",)),
    ("openai.DefaultHttpxClient(proxy=8080)", ("bad-argument-type",)),
    (
        "client.chat.completions.create(model=1, messages=[])",
        ("bad-argument-type",),
    ),
    ('client.chat.completions.create(model="m")', ("no-matching-overload",)),
    (
        'client.chat.completions.create(model="m", messages=['
        '{"role": "robot", "content": "x"}])',
        ("bad-argument-type",),
    ),
    (
        'client.images.generate(prompt="p", quality="ultra")',
        ("no-matching-overload",),
    ),
    ('client.images.edit(image="a.png", prompt="p")', ("bad-argument-type",)),
    (
        'len(client.chat.completions.create(model="m", messages=[])'
        ".choices[0].message.content)",
        ("bad-argument-type",),
    ),
    ("genai.Client(api_key=1)", ("bad-argument-type",)),
    ("genai.types.HttpOptions(api_version=1)", ("bad-argument-type",)),
    (
        'genai_client.models.generate_content(model="m", contents=1)',
        ("bad-argument-type",),
    ),
    (
        'genai_client.models.generate_content(model="m", contents="c", stream=True)',
        ("unexpected-keyword",),
    ),
    (
        "genai_types.GenerateContentConfig(system_instruction=1)",
        ("bad-argument-type",),
    ),
    (
        'genai_client.models.generate_content(model="m", contents="c").text.upper()',
        ("missing-attribute",),
    ),
]
""" 用例列表，每项为一条调用语句和该行预期的 pyrefly 错误码元组 """

ERROR_LINE = re.compile(r"^ERROR (.+):(\d+):\S+: .* \[([a-z-]+)\]$")
""" 匹配 pyrefly min-text 单行 ERROR 输出并提取路径、行号与错误码的正则表达式 """
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


def pyrefly(path: str, *extra: str) -> str:
    """
    在仓库根目录用 pyproject.toml 对指定文件运行 pyrefly check 并返回标准输出。
    Keyword arguments:
    path -- 待检查的 Python 文件路径
    extra -- 附加命令行参数
    Return arguments:
    str -- pyrefly 命令的标准输出文本
    """
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pyrefly",
            "check",
            "--config",
            os.path.join(ROOT, "pyproject.toml"),
            "--output-format=min-text",
            "--summary=none",
            "--progress-bar=no",
            "--color=never",
            *extra,
            path,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout


@unittest.skipUnless(importlib.util.find_spec("pyrefly"), "本测试需要 pyrefly")
class ThirdPartyStubsTest(FastTestCase):
    """验证 pyrefly 通过 tests/_mypy_stubs 检查 openai 与 google.genai 调用"""

    def test_stubs_check_callers(self) -> None:
        """
        核对 pyrefly 检查临时调用模块时的每行错误码，并验证隐藏 site-packages 后输出一致。
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
            empty = os.path.join(tmp, "site-packages")
            os.mkdir(empty)
            output = pyrefly(path, "--python-interpreter-path", sys.executable)
            hidden = pyrefly(
                path,
                "--skip-interpreter-query",
                "--site-packages-path",
                empty,
            )
        found: dict[int, set[str]] = {}
        for line in output.splitlines():
            match = ERROR_LINE.match(line)
            if match is None:
                self.fail(line)
            found.setdefault(int(match.group(2)), set()).add(match.group(3))
        self.assertEqual(expected, found)
        self.assertEqual(output, hidden)
