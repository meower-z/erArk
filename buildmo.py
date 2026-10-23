#!/usr/bin/python3
# -*- coding: UTF-8 -*-
"""
把 data/po 下每个语言的 PO 文件编译成 MO 文件
==============================================
用法：python buildmo.py [--out DIR]
不带 --out 时，MO 写在 PO 旁边（data/po/<语言>/LC_MESSAGES/）。
带 --out 时，MO 写到 DIR/<语言>/LC_MESSAGES/。脚本只读 PO，不改 PO。
编译用 gettext 的 msgfmt；PATH 里没有 msgfmt 时用 polib。
polib 在 requirements-dev.txt 里，游戏本身不需要它。
zh_CN 是原文语言，不编译。它的 PO 由 buildconfig.py、auto_build_config.py
与 buildpo.py 生成，只作翻译原文。游戏用 zh_CN 时直接显示原文，不加载 MO。
"""

import argparse
import os
import shutil
import subprocess
import sys

PO_ROOT = os.path.join("data", "po")
""" 各语言 PO 文件所在的目录 """
SOURCE_LANGUAGE = "zh_CN"
""" 原文语言，不编译 """
MSGFMT = shutil.which("msgfmt")
""" msgfmt 的路径，PATH 里没有时为 None """
try:
  import polib
except ImportError:
  # polib 只在没有 msgfmt 时用到，游戏的依赖里没有它
  HAS_POLIB = False
else:
  HAS_POLIB = True


def find_po_files(po_root: str) -> list[tuple[str, str]]:
  """
  列出要编译的 PO 文件
  Keyword arguments:
  po_root -- 各语言目录所在的目录
  Return arguments:
  list -- (语言, 文件名不带扩展名) 的列表，按语言与文件名排序，不含原文语言
  """
  po_files: list[tuple[str, str]] = []
  for language in sorted(os.listdir(po_root)):
    if language == SOURCE_LANGUAGE:
      continue
    messages_dir = os.path.join(po_root, language, "LC_MESSAGES")
    if not os.path.isdir(messages_dir):
      continue
    for file_name in sorted(os.listdir(messages_dir)):
      if file_name.endswith(".po"):
        po_files.append((language, file_name[: -len(".po")]))
  return po_files


def compile_po(po_path: str, mo_path: str) -> None:
  """
  把一个 PO 文件编译成 MO 文件，有 msgfmt 时用 msgfmt，否则用 polib
  Keyword arguments:
  po_path -- PO 文件路径
  mo_path -- 要写出的 MO 文件路径
  Return arguments:
  无
  """
  if MSGFMT is not None:
    subprocess.run([MSGFMT, "-o", mo_path, po_path], check=True)
  else:
    polib.pofile(po_path).save_as_mofile(mo_path)


def main() -> None:
  """
  读取命令行参数，编译每个语言的全部 PO 文件
  Keyword arguments:
  无
  Return arguments:
  无
  """
  parser = argparse.ArgumentParser(
      description="把 data/po 下的 PO 文件编译成 MO 文件"
  )
  parser.add_argument("--out", help="MO 文件的输出目录，默认写在 PO 旁边")
  args = parser.parse_args()
  if MSGFMT is None and not HAS_POLIB:
    sys.exit(
        "需要 gettext 的 msgfmt 或 polib（pip install -r requirements-dev.txt）"
    )
  out_root = args.out if args.out else PO_ROOT
  for language, name in find_po_files(PO_ROOT):
    out_dir = os.path.join(out_root, language, "LC_MESSAGES")
    os.makedirs(out_dir, exist_ok=True)
    po_path = os.path.join(PO_ROOT, language, "LC_MESSAGES", name + ".po")
    mo_path = os.path.join(out_dir, name + ".mo")
    compile_po(po_path, mo_path)
    print(mo_path)


if __name__ == "__main__":
  main()
