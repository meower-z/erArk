# -*- coding: UTF-8 -*-
"""Register bundled fonts before Tk resolves configured font families."""

import ctypes
import os
import sys

FR_PRIVATE = 0x10
FONT_EXTENSIONS = (".ttf", ".otf", ".ttc")

_registered_font_paths = []


def _dedupe(paths):
    seen = set()
    result = []
    for path in paths:
        if not path:
            continue
        norm_path = os.path.normcase(os.path.abspath(path))
        if norm_path in seen:
            continue
        seen.add(norm_path)
        result.append(os.path.abspath(path))
    return result


def _candidate_roots():
    roots = []
    if hasattr(sys, "_MEIPASS") or getattr(sys, "frozen", False):
        roots.append(os.path.dirname(sys.executable))
        roots.append(getattr(sys, "_MEIPASS", ""))

    roots.append(os.getcwd())

    mod_path = globals().get("__file__", "")
    if mod_path:
        mod_path = os.path.abspath(mod_path)
        if os.path.isdir(mod_path):
            roots.append(os.path.dirname(os.path.dirname(mod_path)))
        else:
            roots.append(os.path.dirname(os.path.dirname(os.path.dirname(mod_path))))

    return _dedupe(roots)


def _candidate_font_dirs():
    dirs = []
    for root in _candidate_roots():
        dirs.append(os.path.join(root, "static", "fonts"))
        dirs.append(os.path.join(root, "fonts"))
    return _dedupe(dirs)


def _iter_font_files(font_dirs=None):
    for font_dir in _dedupe(font_dirs or _candidate_font_dirs()):
        if not os.path.isdir(font_dir):
            continue
        for entry in sorted(os.scandir(font_dir), key=lambda item: item.name.lower()):
            if not entry.is_file():
                continue
            if entry.name.lower().endswith(FONT_EXTENSIONS):
                yield os.path.abspath(entry.path)


def _register_font_file(font_path, gdi32=None):
    # 仅在未注入gdi32时才检查平台，保证非Windows运行时为空操作，同时允许测试注入伪gdi32
    if gdi32 is None:
        if os.name != "nt":
            return 0
        gdi32 = ctypes.windll.gdi32
    font_path = os.path.abspath(font_path)
    added = int(gdi32.AddFontResourceExW(font_path, FR_PRIVATE, 0))
    if added:
        _registered_font_paths.append(font_path)
    return added


def register_local_fonts(font_dirs=None, gdi32=None):
    total = 0
    seen = set()
    for font_path in _iter_font_files(font_dirs):
        norm_path = os.path.normcase(font_path)
        if norm_path in seen:
            continue
        seen.add(norm_path)
        try:
            total += _register_font_file(font_path, gdi32)
        except Exception as exc:
            print(f"[local_fontfix] 字体注册失败: {font_path}, {exc}")

    if total:
        print(f"[local_fontfix] 已注册本地字体资源: {total}")
    return total


if not globals().get("_LOCAL_FONTFIX_DISABLE_AUTO_REGISTER", False):
    register_local_fonts()
