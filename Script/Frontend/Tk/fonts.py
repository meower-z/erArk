"""Tk 前端资源路径解析与 `static/fonts` 本地字体注册模块。"""

import os
import sys
from tkinter import Tk

from Script.Core import game_path_config

ALIAS_OVERRIDES = {
    "等距更纱黑体": ["等距更纱黑体 SC", "Sarasa Mono SC", "SarasaMonoSC"],
    "等距更纱黑体.ttf": ["等距更纱黑体 SC", "Sarasa Mono SC", "SarasaMonoSC"],
    "emoji": ["EmojiSupport"],
    "emoji.ttf": ["EmojiSupport"],
}
"""特定字体文件名到额外 Tk 字体别名的映射表。"""


def resource_path(file_name: str) -> str:
    """
    按当前运行形态拼接游戏资源文件的绝对路径

    参数：
    file_name (str) -- 使用正斜杠分隔的相对资源路径

    返回值类型：str -- 拼接后的本地文件路径
    """
    if getattr(sys, "frozen", False):
        base_path = os.getcwd()
    else:
        base_path = game_path_config.game_path
    return os.path.join(base_path, *file_name.split("/"))


def _fonts_dir() -> str | None:
    if hasattr(sys, "_MEIPASS") or getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
        candidates = [
            os.path.join(base_dir, "static", "fonts"),
            os.path.join(base_dir, "fonts"),
        ]
    else:
        candidates = [
            os.path.join(game_path_config.game_path, "static", "fonts")
        ]
    return next((path for path in candidates if os.path.isdir(path)), None)


def _aliases(file_name: str) -> list[str]:
    base_name = os.path.splitext(file_name)[0]
    names = [
        base_name,
        base_name.replace("_", " "),
        base_name.replace("_", ""),
        file_name,
        *ALIAS_OVERRIDES.get(file_name, []),
        *ALIAS_OVERRIDES.get(base_name, []),
    ]
    aliases: list[str] = []
    for name in names:
        cleaned = name.strip()
        if cleaned and cleaned not in aliases:
            aliases.append(cleaned)
    return aliases


def _create(root: Tk, alias: str, family: str) -> bool:
    try:
        root.tk.call("font", "create", alias, "-family", family)
    except Exception:
        return False
    return True


def _primary(
    root: Tk, font_path: str, aliases: list[str], existing: set[str]
) -> tuple[str, str] | None:
    for alias in aliases:
        if alias in existing:
            return alias, "existing"
    for alias in aliases:
        if _create(root, alias, f"@{font_path}"):
            existing.add(alias)
            return alias, font_path
    try:
        families = set(map(str, root.tk.call("font", "families")))
    except Exception:
        families = set()
    for alias in aliases:
        if alias in families and _create(root, alias, alias):
            existing.add(alias)
            return alias, "system"
    return None


def load_local_fonts(root: Tk) -> None:
    """
    扫描本地字体目录中的字体文件并在 Tk 中注册字体与别名，本地字体文件无法被 Tk 加载时回退同名系统字体

    参数：
    root (Tk) -- 目标 Tk 根窗口

    返回值类型：None
    """
    fonts_dir = _fonts_dir()
    if fonts_dir is None:
        return
    existing = set(map(str, root.tk.call("font", "names")))
    for entry in os.scandir(fonts_dir):
        if not entry.is_file() or not entry.name.lower().endswith(
            (".ttf", ".otf", ".ttc")
        ):
            continue
        font_path = entry.path.replace("\\", "/")
        aliases = _aliases(entry.name)
        found = _primary(root, font_path, aliases, existing)
        if found is None:
            print(
                f"[load_local_fonts] 无法加载字体文件: {font_path} "
                f"(别名尝试: {', '.join(aliases)})"
            )
            continue
        primary, source = found
        for alias in aliases:
            if alias != primary and alias not in existing:
                if _create(root, alias, primary) or _create(root, alias, alias):
                    existing.add(alias)
        if source == font_path:
            print(f"[load_local_fonts] 成功加载字体 {primary} <- {font_path}")
        elif source == "system":
            print(
                f"[load_local_fonts] 使用系统字体 {primary} (未找到本地文件 {font_path})"
            )
