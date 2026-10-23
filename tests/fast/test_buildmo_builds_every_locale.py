# -*- coding: UTF-8 -*-
"""
buildmo.py 的编译范围与输出目录
==============================
在临时目录里摆出一份 data/po（原文语言 zh_CN、两个翻译语言、一个没有 LC_MESSAGES 的目录），
以 --out 运行 buildmo.py，检查每个翻译语言的每个 PO 都编出一个 MO、zh_CN 不编、data/po 里不多出文件，
并用游戏加载翻译的同一个调用（gettext.translation）读回 MO。
"""

import gettext
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from tests.fast.base import FastTestCase
from tests.world import ROOT

HEADER = 'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n'
""" PO 文件头，声明 UTF-8 """
TRANSLATED = "源文一"
""" PO 里已译的原文 """
UNTRANSLATED = "源文二"
""" PO 里未译的原文 """
PO_TEXT = (
    HEADER
    + f'msgid "{TRANSLATED}"\nmsgstr "target one"\n\n'
    + f'msgid "{UNTRANSLATED}"\nmsgstr ""\n'
)
""" 一条已译、一条未译的 PO 内容 """


def write_po(root: str, language: str, name: str) -> None:
  """
  在临时的 data/po 下写一个 PO 文件
  Keyword arguments:
  root -- 临时目录
  language -- 语言目录名
  name -- 文件名，不带扩展名
  Return arguments:
  无
  """
  messages_dir = os.path.join(root, "data", "po", language, "LC_MESSAGES")
  os.makedirs(messages_dir, exist_ok=True)
  with open(
      os.path.join(messages_dir, name + ".po"), "w", encoding="utf-8"
  ) as f:
    f.write(PO_TEXT)


def list_files(root: str) -> set[str]:
  """
  列出目录下全部文件的相对路径
  Keyword arguments:
  root -- 目录
  Return arguments:
  set -- 相对路径的集合，路径分隔符统一为 /
  """
  found = set()
  for dirpath, _dirnames, filenames in os.walk(root):
    for filename in filenames:
      found.add(
          os.path.relpath(os.path.join(dirpath, filename), root).replace(
              os.sep, "/"
          )
      )
  return found


@unittest.skipUnless(
    shutil.which("msgfmt") or importlib.util.find_spec("polib"),
    "buildmo.py 需要 msgfmt 或 polib",
)
class BuildmoBuildsEveryLocaleTest(FastTestCase):
  """buildmo.py --out 为每个翻译语言的每个 PO 编出 gettext 能读的 MO，跳过 zh_CN，不改 data/po"""

  def test_build_into_out_dir(self) -> None:
    """
    以 --out 运行 buildmo.py，检查输出的文件、跳过的语言和读回的翻译
    Keyword arguments:
    无
    Return arguments:
    无
    """
    with tempfile.TemporaryDirectory() as root:
      write_po(root, "zh_CN", "erArk_py")
      write_po(root, "en_US", "erArk_py")
      write_po(root, "en_US", "erArk_csv")
      write_po(root, "ko_KR", "erArk_py")
      os.makedirs(os.path.join(root, "data", "po", "empty_dir"))
      po_before = list_files(os.path.join(root, "data", "po"))
      out = os.path.join(root, "out")
      subprocess.run(
          [sys.executable, os.path.join(ROOT, "buildmo.py"), "--out", out],
          cwd=root,
          check=True,
          capture_output=True,
      )
      self.assertEqual(
          list_files(out),
          {
              "en_US/LC_MESSAGES/erArk_py.mo",
              "en_US/LC_MESSAGES/erArk_csv.mo",
              "ko_KR/LC_MESSAGES/erArk_py.mo",
          },
      )
      self.assertEqual(list_files(os.path.join(root, "data", "po")), po_before)
      for language, name in (
          ("en_US", "erArk_py"),
          ("en_US", "erArk_csv"),
          ("ko_KR", "erArk_py"),
      ):
        translation = gettext.translation(name, out, languages=[language])
        self.assertEqual(translation.gettext(TRANSLATED), "target one")
        self.assertEqual(translation.gettext(UNTRANSLATED), UNTRANSLATED)
