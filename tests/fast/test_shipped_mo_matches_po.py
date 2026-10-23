# -*- coding: UTF-8 -*-
"""
随游戏发布的 MO 与其 PO 一致
============================
游戏运行时只读 data/po 下的 MO，翻译者改的是 PO。
本测试用 buildmo.py --out 把仓库里的 PO 编到临时目录，作为 PO 的译文；
再对 get_text.mo_files_per_language 里每个语言的每个文件：PO 与 MO 都没有的跳过，只有其一的算失败；两者都有时，
用游戏建翻译链的同一函数 get_text.create_translation_chain 只载入这一个仓库里的 MO，
检查 PO 的每条译文都查得到同样的译文，且仓库里的 MO 与临时目录里编出的 MO 含有同一组原文。
"""

import gettext
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

from Script.Core import get_text
from tests.fast.base import FastTestCase
from tests.world import ROOT


class CatalogReader(gettext.GNUTranslations):
  """读 MO 的 GNUTranslations，可取出全部原文与译文"""

  _catalog: dict[str, str]

  def messages(self) -> dict[str, str]:
    """
    取出 MO 里的全部条目
    Keyword arguments:
    无
    Return arguments:
    dict -- 原文到译文，不含文件头（空原文）
    """
    return {msgid: msgstr for msgid, msgstr in self._catalog.items() if msgid}


def read_messages(mo_root: str, language: str, name: str) -> dict[str, str]:
  """
  用 gettext.translation 读一个 MO 的全部条目
  Keyword arguments:
  mo_root -- 各语言目录所在的目录
  language -- 语言
  name -- 文件名，不带扩展名
  Return arguments:
  dict -- 原文到译文，不含文件头
  """
  translation = gettext.translation(
      name, mo_root, languages=[language], class_=CatalogReader
  )
  assert isinstance(translation, CatalogReader)
  return translation.messages()


@unittest.skipUnless(
    shutil.which("msgfmt") or importlib.util.find_spec("polib"),
    "buildmo.py 需要 msgfmt 或 polib",
)
class ShippedMoMatchesPoTest(FastTestCase):
  """每个翻译语言的每个 MO 与其 PO 的已译条目一一相同"""

  def test_shipped_mo_matches_po(self) -> None:
    """
    把 PO 编到临时目录，与仓库里的 MO 逐条比对
    Keyword arguments:
    无
    Return arguments:
    无
    """
    with tempfile.TemporaryDirectory() as out:
      subprocess.run(
          [sys.executable, os.path.join(ROOT, "buildmo.py"), "--out", out],
          cwd=ROOT,
          check=True,
          capture_output=True,
      )
      checked = 0
      for language, name_list in get_text.mo_files_per_language.items():
        for name in name_list:
          base = os.path.join(
              ROOT, get_text.po_data, language, "LC_MESSAGES", name
          )
          has_po = os.path.exists(base + ".po")
          has_mo = os.path.exists(base + ".mo")
          if not has_po and not has_mo:
            continue
          checked += 1
          with self.subTest(language=language, name=name):
            self.assertEqual((has_po, has_mo), (True, True), "有无 PO、有无 MO")
            po_messages = read_messages(out, language, name)
            self.assertTrue(po_messages)
            translation = get_text.create_translation_chain(language, [name])
            assert translation is not None
            mismatched = sum(
                1
                for msgid, msgstr in po_messages.items()
                if translation.gettext(msgid) != msgstr
            )
            self.assertEqual(
                mismatched, 0, "PO 的译文在 MO 里查到不同结果的条数"
            )
            shipped = read_messages(
                os.path.join(ROOT, get_text.po_data), language, name
            )
            self.assertEqual(
                len(shipped.keys() - po_messages.keys()),
                0,
                "仓库里的 MO 有、PO 编出的 MO 没有的条数",
            )
            self.assertEqual(
                len(po_messages.keys() - shipped.keys()),
                0,
                "PO 编出的 MO 有、仓库里的 MO 没有的条数",
            )
      self.assertGreater(checked, 0)
